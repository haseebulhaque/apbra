import {expect,test,type Page} from '@playwright/test';
import {build} from 'esbuild';
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
