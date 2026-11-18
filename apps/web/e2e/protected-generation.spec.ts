import {expect,test,type Page} from '@playwright/test';
import {chmodSync,existsSync,readFileSync,statSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {createHash,randomUUID} from 'node:crypto';


// Explicit retained-component qualification. This test route is never a product route.
const retainedGenerationPath='/__apbra_test_retained_generation__';
let retainedGenerationBundle:Promise<string>|undefined;
async function retainedGenerationCode(){
 if(!retainedGenerationBundle)retainedGenerationBundle=build({stdin:{resolveDir:dirname(fileURLToPath(import.meta.url)),sourcefile:'retained-generation-fixture.tsx',loader:'tsx',contents:`
import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {CaseEditor,ReportCreationWizard,protectedErrorMessage} from '../src/privateCases';
import {DurableConversation} from '../src/durableConversation';
import {authApi,casesApi} from '../src/api';
function RetainedFixture(){
 const [session,setSession]=useState(null),[records,setRecords]=useState([]),[active,setActive]=useState(null),[versions,setVersions]=useState([]),[draft,setDraft]=useState(''),[visible,setVisible]=useState(true),[ready,setReady]=useState(false),[notice,setNotice]=useState('');
 const selecting=useRef(0);
 const fail=error=>setNotice(protectedErrorMessage(error));
 async function select(id){const at=++selecting.current;try{const [record,history]=await Promise.all([casesApi.get(id),casesApi.versions(id)]);if(at!==selecting.current)return;setActive(record);setVersions(history.items);setDraft(record.current_request.request_text);setReady(false);setVisible(true)}catch(error){fail(error)}}
 useEffect(()=>{let live=true;Promise.all([authApi.session(),casesApi.list()]).then(([value,cases])=>{if(!live)return;setSession(value);setRecords(cases.items);const selected=new URLSearchParams(location.search).get('case');if(selected)void select(selected)}).catch(fail);return()=>{live=false;selecting.current++}},[]);
 async function save(){if(!active||!session?.csrf_token)return;try{const next=await casesApi.update(active.id,draft.trim(),active.version,session.csrf_token);setActive(next);setDraft(next.current_request.request_text);setVersions((await casesApi.versions(next.id)).items);setNotice('Your updated request was saved.')}catch(error){fail(error)}}
 if(!session?.actor)return <main><h1>Retained component fixture access unavailable</h1>{notice&&<p role="alert">{notice}</p>}</main>;
 return <main className="private-workspace" data-theme="clear-glass" data-color-mode="light" data-testid="retained-component-workspace"><section className="case-content"><p role="note">Synthetic retained component/API qualification. These controls are not the normal product journey.</p><h1>Your reports</h1><nav aria-label="Retained fixture report selection">{records.map(record=><button key={record.id} onClick={()=>void select(record.id)}>{record.report_title||record.current_request.request_text}</button>)}</nav>{notice&&<p role="alert">{notice}</p>}{active&&<><button onClick={()=>setVisible(false)}>All reports</button><button onClick={()=>setVisible(true)}>Current report</button><section hidden={!visible}><div className="case-identity"><h1>{active.report_title||active.current_request.request_text}</h1><p>{ready?'Candidate ready':'In progress'}</p></div><ReportCreationWizard key={session.actor.membership_id+':'+active.id} hasUnsavedGoal={draft!==active.current_request.request_text} goal={<CaseEditor record={active} versions={versions} requestText={draft} onRequestText={setDraft} onSave={()=>void save()} onRefresh={()=>void select(active.id)} busy={false}/>}>
{step=><DurableConversation key={session.actor.membership_id+':'+active.id} record={active} csrfToken={session.csrf_token} actorRole={session.actor.role} visibleStep={step} onContextChanged={version=>setActive(current=>current&&({...current,semantic_context_version:version}))} onReportReady={setReady} onError={fail}/>}
</ReportCreationWizard></section></>}</section></main>;
}
createRoot(document.getElementById('retained-fixture')!).render(<RetainedFixture/>);
`},bundle:true,write:false,loader:{'.md':'text'},format:'iife',platform:'browser',target:'es2022',define:{'process.env.NODE_ENV':'"test"'}}).then(result=>result.outputFiles[0].text);
 return retainedGenerationBundle;
}
const retainedInstalled=new WeakSet<Page>();
async function mountRetainedGeneration(page:Page,caseId?:string){
 if(!retainedInstalled.has(page)){
  const code=await retainedGenerationCode();
  await page.route('**'+retainedGenerationPath+'*',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/src/style.css"></head><body><div id="retained-fixture"></div><script>'+code.replaceAll('</script','<\\/script')+'</script></body></html>'}));
  retainedInstalled.add(page);
 }
 await page.goto(retainedGenerationPath+(caseId?'?'+new URLSearchParams({case:caseId}):''));
 await expect(page.getByTestId('retained-component-workspace')).toBeVisible();
}
async function ensureRetainedGeneration(page:Page){
 if(await page.getByTestId('retained-component-workspace').count())return;
 const input=page.locator('input[id^="case-evidence-"]').first();await expect(input).toBeAttached();
 const id=(await input.getAttribute('id'))!.slice('case-evidence-'.length);
 await mountRetainedGeneration(page,id);
}

// Current product UI with a labelled synthetic AI adapter; no provider or financial authority is exercised.
async function exerciseCurrentPrimary(sourcePage:Page,scenario:'success'|'member'|'definitive failure'|'lost reply'|'server error'|'stale-goal'){
 test.info().annotations.push({type:'coverage-layer',description:'Current app with synthetic native readiness, receipts, intake/confirmation and file-save projections; real auth/case/manual-upload/protected-download only.'});
 const context=await sourcePage.context().browser()!.newContext(),page=await context.newPage();
 const origin=new URL(test.info().project.use.baseURL!).origin;
 await context.route('**/*',route=>[origin,'http://127.0.0.1:18000'].includes(new URL(route.request().url()).origin)?route.continue():route.abort());
 try{
  await page.goto(origin+'/api/auth/login?'+new URLSearchParams({identity:scenario==='member'?'member':'owner',return_to:'/'}));
  const session=await (await page.request.get(origin+'/api/auth/session')).json();expect(session.authenticated).toBe(true);expect(session.actor.role).toBe(scenario==='member'?'MEMBER':'COMPANY_OWNER');
  await page.getByRole('button',{name:'Create report',exact:true}).first().click();
  const goal='Synthetic current journey '+scenario+' '+Date.now();await page.getByLabel('Your reporting goal').fill(goal);await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  const input=page.locator('input[id^="case-evidence-"]').first();await expect(input).toBeAttached();const caseId=(await input.getAttribute('id'))!.slice('case-evidence-'.length),base='/api/cases/'+caseId;
  const recordResponse=await page.request.get(origin+base);expect(recordResponse.status()).toBe(200);const record=(await recordResponse.json()).case;
  const nativePosts:Array<Record<string,unknown>>=[],legacyPosts:string[]=[];
  page.on('request',request=>{const path=new URL(request.url()).pathname;if(request.method()==='POST'&&path===base+'/native-response-checks')nativePosts.push(request.postDataJSON());if(request.method()==='POST'&&path.startsWith(base+'/')&&/\/(generation|automatic-designs|reviewed-designs|interpretations)(\/|$)/.test(path))legacyPosts.push(path)});
  const steps=page.getByRole('navigation',{name:'Report steps',exact:true});
  await expect(steps.getByRole('button',{name:'Confirm',exact:true})).toBeDisabled();await expect(steps.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();
  if(scenario==='member'){
   await steps.getByRole('button',{name:'Understanding',exact:true}).click();await expect(page.getByRole('alert')).toContainText('requires an authorized company administrator');
   await expect(steps.getByRole('button',{name:'Confirm',exact:true})).toBeDisabled();await expect(steps.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();expect(nativePosts).toEqual([]);expect(legacyPosts).toEqual([]);return;
  }
  const settings=await (await page.request.get(origin+'/api/tenant-settings')).json(),initialOutputs=await (await page.request.get(origin+base+'/outputs?page=1&limit=10')).json();
  let version=record.semantic_context_version,admitted=false,confirmed=false,saved=false;const receipts:Array<Record<string,unknown>>=[],connection=caseId+'-synthetic-analysis';
  const timestamp='2026-11-08T00:00:00Z',bytes=Buffer.from('PK\x03\x04SYNTHETIC-OPAQUE-UNINSPECTED-NATIVE-OUTPUT'),digest=createHash('sha256').update(bytes).digest('hex');
  // Real authentication, case/grant checks, manual opaque-byte upload and protected download use the actual server.
  // The explicit synthetic adapter below mocks native input readiness, response receipts/views, contract admission,
  // acceptance/confirmation, native-file save acknowledgements and output-page projections; it proves UI lifecycle only.
  // It does not prove provider qualification, real native-save provenance or backend protocol admission.
  let seededOutput:Record<string,unknown>|null=null;if(scenario==='success'){const seeded=await page.request.post(origin+base+'/outputs?'+new URLSearchParams({filename:'Synthetic-native-original.zip',expected_context_version:String(version),command_key:randomUUID()}),{headers:{'X-CSRF-Token':session.csrf_token,'Content-Type':'application/octet-stream'},data:bytes});expect(seeded.status()).toBe(200);seededOutput=(await seeded.json()).output;expect(seededOutput!.native_receipt_id).toBeNull();}

  const meaning={id:'synthetic-meaning-'+caseId,state:'READY_FOR_CONFIRMATION',current:true,context_version:version,simulation:'QUALIFIED_SERVER_MODEL',confirmation_summary:{objective:goal,businessQuestions:['Synthetic UI adapter only'],kpiDefinitions:[],scopeAndTime:[],dimensionsAndFilters:[],lifecycleDefinitions:[],materialPolicyDecisions:[]},interpretation:{assumptions:['SYNTHETIC UI ADAPTER: no model or qualification call.']},questions:[],unresolved_ambiguities:[]};
  const contract={id:'synthetic-contract-'+caseId,interpretation_id:meaning.id,schema_version:2,accepted_at:timestamp,contract:{},current:true};
  const output={id:seededOutput?String(seededOutput.id):'synthetic-output-'+caseId,case_id:caseId,request_version_id:record.current_request_version_id,context_version:version,filename:'Synthetic-native-original.zip',origin:'NATIVE',bytes:bytes.length,sha256:digest,native_receipt_id:'synthetic-report-'+caseId,native_task:'REPORT_DESIGN',delivery_kind:'GENERATED_FILE',content_verification:'NOT_RUN',created_at:timestamp};
  let confirmations=0;
  await context.route('**'+base+'/**',async route=>{
   const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();
   if(path===base+'/native-response-input'){
    const task=url.searchParams.get('task');await route.fulfill({json:{ready:true,files:[],receive_available:true,connection_id:task==='REPORT_DESIGN'?caseId+'-synthetic-report':connection,context_version:version,settings_id:settings.id,input_characters:100,input_limit:10000}});return;
   }
   if(path===base+'/native-response-checks'){
    const body=request.postDataJSON();expect(request.headers()['x-csrf-token']).toBe(session.csrf_token);expect(body.expected_context_version).toBe(version);expect(body.expected_settings_id).toBe(settings.id);expect(body.command_key).toMatch(/^[0-9a-f-]{36}$/);
    if(scenario==='lost reply'){await route.abort('failed');return}
    if(scenario==='definitive failure'||scenario==='server error'){await route.fulfill({status:scenario==='definitive failure'?409:503,json:{error:{code:'SYNTHETIC_STOPPED',message:'Synthetic native adapter stopped without a provider call.'}}});return}
    if(body.task==='REPORT_DESIGN')expect(body.confirmed_contract_id).toBe(contract.id);
    const receipt={operation_id:'synthetic-operation-'+receipts.length,state:'RECEIVED',task:body.task,context_version:version,http_status:200,provider_status:'completed',receipt_id:body.task==='REPORT_DESIGN'?'synthetic-report-'+caseId:'synthetic-analysis-'+caseId,bytes:bytes.length,sha256:digest};receipts.push(receipt);await route.fulfill({json:{native_response:receipt}});return;
   }
   if(path===base+'/native-response-receipts'){await route.fulfill({json:{items:receipts}});return}
   if(path.endsWith('/view')){const id=path.split('/').at(-2)!;await route.fulfill({json:{receipt_id:id,context_version:version,texts:['Synthetic native adapter response; no AI service called.'],bytes:bytes.length,sha256:digest}});return}
   if(path.endsWith('/contract')){if(method==='POST'){admitted=true;await route.fulfill({json:{accepted:true,task:'REQUIREMENT_ANALYSIS',interpretation:meaning}})}else await route.fulfill({json:{recognized:true,current:meaning.context_version===version,task:'REQUIREMENT_ANALYSIS',context_version:meaning.context_version,settings_id:settings.id,reason:null,receipt_id:'synthetic-analysis-'+caseId}});return}
   if(path===base+'/acceptance'){await route.fulfill({json:{interpretation:admitted?meaning:null,confirmed_contract:confirmed?contract:null}});return}
   if(path===base+'/confirm'){
    expect(request.headers()['x-csrf-token']).toBe(session.csrf_token);expect(request.postDataJSON()).toEqual({interpretation_id:meaning.id,expected_context_version:version});expect(meaning.context_version).toBe(version);confirmations++;confirmed=true;await route.fulfill({json:{confirmed_contract:contract}});return;
   }
   if(path.endsWith('/files')){await route.fulfill({json:{items:[{index:0,filename:output.filename,savable:true}],retrieval_configured:true,content_verification:'NOT_RUN'}});return}
   if(path.endsWith('/files/0/output')){expect(request.headers()['x-csrf-token']).toBe(session.csrf_token);expect(request.postDataJSON().expected_context_version).toBe(version);saved=true;await route.fulfill({json:{output,replayed:false}});return}
   if(path===base+'/outputs'){await route.fulfill({json:{...initialOutputs,items:saved?[output]:[],total:saved?1:0,page:1,pages:1,page_size:10,current_context_version:version,current_report_available:saved,snapshot:'synthetic-native-files'}});return}
   if(method==='POST'&&/\/(generation|automatic-designs|reviewed-designs|interpretations)(\/|$)/.test(path))throw new Error('Current journey attempted a silent legacy compiler fallback');
   await route.fallback();
  });
  // Reload after installing the adapter so all recovery reads share the same explicit synthetic state.
  await page.reload();await page.getByRole('button',{name:new RegExp(goal),exact:false}).first().click();
  await page.getByRole('navigation',{name:'Report steps',exact:true}).getByRole('button',{name:'Understanding',exact:true}).click();
  if(['definitive failure','lost reply','server error'].includes(scenario)){
   await expect(page.getByRole('alert')).toContainText('did not return a confirmed result');expect(nativePosts).toHaveLength(1);const original=nativePosts[0].command_key;
   await page.reload();await page.getByRole('button',{name:new RegExp(goal)}).first().click();await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Understanding',exact:true}).click();
   await expect(page.getByRole('alert')).toContainText('already started on this connection');expect(nativePosts).toHaveLength(1);expect(await page.evaluate(key=>sessionStorage.getItem(key),'apbra-native-attempt:'+caseId+':'+connection)).toBe(original);expect(confirmations).toBe(0);expect(legacyPosts).toEqual([]);return;
  }
  await expect(page.getByRole('heading',{name:'Here’s what AI understands',exact:true})).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Confirm',exact:true})).toBeDisabled();expect(confirmations).toBe(0);
  if(scenario==='stale-goal'){
   await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Goal',exact:true}).click();await page.getByLabel('Current business request').fill(goal+' changed');await page.getByRole('button',{name:'Save goal changes',exact:true}).click();await expect(page.getByText('Your updated request was saved.',{exact:true})).toBeVisible();version=(await (await page.request.get(origin+base)).json()).case.semantic_context_version;expect(version).toBeGreaterThan(meaning.context_version);
   await page.reload();await page.getByRole('button',{name:new RegExp(goal)}).first().click();await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Understanding',exact:true}).click();await expect(page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Confirm',exact:true})).toBeDisabled();await expect(page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Generate',exact:true})).toBeDisabled();expect(confirmations).toBe(0);expect(nativePosts).toHaveLength(1);expect(legacyPosts).toEqual([]);return;
  }
  await page.getByRole('checkbox',{name:'I have reviewed this understanding, its questions and assumptions.',exact:true}).check();await page.getByRole('button',{name:'Continue to confirmation',exact:true}).click();await expect(page.locator('.wizard-step-heading h2')).toHaveText('Confirm');await page.getByRole('button',{name:'Confirm requirements',exact:true}).click();expect(confirmations).toBe(1);
  await page.getByRole('button',{name:'Generate report',exact:true}).click();await expect(page.locator('.wizard-step-heading h2')).toHaveText('Download');
  const link=page.getByRole('link',{name:output.filename,exact:true});await expect(link).toBeVisible();const protectedPath=await link.getAttribute('href');const transport=await page.request.get(origin+protectedPath);expect(transport.status()).toBe(200);expect(transport.headers()['cache-control']).toBe('no-store');expect(await transport.body()).toEqual(bytes);const anonymous=await context.browser()!.newContext();try{expect((await anonymous.request.get(origin+protectedPath)).status()).toBe(401)}finally{await anonymous.close()}const downloaded=page.waitForEvent('download');await link.click();const file=await downloaded;expect(file.suggestedFilename()).toBe(output.filename);const stream=await file.createReadStream();expect(stream).not.toBeNull();const chunks:Buffer[]=[];for await(const chunk of stream!)chunks.push(Buffer.from(chunk));expect(Buffer.concat(chunks)).toEqual(bytes);
  expect(nativePosts.map(body=>body.task)).toEqual(['REQUIREMENT_ANALYSIS','REPORT_DESIGN']);expect(legacyPosts).toEqual([]);await page.reload();await page.getByRole('button',{name:new RegExp(goal)}).first().click();await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Download',exact:true}).click();await expect(page.getByRole('link',{name:output.filename,exact:true})).toBeVisible();expect(nativePosts).toHaveLength(2);expect(confirmations).toBe(1);
 }finally{await context.close()}
}

async function openRetainedReportHistory(page:Page){
 const history=page.locator('details.report-history');await expect(history).toBeAttached();
 if(!await history.evaluate(element=>(element as HTMLDetailsElement).open))await history.locator(':scope > summary').click();
}
async function openActualReport(page:Page,request:string){
 await page.goto('/');await page.getByRole('button',{name:new RegExp(request)}).first().click();
 await expect(page.locator('.private-workspace')).toBeVisible();
}

async function signIn(page:Page,identity:'owner'|'uninvited'|'foreign'='owner'){
  await page.goto('/api/auth/login?'+new URLSearchParams({identity,return_to:'/'}));
}


async function openStep(page:Page,step:'Goal'|'Information'|'Understanding'|'Confirm'|'Build'|'Report'){
  await ensureRetainedGeneration(page);
  await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:step,exact:true}).click();
  await expect(page.locator('.wizard-step-heading').getByRole('heading',{name:step,exact:true})).toBeVisible();
}

function reviewedSyntheticDesign(contract:any){
  // Test-only reviewed fixture. The application never derives a layout from obligations.
  const measures=[...new Map(contract.obligations.flatMap((item:any)=>item.measures.map((measure:any)=>[measure.id,measure]))).values()] as any[];
  const byName=new Map(measures.map(measure=>[measure.name,measure.id]));
  const pages=contract.pages.map((page:any,pageIndex:number)=>({id:`reviewed-page-${pageIndex}`,name:page.name,purpose:'Synthetic test validation',displayOption:'ActualSize',width:null,height:null,visuals:contract.obligations.filter((item:any)=>item.required&&item.pageNames.includes(page.name)).flatMap((item:any,index:number)=>Array.from({length:Math.max(1,item.minimumRepresentations)},(_,repeat)=>{
    const kind=item.kind,fields=item.fields,measureIds=item.measureNames.map((name:string)=>byName.get(name)),title=[...item.measureNames,...fields.map((field:string)=>field.split('.').at(-1))].join(' by ');
    return {id:`reviewed-${pageIndex}-${index}-${repeat}`,type:kind==='FILTER'?'slicer':kind==='TREND'?'line':kind==='KPI'?'card':'bar',title:title||'Reviewed synthetic visual',categoryField:['TREND','BREAKDOWN','LIFECYCLE'].includes(kind)?fields[0]:'',timeGrain:kind==='TREND'?item.timeGrain:'NONE',measureIds:kind==='FILTER'?[]:measureIds,fields:kind==='FILTER'?fields.slice(0,1):['BREAKDOWN','LIFECYCLE'].includes(kind)?fields.slice(1):[],altText:`Reviewed synthetic presentation of ${title}.`,position:{x:41.25+index*11,y:78.5+repeat*8,width:377.75,height:211.25,z:null,tabOrder:index+.25,angle:null}};
  }))}));
  const schema=contract.provenance.dataStructure,tableNames=schema.tables.map((table:any)=>table.name),factNames=new Set(measures.filter(measure=>measure.field).map(measure=>measure.field.split('.')[0]));
  return {artifact_kind:'ReportDesign',schema_version:2,projectName:'ReviewedSyntheticCandidate',overview:contract.objective,audience:contract.audience,dataModel:{factTables:tableNames.filter((name:string)=>factNames.has(name)),dimensionTables:tableNames.filter((name:string)=>!factNames.has(name)),relationships:schema.relationships},measures,pages,filters:[...new Set(contract.obligations.filter((item:any)=>item.kind==='FILTER').flatMap((item:any)=>item.fields))],branding:{themeName:'Reviewed Synthetic',primary:'#005A9C',accent:'#2D7D9A'},accessibility:['Every test visual has a text alternative.'],standardsApplied:[{citation:'local-knowledge:report-design-standards.md@1.0.0#RD-001',decision:'Reviewed synthetic visual choice for validation only.'}],assumptions:[],warnings:['LOCAL_DETERMINISTIC_NO_MODEL_CALL: synthetic reviewed test design.'],generationRequirements:['Validate the supplied design through the canonical pipeline.']};
}

test('current app with synthetic native lifecycle + retained compiler/backend: confirmed meaning and expert-reviewed plan build durable private candidates across reload',async({page,browser},testInfo)=>{
  await exerciseCurrentPrimary(page,'success');
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Compare completed inspections by facility.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  await openStep(page,'Information');
  const initialUpload=page.getByLabel('Browse files',{exact:true});
  await expect(initialUpload).toBeEnabled();
  await initialUpload.setInputFiles({
    name:'inspections.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Add selected files'}).click();
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review my requirements'}).click();
  const clarification=page.getByText('Clarification required',{exact:true});
  if(await clarification.isVisible())await page.getByText(/Summarise Completed and compare it by Facility/).click();
  const confirmationResponse=page.waitForResponse(response=>response.url().endsWith('/confirm')&&response.request().method()==='POST');
  await openStep(page,'Confirm');
  await page.getByRole('button',{name:'Confirm requirements'}).click();
  const confirmed=(await (await confirmationResponse).json()).confirmed_contract.contract;
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('confirmed-understanding.png'),fullPage:true});
  const design=JSON.stringify(reviewedSyntheticDesign(confirmed));
  await openStep(page,'Build');
  await expect(page.getByText('Create the report design',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Expert report design JSON')).toHaveCount(0);

  const expertContext=await browser.newContext();
  const expert=await expertContext.newPage();
  await signIn(expert,'uninvited');
  const invitationRequired=expert.getByRole('heading',{name:'An invitation is required'}).or(expert.getByRole('heading',{name:'Create Company / Workspace'}));
  const expertAccount=expert.getByRole('button',{name:/^Account menu for /});await expect(invitationRequired.or(expertAccount)).toBeVisible();
  if(await expertAccount.isVisible()){await expertAccount.click();await expect(expert.locator('.account-identity')).toContainText('expert');await expert.keyboard.press('Escape');}
  if(await invitationRequired.isVisible()){
    await page.goto('/');
    await page.getByRole('button',{name:'Administration'}).click();
    await page.getByRole('button',{name:'User management',exact:true}).click();
    await page.getByText('Invite a user',{exact:true}).click();
    await page.getByLabel('Provider subject').fill('dev-uninvited');
    await page.getByLabel('Application role').selectOption('EXPERT');
    await page.getByRole('button',{name:'Issue invitation'}).click();
    const invitationLink=await page.getByLabel('Private invitation link').inputValue();
    await expert.goto(invitationLink);
    await expert.getByRole('button',{name:'Accept invitation'}).click();
    await expect(expert.getByText('Invitation accepted. Your APBRA membership is active.')).toBeVisible();
  }
  await expert.getByRole('button',{name:/^Account menu for /}).click();await expect(expert.locator('.account-identity')).toContainText('expert');await expert.keyboard.press('Escape');
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await openActualReport(page,request);
  await page.getByText('Manage private report access').click();
  await page.getByLabel('Company member').selectOption({label:'Uma Uninvited · dev-uninvited'});
  await page.getByLabel('Report permission').selectOption('EDITOR');
  await page.getByRole('button',{name:'Grant report access'}).click();
  await expert.reload();
  await expert.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(expert,'Build');
  await expert.getByText('Details for experts').last().click();
  await expert.getByLabel('Expert report design JSON').fill(design);
  await expert.getByRole('button',{name:'Submit expert-reviewed design'}).click();
  await expect(expert.getByLabel('Eligible report design')).toBeVisible();
  await expertContext.close();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(page,'Build');
  await expect(page.getByLabel('Eligible report design')).toBeVisible();
  await expect(page.getByLabel('Expert report design JSON')).toHaveCount(0);
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('reviewed-build-readiness.png'),fullPage:true});

  const artifactRoot='/tmp/apbra-164-e2e-artifacts';
  const actor=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {actor:{company_id:string}});
  const reports=await page.evaluate(async()=>await (await fetch('/api/cases',{credentials:'same-origin'})).json() as {items:Array<{id:string;current_request:{request_text:string}}>});
  const caseId=reports.items.find(item=>item.current_request.request_text===request)?.id;
  expect(caseId).toBeTruthy();
  const companyRoot=join(artifactRoot,actor.actor.company_id),caseRoot=join(companyRoot,caseId!);
  const blockedRoot=existsSync(caseRoot)?caseRoot:existsSync(companyRoot)?companyRoot:artifactRoot;
  const previousMode=statSync(blockedRoot).mode&0o777;
  try{
    // An earlier E2E run may already have created a company subtree. Block the
    // nearest existing parent so the new attempt cannot be published there.
    chmodSync(blockedRoot,0o500);
  await openStep(page,'Build');
    await page.getByRole('button',{name:'Build report'}).click();
  await openStep(page,'Report');
    await openRetainedReportHistory(page);
    await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Build failed');
  }finally{chmodSync(blockedRoot,previousMode)}
  await openStep(page,'Build');
  await page.getByRole('button',{name:'Retry failed build'}).click();
  await openStep(page,'Report');
  await expect(page.locator('.generation-history li').filter({hasText:'Version 2'})).toContainText('Report ready');
  await openStep(page,'Report');
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
  await expect(page.getByLabel('Current report')).not.toContainText('Editable first draft recorded');
  await page.unroute('**/generation/*/artifact');
  const retriedDownload=page.waitForEvent('download');
  await page.getByRole('button',{name:'Try current report download again'}).click();
  expect((await retriedDownload).suggestedFilename()).toMatch(/\.zip$/);
  await expect(page.getByLabel('Current report')).toContainText('Editable first draft recorded');

  const apiPid=Number(readFileSync('/tmp/apbra-164-e2e-api.pid','utf8').trim());
  process.kill(apiPid,'SIGTERM');
  await expect.poll(async()=>{
    const replacement=Number(readFileSync('/tmp/apbra-164-e2e-api.pid','utf8').trim());
    if(replacement===apiPid)return false;
    try{return (await page.request.get('/api/health')).status()===200}catch{return false}
  },{timeout:10_000}).toBe(true);

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(page,'Report');
  await openRetainedReportHistory(page);
  await expect(page.locator('.generation-history li').filter({hasText:'Version 2'})).toContainText('Report ready');
  await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Build failed');
  await expect(page.getByText('2 builds',{exact:true})).toBeVisible();
  await openStep(page,'Build');
  await page.getByRole('button',{name:'Build another version'}).click();
  await openStep(page,'Report');
  await expect(page.locator('.generation-history li').filter({hasText:'Version 3'})).toContainText('Report ready');
  await expect(page.getByText('3 builds',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Download current report candidate'})).toHaveCount(1);
  await expect(page.getByRole('button',{name:'Download earlier report candidate'})).toHaveCount(1);
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('report-history.png'),fullPage:true});
  await openActualReport(page,request);
  await page.getByText('Manage private report access').click();
  await page.getByLabel('Company member').selectOption({label:'Morgan Member · dev-member'});
  await page.getByLabel('Report permission').selectOption('VIEWER');
  await page.getByRole('button',{name:'Grant report access'}).click();
  const viewerContext=await browser.newContext();
  const viewer=await viewerContext.newPage();
  await viewer.goto('/api/auth/login?'+new URLSearchParams({identity:'member',return_to:'/'}));
  await viewer.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(viewer,'Build');
  await expect(viewer.getByLabel('Eligible report design')).toBeVisible();
  await expect(viewer.getByText('building or cancelling requires editor access')).toBeVisible();
  await expect(viewer.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  await expect(viewer.getByRole('button',{name:'Retry failed build'})).toHaveCount(0);
  await viewerContext.close();

  await openStep(page,'Goal');
  await page.getByLabel('Current business request').fill(`${request} Show the total completed by facility.`);
  await page.getByRole('button',{name:'Save new version'}).click();
  await openStep(page,'Understanding');
  await expect(page.getByText('Reconfirmation required.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  await expect(page.getByLabel('Current report')).toHaveCount(0);
  await openStep(page,'Report');
  await expect(page.getByText('No current report yet')).toBeVisible();
  await openRetainedReportHistory(page);
  await expect(page.getByRole('button',{name:'Download earlier report candidate'})).toHaveCount(2);
  await openStep(page,'Information');
  const updatedUpload=page.getByLabel('Browse files',{exact:true});
  await expect(updatedUpload).toBeEnabled();
  await updatedUpload.setInputFiles({
    name:'current-inspections.csv',mimeType:'text/csv',buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Add selected files'}).click();
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review updated requirements'}).click();
  if(await page.getByText('Clarification required',{exact:true}).isVisible())
    await page.getByText(/Summarise Completed and compare it by Facility/).click();
  const reconfirmation=page.waitForResponse(response=>response.url().endsWith('/confirm')&&response.request().method()==='POST');
  await openStep(page,'Confirm');
  await page.getByRole('button',{name:'Confirm requirements'}).click();
  const newContract=(await (await reconfirmation).json()).confirmed_contract.contract;
  await expect(page.getByLabel('Current report')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  const currentExpertContext=await browser.newContext();
  const currentExpert=await currentExpertContext.newPage();
  await signIn(currentExpert,'uninvited');
  await currentExpert.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(currentExpert,'Build');
  await currentExpert.getByText('Details for experts').last().click();
  await currentExpert.getByLabel('Expert report design JSON').fill(JSON.stringify(reviewedSyntheticDesign(newContract)));
  await currentExpert.getByRole('button',{name:'Submit expert-reviewed design'}).click();
  await expect(currentExpert.getByLabel('Eligible report design')).toBeVisible();
  await currentExpertContext.close();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(page,'Build');
  await expect(page.getByRole('button',{name:'Build report',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Build another version'})).toHaveCount(0);
  await openActualReport(page,request);
  await page.getByText('Manage private report access').click();
  await page.getByRole('listitem').filter({hasText:'dev-uninvited · editor'}).getByRole('button',{name:'Revoke'}).click();
  await page.getByLabel('Company member').selectOption({label:'Uma Uninvited · dev-uninvited'});
  await page.getByLabel('Report permission').selectOption('VIEWER');
  await page.getByRole('button',{name:'Grant report access'}).click();
  const viewerExpertContext=await browser.newContext();
  const viewerExpert=await viewerExpertContext.newPage();
  await signIn(viewerExpert,'uninvited');
  await viewerExpert.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(viewerExpert,'Build');
  await viewerExpert.getByText('Details for experts').last().click();
  await expect(viewerExpert.getByText('Design submission requires expert edit access')).toBeVisible();
  await expect(viewerExpert.getByLabel('Expert report design JSON')).toHaveCount(0);
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

// These recovery fixtures intercept every API request, including commands. They
// exercise browser reloads and delayed reads without a backend or provider.
async function syntheticGenerationWorkspace(page:Page){
  const calls:string[]=[],timestamp='2026-10-11T00:00:00Z';
  const records=['a','b'].map(letter=>({id:`recovery-${letter}`,company_id:'synthetic-company',creator_membership_id:'synthetic-owner',current_request_version_id:`request-${letter}`,version:1,semantic_context_version:1,report_title:`Recovery report ${letter.toUpperCase()}`,created_at:timestamp,updated_at:timestamp,current_request:{id:`request-${letter}`,sequence:1,request_text:`Compare synthetic results for ${letter.toUpperCase()}.`,created_at:timestamp}}));
  const contract=(id:string)=>({id:`contract-${id}`,interpretation_id:`meaning-${id}`,schema_version:2,accepted_at:timestamp,contract:{},current:true});
  const design=(id:string)=>({id:`design-${id}`,confirmed_contract_id:`contract-${id}`,origin:'AUTO_ELIGIBLE',provenance_label:'Synthetic eligibility check',summary:{page_count:1,visual_count:1,description:'Mocked browser recovery fixture.'}});
  const attempt=(id:string,status:'RUNNING'|'SUCCEEDED')=>({id:`attempt-${id}`,case_id:id,confirmed_contract_id:`contract-${id}`,reviewed_design_id:`design-${id}`,interpretation_id:`meaning-${id}`,request_version_id:'synthetic-request',status,attempt_number:1,retry_of_attempt_id:null,supersedes_attempt_id:null,provenance:{mode:'LOCAL_DETERMINISTIC_NO_MODEL_CALL'},validation:null,failure:null,created_at:timestamp,started_at:timestamp,completed_at:status==='SUCCEEDED'?timestamp:null,cancelled_at:null,artifact:status==='SUCCEEDED'?{filename:'synthetic-candidate.zip',sha256:'a'.repeat(64)}:null});
  const state={calls,attempt,finished:false,designUnavailable:false,historyUnavailable:false,automaticUnavailable:false,holdCaseA:false,releaseCaseA:()=>{},caseARequested:Promise.resolve()};
  let received!:()=>void,release!:()=>void;
  state.caseARequested=new Promise<void>(resolve=>{received=resolve});
  const held=new Promise<void>(resolve=>{release=resolve});state.releaseCaseA=release;
  await page.route('**/api/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;calls.push(request.method()+' '+path);
    // Unexpected mutations can never escape to a real service.
    if(request.method()!=='GET'){await route.abort('failed');return}
    const record=records.find(item=>path.startsWith(`/api/cases/${item.id}`));
    let body:unknown,status=200;
    if(path==='/api/auth/session')body={authenticated:true,identity:{id:'synthetic-identity',display_name:'Synthetic Owner'},actor:{identity_id:'synthetic-identity',membership_id:'synthetic-owner',company_id:'synthetic-company',display_name:'Synthetic Owner',role:'COMPANY_OWNER'},csrf_token:'synthetic-only',membership_state:'ACTIVE'};
    else if(path==='/api/auth/providers')body={items:[],development_identities:[]};
    else if(path==='/api/workspace/branding')body={version:1,primary:'#17635E',accent:'#2D7D9A'};
    else if(path==='/api/cases')body={items:records};
    else if(path==='/api/cases/capabilities/uploads')body={data_extensions:['CSV','XLSX'],reference_extensions:['PNG','JPG','JPEG'],max_file_bytes:5000000,max_files_per_selection:8,max_data_items_per_report:20,max_reference_items_per_report:20};
    else if(record&&path===`/api/cases/${record.id}`)body={case:record};
    else if(record&&path.endsWith('/versions'))body={items:[record.current_request]};
    else if(record&&path.endsWith('/acceptance'))body={interpretation:null,confirmed_contract:contract(record.id)};
    else if(record&&path.endsWith('/reviewed-designs')){
      if(state.designUnavailable){status=409;body={error:{code:'CONTEXT_VERSION_CONFLICT',message:'Synthetic design read conflict'}}}
      else body={items:[design(record.id)],can_build:true,can_submit:false};
      if(record.id==='recovery-a'&&state.holdCaseA)await held;
    }else if(record&&path.endsWith('/automatic-designs')&&state.automaticUnavailable){
      status=409;body={error:{code:'CONTEXT_VERSION_CONFLICT',message:'Synthetic automatic design read conflict'}};
    }else if(record&&path.endsWith('/generation')){
      // Capture A's result before delaying it, as a real in-flight response would.
      body={items:record.id==='recovery-a'?[attempt(record.id,state.finished?'SUCCEEDED':'RUNNING')]:[]};
      if(state.historyUnavailable){status=503;body={error:{code:'SYNTHETIC_HISTORY_UNAVAILABLE',message:'Synthetic history read failed'}}}
      if(record.id==='recovery-a'&&state.holdCaseA){received();await held}
    }else if(record&&['conversation','evidence','reference-material','automatic-designs'].some(suffix=>path.endsWith('/'+suffix)))body={items:[]};
    else {status=503;body={error:{code:'SYNTHETIC_UNHANDLED_READ',message:'Synthetic read is not configured'}}}
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
  await mountRetainedGeneration(page);
  return state;
}

test('retained compiler component: mocked recovery reload polls a saved running build to success without resubmitting',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);
  await page.getByRole('button',{name:/Recovery report A/}).first().click();
  await openStep(page,'Build');await expect(page.getByRole('button',{name:'Cancel build',exact:true})).toBeVisible();
  await page.reload();await page.getByRole('button',{name:/Recovery report A/}).first().click();
  await openStep(page,'Build');await expect(page.getByRole('button',{name:'Cancel build',exact:true})).toBeVisible();
  const reads=()=>state.calls.filter(call=>call==='GET /api/cases/recovery-a/generation').length;
  const afterReload=reads();await expect.poll(reads).toBeGreaterThan(afterReload);
  state.finished=true;
  await expect(page.locator('.case-identity')).toContainText('Candidate ready');
  await openStep(page,'Report');await expect(page.getByLabel('Current report')).toContainText('Your editable first draft is ready');
  await openRetainedReportHistory(page);await expect(page.locator('.generation-history li')).toContainText('Report ready');
  expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
});

test('retained compiler component: mocked recovery design-read conflict preserves build history and explicit refresh restores commands',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);state.finished=true;state.designUnavailable=true;
  await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Build');
  await expect(page.getByText('Report design could not be refreshed',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/^(Build report|Build another version|Create report design|Create another design|Cancel build|Retry failed build)/})).toHaveCount(0);
  await expect(page.locator('.case-identity')).toContainText('Candidate ready');
  await openStep(page,'Report');await openRetainedReportHistory(page);
  await expect(page.locator('.generation-history li')).toContainText('Report ready');
  await expect(page.getByLabel('Current report')).toBeVisible();
  await openStep(page,'Build');state.designUnavailable=false;
  await page.getByRole('button',{name:'Refresh report design',exact:true}).click();
  await expect(page.getByText('Report design could not be refreshed',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Synthetic design read conflict',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:/^Build another version/})).toBeEnabled();
  await expect(page.getByLabel('Eligible report design')).toBeVisible();
  expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
});

test('retained compiler component: mocked recovery automatic-design read failure keeps history visible and commands closed',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);state.finished=true;state.automaticUnavailable=true;
  await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Build');
  await expect(page.getByText('Report design could not be refreshed',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/^(Build report|Build another version|Create report design|Create another design|Cancel build|Retry failed build)/})).toHaveCount(0);
  await openStep(page,'Report');await expect(page.getByLabel('Current report')).toBeVisible();
  await openStep(page,'Build');state.automaticUnavailable=false;
  await page.getByRole('button',{name:'Refresh report design',exact:true}).click();
  await expect(page.getByRole('button',{name:/^Build another version/})).toBeEnabled();
  await expect(page.getByText('Report design could not be refreshed',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Synthetic automatic design read conflict',{exact:true})).toHaveCount(0);
  expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
});

test('retained compiler component: mocked recovery history read failure avoids false empty state and retries without a command',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);state.finished=true;state.historyUnavailable=true;
  await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Report');
  await expect(page.getByText('Build history could not be refreshed',{exact:true})).toBeVisible();
  await expect(page.getByText('No current report yet',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Current report')).toHaveCount(0);
  await openRetainedReportHistory(page);
  await expect(page.getByText('No report builds yet.',{exact:true})).toHaveCount(0);
  await expect(page.locator('.report-history summary')).toContainText('Unavailable');
  state.historyUnavailable=false;
  await page.getByRole('button',{name:'Refresh build history',exact:true}).click();
  await expect(page.getByLabel('Current report')).toBeVisible();
  await expect(page.getByText('Build history could not be refreshed',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Synthetic history read failed',{exact:true})).toHaveCount(0);
  expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
});

test('retained compiler component: mocked recovery delayed completed build from an unmounted case cannot mark the next report ready',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);state.finished=true;state.holdCaseA=true;
  try{
    await page.getByRole('button',{name:/Recovery report A/}).first().click();await state.caseARequested;
    await page.getByRole('button',{name:'All reports',exact:true}).click();
    await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Report');
    await expect(page.locator('.case-identity')).toContainText('Recovery report B');
    await expect(page.locator('.case-identity')).toContainText('In progress');
    await expect(page.getByText('No current report yet',{exact:true})).toBeVisible();
    const oldResponses=Promise.all(['generation','reviewed-designs'].map(suffix=>page.waitForResponse(response=>new URL(response.url()).pathname==='/api/cases/recovery-a/'+suffix)));
    state.releaseCaseA();await oldResponses;
    // Flush the completed fetch and its React effects, rather than relying on a sleep.
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    await expect(page.locator('.case-identity')).not.toContainText('Candidate ready');
    await expect(page.getByLabel('Current report')).toHaveCount(0);
    await expect(page.getByText('No current report yet',{exact:true})).toBeVisible();
    await openStep(page,'Build');
    await expect(page.getByLabel('Eligible report design')).toHaveValue('design-recovery-b');
    await expect(page.getByLabel('Eligible report design').locator('option')).toHaveCount(1);
    expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
  }finally{state.releaseCaseA()}
});

test('current member guard + retained compiler cancellation: business UI cancels an active attempt and keeps its truthful history',async({page})=>{
  await exerciseCurrentPrimary(page,'member');
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Compare completed synthetic inspections by facility.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  await openStep(page,'Information');
  const cancellationUpload=page.getByLabel('Browse files',{exact:true});
  await expect(cancellationUpload).toBeEnabled();
  await cancellationUpload.setInputFiles({
    name:'inspections.csv',mimeType:'text/csv',buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Add selected files'}).click();
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review my requirements'}).click();
  if(await page.getByText('Clarification required',{exact:true}).isVisible())
    await page.getByText(/Summarise Completed and compare it by Facility/).click();
  const confirmation=page.waitForResponse(response=>response.url().endsWith('/confirm')&&response.request().method()==='POST');
  await openStep(page,'Confirm');
  await page.getByRole('button',{name:'Confirm requirements'}).click();
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
  await openStep(page,'Build');
  await expect(page.getByRole('button',{name:'Cancel build'})).toBeVisible();
  await page.getByRole('button',{name:'Cancel build'}).click();
  await openStep(page,'Report');
  await openRetainedReportHistory(page);
  await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Cancelled');
  await expect(page.getByRole('button',{name:'Cancel build'})).toHaveCount(0);
});

test('retained compiler component: design feedback remains pending across Back, prevents repeat submission and recovers after failure',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill('Compare completed synthetic feedback checks by facility.');
  await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  await openStep(page,'Information');
  await page.getByLabel('Browse files',{exact:true}).setInputFiles({
    name:'feedback-checks.csv',mimeType:'text/csv',buffer:Buffer.from('Facility,Completed\nNorth,18\nSouth,25\n'),
  });
  await page.getByRole('button',{name:'Add selected files'}).click();
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await expect(page.getByText('Review the accepted assumptions, limits and supported scope before proceeding. Optional questions do not prevent acceptance.')).toBeVisible();
  await openStep(page,'Confirm');
  await page.getByRole('button',{name:'Confirm requirements'}).click();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  await openStep(page,'Build');

  let release!:()=>void,observed!:()=>void,requests=0;
  const held=new Promise<void>(resolve=>{release=resolve});
  const intercepted=new Promise<void>(resolve=>{observed=resolve});
  // POSTs are always fulfilled/aborted here: this test cannot reach a provider.
  await page.route('**/api/cases/*/automatic-designs',async route=>{
    if(route.request().method()!=='POST'){await route.continue();return}
    requests+=1;
    if(requests>1){await route.abort('failed');return}
    observed();
    await held;
    await route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:{code:'AUTOMATIC_DESIGN_UNAVAILABLE',message:'Synthetic design request failed.'}})});
  });
  try{
    await page.getByRole('button',{name:'Create report design',exact:true}).click();
    await intercepted;
    const feedback=page.getByRole('status').filter({hasText:'Preparing report design…'});
    const pending=page.getByRole('button',{name:/Creating and checking design/});
    await expect(feedback).toBeVisible();
    await expect(feedback.locator('.processing-spinner')).toBeVisible();
    await expect(pending).toBeDisabled();
    await expect(pending).toHaveAttribute('aria-busy','true');
    await pending.evaluate(button=>(button as HTMLButtonElement).click());
    expect(requests).toBe(1);
    await page.getByRole('button',{name:'Back',exact:true}).click();
    await expect(page.locator('.wizard-step-heading').getByRole('heading',{name:'Confirm',exact:true})).toBeFocused();
    await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
    await page.getByRole('button',{name:'Next: Build',exact:true}).click();
    await expect(feedback).toBeVisible();
    await expect(pending).toBeDisabled();
    expect(requests).toBe(1);
    release();
    await expect(page.getByRole('alert').filter({hasText:'Synthetic design request failed.'})).toBeVisible();
    await expect(feedback).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Create report design',exact:true})).toBeEnabled();
    await expect(page.getByRole('button',{name:'Build report',exact:true})).toHaveCount(0);
    // A deliberately interrupted explicit retry clears pending feedback too.
    await page.getByRole('button',{name:'Create report design',exact:true}).click();
    await expect.poll(()=>requests).toBe(2);
    await expect(feedback).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Create report design',exact:true})).toBeEnabled();
    await expect(page.getByRole('alert')).toBeVisible();
    await openStep(page,'Report');
    await expect(page.getByText('No current report yet')).toBeVisible();
    await expect(page.getByRole('button',{name:'Download current report candidate'})).toHaveCount(0);
    await page.reload();
    await page.getByRole('button',{name:/Compare completed synthetic feedback checks by facility/}).first().click();
    await expect(page.locator('.wizard-step-heading').getByRole('heading',{name:'Goal',exact:true})).toBeVisible();
    await openStep(page,'Confirm');
    await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
    expect(requests).toBe(2);
  }finally{release()}
});

for(const firstResponse of ['definitive failure','lost reply','server error'] as const){
  test(`current native failure guard + retained compiler retry: mocked design retry ${firstResponse} preserves the correct proposal identity`,async({page})=>{
    await exerciseCurrentPrimary(page,firstResponse);
    await syntheticGenerationWorkspace(page);
    const keys:string[]=[],cached=new Map<string,any>();let proposals=0,eligible=false;
    const timestamp='2026-10-11T00:00:00Z';
    const reviewed={id:'retry-design',confirmed_contract_id:'contract-recovery-b',origin:'AUTO_ELIGIBLE',provenance_label:'Synthetic eligibility check',summary:{page_count:1,visual_count:1,description:'Cached synthetic proposal.'}};
    await page.route('**/api/cases/recovery-b/reviewed-designs**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:eligible?[reviewed]:[],can_build:true,can_submit:false})}));
    await page.route('**/api/cases/recovery-b/automatic-designs**',async route=>{
      if(route.request().method()==='GET'){
        await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:[...cached.values()].map(result=>result.attempt)})});return;
      }
      expect(route.request().method()).toBe('POST');
      const body=route.request().postDataJSON();expect(body.confirmed_contract_id).toBe('contract-recovery-b');
      expect(route.request().headers()['x-csrf-token']).toBe('synthetic-only');
      const key=body.command_key as string;expect(key).toBeTruthy();keys.push(key);
      let result=cached.get(key);
      if(!result){
        proposals+=1;const failed=firstResponse==='definitive failure'&&proposals===1;
        result={attempt:{id:`synthetic-proposal-${proposals}`,confirmed_contract_id:'contract-recovery-b',status:failed?'FAILED':'ELIGIBLE',provider_profile_id:null,model_or_deployment:null,prompt_version:null,configuration_id:null,capability_profile:{},usage:{call_count:0},failure:failed?{code:'SYNTHETIC_DESIGN_FAILED',message:'Synthetic definitive design failure.'}:null,validation:null,created_at:timestamp,completed_at:timestamp},reviewed_design:failed?null:reviewed};
        cached.set(key,result);eligible=!failed;
      }
      // All commands are intercepted; this counter simulates new work, never a provider call.
      if(keys.length===1&&firstResponse==='lost reply'){await route.abort('failed');return}
      if(keys.length===1&&firstResponse==='server error'){
        await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'AUTOMATIC_DESIGN_UNAVAILABLE',message:'Synthetic ambiguous server failure.'}})});return;
      }
      if(result.attempt.status==='FAILED'){
        await route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:{code:'AUTOMATIC_DESIGN_UNAVAILABLE',message:'Synthetic definitive design failure.'}})});return;
      }
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)});
    });
    await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Build');
    await page.getByRole('button',{name:'Create report design',exact:true}).click();
    await expect(page.getByRole('alert')).toBeVisible();
    const retry=page.getByRole('button',{name:/^Create (report design|another design)$/});
    await expect(retry).toBeEnabled();expect(keys).toHaveLength(1);await retry.click();
    await expect.poll(()=>keys.length).toBe(2);
    if(firstResponse==='definitive failure'){
      expect(keys[1]).not.toBe(keys[0]);expect(proposals).toBe(2);
      expect([...cached.values()].map(result=>result.attempt.status)).toEqual(['FAILED','ELIGIBLE']);
    }else{
      expect(keys[1]).toBe(keys[0]);expect(proposals).toBe(1);
      expect([...cached.values()].map(result=>result.attempt.id)).toEqual(['synthetic-proposal-1']);
    }
    await expect(page.getByLabel('Eligible report design')).toHaveValue('retry-design');
    await expect(page.getByRole('button',{name:'Build report',exact:true})).toBeEnabled();
  });
}
test('retained compiler component: a historical geometry-less plan offers the existing explicit fresh proposal without rebuilding it',async({page})=>{
 await syntheticGenerationWorkspace(page);let builds=0,proposals=0;
 await page.route('**/api/cases/recovery-b/generation',async route=>{if(route.request().method()==='GET'){await route.fulfill({json:{items:[]}});return}builds++;await route.fulfill({status:409,json:{error:{code:'AI_AUTHORED_GEOMETRY_REQUIRED',message:'This saved design has no AI-authored geometry. Use Create another design to request a fresh proposal; existing report files remain available.'}}})});
 await page.route('**/api/cases/recovery-b/automatic-designs',async route=>{if(route.request().method()!=='POST'){await route.fulfill({json:{items:[]}});return}proposals++;await route.fulfill({status:409,json:{error:{code:'AUTOMATIC_DESIGN_UNAVAILABLE',message:'Synthetic proposal stopped; no provider invoked.'}}})});
 await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Build');await page.getByRole('button',{name:'Build report',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Use Create another design');expect(builds).toBe(1);expect(proposals).toBe(0);await page.getByRole('button',{name:'Create another design',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Synthetic proposal stopped');expect(builds).toBe(1);expect(proposals).toBe(1);
});

async function syntheticExpertIngress(page:Page){
 await syntheticGenerationWorkspace(page);
 await page.route('**/api/auth/session',route=>route.fulfill({json:{authenticated:true,identity:{id:'synthetic-identity',display_name:'Synthetic Expert'},actor:{identity_id:'synthetic-identity',membership_id:'synthetic-owner',company_id:'synthetic-company',display_name:'Synthetic Expert',role:'EXPERT'},csrf_token:'synthetic-only',membership_state:'ACTIVE'}}));
 await page.route('**/api/cases/recovery-b/reviewed-designs**',route=>route.fulfill({json:{items:[],can_build:true,can_submit:true}}));
 await page.reload();await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Build');await page.locator('.generation-panel').getByText('Details for experts',{exact:true}).click();await expect(page.getByLabel('Expert report design JSON')).toBeVisible();
}
for(const token of ['9007199254740993','9007199254740993.0','9.007199254740993e15'] as const)test(`retained compiler component: expert raw geometry ${token} is not silently rounded or submitted`,async({page})=>{
 await syntheticExpertIngress(page);let posts=0;
 await page.route('**/api/cases/recovery-b/reviewed-designs',route=>{posts++;return route.fulfill({status:409,json:{error:{code:'SYNTHETIC_POST',message:'A rounded body reached the synthetic boundary.'}}})});
 const source=`{"schema_version":2,"pages":[{"displayOption":"ActualSize","visuals":[{"position":{"x":${token},"y":0,"width":0,"height":0}}]}]}`,draft=page.getByLabel('Expert report design JSON');await draft.fill(source);await page.getByRole('button',{name:'Submit expert-reviewed design',exact:true}).click();await expect(page.getByRole('alert')).toContainText('REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE');expect(posts).toBe(0);await expect(draft).toHaveValue(source);await expect(page.getByRole('button',{name:'Submit expert-reviewed design',exact:true})).toBeEnabled();
});
test('retained compiler component: expert exact large geometry retains original integer decimals through selected transport',async({page})=>{
 await syntheticExpertIngress(page);let body='',posts=0;
 await page.route('**/api/cases/recovery-b/reviewed-designs',route=>{posts++;body=route.request().postData()??'';expect(route.request().headers()['x-csrf-token']).toBe('synthetic-only');return route.fulfill({status:409,json:{error:{code:'SYNTHETIC_RETAINED',message:'Synthetic boundary retained the exact submission.'}}})});
 const position=Object.fromEntries(['x','y','width','height','z','tabOrder','angle'].map(key=>[key,'1152921504606846976']));
 const source=`{"schema_version":2,"pages":[{"displayOption":"ActualSize","width":1152921504606846976,"height":1152921504606846976,"visuals":[{"position":{${Object.entries(position).map(([key,value])=>`"${key}":${value}`).join(',')}}}]}]}`,draft=page.getByLabel('Expert report design JSON');await draft.fill(source);await page.getByRole('button',{name:'Submit expert-reviewed design',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Synthetic boundary retained the exact submission.');expect(posts).toBe(1);expect(body.match(/1152921504606846976/g)).toHaveLength(9);expect(body).not.toContain('1152921504606847000');expect(JSON.parse(body).confirmed_contract_id).toBe('contract-recovery-b');await expect(draft).toHaveValue(source);
});

test('retained compiler component: expert raw geometry malformed JSON keeps the draft and exposes only a fixed correction',async({page})=>{
 await syntheticExpertIngress(page);let posts=0;
 await page.route('**/api/cases/recovery-b/reviewed-designs',route=>{posts++;return route.fulfill({status:409,json:{error:{code:'SYNTHETIC_POST',message:'Malformed JSON reached the synthetic boundary.'}}})});
 const source='{"schema_version":2,"private_fixture":"SYNTHETIC_PRIVATE_PARSE_CANARY",}',draft=page.getByLabel('Expert report design JSON');await draft.fill(source);await page.getByRole('button',{name:'Submit expert-reviewed design',exact:true}).click();await expect(page.getByRole('alert')).toContainText('The expert report plan must be valid JSON.');await expect(page.getByRole('alert')).not.toContainText('SYNTHETIC_PRIVATE_PARSE_CANARY');expect(posts).toBe(0);await expect(draft).toHaveValue(source);
});

test('retained compiler component: expert raw geometry schema version alias keeps the original draft without intake',async({page})=>{
 await syntheticExpertIngress(page);let posts=0;
 await page.route('**/api/cases/recovery-b/reviewed-designs',route=>{posts++;return route.fulfill({status:409,json:{error:{code:'SYNTHETIC_POST',message:'A rounded version reached the synthetic boundary.'}}})});
 const source='{"schema_version":2.000000000000000000000001,"pages":[]}',draft=page.getByLabel('Expert report design JSON');await draft.fill(source);await page.getByRole('button',{name:'Submit expert-reviewed design',exact:true}).click();await expect(page.getByRole('alert')).toContainText('REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE');expect(posts).toBe(0);await expect(draft).toHaveValue(source);
});
for(const version of ['2.0','2e0'] as const)test(`retained compiler component: expert raw geometry exact schema version ${version} reaches selected intake unchanged in value`,async({page})=>{
 await syntheticExpertIngress(page);let posts=0,body='';
 await page.route('**/api/cases/recovery-b/reviewed-designs',route=>{posts++;body=route.request().postData()??'';return route.fulfill({status:409,json:{error:{code:'SYNTHETIC_EQUIVALENT',message:'Synthetic equivalent version reached intake.'}}})});
 const source=`{"schema_version":${version},"pages":[]}`,draft=page.getByLabel('Expert report design JSON');await draft.fill(source);await page.getByRole('button',{name:'Submit expert-reviewed design',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Synthetic equivalent version reached intake.');expect(posts).toBe(1);expect(JSON.parse(body).report_design.schema_version).toBe(2);await expect(draft).toHaveValue(source);
});

for(const status of ['PENDING','RUNNING'] as const)test(`retained compiler component: saved ${status.toLowerCase()} build prevents another submission and unlocks after completion`,async({page})=>{
  const state=await syntheticGenerationWorkspace(page);
  await page.route('**/api/cases/recovery-a/generation',async route=>{
    state.calls.push(route.request().method()+' /api/cases/recovery-a/generation');
    if(route.request().method()!=='GET'){await route.abort('failed');return}
    await route.fulfill({json:{items:[{...state.attempt('recovery-a',state.finished?'SUCCEEDED':'RUNNING'),status:state.finished?'SUCCEEDED':status}]}});
  });
  await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Build');
  const build=page.locator('.build-readiness .command-bar button').first();
  await expect(page.getByRole('button',{name:'Cancel build',exact:true})).toBeVisible();
  await expect(build).toBeDisabled();await expect(build).toHaveAttribute('aria-busy','true');
  await openStep(page,'Information');await openStep(page,'Build');await expect(build).toBeDisabled();
  await page.reload();await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Build');
  await expect(build).toBeDisabled();
  state.finished=true;
  await expect(page.getByRole('button',{name:/^Build another version/})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Cancel build',exact:true})).toHaveCount(0);
  await openStep(page,'Report');await openRetainedReportHistory(page);
  await expect(page.locator('.generation-history li')).toContainText('Report ready');
  expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
});

test('retained compiler component: unreadable build history prevents another build until explicit read recovery',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);state.finished=true;state.historyUnavailable=true;
  await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Build');
  await expect(page.getByText('Build history could not be refreshed',{exact:true})).toBeVisible();
  const build=page.locator('.build-readiness .command-bar button').first();
  await expect(build).toBeDisabled();
  await expect(page.getByLabel('Eligible report design')).toHaveValue('design-recovery-a');
  state.historyUnavailable=false;await page.getByRole('button',{name:'Refresh build history',exact:true}).click();
  await expect(page.getByRole('button',{name:/^Build another version/})).toBeEnabled();
  await expect(page.getByText('Build history could not be refreshed',{exact:true})).toHaveCount(0);
  await openStep(page,'Report');await expect(page.getByLabel('Current report')).toBeVisible();
  expect(state.calls.filter(call=>!call.startsWith('GET '))).toEqual([]);
});

test('retained compiler component: one build dispatch stays disabled through its pending acknowledgement and wizard navigation',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);
  let dispatches=0,saved=false,release!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve});
  const pending={...state.attempt('recovery-b','RUNNING'),status:'PENDING'};
  await page.route('**/api/cases/recovery-b/generation',async route=>{
    if(route.request().method()==='GET'){await route.fulfill({json:{items:saved?[pending]:[]}});return}
    if(route.request().method()!=='POST'){await route.abort('failed');return}
    dispatches++;await held;saved=true;await route.fulfill({json:{attempt:pending}});
  });
  try{
    await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Build');
    const build=page.locator('.build-readiness .command-bar button').first();await expect(build).toBeEnabled();
    await build.evaluate((button:HTMLButtonElement)=>{button.click();button.click()});
    await expect.poll(()=>dispatches).toBe(1);await expect(page.getByText('Submitting this build',{exact:true})).toBeVisible();
    await expect(build).toBeDisabled();
    await openStep(page,'Information');await openStep(page,'Build');await expect(build).toBeDisabled();
    release();await expect(page.getByRole('button',{name:'Cancel build',exact:true})).toBeVisible();
    await expect(page.getByText('Submitting this build',{exact:true})).toHaveCount(0);
    await expect(build).toBeDisabled();await expect(build).toHaveAttribute('aria-busy','true');
    await expect(build).toContainText('Waiting to build');expect(dispatches).toBe(1);
  }finally{release()}
});

test('retained compiler component: an uncertain build acknowledgement reuses its original idempotency key on explicit retry',async({page})=>{
  const state=await syntheticGenerationWorkspace(page),bodies:Array<{command_key:string;confirmed_contract_id:string;reviewed_design_id:string}>=[];
  let saved=false;
  const completed=state.attempt('recovery-b','SUCCEEDED');
  await page.route('**/api/cases/recovery-b/generation',async route=>{
    if(route.request().method()==='GET'){await route.fulfill({json:{items:saved?[completed]:[]}});return}
    if(route.request().method()!=='POST'){await route.abort('failed');return}
    bodies.push(route.request().postDataJSON());
    if(bodies.length===1){await route.abort('failed');return}
    saved=true;await route.fulfill({json:{attempt:completed}});
  });
  await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Build');
  const build=page.locator('.build-readiness .command-bar button').first();await expect(build).toBeEnabled();
  await build.click();await expect.poll(()=>bodies.length).toBe(1);await expect(build).toBeEnabled();
  await build.click();await expect.poll(()=>bodies.length).toBe(2);
  expect(bodies[0].command_key).toBeTruthy();expect(bodies[1]).toEqual(bodies[0]);
  expect(bodies[0].confirmed_contract_id).toBe('contract-recovery-b');expect(bodies[0].reviewed_design_id).toBe('design-recovery-b');
  await expect(page.getByRole('button',{name:/^Build another version/})).toBeEnabled();
  await openStep(page,'Report');await expect(page.getByLabel('Current report')).toBeVisible();
});

test('retained compiler component: an earlier unfinished current build stays cancellable when a newer completed version is visible',async({page})=>{
  const state=await syntheticGenerationWorkspace(page);state.finished=true;
  const old={...state.attempt('recovery-a','RUNNING'),id:'earlier-active',attempt_number:1};
  const completed={...state.attempt('recovery-a','SUCCEEDED'),id:'newer-completed',attempt_number:2};
  let cancelled=false,cancels=0;
  await page.route('**/api/cases/recovery-a/generation',async route=>{
    if(route.request().method()!=='GET'){await route.abort('failed');return}
    await route.fulfill({json:{items:[completed,{...old,status:cancelled?'CANCELLED':'RUNNING'}]}});
  });
  await page.route('**/api/cases/recovery-a/generation/earlier-active/cancel',async route=>{
    if(route.request().method()!=='POST'){await route.abort('failed');return}
    cancels++;cancelled=true;await route.fulfill({json:{attempt:{...old,status:'CANCELLED',cancelled_at:'2026-10-14T00:00:00Z'}}});
  });
  await page.getByRole('button',{name:/Recovery report A/}).first().click();await openStep(page,'Build');
  await expect(page.locator('.build-readiness .command-bar button').first()).toBeDisabled();
  await page.getByRole('button',{name:'Cancel build',exact:true}).click();
  await expect(page.getByRole('button',{name:/^Build another version/})).toBeEnabled();expect(cancels).toBe(1);
  await openStep(page,'Report');await expect(page.getByLabel('Current report')).toContainText('Version 2');
  await openRetainedReportHistory(page);await expect(page.locator('.generation-history li').filter({hasText:'Version 1'})).toContainText('Cancelled');
});

test('current stale-goal guard + retained compiler: an unfinished historical confirmation does not block the current confirmed build',async({page})=>{
  await exerciseCurrentPrimary(page,'stale-goal');
  const state=await syntheticGenerationWorkspace(page);
  await page.route('**/api/cases/recovery-b/generation',async route=>{
    if(route.request().method()!=='GET'){await route.abort('failed');return}
    await route.fulfill({json:{items:[{...state.attempt('recovery-b','RUNNING'),confirmed_contract_id:'historical-confirmation'}]}});
  });
  await page.getByRole('button',{name:/Recovery report B/}).first().click();await openStep(page,'Build');
  await expect(page.locator('.build-readiness .command-bar button').first()).toBeEnabled();
  await expect(page.getByRole('button',{name:'Cancel build',exact:true})).toHaveCount(0);
});
