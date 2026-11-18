import assert from "node:assert/strict";
import { test } from "node:test";
import { connectOrigin, internalUrlProblem, isFetchableServerUrl, visitorAddress, visitorHeaders, warnOnce } from "./server-api.ts";

test("the visitor is the address Caddy wrote: the last entry of X-Forwarded-For", () => {
  assert.equal(visitorAddress("203.0.113.9"), "203.0.113.9");
  assert.equal(visitorAddress("2001:db8::1"), "2001:db8::1");
  // Entries a client put in front of the proxy's own are never read.
  assert.equal(visitorAddress("10.77.88.20, 198.51.100.1, 203.0.113.9"), "203.0.113.9");
  assert.equal(visitorAddress(" 203.0.113.9 "), "203.0.113.9");
});

test("nothing that is not a bare IP address is forwarded", () => {
  for (const bad of [null, undefined, "", " ", ",", "203.0.113.9,", "unknown", "203.0.113.9:443", "[2001:db8::1]", "1.2.3.4\r\nx-evil: 1", "a".repeat(600), "999.1.1.1"]) {
    assert.equal(visitorAddress(bad), null, String(bad));
    assert.deepEqual(visitorHeaders(bad), {}, String(bad));
  }
});

test("a call made for a visitor carries only the forwarded address", () => {
  assert.deepEqual(visitorHeaders("198.51.100.4"), { "x-forwarded-for": "198.51.100.4" });
  assert.deepEqual(visitorHeaders("evil, 198.51.100.4"), { "x-forwarded-for": "198.51.100.4" });
});

test("the server-side guard: only absolute http(s) URLs can be fetched", () => {
  assert.equal(isFetchableServerUrl("http://api:8000/api/v1"), true);
  assert.equal(isFetchableServerUrl("https://example.org/api/v1"), true);
  for (const url of ["/api/v1", "api:8000/api/v1", "//api/v1", "", "ftp://api/v1"]) assert.equal(isFetchableServerUrl(url), false, url);
});

test("a misconfigured API_INTERNAL_URL is reported; unset or valid is not", () => {
  assert.equal(internalUrlProblem(undefined), null);
  assert.equal(internalUrlProblem(""), null);
  assert.equal(internalUrlProblem("http://api:8000/api/v1"), null);
  assert.match(internalUrlProblem("api:8000/api/v1") ?? "", /API_INTERNAL_URL.*api:8000\/api\/v1.*absolute/);
});

test("the warning is logged once per message", () => {
  const lines: string[] = [];
  const log = (m: string) => lines.push(m);
  warnOnce("server-api test: first", log);
  warnOnce("server-api test: first", log);
  warnOnce("server-api test: second", log);
  assert.deepEqual(lines, ["server-api test: first", "server-api test: second"]);
});

test("a relative public API URL adds nothing to connect-src; an absolute one adds its origin", () => {
  assert.equal(connectOrigin("/api/v1"), null);
  assert.equal(connectOrigin(""), null);
  assert.equal(connectOrigin("https://veedor.example.org/api/v1"), "https://veedor.example.org");
  assert.equal(connectOrigin("http://localhost:8000/api/v1"), "http://localhost:8000");
  assert.equal(connectOrigin(undefined), "http://localhost:8000"); // the development default
});
