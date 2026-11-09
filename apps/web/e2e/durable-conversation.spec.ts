import {expect,test,type Page} from '@playwright/test';
import {build} from 'esbuild';
import {dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

// Explicit retained-component qualification. This test route is never a product route.
const retainedGenerationPath='/__apbra_test_retained_conversation__';
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



async function signIn(page:Page){
  await page.goto('/api/auth/login?'+new URLSearchParams({identity:'member',return_to:'/'}));
}


async function openStep(page:Page,step:'Goal'|'Information'|'Understanding'|'Confirm'|'Build'|'Report'){
  if(!await page.getByTestId('retained-component-workspace').count()){
    await expect(page.getByLabel('Browse files',{exact:true})).toHaveAttribute('accept','.csv,.xlsx');
    expect((await (await page.request.get('/api/auth/session')).json()).actor.role).toBe('MEMBER');
  }
  await ensureRetainedGeneration(page);
  await page.getByRole('navigation',{name:'Report steps'}).getByRole('button',{name:step,exact:true}).click();
  await expect(page.locator('.wizard-step-heading').getByRole('heading',{name:step,exact:true})).toBeVisible();
}
async function expectSyntheticUploadPolicy(page:Page){await expect(page.getByText('CSV, XLSX data · PNG, JPEG, JPG reference · up to 8 at once')).toBeVisible()}

// Current normal app proof remains distinct from deterministic retained component qualification.
async function expectCurrentMemberRecovery(page:Page,options:{request:string;message?:string;files:string[];excludedFiles?:string[]}){
 const caseId=new URL(page.url()).searchParams.get('case');expect(caseId).toBeTruthy();
 const actual=(await (await page.request.get(`/api/cases/${caseId}`)).json()).case;const title=actual.report_title||actual.current_request.request_text;expect(actual.current_request.request_text).toBe(options.request);
 const acceptance=(await (await page.request.get(`/api/cases/${caseId}/acceptance`)).json());
 if(acceptance.interpretation)expect(acceptance.interpretation.simulation).toBe('LOCAL_DETERMINISTIC_NO_MODEL_CALL');
 const calls:string[]=[];const observe=(request:import('@playwright/test').Request)=>{if(request.method()!=='GET'&&new URL(request.url()).pathname.startsWith('/api/'))calls.push(new URL(request.url()).pathname)};page.on('request',observe);
 try{
  await page.goto('/');await page.locator('button.case-row').filter({has:page.getByText(title,{exact:true})}).first().click();
  const steps=page.getByRole('navigation',{name:'Report steps',exact:true});await steps.getByRole('button',{name:'Supporting information',exact:true}).click();
  await expect(page.getByLabel('Browse files',{exact:true})).toHaveAttribute('accept','.csv,.xlsx');
  if(options.message)await expect(page.getByText(options.message,{exact:true})).toBeVisible();
  for(const file of options.files)await expect(page.locator('.evidence-attached')).toContainText(file);for(const file of options.excludedFiles??[])await expect(page.getByText(file,{exact:true})).toHaveCount(0);
  await page.reload();await page.locator('button.case-row').filter({has:page.getByText(title,{exact:true})}).first().click();await steps.getByRole('button',{name:'Supporting information',exact:true}).click();
  if(options.message)await expect(page.getByText(options.message,{exact:true})).toBeVisible();for(const file of options.files)await expect(page.locator('.evidence-attached')).toContainText(file);for(const file of options.excludedFiles??[])await expect(page.getByText(file,{exact:true})).toHaveCount(0);
  await steps.getByRole('button',{name:'Understanding',exact:true}).click();await expect(page.getByRole('alert')).toContainText('requires an authorized company administrator');
  // Retained deterministic confirmation cannot become qualified AI or native-generation authority.
  await expect(page.getByRole('heading',{name:'Here’s what AI understands',exact:true})).toHaveCount(0);await expect(page.getByText('Your current requirements are confirmed.',{exact:false})).toHaveCount(0);
  await expect(steps.getByRole('button',{name:'Confirm',exact:true})).toBeDisabled();await expect(steps.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();expect(calls).toEqual([]);
 }finally{page.off('request',observe)}
}

function crc32(data:Buffer){let value=0xffffffff;for(const byte of data){value^=byte;for(let bit=0;bit<8;bit+=1)value=(value>>>1)^((value&1)?0xedb88320:0)}return(value^0xffffffff)>>>0}
function storedZip(entries:Array<[string,string]>){const local:Buffer[]=[],central:Buffer[]=[];let offset=0;for(const[name,text]of entries){const filename=Buffer.from(name),data=Buffer.from(text),crc=crc32(data),header=Buffer.alloc(30),directory=Buffer.alloc(46);header.writeUInt32LE(0x04034b50,0);header.writeUInt16LE(20,4);header.writeUInt32LE(crc,14);header.writeUInt32LE(data.length,18);header.writeUInt32LE(data.length,22);header.writeUInt16LE(filename.length,26);directory.writeUInt32LE(0x02014b50,0);directory.writeUInt16LE(20,4);directory.writeUInt16LE(20,6);directory.writeUInt32LE(crc,16);directory.writeUInt32LE(data.length,20);directory.writeUInt32LE(data.length,24);directory.writeUInt16LE(filename.length,28);directory.writeUInt32LE(offset,42);local.push(header,filename,data);central.push(directory,filename);offset+=header.length+filename.length+data.length}const directoryOffset=offset,directoryBytes=Buffer.concat(central),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(entries.length,8);end.writeUInt16LE(entries.length,10);end.writeUInt32LE(directoryBytes.length,12);end.writeUInt32LE(directoryOffset,16);return Buffer.concat([...local,directoryBytes,end])}
function supportedXlsx(){return storedZip([
  ['xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Observations" sheetId="1" r:id="rId1"/></sheets></workbook>'],
  ['xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'],
  ['xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>Clinic</t></is></c><c t="inlineStr"><is><t>WaitMinutes</t></is></c></row><row><c t="inlineStr"><is><t>East</t></is></c><c><v>14</v></c></row></sheetData></worksheet>'],
])}

test('current member recovery + retained deterministic component/backend: CSV conversation, clarification and confirmation survive reload',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Help managers understand the supplied fleet evidence.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  await expect(page.getByText('Your goal is saved. Add supporting information next.')).toBeVisible();

  await openStep(page,'Information');
  const message='Use monthly periods and keep maintenance class available for filtering.';
  await page.getByLabel('Add more requirements').fill(message);
  const savedMessage=page.waitForResponse(response=>response.url().endsWith('/conversation')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Add to report requirements'}).click();
  expect((await savedMessage).status()).toBe(200);
  await expect(page.getByLabel('Add more requirements')).toBeEmpty();
  await expect(page.getByText(message,{exact:true})).toBeVisible();

  await openStep(page,'Information');
  await expectSyntheticUploadPolicy(page);
  await page.getByLabel('Browse files',{exact:true}).setInputFiles([
    {name:'fleet.csv',mimeType:'text/csv',buffer:Buffer.from('Date,Depot,Availability\n2026-01-01,North,0.96\n')},
    {name:'layout.png',mimeType:'image/png',buffer:Buffer.concat([Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]),Buffer.from('synthetic reference')])},
  ]);
  await page.getByRole('button',{name:'Add selected files'}).click();
  await expect(page.locator('.evidence-attached')).toContainText('2 saved');
  await expect(page.getByText(/Data source.*CSV/)).toBeVisible();
  await expect(page.getByText('Saved, visual meaning not interpreted')).toBeVisible();
  await page.getByText('Source details').click();
  await expect(page.getByText(/Depot \(text\).*Availability \(decimal\)/)).toBeVisible();
  await page.route('**/api/cases/*/interpretations',async route=>{
    if(route.request().method()==='POST')await new Promise(resolve=>setTimeout(resolve,300));
    await route.continue();
  });
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await expect(page.getByRole('status').filter({hasText:'Checking your information and preparing the understanding'})).toBeVisible();
  await expect(page.getByText('Optional refinement',{exact:false}).first()).toBeVisible();
  await expect(page.getByRole('status').filter({hasText:'Checking your information and preparing the understanding'})).toHaveCount(0);
  await page.getByRole('button',{name:/Summarise Availability and compare it by Depot/}).click();
  await expect(page.getByText('Review the accepted assumptions, limits and supported scope before proceeding. Optional questions do not prevent acceptance.')).toBeVisible();
  await openStep(page,'Confirm');
  await page.getByRole('button',{name:'Confirm requirements'}).click();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(page,'Information');
  await expect(page.getByText(message,{exact:true})).toBeVisible();
  await expect(page.locator('.evidence-attached')).toContainText('2 saved');
  await expect(page.getByText(/Data source.*CSV/)).toBeVisible();
  await expect(page.getByText('Saved, visual meaning not interpreted')).toBeVisible();
  await openStep(page,'Understanding');
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  await expectCurrentMemberRecovery(page,{request,message,files:['fleet.csv','layout.png']});
  await openStep(page,'Goal');
  await page.getByLabel('Current business request').fill('Compare synthetic fleet availability by depot and maintenance class.');
  await page.getByRole('button',{name:'Save new version'}).click();
  await openStep(page,'Understanding');
  await expect(page.getByText(/Reconfirmation required/)).toBeVisible();
  await expectCurrentMemberRecovery(page,{request:'Compare synthetic fleet availability by depot and maintenance class.',message,files:[],excludedFiles:['fleet.csv','layout.png']});
});

test('current member recovery + retained deterministic component/backend: protected XLSX confirmation',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Compare WaitMinutes by Clinic for appointment operations.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  await openStep(page,'Information');
  await expectSyntheticUploadPolicy(page);
  const workbook=supportedXlsx();
  await page.getByLabel('Browse files',{exact:true}).setInputFiles({name:'appointments.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});
  await page.getByRole('button',{name:'Add selected files'}).click();
  await expect(page.locator('.evidence-attached')).toContainText('1 saved');
  await expect(page.getByText(/Data source.*XLSX/)).toBeVisible();
  await page.getByText('Source details').click();
  await expect(page.getByText(/Clinic \(text\).*WaitMinutes \(integer\)/)).toBeVisible();
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await expect(page.getByText('Review the accepted assumptions, limits and supported scope before proceeding. Optional questions do not prevent acceptance.')).toBeVisible();
  await openStep(page,'Confirm');
  await page.getByRole('button',{name:'Confirm requirements'}).click();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await openStep(page,'Information');
  await expect(page.locator('.evidence-attached')).toContainText('1 saved');
  await expect(page.getByText(/Data source.*XLSX/)).toBeVisible();
  await openStep(page,'Understanding');
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  await expectCurrentMemberRecovery(page,{request,files:['appointments.xlsx']});
});

test('current member AI guard + retained deterministic component/backend: late interpretation cannot repaint a newer request',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill('Compare Availability by Depot.');
  await page.locator('.new-report-card').getByRole('button',{name:'Continue to supporting information',exact:true}).click();
  await openStep(page,'Information');
  await expectSyntheticUploadPolicy(page);
  await page.getByLabel('Browse files',{exact:true}).setInputFiles({
    name:'availability.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Depot,Availability\nNorth,0.96\n'),
  });
  await page.getByRole('button',{name:'Add selected files'}).click();

  await expectCurrentMemberRecovery(page,{request:'Compare Availability by Depot.',files:['availability.csv']});

  let release!:()=>void,observed!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve});
  const intercepted=new Promise<void>(resolve=>{observed=resolve});
  await page.route('**/api/cases/*/interpretations',async route=>{
    observed();
    await held;
    await route.continue();
  });
  await openStep(page,'Understanding');
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await intercepted;
  await openStep(page,'Goal');
  await page.getByLabel('Current business request').fill(
    'Compare the revised maintenance schedule by facility.',
  );
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Your updated request was saved.')).toBeVisible();
  release();
  await openStep(page,'Understanding');
  await expect(page.getByText('This local preview uses deterministic rules to propose an understanding; no AI model was called.')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Review my requirements'})).toBeDisabled();
  await expectCurrentMemberRecovery(page,{request:'Compare the revised maintenance schedule by facility.',files:[],excludedFiles:['availability.csv']});
});
