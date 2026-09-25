import {expect,test,type Page} from '@playwright/test';
import {chmodSync,readFileSync} from 'node:fs';

async function signIn(page:Page,identity:'member'|'foreign'='member'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
}

test('confirmed meaning builds one durable private candidate across reload',async({page,browser})=>{
  await signIn(page);
  const request='Compare completed inspections by facility.';
  await page.getByLabel('Original business request').fill(request);
  await page.getByRole('button',{name:'Create case'}).click();
  await page.getByLabel('Add CSV or XLSX evidence').setInputFiles({
    name:'inspections.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Prepare understanding'}).click();
  const clarification=page.getByText('Clarification required',{exact:true});
  if(await clarification.isVisible())await page.getByText(/Summarise Completed and compare it by Facility/).click();
  await page.getByRole('button',{name:'Confirm this exact meaning'}).click();
  await expect(page.getByText('ConfirmedRequirementContract v2 created')).toBeVisible();

  const artifactRoot='/tmp/apbra-164-e2e-artifacts';
  try{
    chmodSync(artifactRoot,0o500);
    await page.getByRole('button',{name:'Build report'}).click();
    await expect(page.getByText(/Version 1 · Build failed/)).toBeVisible();
  }finally{chmodSync(artifactRoot,0o700)}
  await page.getByRole('button',{name:'Retry failed build'}).click();
  await expect(page.getByText(/Version 2 · Report ready/)).toBeVisible();
  const download=page.getByRole('link',{name:'Download validated Power BI candidate'});
  await expect(download).toBeVisible();
  const artifactPath=await download.getAttribute('href')??'';
  const response=await page.request.get(artifactPath);
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/zip');
  expect((await response.body()).subarray(0,2).toString()).toBe('PK');

  const apiPid=Number(readFileSync('/tmp/apbra-164-e2e-api.pid','utf8').trim());
  process.kill(apiPid,'SIGTERM');
  await expect.poll(async()=>{
    const replacement=Number(readFileSync('/tmp/apbra-164-e2e-api.pid','utf8').trim());
    if(replacement===apiPid)return false;
    try{return (await page.request.get('/api/health')).status()===200}catch{return false}
  },{timeout:10_000}).toBe(true);

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByText(/Version 2 · Report ready/)).toBeVisible();
  await expect(page.getByText(/Version 1 · Build failed/)).toBeVisible();
  await expect(page.getByText('2 attempts',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Build another version'}).click();
  await expect(page.getByText(/Version 3 · Report ready/)).toBeVisible();
  await expect(page.getByText('3 attempts',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download validated Power BI candidate'})).toHaveCount(2);

  await page.getByLabel('Current business request').fill(`${request} Include the latest reviewed period.`);
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Reconfirmation required.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);

  const foreignContext=await browser.newContext();
  const foreign=await foreignContext.newPage();
  await signIn(foreign,'foreign');
  await expect(foreign.getByRole('button',{name:new RegExp(request)})).toHaveCount(0);
  const denied=await foreign.request.get(new URL(artifactPath,'http://127.0.0.1:5173').toString());
  expect(denied.status()).toBe(404);
  await foreignContext.close();
});
