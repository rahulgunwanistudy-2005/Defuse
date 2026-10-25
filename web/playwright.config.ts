import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: process.env.DEFUSE_WEB ?? 'http://127.0.0.1:5173',
    launchOptions: { executablePath: process.env.PW_CHROMIUM ?? undefined }
  },
  reporter: [['list']]
});
