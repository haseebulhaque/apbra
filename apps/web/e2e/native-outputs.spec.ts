import {expect,test,type Page} from '@playwright/test';
import {build} from 'esbuild';
import {createHash,randomUUID} from 'node:crypto';
import {dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

// Explicit retained RequestOutputs component qualification; never a product route.
const retainedOutputPath='/__apbra_test_retained_outputs__';
let retainedOutputBundle:Promise<string>|undefined;
const outputHarnessInstalled=new WeakSet<Page>();
async function mountRetainedOutput(page:Page,caseId:string){
 if(!retainedOutputBundle)retainedOutputBundle=build({stdin:{resolveDir:dirname(fileURLToPath(import.meta.url)),sourcefile:'retained-output-fixture.tsx',loader:'tsx',contents:`
import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {RequestOutputs} from '../src/RequestOutputs';
import {authApi,casesApi} from '../src/api';
import {protectedErrorMessage} from '../src/privateCases';
function RetainedOutput(){const [binding,setBinding]=useState(null),[visible,setVisible]=useState(true),[message,setMessage]=useState('');useEffect(()=>{let live=true;const id=new URLSearchParams(location.search).get('case');Promise.all([authApi.session(),casesApi.get(id)]).then(([session,record])=>{if(live)setBinding({session,record})}).catch(error=>setMessage(protectedErrorMessage(error)));return()=>{live=false}},[]);return <main data-testid="retained-output-fixture"><p>Synthetic retained component qualification. Manual generated-file intake is not the normal business journey.</p><button onClick={()=>setVisible(false)}>Leave retained output view</button><button onClick={()=>setVisible(true)}>Return to retained output view</button>{message&&<p role="alert">{message}</p>}{binding&&<section hidden={!visible}><RequestOutputs caseId={binding.record.id} contextVersion={binding.record.semantic_context_version} csrfToken={binding.session.csrf_token} onError={error=>setMessage(protectedErrorMessage(error))}/></section>}</main>}
createRoot(document.getElementById('retained-output')!).render(<RetainedOutput/>);
`},bundle:true,write:false,loader:{'.md':'text'},format:'iife',platform:'browser',target:'es2022',define:{'process.env.NODE_ENV':'"test"'}}).then(result=>result.outputFiles[0].text);
 if(!outputHarnessInstalled.has(page)){const code=await retainedOutputBundle;await page.route('**'+retainedOutputPath+'*',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/src/style.css"></head><body><div id="retained-output"></div><script>'+code.replaceAll('</script','<\\/script')+'</script></body></html>'}));outputHarnessInstalled.add(page)}
 await page.goto(retainedOutputPath+'?'+new URLSearchParams({case:caseId}));await expect(page.getByTestId('retained-output-fixture')).toBeVisible();await expect(page.getByLabel('Generated output file')).toBeVisible();
}
async function currentCaseId(page:Page){const input=page.locator('input[id^="case-evidence-"]').first();await expect(input).toBeAttached();return(await input.getAttribute('id'))!.slice('case-evidence-'.length)}

async function openNew(page:Page,identity:'owner'|'member'){
 await page.goto('/api/auth/login?'+new URLSearchParams({identity,return_to:'/'}));
 await expect(page.getByRole('button',{name:/^Account menu for /})).toBeVisible();
 await page.getByRole('button',{name:'Create report',exact:true}).first().click();
 const goal='Synthetic opaque output '+identity+' '+Date.now();
 await page.getByLabel('Your reporting goal').fill(goal);
 await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
 await expect(page.getByText('Your goal is saved. Add supporting information next.')).toBeVisible();
 return goal;
}

test('retained output component + current member download: original opaque ZIP bytes survive reopen',async({page,request})=>{
 const goal=await openNew(page,'member');
 await expect(page.getByRole('region',{name:'Saved Azure information'})).toHaveCount(0);await expect(page.getByLabel('Generated output file')).toHaveCount(0);const caseId=await currentCaseId(page);await mountRetainedOutput(page,caseId);
 const original=Buffer.from('UEsDBBQAAAAAAFVuU13tHB4kHAAAABwAAAAQAAAALi4vc3ludGhldGljLnR4dFNZTlRIRVRJQy1QUkVTRVJWRS1VTkNIQU5HRURQSwECFAMUAAAAAABVblNd7RweJBwAAAAcAAAAEAAAAAAAAAAAAAAAgAEAAAAALi4vc3ludGhldGljLnR4dFBLBQYAAAAAAQABAD4AAABKAAAAAAA=','base64');
 await page.getByLabel('Generated output file').setInputFiles({name:'Synthetic.zip',mimeType:'application/zip',buffer:original});
 await page.getByRole('button',{name:'Save generated file',exact:true}).click();
 const link=page.getByRole('link',{name:'Synthetic.zip',exact:true});await expect(link).toBeVisible();
 const path=await link.getAttribute('href');expect(path).toMatch(/^\/api\/cases\/[^/]+\/outputs\/[^/]+\/download$/);
 const saved=await page.request.get(path!);expect(saved.status()).toBe(200);expect(await saved.body()).toEqual(original);
 expect(saved.headers()['cache-control']).toBe('no-store');expect(saved.headers()['content-disposition']).toContain('attachment');
 expect((await request.get(path!)).status()).toBe(401);
 // Return to the real normal app with the same member and actual protected output row.
 await page.goto('/');await page.getByRole('button',{name:new RegExp(goal)}).first().click();
 await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:'Download',exact:true}).click();await page.getByText('Other saved files',{exact:true}).click();await expect(link).toBeVisible();
 expect(await link.getAttribute('href')).toBe(path);
 await expect(page.getByRole('heading',{name:'ReportDesign compiler fallback',exact:true})).toHaveCount(0);await expect(page.getByRole('heading',{name:'Your report is not available yet',exact:true})).toBeVisible();
});

test('current app selected-report support: owner passive inspection cannot acquire a send grant',async({page})=>{
 const sends:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/native-response-checks'))sends.push(r.url())});
 await openNew(page,'owner');await page.getByRole('button',{name:'Administration',exact:true}).click();await page.getByRole('button',{name:'Selected report support',exact:true}).click();
 await expect(page.getByRole('region',{name:'Saved Azure information'})).toBeVisible();
 const response=page.waitForResponse(r=>r.url().includes('/native-response-input'));
 await page.getByRole('button',{name:'Check agent connection and input',exact:true}).click();await response;
 await expect(page.getByRole('button',{name:'Send once to agent',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Show saved answers',exact:true}).click();
 await expect(page.getByText('No saved Azure responses.',{exact:true})).toBeVisible();
 expect(sends).toEqual([]);
});

test('retained output component: visibility changes retain the queued File without saving',async({page})=>{
 await openNew(page,'member');await expect(page.getByLabel('Generated output file')).toHaveCount(0);await mountRetainedOutput(page,await currentCaseId(page));
 const saves:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/outputs'))saves.push(r.url())});
 await page.getByLabel('Generated output file').setInputFiles({name:'Queued-original.bin',mimeType:'application/octet-stream',buffer:Buffer.from('SYNTHETIC-NOT-SENT')});
 await page.getByRole('button',{name:'Leave retained output view',exact:true}).click();
 await expect(page.getByLabel('Generated output file')).toBeHidden();
 await page.getByRole('button',{name:'Return to retained output view',exact:true}).click();
 await expect(page.getByLabel('Generated output file')).toBeVisible();
 expect(await page.getByLabel('Generated output file').evaluate((element:HTMLInputElement)=>element.files?.[0]?.name)).toBe('Queued-original.bin');
 expect(saves).toEqual([]);
});


// Only the native-service response, admission and projection are simulated here.
// The signed-in case, source upload, protected output storage, download and
// anonymous denial use the test server. No Foundry or Desktop result is implied.
for(const width of [1280,375]){
 test(`signed-in v10 browser fixture at ${width}px requires two actions and verifies the protected download`,async({page,request})=>{
  await page.setViewportSize({width,height:824});
  const goal=await openNew(page,'owner');
  const id=await currentCaseId(page);
  const path='/api/cases/'+id;
  const csv=Buffer.from('month,work_order_type,completed\n2026-08,Electrical,4\n2026-08,Mechanical,7\n2026-09,Electrical,6\n2026-09,Mechanical,3\n2026-10,Electrical,5\n2026-10,Mechanical,8\n');
  expect(createHash('sha256').update(csv).digest('hex')).toBe('5226ffea2c59ff6c00e7171e38787de98584775491e1f591922434714b1842f4');
  await page.getByLabel('Browse files',{exact:true}).setInputFiles({name:'synthetic-maintenance.csv',mimeType:'text/csv',buffer:csv});
  const upload=page.waitForResponse(r=>r.url().includes(path+'/evidence')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Add selected files',exact:true}).click();
  expect((await upload).ok()).toBe(true);
  const {case:record}=await (await page.request.get(path)).json();
  const session=await (await page.request.get('/api/auth/session')).json();
  const version=record.semantic_context_version;
  const bytes=Buffer.from('Synthetic browser download fixture. No report service was invoked.');
  const digest=createHash('sha256').update(bytes).digest('hex');
  const saved=await page.request.post(path+'/outputs?'+new URLSearchParams({
   filename:'synthetic-project.zip',expected_context_version:String(version),command_key:randomUUID(),
  }),{headers:{'X-CSRF-Token':session.csrf_token,'Content-Type':'application/octet-stream'},data:bytes});
  expect(saved.ok()).toBe(true);
  const {output:stored}=await saved.json();
  const filePage=await (await page.request.get(path+'/outputs?page=1&limit=10')).json();
  const settingsId=randomUUID();
  const analysisId=randomUUID();
  const reportId=randomUUID();
  const meaning={id:randomUUID(),state:'READY_FOR_CONFIRMATION',current:true,context_version:version,simulation:'QUALIFIED_SERVER_MODEL',confirmation_summary:{objective:goal,businessQuestions:[],kpiDefinitions:[],scopeAndTime:[],dimensionsAndFilters:[],lifecycleDefinitions:[],materialPolicyDecisions:[]},interpretation:{},questions:[],unresolved_ambiguities:[]};
  const contract={id:randomUUID(),interpretation_id:meaning.id,schema_version:2,accepted_at:new Date().toISOString(),contract:{},current:true};
  const original={...stored,v10_provenance:'OFFLINE_FIXTURE',native_receipt_id:reportId,native_task:'FULL_REPORT_ARTIFACT',delivery_kind:'V10_REPORT_ORIGINAL',content_verification:'PACKAGE_CHECKED',origin:'NATIVE_OUTPUT'};
  const calls:string[]=[];
  const receipts:Record<string,unknown>[]=[];
  let admitted=false,confirmed=false;
  await page.route('**'+path+'/**',async route=>{
   const req=route.request(),url=new URL(req.url()),endpoint=url.pathname.slice(path.length);
   if(endpoint==='/outputs'&&req.method()==='GET'){
    return route.fulfill({json:{...filePage,demo_mode:'FOUNDRY_V10',items:[calls.includes('FULL_REPORT_ARTIFACT')?original:stored],current_report_available:calls.includes('FULL_REPORT_ARTIFACT')}});
   }
   if(endpoint==='/native-response-input'){
    const purpose=url.searchParams.get('task');
    return route.fulfill({json:{demo_mode:'FOUNDRY_V10',ready:true,files:[],receive_available:true,connection_id:'fixture-'+purpose,settings_id:settingsId,request_version_id:record.current_request_version_id,context_version:version,input_characters:csv.length,input_limit:10000}});
   }
   if(endpoint==='/native-response-checks'){
    const body=req.postDataJSON();
    expect(body.explicit_demo_action).toBe(true);
    expect(body.expected_context_version).toBe(version);
    expect(body.expected_settings_id).toBe(settingsId);
    expect(req.headers()['x-csrf-token']).toBe(session.csrf_token);
    expect(calls).not.toContain(body.task);
    expect(body.task).toBe(confirmed?'FULL_REPORT_ARTIFACT':'REQUIREMENT_ANALYSIS');
    if(confirmed)expect(body.confirmed_contract_id).toBe(contract.id);
    calls.push(body.task);
    const receipt={operation_id:randomUUID(),task:body.task,context_version:version,state:'RECEIVED',http_status:200,provider_status:'completed',receipt_id:confirmed?reportId:analysisId,bytes:bytes.length,sha256:digest,...(confirmed?{report_output:original}:{})};
    receipts.push(receipt);
    return route.fulfill({json:{native_response:receipt}});
   }
   if(endpoint==='/native-response-receipts')return route.fulfill({json:{items:receipts}});
   if(endpoint==='/native-response-receipts/'+analysisId+'/view')return route.fulfill({json:{receipt_id:analysisId,context_version:version,texts:['Synthetic offline analysis'],bytes:bytes.length,sha256:digest}});
   if(endpoint==='/native-response-receipts/'+analysisId+'/contract'){
    if(req.method()==='POST'){admitted=true;return route.fulfill({json:{accepted:true,interpretation:meaning}})}
    return route.fulfill({json:{recognized:true,current:true,task:'REQUIREMENT_ANALYSIS',context_version:version,settings_id:settingsId,receipt_id:analysisId}});
   }
   if(endpoint==='/acceptance')return route.fulfill({json:{interpretation:admitted?meaning:null,confirmed_contract:confirmed?contract:null}});
   if(endpoint==='/confirm'){
    expect(calls).toEqual(['REQUIREMENT_ANALYSIS']);
    expect(req.postDataJSON()).toEqual({interpretation_id:meaning.id,expected_context_version:version});
    confirmed=true;
    return route.fulfill({json:{confirmed_contract:contract}});
   }
   return route.fallback();
  });
  const steps=page.getByRole('navigation',{name:'Report steps'});
  const openStep=async(name:string)=>steps.getByRole('button',{name,exact:true}).press('Enter');
  const reopen=async()=>{await page.reload();await page.getByRole('button',{name:new RegExp(goal)}).first().click()};
  await reopen();
  await openStep('Download');
  await expect(page.getByRole('heading',{name:'Your report is not available yet'})).toBeVisible();
  await openStep('Understanding');
  await expect(page.getByRole('button',{name:'Start AI review'})).toBeEnabled();
  await reopen();
  await openStep('Understanding');
  const start=page.getByRole('button',{name:'Start AI review'});
  await expect(start).toBeEnabled();expect(calls).toEqual([]);
  await start.press('Enter');
  await expect(page.getByRole('heading',{name:'Here’s what AI understands'})).toBeVisible();
  await expect(steps.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();
  await page.getByRole('checkbox',{name:/I have reviewed/}).press('Space');
  await page.getByRole('button',{name:'Continue to confirmation',exact:true}).press('Enter');
  await page.getByRole('button',{name:'Confirm requirements',exact:true}).press('Enter');
  const generate=page.getByRole('button',{name:'Generate report',exact:true});
  await expect(generate).toBeEnabled();expect(calls).toEqual(['REQUIREMENT_ANALYSIS']);
  await generate.press('Enter');
  const download=page.getByRole('button',{name:'Download synthetic-project.zip',exact:true});
  await expect(download).toBeVisible();
  await expect(page.getByText(digest,{exact:true})).toBeVisible();
  await expect(page.getByText('Synthetic report package from an offline test fixture.',{exact:true})).toBeVisible();
  await expect(page.getByText(/Verified service records identify Foundry/)).toHaveCount(0);
  await expect(page.getByText(/Power BI Desktop verification and business acceptance are pending/)).toBeVisible();
  const protectedPath=path+'/outputs/'+stored.id+'/download';
  expect((await request.get(protectedPath)).status()).toBe(401);
  await page.route('**'+protectedPath,r=>r.fulfill({body:Buffer.alloc(bytes.length,0x78)}));
  await download.press('Enter');
  await expect(page.getByRole('alert')).toContainText('did not match the original file');
  await page.unroute('**'+protectedPath);
  const saving=page.waitForEvent('download');await download.press('Enter');
  const file=await saving;expect(file.suggestedFilename()).toBe(stored.filename);
  const stream=await file.createReadStream();expect(stream).not.toBeNull();
  const chunks:Buffer[]=[];for await(const chunk of stream!)chunks.push(Buffer.from(chunk));
  expect(createHash('sha256').update(Buffer.concat(chunks)).digest('hex')).toBe(digest);
  await expect(page.getByText('Download bytes matched the original SHA-256.')).toBeVisible();
  await reopen();await openStep('Download');await expect(download).toBeVisible();
  await openStep('Generate');await expect(generate).toBeDisabled();
  // Exercise display of simulated wire metadata only. No live service call occurs.
  original.v10_provenance='LIVE_METADATA_VERIFIED';
  await reopen();await openStep('Download');
  await expect(page.getByText(/Verified service records identify Foundry v10/)).toBeVisible();
  await expect(page.getByText(/Synthetic report package from an offline test fixture/)).toHaveCount(0);
  original.v10_provenance='UNRECOGNIZED';
  await reopen();await openStep('Download');
  await expect(page.getByText('Other saved files',{exact:true})).toBeVisible();
  await expect(download).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Your report is not available yet'})).toBeVisible();
  expect(calls).toEqual(['REQUIREMENT_ANALYSIS','FULL_REPORT_ARTIFACT']);
 });
}
