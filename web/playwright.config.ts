import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: process.env.DEFUSE_WEB ?? 'http://127.0.0.1:15173',
    launchOptions: {
      executablePath: process.env.PW_CHROMIUM ?? undefined,
      args: process.env.PW_CHROMIUM ? ['--headless=new'] : []
    }
  },
  reporter: [['list']],
  webServer: process.env.DEFUSE_WEB ? undefined : [
    {
      command: '../engine/.venv/bin/python -m uvicorn defuse.api.app:create_app --factory --app-dir ../engine --host 127.0.0.1 --port 18000',
      url: 'http://127.0.0.1:18000/healthz',
      env: { DEFUSE_DATABASE_URL: 'sqlite+aiosqlite:///:memory:', DEFUSE_SEED_SCENARIO: 'true' },
      reuseExistingServer: false
    },
    {
      command: 'npm run build && node build',
      url: 'http://127.0.0.1:15173',
      env: { HOST: '127.0.0.1', PORT: '15173', DEFUSE_API_BASE: 'http://127.0.0.1:18000' },
      reuseExistingServer: false,
      timeout: 120000
    }
  ]
});
