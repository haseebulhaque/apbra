import {defineConfig} from '@playwright/test';

const ci=Boolean(process.env.CI);

export default defineConfig({
  testDir:'./e2e',
  timeout:30_000,
  fullyParallel:false,
  retries:ci?1:0,
  workers:1,
  reporter:ci?'line':'list',
  use:{baseURL:'http://127.0.0.1:5173',trace:'retain-on-failure'},
  webServer:[
    {
      command:'../api/.venv/bin/alembic -c ../api/alembic.ini upgrade head && ../api/.venv/bin/python -m apbra_api.bootstrap && ../api/.venv/bin/uvicorn apbra_api.main:app --host 127.0.0.1 --port 8000 --no-access-log',
      url:'http://127.0.0.1:8000/api/health',
      cwd:'.',
      reuseExistingServer:!ci,
      timeout:60_000,
    },
    {
      command:'npm run dev -- --port 5173 --strictPort',
      url:'http://127.0.0.1:5173',
      cwd:'.',
      reuseExistingServer:!ci,
      timeout:60_000,
    },
  ],
});
