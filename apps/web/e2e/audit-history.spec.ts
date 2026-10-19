import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page,identity:'owner'|'member'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
  await expect(page.getByRole('button',{name:/^Account menu for /})).toBeVisible();
  if((page.viewportSize()?.width??1280)<=768)await page.getByRole('button',{name:'Open workspace navigation',exact:true}).click();
}

test('owner can read a real retained support occurrence and audit history through administration',async({page})=>{
  await signIn(page,'owner');
  const session=await (await page.request.get('/api/auth/session')).json();
  const headers={'X-Expected-Membership-Id':session.actor.membership_id};
  const failure=await page.request.get('/api/tenant-settings/errors?limit=PRIVATE-SYNTHETIC-QUERY-CANARY',{headers});
  expect(failure.status()).toBe(422);
  const {error}=await failure.json();expect(error.recorded).toBe(true);
  await page.getByRole('button',{name:'Administration',exact:true}).click();
  await page.getByRole('button',{name:'Audit',exact:true}).click();
  await expect(page.getByRole('region',{name:'Tenant audit history'})).toBeVisible();
  await page.getByRole('button',{name:'Errors and processing',exact:true}).click();
  const history=page.getByRole('region',{name:'Tenant error history'});
  await history.getByRole('button',{name:`View occurrence ${error.support_reference}`,exact:true}).click();
  const detail=page.getByRole('dialog',{name:'History occurrence details'});
  await expect(detail).toContainText(error.support_reference);
  await expect(detail).toContainText('Correlation reference');
  await expect(detail).not.toContainText('PRIVATE-SYNTHETIC-QUERY-CANARY');
  await detail.getByRole('button',{name:'Close details'}).click();
  await expect(detail).toHaveCount(0);
});

test('changing a filter invalidates a delayed history response before the newer result renders',async({page})=>{
  await signIn(page,'owner');
  const session=await (await page.request.get('/api/auth/session')).json();
  const oldId='11111111-1111-4111-8111-111111111111',newId='22222222-2222-4222-8222-222222222222';
  let release!:()=>void,received!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve}),ready=new Promise<void>(resolve=>{received=resolve});
  const item=(id:string)=>({id,support_reference:id,occurred_at:'2026-10-19T00:00:00Z',module:'API',operation:'NEW',outcome:'FAILED',actor_id:null,target_type:null,target_id:null,category:'INTERNAL',message:'Synthetic safe failure',correlation_id:id,case_id:null,source_kind:null,source_id:null});
  await page.route('**/api/tenant-settings/errors*',async route=>{
    expect(route.request().headers()['x-expected-membership-id']).toBe(session.actor.membership_id);
    const first=!new URL(route.request().url()).searchParams.has('operation');
    if(first){received();await held}
    await route.fulfill({json:{company_id:session.actor.company_id,items:[item(first?oldId:newId)],next_cursor:null}});
  });
  await page.getByRole('button',{name:'Administration',exact:true}).click();
  await page.getByRole('button',{name:'Errors and processing',exact:true}).click();
  await ready;
  const history=page.getByRole('region',{name:'Tenant error history'});
  await history.getByLabel('Operation',{exact:true}).fill('NEW');
  await history.getByRole('button',{name:'Search history',exact:true}).click();
  await expect(history.getByRole('button',{name:`View occurrence ${newId}`,exact:true})).toBeVisible();
  const replied=page.waitForResponse(response=>response.url().endsWith('/api/tenant-settings/errors'));
  release();await (await replied).finished();
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
  await expect(history.getByRole('button',{name:`View occurrence ${oldId}`,exact:true})).toHaveCount(0);
  await expect(history.getByRole('button',{name:`View occurrence ${newId}`,exact:true})).toBeVisible();
});

test('ordinary members have neither administration controls nor tenant history authority',async({page})=>{
  await signIn(page,'member');
  await expect(page.getByRole('button',{name:'Administration',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Errors and processing',exact:true})).toHaveCount(0);
  const session=await (await page.request.get('/api/auth/session')).json();
  for(const path of ['audit-events','errors']){
    const response=await page.request.get('/api/tenant-settings/'+path,{headers:{'X-Expected-Membership-Id':session.actor.membership_id}});
    expect(response.status()).toBe(403);
  }
});
