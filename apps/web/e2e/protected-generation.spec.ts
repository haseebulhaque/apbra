import {expect,test,type Page} from '@playwright/test';
import {chmodSync,readFileSync} from 'node:fs';

async function signIn(page:Page,identity:'member'|'foreign'='member'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
}

function reviewedSyntheticDesign(contract:any){
  // Test-only reviewed fixture. The application never derives a layout from obligations.
  const measures=[...new Map(contract.obligations.flatMap((item:any)=>item.measures.map((measure:any)=>[measure.id,measure]))).values()] as any[];
  const byName=new Map(measures.map(measure=>[measure.name,measure.id]));
  const pages=contract.pages.map((page:any,pageIndex:number)=>({id:`reviewed-page-${pageIndex}`,name:page.name,purpose:'Synthetic test validation',visuals:contract.obligations.filter((item:any)=>item.required&&item.pageNames.includes(page.name)).flatMap((item:any,index:number)=>Array.from({length:Math.max(1,item.minimumRepresentations)},(_,repeat)=>{
    const kind=item.kind,fields=item.fields,measureIds=item.measureNames.map((name:string)=>byName.get(name)),title=[...item.measureNames,...fields.map((field:string)=>field.split('.').at(-1))].join(' by ');
    return {id:`reviewed-${pageIndex}-${index}-${repeat}`,type:kind==='FILTER'?'slicer':kind==='TREND'?'line':kind==='KPI'?'card':'bar',title:title||'Reviewed synthetic visual',categoryField:['TREND','BREAKDOWN','LIFECYCLE'].includes(kind)?fields[0]:'',timeGrain:kind==='TREND'?item.timeGrain:'NONE',measureIds:kind==='FILTER'?[]:measureIds,fields:kind==='FILTER'?fields.slice(0,1):['BREAKDOWN','LIFECYCLE'].includes(kind)?fields.slice(1):[],altText:`Reviewed synthetic presentation of ${title}.`};
  }))}));
  const schema=contract.provenance.dataStructure,tableNames=schema.tables.map((table:any)=>table.name),factNames=new Set(measures.filter(measure=>measure.field).map(measure=>measure.field.split('.')[0]));
  return {artifact_kind:'ReportDesign',schema_version:1,projectName:'ReviewedSyntheticCandidate',overview:contract.objective,audience:contract.audience,dataModel:{factTables:tableNames.filter((name:string)=>factNames.has(name)),dimensionTables:tableNames.filter((name:string)=>!factNames.has(name)),relationships:schema.relationships},measures,pages,filters:[...new Set(contract.obligations.filter((item:any)=>item.kind==='FILTER').flatMap((item:any)=>item.fields))],branding:{themeName:'Reviewed Synthetic',primary:'#005A9C',accent:'#2D7D9A'},accessibility:['Every test visual has a text alternative.'],standardsApplied:[{citation:'local-knowledge:report-design-standards.md@1.0.0#RD-001',decision:'Reviewed synthetic visual choice for validation only.'}],assumptions:[],warnings:['LOCAL_DETERMINISTIC_NO_MODEL_CALL: synthetic reviewed test design.'],generationRequirements:['Validate the supplied design through the canonical pipeline.']};
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
  const confirmationResponse=page.waitForResponse(response=>response.url().endsWith('/confirm')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Confirm this exact meaning'}).click();
  const confirmed=(await (await confirmationResponse).json()).confirmed_contract.contract;
  await expect(page.getByText('ConfirmedRequirementContract v2 created')).toBeVisible();
  const design=JSON.stringify(reviewedSyntheticDesign(confirmed));
  await page.getByLabel('Reviewed ReportDesign JSON').fill(design);

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
  await page.getByLabel('Reviewed ReportDesign JSON').fill(design);
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
  const packageCOrigin=new URL(page.url()).origin;
  expect(new URL(foreign.url()).origin).toBe(packageCOrigin);
  const denied=await foreign.request.get(new URL(artifactPath,packageCOrigin).toString());
  expect(denied.status()).toBe(404);
  await foreignContext.close();
});
