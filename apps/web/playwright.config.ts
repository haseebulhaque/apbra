import {defineConfig} from '@playwright/test';

const ci=Boolean(process.env.CI);
const apiPort=18000,webPort=15173;
const databaseUrl=process.env.APBRA_E2E_DATABASE_URL;
const sessionSecret=process.env.APBRA_E2E_SESSION_SECRET;
const inheritedTargetVariables=['PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGSERVICE','PGSERVICEFILE','PGSYSCONFDIR'].filter((name)=>process.env[name]);
if(!databaseUrl)throw new Error('APBRA_E2E_DATABASE_URL must name an isolated disposable PostgreSQL database.');
if(!databaseUrl.startsWith('postgresql+psycopg://'))throw new Error('APBRA_E2E_DATABASE_URL must use the locked postgresql+psycopg driver.');
if(inheritedTargetVariables.length)throw new Error(`Playwright rejects inherited libpq target settings: ${inheritedTargetVariables.join(', ')}.`);
let databaseTarget:URL;
try{databaseTarget=new URL(databaseUrl.replace(/^postgresql\+psycopg:/,'postgresql:'))}catch{throw new Error('APBRA_E2E_DATABASE_URL must be a valid PostgreSQL URL.');}
if(databaseTarget.protocol!=='postgresql:'||!['127.0.0.1','localhost'].includes(databaseTarget.hostname)||!databaseTarget.port||databaseTarget.pathname!=='/apbra_e2e'||databaseTarget.searchParams.size>0||databaseTarget.hash)throw new Error('Playwright may reset only an explicit loopback PostgreSQL database named apbra_e2e, without connection query options.');
const targetKey=(url:URL)=>`${url.hostname==='localhost'?'127.0.0.1':url.hostname}:${url.port}:${decodeURIComponent(url.pathname)}`;
for(const name of ['APBRA_DATABASE_URL','APBRA_TEST_DATABASE_URL'] as const){
  const candidate=process.env[name];
  if(!candidate)continue;
  if(!candidate.startsWith('postgresql+psycopg://')&&!candidate.startsWith('postgresql://'))throw new Error(`${name} must expose an unambiguous host, port and database while browser tests run.`);
  let candidateTarget:URL;
  try{candidateTarget=new URL(candidate.replace(/^postgresql\+psycopg:/,'postgresql:'))}catch{throw new Error(`${name} must expose an unambiguous host, port and database while browser tests run.`);}
  if(candidateTarget.protocol!=='postgresql:'||!candidateTarget.hostname||!candidateTarget.port||candidateTarget.pathname==='/'||candidateTarget.searchParams.size>0||candidateTarget.hash)throw new Error(`${name} must expose an unambiguous host, port and database while browser tests run.`);
  if(decodeURIComponent(candidateTarget.pathname)==='/apbra_e2e'||targetKey(candidateTarget)===targetKey(databaseTarget))throw new Error('The Playwright database must be separate from preview and backend-test databases.');
}
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
