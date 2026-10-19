import {expect,test,type Page} from '@playwright/test';

async function openNew(page:Page,identity:'owner'|'member'){
 await page.goto('/');await page.getByText('Local development identities').click();
 await page.getByRole('link',{name:identity,exact:true}).click();
 await expect(page.getByRole('button',{name:/^Account menu for /})).toBeVisible();
 await page.getByRole('button',{name:'Create report',exact:true}).first().click();
 const goal='Synthetic opaque output '+identity+' '+Date.now();
 await page.getByLabel('Your reporting goal').fill(goal);
 await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
 await expect(page.getByText('Report request created and saved.')).toBeVisible();
 return goal;
}

test('member saves original opaque ZIP bytes and protected download survives reopen',async({page,request})=>{
 const goal=await openNew(page,'member');
 await expect(page.getByRole('region',{name:'Saved Azure information'})).toHaveCount(0);
 const original=Buffer.from('UEsDBBQAAAAAAFVuU13tHB4kHAAAABwAAAAQAAAALi4vc3ludGhldGljLnR4dFNZTlRIRVRJQy1QUkVTRVJWRS1VTkNIQU5HRURQSwECFAMUAAAAAABVblNd7RweJBwAAAAcAAAAEAAAAAAAAAAAAAAAgAEAAAAALi4vc3ludGhldGljLnR4dFBLBQYAAAAAAQABAD4AAABKAAAAAAA=','base64');
 await page.getByLabel('Generated output file').setInputFiles({name:'Synthetic.zip',mimeType:'application/zip',buffer:original});
 await page.getByRole('button',{name:'Save generated file',exact:true}).click();
 const link=page.getByRole('link',{name:'Synthetic.zip',exact:true});await expect(link).toBeVisible();
 const path=await link.getAttribute('href');expect(path).toMatch(/^\/api\/cases\/[^/]+\/outputs\/[^/]+\/download$/);
 const saved=await page.request.get(path!);expect(saved.status()).toBe(200);expect(await saved.body()).toEqual(original);
 expect(saved.headers()['cache-control']).toBe('no-store');expect(saved.headers()['content-disposition']).toContain('attachment');
 expect((await request.get(path!)).status()).toBe(401);
 await page.reload();await page.getByRole('button',{name:new RegExp(goal)}).first().click();
 await page.getByRole('button',{name:'Show saved output files',exact:true}).click();await expect(link).toBeVisible();
 expect(await link.getAttribute('href')).toBe(path);
 await expect(page.getByRole('heading',{name:'ReportDesign compiler fallback',exact:true})).toBeVisible();
});

test('owner passive native inspection cannot acquire a send grant',async({page})=>{
 const sends:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/native-response-checks'))sends.push(r.url())});
 await openNew(page,'owner');
 await expect(page.getByRole('region',{name:'Saved Azure information'})).toBeVisible();
 const response=page.waitForResponse(r=>r.url().includes('/native-response-input'));
 await page.getByRole('button',{name:'Check agent connection and input',exact:true}).click();await response;
 await expect(page.getByRole('button',{name:'Send once to agent',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Show saved answers',exact:true}).click();
 await expect(page.getByText('No saved Azure responses.',{exact:true})).toBeVisible();
 expect(sends).toEqual([]);
});

test('same-report navigation retains a queued generated output without saving',async({page})=>{
 await openNew(page,'member');
 const saves:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/outputs'))saves.push(r.url())});
 await page.getByLabel('Generated output file').setInputFiles({name:'Queued-original.bin',mimeType:'application/octet-stream',buffer:Buffer.from('SYNTHETIC-NOT-SENT')});
 await page.getByRole('navigation',{name:'Workspace sections'}).getByRole('button',{name:'Home',exact:true}).click();
 await expect(page.getByLabel('Generated output file')).toBeHidden();
 await page.getByRole('button',{name:'Current report',exact:true}).click();
 await expect(page.getByLabel('Generated output file')).toBeVisible();
 expect(await page.getByLabel('Generated output file').evaluate((element:HTMLInputElement)=>element.files?.[0]?.name)).toBe('Queued-original.bin');
 expect(saves).toEqual([]);
});
