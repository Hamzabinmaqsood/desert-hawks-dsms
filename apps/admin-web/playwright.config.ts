import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  globalSetup: "./e2e/global-setup.ts",
  expect: { timeout: 15_000 },
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
});
