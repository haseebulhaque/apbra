import {defineConfig} from '@playwright/test';

const ci=Boolean(process.env.CI);
const apiPort=18000,webPort=15173;
const databaseUrl=process.env.APBRA_E2E_DATABASE_URL;
const sessionSecret=process.env.APBRA_E2E_SESSION_SECRET;
if(!databaseUrl)throw new Error('APBRA_E2E_DATABASE_URL must name an isolated disposable PostgreSQL database.');
if(databaseUrl===process.env.APBRA_DATABASE_URL||databaseUrl===process.env.APBRA_TEST_DATABASE_URL)throw new Error('The Playwright database must be separate from preview and backend-test databases.');
if(!sessionSecret)throw new Error('APBRA_E2E_SESSION_SECRET must be provided for the isolated browser-test stack.');

export default defineConfig({
  testDir:'./e2e',
  outputDir:process.env.APBRA_E2E_OUTPUT_DIR||'/tmp/apbra-162-playwright-output',
  timeout:30_000,
  fullyParallel:false,
  retries:ci?1:0,
  workers:1,
  reporter:ci?'line':'list',
  use:{baseURL:`http://127.0.0.1:${webPort}`,trace:'retain-on-failure'},
  webServer:[
    {
      command:`../api/.venv/bin/alembic -c ../api/alembic.ini downgrade base && ../api/.venv/bin/alembic -c ../api/alembic.ini upgrade head && ../api/.venv/bin/python -m apbra_api.bootstrap && ../api/.venv/bin/uvicorn apbra_api.main:app --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      url:`http://127.0.0.1:${apiPort}/api/health`,
      cwd:'.',
      reuseExistingServer:false,
      timeout:60_000,
      env:{APBRA_PROFILE:'test',APBRA_DATABASE_URL:databaseUrl,APBRA_PUBLIC_ORIGIN:`http://127.0.0.1:${webPort}`,APBRA_API_ORIGIN:`http://127.0.0.1:${apiPort}`,APBRA_SESSION_SECRET:sessionSecret,APBRA_BOOTSTRAP_ENABLED:'true'},
    },
    {
      command:`npm run dev -- --port ${webPort} --strictPort`,
      url:`http://127.0.0.1:${webPort}`,
      cwd:'.',
      reuseExistingServer:false,
      timeout:60_000,
      env:{APBRA_API_URL:`http://127.0.0.1:${apiPort}`},
    },
  ],
});
