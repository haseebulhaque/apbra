import {spawnSync} from 'node:child_process';

const result=spawnSync('npm',['test','--','--run','src/genericFoundry.integration.test.ts'],{
  cwd:new URL('..',import.meta.url),
  env:{...process.env,RUN_FOUNDRY_INTEGRATION:'1'},
  stdio:'inherit',
});
process.exit(result.status??1);
