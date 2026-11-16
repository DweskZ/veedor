# Observability

OpenTelemetry traces and metrics for API requests and every investigation step, with a local
Grafana dashboard. Off unless `VEEDOR_OTEL_ENDPOINT` is set: without it every helper is a no-op and
nothing is exported, so tests and the CLI work offline.

## Run it

```bash
make obs-up                    # docker compose up -d --build --wait observability api
make obs-verify                # generate traffic, then assert spans and series exist
```

| What | Where | Credentials |
|---|---|---|
| Grafana (dashboard "Veedor") | http://localhost:3001 | user `admin`, password `veedor_dev` (override with `GRAFANA_ADMIN_PASSWORD`); no anonymous access, sign-up off |
| OTLP/HTTP receiver | http://localhost:4318 | none |
| Prometheus HTTP API | http://localhost:9090 | none |
| Tempo HTTP API | http://localhost:3200 | none |

Every port is bound to `127.0.0.1`. The password is a local-development default: change it, or do
not run this service, anywhere that is not your own machine. Port 3000 is the web app, hence 3001.

The single service is `grafana/otel-lgtm:0.41.0` (checked on Docker Hub, amd64 and arm64): OpenTelemetry
Collector, Tempo (traces), Prometheus (metrics), Loki and Grafana in one container. It is a
development image, not a production backend. Limits: 1.5 CPU, 1.5 GB; Prometheus keeps 7 days; data
lives in the `veedor_obsdata` volume.

The API container gets `VEEDOR_OTEL_ENDPOINT=http://observability:4318` from compose. For a process
on the host (CLI, scripts) use `VEEDOR_OTEL_ENDPOINT=http://localhost:4318`.

## What is collected

Spans (service `veedor-api`, or `veedor-cli` for the command line):

- One server span per HTTP request, named `GET /api/v1/processes/{ocid}` (the route **template**).
  `/health` is not traced.
- Spans opened with `span(...)` by the agent code: investigation, specialist, tool call, graph node.

Metrics (Prometheus names after the OTLP translation):

| Metric | Labels | Meaning |
|---|---|---|
| `http_server_request_duration_seconds` (histogram) | `http_request_method`, `http_route`, `http_response_status_code` | RED: rate, errors, duration |
| `veedor_investigations_total`, `veedor_investigation_duration_milliseconds` | `final_mode` | finished investigations |
| `veedor_specialist_runs_total` | `specialist`, `outcome` | specialist runs |
| `veedor_tool_calls_total` | `tool`, `outcome` | tool calls (`ok`, `timeout`, `upstream_error`, `invalid_result`, `skipped`) |
| `veedor_tool_duration_milliseconds` (histogram) | `tool` | tool latency |
| `veedor_llm_tokens_total` | `model`, `token_type` (`prompt`, `completion`) | model tokens |
| `veedor_grounding_results_total` | `passed`, `mode` | grounding verifier results |

## Public helpers (`veedor.infrastructure.telemetry`)

`setup_telemetry(service_name)`, `shutdown_telemetry()`, `span(name, **attributes)` (yields a handle
with `set_attribute`, `mark_error`), `record_llm_usage(model, prompt_tokens, completion_tokens)`,
`record_tool_call(tool, outcome, duration_ms)`, `record_grounding(passed, mode)`. Two additions
beyond the contract: `record_investigation(final_mode, duration_ms=None)` and
`record_specialist_run(specialist, outcome="ok")`; they feed the "investigations by final mode"
and "specialist runs" panels, which no contract helper covers.

**Graph bridge.** `traced_node(name)` wraps a node function in a span `node <name>` with no change
in behaviour (and no cost beyond a function call when telemetry is off). The investigator graph
file was not edited; to adopt it, apply the decorator where nodes are registered, for example
`graph.add_node(name, traced_node(name)(_timed(name, fn)))`, or wrap `fn(state)` inside `_timed`.

## Privacy: the attribute allow-list

Public procurement data contains people. Observability data is easy to copy and keep, so it carries
**no personal data by construction**, enforced in code (`allowlist.py`), not by convention:

- A span attribute or metric label whose **key** is not on the list is dropped. Metric labels are
  the subset without `ocid`, `node`, counts and durations (an `ocid` label would also be unbounded
  cardinality). Each listed key then has its **own value rule**:

| Key(s) | Rule | Otherwise |
|---|---|---|
| `tool`, `specialist`, `outcome`, `final_mode`, `mode` | member of a closed set taken from the domain: tools, specialists and lookup outcomes from `veedor.domain.investigation.vocab` (plus `partial` for specialist outcomes), modes from the `Dossier.mode` type | replaced by `other` |
| `node` | `<specialist>_agent` plus names registered with `register_vocabulary(node=[...])` | `other` |
| `token_type` | `prompt` or `completion` | `other` |
| `http.request.method` | `GET HEAD POST PUT PATCH DELETE OPTIONS _OTHER` | `other` |
| `error.type` | a Python built-in exception class name or one registered with `register_vocabulary(**{"error.type": [...]})` | `other` |
| `model` | the configured `VEEDOR_LLM_MODEL` (or that name followed by a short suffix such as a date), `fake`, or a registered name; at most 64 characters, no run of 10+ digits | `other` |
| `ocid` | exact open-contracting id shape (`ocds-xxxxxx-...`) | dropped |
| `http.route` | `unmatched` or a lowercase template such as `/api/v1/processes/{ocid}` (letters, digits, underscore, `{param}`); no hyphens, no digit-only segments | dropped |
| `passed` | a bool | dropped |
| `attempt` (int 0-20), `n_signals` (0-1,000), `n_findings` (0-10,000), `n_tool_calls` (0-100), `n_dispatches` (0-100), `prompt_tokens`, `completion_tokens` (0-10,000,000), `duration_ms` (finite number 0-3,600,000), `http.response.status_code` (int 100-599) | type and range per key; bools, strings, NaN and out-of-range values rejected | dropped |

  Vocabularies are not copied into the telemetry module, so they cannot drift. What the domain does
  not define (graph node names, extra exception classes, extra model names) is added by its owner
  with `register_vocabulary`; entries must be identifier-shaped and a bad key or entry raises
  `ValueError`. A node name that is not registered is exported as `other`, so the graph owner should
  call `register_vocabulary(node=<graph node names>)` when the graph is built.
- Span names are checked the same way; a bad one becomes `invalid_span_name`.
- Exceptions are never recorded with their message (it could hold free text): only `error.type`
  (the class name) and an error status.
- HTTP spans use the route template. The stock FastAPI instrumentor was **not** used because it
  records `url.path` / `http.target` with the raw path; the project middleware (`asgi.py`) sets only
  allow-listed attributes. Unmatched paths (404 for unknown URLs) are labelled `unmatched`.

Tests (`tests/infrastructure/telemetry`) use the SDK's in-memory exporters to prove that RUC-shaped
and free-text values under disallowed or allowed keys never reach the exporter, and that a raw path
never becomes a span name or label. `scripts/verify_telemetry.py` repeats the check against the
real stores.

Residual limit: an `ocid` is an identifier of a public process and is kept as a span attribute by
design. `model` accepts a configured name plus a suffix, so a model name that itself contained
personal data would pass; it comes from configuration, not from data.

## Dashboard "Veedor" (provisioned, `ops/observability/grafana/dashboards/veedor.json`)

Generated by `ops/observability/build_dashboard.py`; edit that file, rerun it, Grafana reloads within 30 s.

| Panel | Question it answers |
|---|---|
| Request rate by route | Which endpoints get the traffic? |
| Errors by route and status class | Which routes return 5xx or 4xx, and how often? |
| Latency p50 / p95 by route | Which endpoints are slow? |
| Investigations by final mode | How many investigations finished as `template` vs `llm`? |
| Specialist runs | Which specialists ran? |
| Tool-call outcomes by tool | Which lookups succeed, time out or fail upstream? |
| Tool latency p50 / p95 by tool | How slow are external lookups? |
| Tokens per investigation | What does one investigation cost in tokens? |
| Grounding pass rate | How often does generated text pass the verifier? |
| Recent traces (Tempo) | Open a trace to see its spans. |

The investigation panels show the latest cumulative counter value in the selected range (counters
are cumulative since the process started; a restart resets them). Latency-by-tool panels are sparse
when there are few calls: a quantile over a rate needs several samples in the window.

## How the CLI flushes

Batch commands are short-lived, and spans/metrics are exported in batches. `setup_telemetry`
registers `shutdown_telemetry()` with `atexit`; it flushes spans and metrics (5 s cap per provider,
5 s export timeout) and stops. Call `shutdown_telemetry()` explicitly before `os._exit` or when
embedding in a long-lived host. If the collector is down, export errors are logged by the SDK and
the command still exits (worst case it waits the timeouts).

## Verification

`make obs-verify` (`scripts/generate_traffic.py`, then `scripts/verify_telemetry.py`) hits a spread
of routes (200, 404, 422), runs a batch with the CLI when `veedor investigate` exists, and otherwise
emits one **synthetic, clearly labelled** investigation (service `veedor-synthetic-traffic`). It then
queries Tempo and Prometheus and fails (exit 1) unless: request spans exist with route-template names,
`/health` is absent, no span name/attribute/label holds a 13-digit number or an `ocds-` id outside
`ocid`, and every expected metric series is non-zero. Only spans from the last `SINCE_SECONDS`
(default 300) count.

## Limits

- Local single-node stack: no replication, no alerting, no authentication on the OTLP/Tempo/Prometheus
  ports (loopback only), development image.
- Sampling is 100 % (every span exported); fine locally, not a production setting.
- Metrics are exported every 5 s; the dashboard lags by up to that plus Grafana's 10 s refresh.
- Request latency is measured inside the app, outside the other middleware, not at the client.
- Counters reset when a process restarts; the dashboard does not correct for that.
