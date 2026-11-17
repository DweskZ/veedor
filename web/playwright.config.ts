import { defineConfig, devices } from "@playwright/test";

/**
 * Cross-browser end-to-end and accessibility suite.
 * It runs against an already running site (default: a production build on :3100):
 *   E2E_BASE_URL=http://localhost:3000 npm run test:e2e
 */
export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  retries: 0,
  workers: process.env.CI ? 2 : 4,
  globalSetup: "./e2e/global-setup.ts",
  reporter: [["list"], ["json", { outputFile: "test-results/report.json" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    locale: "es-EC",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "webkit-mobile", use: { ...devices["Desktop Safari"], viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});
