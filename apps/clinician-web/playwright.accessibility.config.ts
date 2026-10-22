import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/accessibility",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:3210",
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "CADENCE_ACCESSIBILITY_AUDIT_MODE=1 pnpm dev --hostname 127.0.0.1 --port 3210",
    url: "http://127.0.0.1:3210/access?reason=authentication-required",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
