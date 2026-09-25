import {expect,test,type Page} from '@playwright/test';

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

  await page.getByRole('button',{name:'Build report'}).click();
  await expect(page.getByText(/Version 1 · Report ready/)).toBeVisible();
  const download=page.getByRole('link',{name:'Download validated Power BI candidate'});
  await expect(download).toBeVisible();
  const response=await page.request.get(await download.getAttribute('href')??'');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/zip');
  expect((await response.body()).subarray(0,2).toString()).toBe('PK');

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByText(/Version 1 · Report ready/)).toBeVisible();
  await expect(page.getByText('1 attempt',{exact:true})).toBeVisible();

  const foreignContext=await browser.newContext();
  const foreign=await foreignContext.newPage();
  await signIn(foreign,'foreign');
  await expect(foreign.getByRole('button',{name:new RegExp(request)})).toHaveCount(0);
  await foreignContext.close();
});
