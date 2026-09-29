import {expect,test,type Page} from '@playwright/test';
import {chmodSync,readFileSync} from 'node:fs';

async function signIn(page:Page,identity:'owner'|'uninvited'|'foreign'='owner'){
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

test('confirmed meaning and expert-reviewed plan build durable private candidates across reload',async({page,browser},testInfo)=>{
  await signIn(page);
  const request='Compare completed inspections by facility.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
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
  await expect(page.getByText('Your understanding is confirmed')).toBeVisible();
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('confirmed-understanding.png'),fullPage:true});
  const design=JSON.stringify(reviewedSyntheticDesign(confirmed));
  await expect(page.getByText('Expert review needed',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Expert report plan JSON')).toHaveCount(0);

  const expertContext=await browser.newContext();
  const expert=await expertContext.newPage();
  await signIn(expert,'uninvited');
  const invitationRequired=expert.getByRole('heading',{name:'An invitation is required'});
  await expect(invitationRequired.or(expert.locator('.account-controls').getByText('expert',{exact:true}))).toBeVisible();
  if(await invitationRequired.isVisible()){
    await page.getByText('Manage company access').click();
    await page.getByLabel('External subject').fill('dev-uninvited');
    await page.getByLabel('Application role').selectOption('EXPERT');
    await page.getByRole('button',{name:'Issue invitation'}).click();
    const invitationLink=await page.getByLabel('One-time invitation link').inputValue();
    await expert.goto(invitationLink);
    await expert.getByRole('button',{name:'Accept invitation'}).click();
    await expect(expert.getByText('Invitation accepted. Your APBRA membership is active.')).toBeVisible();
  }
  await expect(expert.locator('.account-controls').getByText('expert',{exact:true})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await page.getByText('Manage private case access').click();
  await page.getByLabel('Company member').selectOption({label:'Uma Uninvited · dev-uninvited'});
  await page.getByLabel('Case permission').selectOption('EDITOR');
  await page.getByRole('button',{name:'Grant case access'}).click();
  await expert.reload();
  await expert.getByRole('button',{name:new RegExp(request)}).first().click();
  await expert.getByText('Details for experts').last().click();
  await expert.getByLabel('Expert report plan JSON').fill(design);
  await expert.getByRole('button',{name:'Submit reviewed plan'}).click();
  await expect(expert.getByLabel('Reviewed report plan')).toBeVisible();
  await expertContext.close();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByLabel('Reviewed report plan')).toBeVisible();
  await expect(page.getByLabel('Expert report plan JSON')).toHaveCount(0);
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('reviewed-build-readiness.png'),fullPage:true});

  const artifactRoot='/tmp/apbra-164-e2e-artifacts';
  try{
    chmodSync(artifactRoot,0o500);
    await page.getByRole('button',{name:'Build report'}).click();
    await page.locator('.report-history summary').click();
    await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Build failed');
  }finally{chmodSync(artifactRoot,0o700)}
  await page.getByRole('button',{name:'Retry failed build'}).click();
  await expect(page.locator('.generation-history li').filter({hasText:'Version 2'})).toContainText('Report ready');
  const download=page.getByRole('button',{name:'Download current report candidate'});
  await expect(download).toBeVisible();
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('current-report.png'),fullPage:true});
  const artifactResponse=page.waitForResponse(response=>response.url().endsWith('/artifact')&&response.request().method()==='GET');
  const savedDownload=page.waitForEvent('download');
  await download.click();
  const artifactPath=new URL((await artifactResponse).url()).pathname;
  expect((await savedDownload).suggestedFilename()).toMatch(/\.zip$/);
  const response=await page.request.get(artifactPath);
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/zip');
  expect((await response.body()).subarray(0,2).toString()).toBe('PK');
  await page.route('**/generation/*/artifact',route=>route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({error:{code:'ARTIFACT_NOT_FOUND',message:'internal detail'}})}));
  await download.click();
  await expect(page.getByRole('alert').filter({hasText:'This report file is unavailable'})).toContainText('This report file is unavailable or you no longer have access.');
  await expect(page.getByRole('alert').filter({hasText:'This report file is unavailable'})).not.toContainText('internal detail');
  await expect(page.getByLabel('Current report')).toContainText('This completed build has no available file.');
  await expect(page.getByLabel('Current report')).not.toContainText('Validated candidate recorded');
  await page.unroute('**/generation/*/artifact');
  const retriedDownload=page.waitForEvent('download');
  await page.getByRole('button',{name:'Try current report download again'}).click();
  expect((await retriedDownload).suggestedFilename()).toMatch(/\.zip$/);
  await expect(page.getByLabel('Current report')).toContainText('Validated candidate recorded');

  const apiPid=Number(readFileSync('/tmp/apbra-164-e2e-api.pid','utf8').trim());
  process.kill(apiPid,'SIGTERM');
  await expect.poll(async()=>{
    const replacement=Number(readFileSync('/tmp/apbra-164-e2e-api.pid','utf8').trim());
    if(replacement===apiPid)return false;
    try{return (await page.request.get('/api/health')).status()===200}catch{return false}
  },{timeout:10_000}).toBe(true);

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await page.locator('.report-history summary').click();
  await expect(page.locator('.generation-history li').filter({hasText:'Version 2'})).toContainText('Report ready');
  await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Build failed');
  await expect(page.getByText('2 builds',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Build another version'}).click();
  await expect(page.locator('.generation-history li').filter({hasText:'Version 3'})).toContainText('Report ready');
  await expect(page.getByText('3 builds',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Download current report candidate'})).toHaveCount(1);
  await expect(page.getByRole('button',{name:'Download earlier report candidate'})).toHaveCount(1);
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('report-history.png'),fullPage:true});
  await page.getByText('Manage private case access').click();
  await page.getByLabel('Company member').selectOption({label:'Morgan Member · dev-member'});
  await page.getByLabel('Case permission').selectOption('VIEWER');
  await page.getByRole('button',{name:'Grant case access'}).click();
  const viewerContext=await browser.newContext();
  const viewer=await viewerContext.newPage();
  await viewer.goto('/');
  await viewer.getByText('Local development identities').click();
  await viewer.getByRole('link',{name:'member',exact:true}).click();
  await viewer.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(viewer.getByLabel('Reviewed report plan')).toBeVisible();
  await expect(viewer.getByText('building or cancelling a report requires editor access')).toBeVisible();
  await expect(viewer.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  await expect(viewer.getByRole('button',{name:'Retry failed build'})).toHaveCount(0);
  await viewerContext.close();

  await page.getByLabel('Current business request').fill(`${request} Show the total completed by facility.`);
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Reconfirmation required.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  await expect(page.getByLabel('Current report')).toHaveCount(0);
  await expect(page.getByText('No current report yet')).toBeVisible();
  await expect(page.getByRole('button',{name:'Download earlier report candidate'})).toHaveCount(2);
  await page.getByLabel('Add CSV or XLSX evidence').setInputFiles({
    name:'current-inspections.csv',mimeType:'text/csv',buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Prepare updated understanding'}).click();
  if(await page.getByText('Clarification required',{exact:true}).isVisible())
    await page.getByText(/Summarise Completed and compare it by Facility/).click();
  const reconfirmation=page.waitForResponse(response=>response.url().endsWith('/confirm')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Confirm this exact meaning'}).click();
  const newContract=(await (await reconfirmation).json()).confirmed_contract.contract;
  await expect(page.getByLabel('Current report')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  const currentExpertContext=await browser.newContext();
  const currentExpert=await currentExpertContext.newPage();
  await signIn(currentExpert,'uninvited');
  await currentExpert.getByRole('button',{name:new RegExp(request)}).first().click();
  await currentExpert.getByText('Details for experts').last().click();
  await currentExpert.getByLabel('Expert report plan JSON').fill(JSON.stringify(reviewedSyntheticDesign(newContract)));
  await currentExpert.getByRole('button',{name:'Submit reviewed plan'}).click();
  await expect(currentExpert.getByLabel('Reviewed report plan')).toBeVisible();
  await currentExpertContext.close();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByRole('button',{name:'Build report',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  await page.getByText('Manage private case access').click();
  await page.getByRole('listitem').filter({hasText:'dev-uninvited · editor'}).getByRole('button',{name:'Revoke'}).click();
  await page.getByLabel('Company member').selectOption({label:'Uma Uninvited · dev-uninvited'});
  await page.getByLabel('Case permission').selectOption('VIEWER');
  await page.getByRole('button',{name:'Grant case access'}).click();
  const viewerExpertContext=await browser.newContext();
  const viewerExpert=await viewerExpertContext.newPage();
  await signIn(viewerExpert,'uninvited');
  await viewerExpert.getByRole('button',{name:new RegExp(request)}).first().click();
  await viewerExpert.getByText('Details for experts').last().click();
  await expect(viewerExpert.getByText('Report-plan submission requires expert edit access')).toBeVisible();
  await expect(viewerExpert.getByLabel('Expert report plan JSON')).toHaveCount(0);
  await viewerExpertContext.close();

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

test('business UI cancels an active attempt and keeps its truthful history',async({page})=>{
  await signIn(page);
  const request='Compare completed synthetic inspections by facility.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await page.getByLabel('Add CSV or XLSX evidence').setInputFiles({
    name:'inspections.csv',mimeType:'text/csv',buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Prepare understanding'}).click();
  if(await page.getByText('Clarification required',{exact:true}).isVisible())
    await page.getByText(/Summarise Completed and compare it by Facility/).click();
  const confirmation=page.waitForResponse(response=>response.url().endsWith('/confirm')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Confirm this exact meaning'}).click();
  const confirmed=(await (await confirmation).json()).confirmed_contract;
  let status:'RUNNING'|'CANCELLED'='RUNNING';
  const attempt=()=>({id:'synthetic-running-attempt',case_id:'synthetic-case',confirmed_contract_id:confirmed.id,reviewed_design_id:'synthetic-reviewed-plan',interpretation_id:confirmed.interpretation_id,request_version_id:'synthetic-version',status,attempt_number:1,retry_of_attempt_id:null,supersedes_attempt_id:null,provenance:{mode:'LOCAL_DETERMINISTIC_NO_MODEL_CALL',pipeline:'canonical',runtimeEvidence:{}},validation:null,failure:null,created_at:new Date().toISOString(),started_at:new Date().toISOString(),completed_at:null,cancelled_at:status==='CANCELLED'?new Date().toISOString():null,artifact:null});
  await page.route('**/api/cases/*/generation',route=>route.request().method()==='GET'?route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:[attempt()]})}):route.continue());
  await page.route('**/api/cases/*/generation/*/cancel',route=>{
    status='CANCELLED';
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({attempt:attempt()})});
  });
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByRole('button',{name:'Cancel build'})).toBeVisible();
  await page.getByRole('button',{name:'Cancel build'}).click();
  await page.locator('.report-history summary').click();
  await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Cancelled');
  await expect(page.getByRole('button',{name:'Cancel build'})).toHaveCount(0);
});
