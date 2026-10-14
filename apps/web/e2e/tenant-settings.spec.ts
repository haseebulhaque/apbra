import {defaultTenantSettings} from '../src/tenant';
import {expect,test,type Page,type Route} from '@playwright/test';

async function setAppearance(page:Page,mode:string){const button=page.getByRole('button',{name:mode==='system'?'Use system appearance':mode==='light'?'Light appearance':'Dark appearance',exact:true});if(!await button.isVisible())await page.getByRole('button',{name:/^Account menu for /}).click();await button.click();const menu=page.getByRole('menu',{name:'Account',exact:true});if(await menu.isVisible()){await page.keyboard.press('Escape');await expect(menu).toHaveCount(0)}}

async function signOut(page:Page){
  const account=page.getByRole('button',{name:/^Account menu for /});
  await expect(account.or(page.getByRole('button',{name:'Sign out',exact:true}))).toBeVisible();
  if(await account.count()){await account.click();await page.getByRole('menuitem',{name:'Sign out',exact:true}).click()}
  else await page.getByRole('button',{name:'Sign out',exact:true}).click();
}

async function signIn(page:Page,identity:'owner'|'member'|'foreign'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
  const navigation=page.getByRole('button',{name:'Open workspace navigation',exact:true});
  if((page.viewportSize()?.width??1280)<=768){await expect(navigation).toBeVisible();await navigation.click();}
}

test('business members consume branding without settings navigation, direct pages or read/write authority',async({page})=>{
  await signIn(page,'owner');
  const before=await (await page.request.get('/api/tenant-settings')).json();
  const history=await (await page.request.get('/api/tenant-settings/history')).json();
  await signOut(page);await signIn(page,'member');
  const state=await (await page.request.get('/api/auth/session')).json();
  const read=await page.request.get('/api/workspace/branding'),branding=await read.json();
  expect(read.status()).toBe(200);expect(read.headers()['cache-control']).toBe('no-store');
  expect(branding).toEqual({version:before.version,primary:before.settings.generation_policy.branding.primary,accent:before.settings.generation_policy.branding.accent});
  await expect.poll(()=>page.locator('.private-workspace').evaluate(root=>(root as HTMLElement).style.getPropertyValue('--tenant-primary-original'))).toBe(branding.primary.toLowerCase());
  for(const path of ['/tenant-settings','/administration','/?view=admin','/#tenant-settings']){
    await page.goto(path);await expect(page.getByRole('button',{name:/^Account menu for /})).toBeVisible();
    await expect(page.getByRole('button',{name:'Administration',exact:true})).toHaveCount(0);
    await expect(page.getByLabel('Tenant administration')).toHaveCount(0);
    await expect(page.getByLabel('Primary colour',{exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:/Review branding changes/})).toHaveCount(0);
  }
  for(const path of ['/api/tenant-settings','/api/tenant-settings/history','/api/tenant-settings/qualified-profiles'])expect((await page.request.get(path)).status()).toBe(403);
  const headers={'X-CSRF-Token':state.csrf_token};
  expect((await page.request.put('/api/tenant-settings',{headers,data:{expected_version:before.version,settings:before.settings}})).status()).toBe(403);
  expect((await page.request.patch('/api/tenant-settings/sections/branding_organisation',{headers,data:{expected_version:before.version,changes:{'generation_policy.branding':{...before.settings.generation_policy.branding,primary:'#FF0000'}}}})).status()).toBe(403);
  for(const method of ['POST','PUT','PATCH','DELETE'])expect((await page.request.fetch('/api/workspace/branding',{method})).status()).toBe(405);
  for(const mode of ['light','dark','system']){await setAppearance(page,mode);await expect.poll(()=>page.locator('.private-workspace').evaluate(root=>(root as HTMLElement).style.getPropertyValue('--tenant-primary-original'))).toBe(branding.primary.toLowerCase());}
  await signOut(page);await signIn(page,'owner');
  expect(await (await page.request.get('/api/tenant-settings')).json()).toEqual(before);
  expect(await (await page.request.get('/api/tenant-settings/history')).json()).toEqual(history);
});

test('an older branding read cannot replace a newer effective admin version',async({page})=>{
  let release!:()=>void,received!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve}),ready=new Promise<void>(resolve=>{received=resolve});
  await page.route('**/api/workspace/branding',async route=>{const response=await route.fetch();received();await held;await route.fulfill({response})});
  await page.route('**/api/tenant-settings',async route=>{const response=await route.fetch(),value=await response.json();value.version+=1;value.settings.generation_policy.branding={...value.settings.generation_policy.branding,primary:'#654321',accent:'#ABCDEF'};await route.fulfill({response,json:value})});
  await signIn(page,'owner');await ready;
  const before=await (await page.request.get('/api/tenant-settings')).json();
  await page.getByRole('button',{name:'Administration',exact:true}).click();
  const original=()=>page.locator('.private-workspace').evaluate(root=>(root as HTMLElement).style.getPropertyValue('--tenant-primary-original'));
  await expect.poll(original).toBe('#654321');
  const replied=page.waitForResponse(response=>response.url().endsWith('/api/workspace/branding')&&response.status()===200);
  release();await (await replied).finished();
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
  expect(await original()).toBe('#654321');
  expect(await (await page.request.get('/api/tenant-settings')).json()).toEqual(before);
});

test('owner edits and restores a versioned clarification policy without exposing a credential',async({page})=>{
  await signIn(page,'owner');
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.getByRole('heading',{name:'Tenant Settings'})).toBeVisible();
  await admin.getByRole('button',{name:/AI & models/}).click();
  await expect(admin.getByText('Not configured')).toBeVisible();
  await expect(admin.getByText(/Current effective version 1 · Validation PASS · Applies to this company’s new and revalidated operations/)).toBeVisible();
  await expect(admin.getByRole('button',{name:/Reveal|Show key|Copy existing key/i})).toHaveCount(0);
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  const turns=admin.getByLabel('Turns per cycle',{exact:false});
  const original=Number(await turns.inputValue());
  await turns.fill(String(original+1));
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(review).toContainText('max_clarification_rounds_per_cycle');
  await expect(review).toContainText('future clarification');
  await expect((await page.request.get('/api/tenant-settings')).json()).resolves.toMatchObject({version:1});
  await review.getByRole('button',{name:'Cancel'}).click();
  await expect((await page.request.get('/api/tenant-settings')).json()).resolves.toMatchObject({version:1});
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  await review.getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByText(/settings version 2 is now effective/i)).toBeVisible();
  await admin.getByText('Settings history').click();
  await admin.getByRole('button',{name:'Review restore'}).click();
  const dialog=page.getByRole('dialog',{name:'Restore tenant settings'});
  await expect(dialog).toContainText('creates a new effective version');
  await dialog.getByRole('button',{name:'Restore as new version'}).click();
  await expect(admin.getByText(/Version 3 is now effective, restored from version 1/)).toBeVisible();
  await expect(turns).toHaveValue(String(original));
  await page.reload();
  await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.locator('.status-badge',{hasText:/^Version 3$/})).toBeVisible();
});

test('ordinary member cannot see owner settings and narrow admin form does not overflow',async({page})=>{
  await signIn(page,'member');
  await expect(page.getByLabel('Tenant administration')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Administration'})).toHaveCount(0);
  await page.getByRole('button',{name:'My profile'}).click();
  await expect(page.getByRole('heading',{name:'My profile'})).toBeVisible();
  await signOut(page);
  await signIn(page,'owner');
  await page.setViewportSize({width:375,height:812});
  await page.getByRole('button',{name:'Open workspace navigation',exact:true}).click();
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeVisible();
  const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth}));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
});

test('high-impact changes remain in separate section drafts and each review excludes unrelated fields',async({page})=>{
  await signIn(page,'owner');
  await page.setViewportSize({width:375,height:812});
  await page.getByRole('button',{name:'Open workspace navigation',exact:true}).click();
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  const before=(await (await page.request.get('/api/tenant-settings')).json()).version;
  await admin.getByRole('combobox').selectOption('synthetic-e2e-profile');
  await admin.getByLabel('Calls per operation',{exact:false}).fill('1');
  await admin.getByLabel('Retry limit',{exact:false}).fill('0');
  await admin.getByRole('checkbox',{name:/Expert assistance/}).uncheck();
  await admin.getByRole('checkbox',{name:/Automatic intelligent generation/}).check();
  await admin.getByRole('button',{name:/Responses & report standards/}).click();
  await admin.getByLabel('Visuals per page',{exact:false}).fill('5');
  await admin.getByRole('textbox',{name:'Report naming',exact:true}).fill('Synthetic test naming convention');
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  await admin.getByLabel('Turns overall',{exact:false}).fill('9');
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(review).toContainText('max_clarification_rounds_overall');
  for(const unrelated of ['provider_profile','automatic_generation_enabled','generation_policy.governance.maxVisualsPerPage','conventions.report_naming'])await expect(review).not.toContainText(unrelated);
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(before);
  await review.getByRole('button',{name:'Cancel'}).click();
  await admin.getByRole('button',{name:/AI & models/}).click();
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  await expect(review).toContainText('provider_profile');
  await expect(review).toContainText('automatic_generation_enabled');
  await expect(review).toContainText('protected credential');
  await expect(review).not.toContainText('max_clarification_rounds_overall');
  const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth}));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
  await review.getByRole('button',{name:'Cancel'}).click();
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(before);
});

test('mobile navigation preserves section drafts and a pending save cannot be repeated',async({page})=>{
  await page.setViewportSize({width:320,height:812});
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const admin=page.getByLabel('Tenant administration');
  const before=await (await page.request.get('/api/tenant-settings')).json();
  const expert=admin.getByRole('checkbox',{name:/Expert assistance/});
  if(before.settings.expert_escalation_enabled)await expert.uncheck();else await expert.check();
  const menu=page.locator('.workspace-menu-toggle');
  for(let n=0;n<3;n++){await menu.click();await page.keyboard.press('Escape');await expect(menu).toBeFocused();}
  await expect(expert).toHaveJSProperty('checked',!before.settings.expert_escalation_enabled);
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  const lifetime=admin.getByLabel('Invitation lifetime (days)');
  await lifetime.fill(String(before.settings.invitation_ttl_days+1));
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(review).toContainText('invitation_ttl_days');
  await expect(review).not.toContainText('expert_escalation_enabled');
  let attempts=0,release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve});
  await page.route('**/api/tenant-settings/sections/budgets_limits',async route=>{attempts++;await gate;await route.continue()});
  await review.getByRole('button',{name:'Confirm and save new version'}).click();
  const saving=review.getByRole('button',{name:'Saving…'});
  await expect(saving).toBeDisabled();await expect(admin).toHaveAttribute('aria-busy','true');
  // Native disabled buttons must reject repeated activation while the request is held.
  await saving.evaluate(button=>{(button as HTMLButtonElement).click();(button as HTMLButtonElement).click()});
  await expect.poll(()=>attempts).toBe(1);release();
  await expect(admin.getByText(`Tenant settings version ${before.version+1} is now effective.`,{exact:false})).toBeVisible();
  expect(attempts).toBe(1);
  const saved=await (await page.request.get('/api/tenant-settings')).json();
  expect(saved.version).toBe(before.version+1);
  expect(saved.settings.invitation_ttl_days).toBe(before.settings.invitation_ttl_days+1);
  expect(saved.settings.expert_escalation_enabled).toBe(before.settings.expert_escalation_enabled);
  await admin.getByRole('button',{name:/AI & models/}).click();
  await expect(admin.getByRole('checkbox',{name:/Expert assistance/})).toHaveJSProperty('checked',!before.settings.expert_escalation_enabled);
  await menu.click();await page.getByRole('button',{name:'Home'}).click();
  await menu.click();await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.getByRole('checkbox',{name:/Expert assistance/})).toHaveJSProperty('checked',!before.settings.expert_escalation_enabled);
  await admin.getByRole('button',{name:'Cancel section changes'}).click();
  await expect(admin.getByRole('checkbox',{name:/Expert assistance/})).toHaveJSProperty('checked',before.settings.expert_escalation_enabled);
});

test('stale section saves fail closed and preserve the draft while loading current policy',async({page,context})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const original=await (await page.request.get('/api/tenant-settings')).json();
  const first=page.getByLabel('Tenant administration');
  await first.getByRole('button',{name:/Budget & limits/}).click();
  await first.getByLabel('Invitation lifetime (days)').fill(String(original.settings.invitation_ttl_days+1));

  const secondPage=await context.newPage();
  await secondPage.goto('/');
  await secondPage.getByRole('button',{name:'Administration'}).click();
  const second=secondPage.getByLabel('Tenant administration');
  await second.getByRole('button',{name:/Budget & limits/}).click();
  const files=second.getByLabel('Files per selection');
  await files.fill(String(original.settings.upload_policy.max_files_per_selection+1));
  await second.getByRole('button',{name:/Review .* changes/}).click();
  await secondPage.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(second.getByText(`Tenant settings version ${original.version+1} is now effective.`,{exact:false})).toBeVisible();

  await first.getByRole('button',{name:/Review .* changes/}).click();
  await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(first.getByRole('alert')).toContainText('rejected this stale version');
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(original.version+1);
  await first.getByRole('button',{name:'Load latest settings and keep my draft'}).click();
  await expect(first.getByText('Your unsaved draft was kept.',{exact:false})).toBeVisible();
  await expect(first.getByLabel('Invitation lifetime (days)')).toHaveValue(String(original.settings.invitation_ttl_days+1));
  await expect(first.getByLabel('Files per selection')).toHaveValue(String(original.settings.upload_policy.max_files_per_selection+1));
  await first.getByRole('button',{name:/Review .* changes/}).click();
  await expect(page.getByRole('dialog',{name:'Review tenant settings changes'})).toContainText('invitation_ttl_days');
  await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Cancel'}).click();
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(original.version+1);
  await secondPage.close();
});

test('a committed section save stays successful when history refresh fails',async({page})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const admin=page.getByLabel('Tenant administration');
  const before=await (await page.request.get('/api/tenant-settings')).json();
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  await admin.getByLabel('Invitation lifetime (days)').fill(String(before.settings.invitation_ttl_days+1));
  await page.route('**/api/tenant-settings/history',route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":{"code":"TEMPORARY","message":"Synthetic history failure"}}'}));
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByText(`Tenant settings version ${before.version+1} is now effective.`,{exact:false})).toBeVisible();
  await expect(admin.getByText('Settings history could not be refreshed',{exact:false})).toBeVisible();
  await expect(page.getByRole('dialog',{name:'Review tenant settings changes'})).toHaveCount(0);
  await expect(admin.getByLabel('Invitation lifetime (days)')).toHaveValue(String(before.settings.invitation_ttl_days+1));
  const after=await (await page.request.get('/api/tenant-settings')).json();
  expect(after.version).toBe(before.version+1);
  expect(after.settings.invitation_ttl_days).toBe(before.settings.invitation_ttl_days+1);
});

test('lost section-save response reconciles current policy without replaying the change',async({page})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const admin=page.getByLabel('Tenant administration');
  const before=await (await page.request.get('/api/tenant-settings')).json();
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  await admin.getByLabel('Invitation lifetime (days)').fill(String(before.settings.invitation_ttl_days+1));
  let attempts=0;
  await page.route('**/api/tenant-settings/sections/budgets_limits',async route=>{
    attempts+=1;
    const committed=await route.fetch();
    expect(committed.status()).toBe(200);
    await route.fulfill({status:503,contentType:'application/json',body:'{"error":{"code":"TEMPORARY","message":"Synthetic response lost after commit"}}'});
  });
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByText('The save response could not be confirmed.',{exact:false})).toBeVisible();
  await expect(admin.getByText('The requested values are now effective',{exact:false})).toBeVisible();
  await expect(page.getByRole('dialog',{name:'Review tenant settings changes'})).toHaveCount(0);
  expect(attempts).toBe(1);
  const after=await (await page.request.get('/api/tenant-settings')).json();
  expect(after.version).toBe(before.version+1);
  expect(after.settings.invitation_ttl_days).toBe(before.settings.invitation_ttl_days+1);
});

test('unknown save outcome blocks all settings writes until an authoritative read succeeds',async({page})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const admin=page.getByLabel('Tenant administration');
  const before=await (await page.request.get('/api/tenant-settings')).json();
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  await admin.getByLabel('Invitation lifetime (days)').fill(String(before.settings.invitation_ttl_days+1));
  let writes=0;
  await page.route('**/api/tenant-settings/sections/budgets_limits',async route=>{
    writes+=1;
    const committed=await route.fetch();
    expect(committed.status()).toBe(200);
    await route.fulfill({status:503,contentType:'application/json',body:'{"error":{"code":"TEMPORARY","message":"Synthetic response lost after commit"}}'});
  });
  await page.route('**/api/tenant-settings',route=>route.request().method()==='GET'?route.fulfill({status:503,contentType:'application/json',body:'{"error":{"code":"TEMPORARY","message":"Synthetic current read unavailable"}}'}):route.continue());
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByRole('alert')).toContainText('Settings writes are paused');
  await expect(page.getByRole('dialog',{name:'Review tenant settings changes'})).toHaveCount(0);
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeDisabled();
  await expect(admin.getByLabel('Invitation lifetime (days)')).toHaveValue(String(before.settings.invitation_ttl_days+1));
  expect(writes).toBe(1);
  await admin.getByRole('button',{name:'Check current settings before another save'}).click();
  await expect(admin.getByRole('alert')).toContainText('Settings writes remain paused');
  expect(writes).toBe(1);
  await page.unroute('**/api/tenant-settings');
  await admin.getByRole('button',{name:'Check current settings before another save'}).click();
  await expect(admin.getByText(`Current effective settings version ${before.version+1} loaded.`,{exact:false})).toBeVisible();
  await expect(admin.getByRole('button',{name:'Check current settings before another save'})).toHaveCount(0);
  expect(writes).toBe(1);
  const after=await (await page.request.get('/api/tenant-settings')).json();
  expect(after.version).toBe(before.version+1);
  expect(after.settings.invitation_ttl_days).toBe(before.settings.invitation_ttl_days+1);
});

test('owner configures and rotates a synthetic protected credential without revealing it',async({page})=>{
  await signIn(page,'owner');
  const initialVersion=(await (await page.request.get('/api/tenant-settings')).json()).version;
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  await admin.getByRole('combobox').selectOption('synthetic-e2e-profile');
  await expect(admin.getByText(/Qualified deployment: synthetic-e2e-model/)).toBeVisible();
  await expect(admin.getByLabel('Profile identity')).toHaveCount(0);
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(review).toContainText('provider_profile');
  await expect(review).toContainText('new protected credential');
  await review.getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByText(`Tenant settings version ${initialVersion+1} is now effective.`,{exact:false})).toBeVisible();
  await admin.getByRole('button',{name:'Configure credential'}).click();
  const dialog=page.getByRole('dialog',{name:'Replace provider credential'});
  await dialog.getByLabel('New credential').fill('synthetic-e2e-secret-first');
  await dialog.getByRole('button',{name:'Replace credential'}).click();
  await expect(admin.getByText('Configured · ***')).toBeVisible();
  await expect(admin.getByRole('button',{name:'Replace / rotate credential'})).toBeVisible();
  await expect(page.locator('body')).not.toContainText('synthetic-e2e-secret-first');
  const beforeRotation=await (await page.request.get('/api/tenant-settings')).json();
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  await admin.getByLabel('Invitation lifetime (days)').fill(String(beforeRotation.settings.invitation_ttl_days+1));
  await admin.getByRole('button',{name:/AI & models/}).click();
  await admin.getByRole('button',{name:'Replace / rotate credential'}).click();
  await dialog.getByLabel('New credential').fill('synthetic-e2e-secret-second');
  await dialog.getByRole('button',{name:'Replace credential'}).click();
  await expect(admin.getByText(/Protected credential replaced in settings version/)).toBeVisible();
  await expect(page.locator('body')).not.toContainText('synthetic-e2e-secret-second');
  await admin.getByRole('button',{name:/Budget & limits/}).click();
  await expect(admin.getByLabel('Invitation lifetime (days)')).toHaveValue(String(beforeRotation.settings.invitation_ttl_days+1));
  await expect(admin.getByText('Unsaved changes',{exact:true})).toBeVisible();
  expect((await (await page.request.get('/api/tenant-settings')).json()).settings.invitation_ttl_days).toBe(beforeRotation.settings.invitation_ttl_days);
  await admin.getByRole('button',{name:/AI & models/}).click();
  const current=await (await page.request.get('/api/tenant-settings')).text();
  const history=await (await page.request.get('/api/tenant-settings/history')).text();
  for(const response of [current,history]){
    expect(response).not.toContain('synthetic-e2e-secret-first');
    expect(response).not.toContain('synthetic-e2e-secret-second');
  }
  expect(JSON.parse(current).credential.maskedValue).toBe('***');
  await admin.getByLabel('Calls per operation',{exact:false}).fill('1');
  await admin.getByLabel('Retry limit',{exact:false}).fill('0');
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  const budgetReview=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(budgetReview).toContainText('provider_profile.max_calls_per_operation');
  await expect(budgetReview).toContainText('provider_profile.retry_limit');
  await expect(budgetReview).toContainText('model call, retry, size or time budget');
  await budgetReview.getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByText('Configured · ***')).toBeVisible();
});

test('owner settings fit desktop, laptop, tablet and narrow mobile viewports',async({page})=>{
  await signIn(page,'owner');
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  for(const width of [1440,1024,768,375]){
    await page.setViewportSize({width,height:812});
    await expect(admin.getByRole('heading',{name:'Tenant Settings'})).toBeVisible();
    const extent=await page.evaluate(()=>document.documentElement.scrollWidth);
    expect(extent,`horizontal overflow at ${width}px`).toBeLessThanOrEqual(width);
  }
});

test('foreign owner sees only their own settings and member has no settings route',async({page})=>{
  await signIn(page,'owner');
  const owner=await (await page.request.get('/api/tenant-settings')).json();
  await signOut(page);
  await signIn(page,'foreign');
  const foreign=await (await page.request.get('/api/tenant-settings')).json();
  expect(foreign.id).not.toBe(owner.id);
  expect(foreign.settings.provider_profile).toBeNull();
  await signOut(page);
  await signIn(page,'member');
  await expect(page.getByLabel('Tenant administration')).toHaveCount(0);
  expect((await page.request.get('/api/tenant-settings')).status()).toBe(403);
  expect((await page.request.get('/api/tenant-settings/history')).status()).toBe(403);
  expect((await page.request.get('/api/tenant-settings/qualified-profiles')).status()).toBe(403);
});


test('settings sections expose keyboard navigation, field help and independent unsaved indicators',async({page})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const admin=page.getByLabel('Tenant administration');
  const navigation=admin.getByRole('navigation',{name:'Tenant Settings sections'});
  const aiSection=navigation.getByRole('button',{name:'AI & models',exact:true});
  await expect(aiSection).toHaveAttribute('aria-current','page');
  await expect(admin.getByRole('heading',{name:'AI & models',exact:true})).toBeVisible();
  await expect(admin.getByRole('combobox',{name:'Qualified model profile'})).toBeVisible();
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeDisabled();
  const expert=admin.getByRole('checkbox',{name:'Expert assistance',exact:true});
  await expert.setChecked(!await expert.isChecked());
  await expect(navigation.getByRole('button',{name:'AI & models · Unsaved',exact:true})).toBeVisible();
  const limits=navigation.getByRole('button',{name:'Budget & limits',exact:true});
  await limits.focus();
  await page.keyboard.press('Enter');
  await expect(limits).toHaveAttribute('aria-current','page');
  await expect(admin.getByRole('heading',{name:'Budget & limits',exact:true})).toBeVisible();
  await expect(admin.getByRole('checkbox',{name:'Expert assistance',exact:true})).toBeHidden();
  const turns=admin.getByRole('spinbutton',{name:'Turns per cycle',exact:true});
  await expect(turns).toHaveAccessibleDescription(/Affects future clarification turns, not saved history/);
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeDisabled();
  await navigation.getByRole('button',{name:'AI & models · Unsaved',exact:true}).click();
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeEnabled();
  await admin.getByRole('button',{name:'Cancel section changes'}).click();
  await expect(navigation.getByRole('button',{name:'AI & models',exact:true})).toBeVisible();
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeDisabled();
});


test('settings dialogs isolate keyboard focus, dismiss safely and restore the opener',async({page})=>{
  await signIn(page,'owner');await page.getByRole('button',{name:'Administration',exact:true}).click();
  const admin=page.getByLabel('Tenant administration');let before=(await (await page.request.get('/api/tenant-settings')).json()).version;
  const exercise=async(opener:ReturnType<Page['getByRole']>,name:string)=>{
    await opener.focus();await page.keyboard.press('Enter');
    const dialog=page.getByRole('dialog',{name,exact:true});await expect(dialog).toBeVisible();await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeFocused();
    for(let i=0;i<8;i++){await page.keyboard.press('Tab');expect(await dialog.evaluate(element=>element.contains(document.activeElement))).toBe(true)}
    for(let i=0;i<8;i++){await page.keyboard.press('Shift+Tab');expect(await dialog.evaluate(element=>element.contains(document.activeElement))).toBe(true)}
    await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(opener).toBeFocused();
    expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(before);
  };
  // Profile selection enables the replacement disclosure; no credential is sent.
  await admin.getByRole('combobox').selectOption('synthetic-e2e-profile');
  await exercise(admin.getByRole('button',{name:/^(Configure credential|Replace \/ rotate credential)$/}),'Replace provider credential');
  await admin.getByRole('button',{name:/Budget & limits/}).click();const turns=admin.getByLabel('Turns per cycle',{exact:false});await turns.fill(String(Number(await turns.inputValue())+1));
  await exercise(admin.getByRole('button',{name:/Review .* changes/}),'Review tenant settings changes');
  // Create a synthetic second version so a historical restore action exists.
  await admin.getByRole('button',{name:/Review .* changes/}).click();await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version',exact:true}).click();await expect(admin.getByText(new RegExp(`settings version ${before+1} is now effective`,'i'))).toBeVisible();before=(await (await page.request.get('/api/tenant-settings')).json()).version;
  await admin.getByText('Settings history',{exact:true}).click();
  await exercise(admin.getByRole('button',{name:'Review restore',exact:true}).first(),'Restore tenant settings');
});

// Synthetic browser qualification-list fixture; no Foundry service is invoked.
test('a Foundry profile draft uses Entra disclosure and cannot reuse the legacy credential indicator',async({page})=>{
  await page.route('**/api/tenant-settings/qualified-profiles',async route=>{
    const response=await route.fetch();const body=await response.json();
    const source=body.items[0];
    const foundry={...source,profile_id:'synthetic-foundry-profile',protocol:'FOUNDRY_AGENT_RESPONSES',endpoint:'https://provider.invalid/api/projects/project/agents/agent/endpoint/protocols/openai/responses',api_version:'v1',model_or_deployment:'synthetic-agent',configuration_id:'synthetic-foundry-configuration'};
    await route.fulfill({response,json:{items:[...body.items,foundry]}});
  });
  await signIn(page,'owner');await page.getByRole('button',{name:'Administration',exact:true}).click();
  const admin=page.getByLabel('Tenant administration');
  await admin.getByRole('combobox',{name:'Qualified model profile'}).selectOption('synthetic-foundry-profile');
  await expect(admin.getByText('Foundry agent · Microsoft Entra server identity',{exact:true})).toBeVisible();
  await expect(admin.getByText(/Server authentication capability is unavailable/)).toBeVisible();
  await expect(admin.getByText(/agent uses its stored instructions and knowledge tools/)).toBeVisible();
  await expect(admin.getByRole('button',{name:/^(Configure credential|Replace \/ rotate credential)$/})).toHaveCount(0);
  await admin.getByRole('button',{name:'Cancel section changes'}).click();
  await expect(admin.getByRole('combobox',{name:'Qualified model profile'})).not.toHaveValue('synthetic-foundry-profile');
});

async function syntheticSettingsDialogFixture(page:Page){
 const profile={profile_id:'synthetic',protocol:'OPENAI_CHAT_COMPATIBLE',endpoint:'https://example.invalid',model_or_deployment:'synthetic',api_version:'v1',region:'synthetic',prompt_version:'v1',configuration_id:'synthetic',capabilities:{structured_output:true,vision:false},max_calls_per_operation:1,max_input_characters:1000,max_output_tokens:128,time_budget_seconds:30,request_timeout_seconds:10,retry_limit:0};
 const settings={clarification_enabled:false,max_clarification_rounds_per_cycle:3,max_clarification_rounds_overall:12,expert_escalation_enabled:true,automatic_generation_enabled:false,invitation_ttl_days:7,upload_policy:{data_extensions:['CSV'],reference_extensions:['PNG'],max_file_bytes:5000000,max_files_per_selection:8,max_data_items_per_report:20,max_reference_items_per_report:20},clarification_policy:{max_questions_per_round:5,max_answer_characters:2000},generation_policy:{organisation:structuredClone(defaultTenantSettings.organisation),branding:structuredClone(defaultTenantSettings.branding),governance:{...defaultTenantSettings.governance,maxVisualsPerPage:6},generation:structuredClone(defaultTenantSettings.generation)},provider_profile:profile,delivery_guide_policy:{enabled:true,include_handover_instructions:true},conventions:{report_naming:'Synthetic',semantic_modelling:'Synthetic',accessibility:'Synthetic',terminology:{}}};
 const version=(n:number)=>({id:'v'+n,version:n,digest:'synthetic',validation_status:'PASS',applicability:'COMPANY_NEW_OR_REVALIDATED_OPERATIONS',settings:structuredClone(settings),credential:{status:'CONFIGURED',maskedValue:'***',updatedAt:null,canReplace:true,canRotate:true}});
 const state:{held?:Route;posts:string[]}={posts:[]};
 await page.route('**/api/**',async(route:Route)=>{
  const r=route.request(),p=new URL(r.url()).pathname;let body:any={items:[]};
  if(r.method()!=='GET'){if(r.method()==='POST'&&['/api/tenant-settings/restore','/api/tenant-settings/credential'].includes(p)){state.posts.push(p);state.held=route;return}await route.abort();return}
  if(p==='/api/auth/session')body={authenticated:true,identity:{id:'i',display_name:'Synthetic Owner'},actor:{identity_id:'i',membership_id:'owner',company_id:'c',display_name:'Synthetic Owner',role:'COMPANY_OWNER'},csrf_token:'synthetic-only',membership_state:'ACTIVE'};
  else if(p==='/api/auth/providers')body={items:[],development_identities:[]};
  else if(p==='/api/workspace/branding')body={version:2,primary:settings.generation_policy.branding.primary,accent:settings.generation_policy.branding.accent};
  else if(p==='/api/tenant-settings')body=version(2);
  else if(p==='/api/tenant-settings/qualified-profiles')body={items:[profile]};
  else if(p==='/api/tenant-settings/history')body={items:[{id:'h1',version:1,created_at:'2026-10-11T00:00:00Z',changed_keys:[],safe_changes:{},restored_from_version_id:null,current:false,validation_status:'PASS'}]};
  await route.fulfill({json:body});
 });
 await page.goto('/');await expect(page.getByRole('button',{name:'Account menu for Synthetic Owner',exact:true})).toBeVisible();if(!await page.getByRole('button',{name:'Administration',exact:true}).isVisible())await page.getByRole('button',{name:'Open workspace navigation',exact:true}).click();await page.getByRole('button',{name:'Administration',exact:true}).click();await expect(page.getByLabel('Tenant administration')).toContainText('Current effective version 2');
 return{state,version};
}

for(const operation of ['restore','credential'] as const)for(const outcome of ['success','failure'] as const)test(`pending ${operation} dialog locks dismissal and competing drafts until ${outcome}`,async({page})=>{
 const {state,version}=await syntheticSettingsDialogFixture(page),admin=page.getByLabel('Tenant administration');
 await admin.getByRole('button',{name:/Branding & organisation/}).click();const branding=admin.getByLabel('Display name',{exact:true});await branding.fill('Preserved synthetic branding draft');await admin.getByRole('button',{name:/AI & models/}).click();
 let opener:ReturnType<Page['getByRole']>;
 if(operation==='restore'){await admin.getByText('Settings history',{exact:true}).click();opener=admin.getByRole('button',{name:'Review restore',exact:true});await opener.focus();await page.keyboard.press('Enter')}
 else{opener=admin.getByRole('button',{name:'Replace / rotate credential'});await opener.focus();await page.keyboard.press('Enter');await page.getByLabel('New credential').fill('synthetic-noncredential-fixture')}
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:operation==='restore'?'Restore as new version':'Replace credential',exact:true}).click();await expect.poll(()=>Boolean(state.held)).toBe(true);await expect(admin).toHaveAttribute('aria-busy','true');await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeDisabled();await expect(branding).toBeDisabled();await expect(admin.getByRole('button',{name:/Branding & organisation/})).toBeDisabled();if(operation==='credential')await expect(dialog.getByLabel('New credential')).toBeDisabled();
 await page.keyboard.press('Escape');await expect(dialog).toBeVisible();for(const key of ['Tab','Shift+Tab']){await page.keyboard.press(key);expect(await dialog.evaluate(element=>element.contains(document.activeElement))).toBe(true)}expect(state.posts).toEqual(['/api/tenant-settings/'+operation]);
 if(outcome==='success'){await state.held!.fulfill({json:version(3)});await expect(dialog).toHaveCount(0);await expect(admin).toHaveAttribute('aria-busy','false');await expect(admin).toContainText('Current effective version 3');await admin.getByRole('button',{name:/Branding & organisation/}).click();await expect(branding).toBeEnabled();await expect(branding).toHaveValue(operation==='credential'?'Preserved synthetic branding draft':defaultTenantSettings.organisation.displayName)}
 else{await state.held!.fulfill({status:400,json:{error:{code:'SYNTHETIC_REJECTED',message:'Synthetic operation rejected; no settings changed.'}}});await expect(admin).toHaveAttribute('aria-busy','false');await expect(admin).toContainText('Synthetic operation rejected; no settings changed.');await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeEnabled();if(operation==='credential')await expect(dialog.getByLabel('New credential')).toHaveValue('');await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(opener).toBeFocused();await admin.getByRole('button',{name:/Branding & organisation/}).click();await expect(branding).toBeEnabled();await expect(branding).toHaveValue('Preserved synthetic branding draft');await expect(admin).toContainText('Current effective version 2')}
 expect(state.posts).toEqual(['/api/tenant-settings/'+operation]);await expect(page.locator('body')).not.toContainText('synthetic-noncredential-fixture');
});
test('AI-authored geometry discloses numeric settings as preserved historical metadata',async({page})=>{await syntheticSettingsDialogFixture(page);const admin=page.getByLabel('Tenant administration');await admin.getByRole('button',{name:/Responses & report standards/}).click();const visuals=admin.getByLabel('Visuals per page',{exact:true});await expect(visuals).toHaveValue('6');await expect(visuals).not.toHaveAttribute('max');await expect(admin).toContainText('These saved numeric preferences remain historical metadata and do not limit new layouts.');await expect(admin).not.toContainText('up to six visuals');});

async function syntheticDocumentFixture(page:Page){
 await syntheticSettingsDialogFixture(page);
 const base='/api/tenant-settings/knowledge-documents',documentId='10000000-0000-4000-8000-000000000001',revisionId='20000000-0000-4000-8000-000000000001';
 const originals={title:'Synthetic original',source_version:'opaque\u0000',text:'\ufefforiginal\r\n\u0000<script>synthetic</script>'};
 const metadata=(id=revisionId,fields=originals)=>({revision_id:id,predecessor_revision_id:null,title:fields.title,source_version:fields.source_version,text_sha256:'synthetic',text_byte_count:new TextEncoder().encode(fields.text).length,created_at:'2026-10-13T00:00:00Z',local_state:'LOCAL_DRAFT',provider_write_outcome:'NOT_SENT',used_by_ai:false});
 const context=(id=revisionId)=>({company_id:state.company,document_id:documentId,current_revision_id:id,current_operation_id:null,current_revision:metadata(id),local_state:'LOCAL_DRAFT',provider_write_outcome:'NOT_SENT',used_by_ai:false});
 const state:{company:string;membership:string;csrf:string;posts:Array<{key:string;body:string;route:Route}>;mode:'hold'|'lost'|'success'|'context'|'malformed';reconciliation:'COMMITTED'|'NOT_OBSERVED';unknown:string[];saved:typeof originals;latest:string}={company:'c',membership:'owner',csrf:'synthetic-only',posts:[],mode:'success',reconciliation:'NOT_OBSERVED',unknown:[],saved:{...originals},latest:revisionId};
 const envelope=(key:string,kind='CREATE')=>({company_id:state.company,disposition:'APPLIED',command:{command_key:key,operation_id:'30000000-0000-4000-8000-000000000001',document_id:documentId,kind,target_revision_id:revisionId,expected_current_revision_id:null,created_at:'2026-10-13T00:00:00Z',provider_write_outcome:'NOT_SENT'},document:context(state.latest)});
 // The mounted user-management sibling reads this exact route after membership remounts; its synthetic list is empty.
 const known=new Set(['/api/memberships','/api/auth/session','/api/auth/providers','/api/workspace/branding','/api/cases','/api/tenant-settings','/api/tenant-settings/qualified-profiles','/api/tenant-settings/history']);
 await page.route('**/api/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  if(!path.startsWith(base)){if(request.method()==='GET'&&known.has(path)){await route.fallback();return}state.unknown.push(path);await route.abort();return}
  if(path===base+'/capabilities'){await route.fulfill({json:{company_id:state.company,membership_id:state.membership,maximum_request_bytes:5000000,storage:'LOCAL_DRAFT_DATABASE',provider_write_outcome:'NOT_SENT',indexed:false,used_by_ai:false}});return}
  expect(request.headers()['x-expected-membership-id']).toBe(state.membership);
  if(request.method()==='POST'){
   expect(request.headers()['x-csrf-token']).toBe(state.csrf);const key=request.headers()['idempotency-key'];expect(key).toMatch(/^[0-9a-f-]{36}$/);state.posts.push({key,body:request.postData()!,route});
   if(state.mode==='hold')return;if(state.mode==='malformed'){await route.fulfill({json:{company_id:state.company}});return}if(state.mode==='lost'){await route.abort();return}if(state.mode==='context'){await route.fulfill({status:409,json:{error:{code:'KNOWLEDGE_CONTEXT_CHANGED',message:'Context changed.'}}});return}
   const body=request.postDataJSON();if('text' in body)state.saved={title:body.title,source_version:body.source_version,text:body.text};await route.fulfill({json:envelope(key,path.endsWith('/archive')?'ARCHIVE':path.endsWith('/revisions')?'REVISION':'CREATE')});return;
  }
  if(path.startsWith(base+'/commands/')){const key=path.slice((base+'/commands/').length);await route.fulfill({json:state.reconciliation==='NOT_OBSERVED'?{company_id:state.company,reconciliation:'NOT_OBSERVED',command:null,document:null}:{...envelope(key),reconciliation:'COMMITTED'}});return}
  if(path===base){await route.fulfill({json:{company_id:state.company,items:[context()]}});return}
  if(path===base+'/'+documentId){await route.fulfill({json:context(state.latest)});return}
  if(path.endsWith('/history')){await route.fulfill({json:{company_id:state.company,document:context(state.latest),revisions:[metadata()],operations:[]}});return}
  if(path.endsWith('/original')){await route.fulfill({json:{company_id:state.company,document_id:documentId,revision_id:path.split('/').at(-2),...state.saved,text_sha256:'synthetic',text_byte_count:new TextEncoder().encode(state.saved.text).length,created_at:'2026-10-13T00:00:00Z'}});return}
  state.unknown.push(path);await route.abort();
 });
 await page.getByRole('button',{name:'Documents',exact:true}).click();const panel=page.getByLabel('Tenant documents');await expect(panel.getByRole('button',{name:'New document draft',exact:true})).toBeVisible();
 return{state,panel,originals,documentId,revisionId,envelope};
}

test('mocked tenant documents preserve loaded exact text on title-only revision and unrelated settings drafts',async({page})=>{
 const {state,panel,originals}=await syntheticDocumentFixture(page);
 await panel.getByRole('button',{name:/Synthetic original · Local draft/}).click();await expect(panel.getByLabel('Document title')).toHaveValue(originals.title);
 await panel.getByLabel('Document title').fill('Changed title');await panel.getByRole('button',{name:'Save new local revision',exact:true}).click();await expect(panel).toContainText('Saved locally.');
 expect(JSON.parse(state.posts[0].body)).toMatchObject({title:'Changed title',source_version:originals.source_version,text:originals.text});
 await panel.getByRole('button',{name:'View document history'}).click();await expect(panel).toContainText('Retained document history');await panel.getByRole('button',{name:/Read original/}).click();await expect(panel.getByLabel('Retained original document')).toContainText('<script>synthetic</script>');expect(await page.evaluate(()=>('synthetic' in window))).toBe(false);
 await page.getByRole('button',{name:'Documents',exact:true}).click();await page.getByRole('button',{name:/Branding & organisation/}).click();await page.getByLabel('Display name',{exact:true}).fill('Unrelated company draft');await page.getByRole('button',{name:'Documents',exact:true}).click();await panel.getByLabel('Document title').fill('Unsaved document');await page.getByRole('button',{name:'Documents',exact:true}).click();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Unrelated company draft');await page.getByRole('button',{name:'Documents',exact:true}).click();await expect(panel.getByLabel('Document title')).toHaveValue('Unsaved document');expect(state.unknown).toEqual([]);
});

test('mocked tenant documents synchronously lock duplicate saves and pending edits',async({page})=>{
 const {state,panel,envelope}=await syntheticDocumentFixture(page);state.mode='hold';await panel.getByLabel('Document title').fill('Held intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).dblclick();await expect.poll(()=>state.posts.length).toBe(1);await expect(panel.getByLabel('Plaintext document')).toBeDisabled();await expect(panel.getByRole('button',{name:'New document draft',exact:true})).toBeDisabled();await state.posts[0].route.fulfill({json:envelope(state.posts[0].key)});await expect(panel).toContainText('Saved locally.');expect(state.posts.length).toBe(1);expect(state.unknown).toEqual([]);
});

test('mocked tenant documents reconcile NOT_OBSERVED with exactly the same command and original JSON',async({page})=>{
 const {state,panel}=await syntheticDocumentFixture(page);state.mode='lost';await panel.getByLabel('Document title').fill('Lost acknowledgement');await panel.getByLabel('Plaintext document').fill('Keep this original intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('save outcome is unknown');await expect(panel.getByLabel('Document title')).toBeDisabled();await panel.getByRole('button',{name:'Check original command'}).click();await expect(panel).toContainText('does not prove failure');state.mode='success';await panel.getByRole('button',{name:'Retry same original command'}).click();await expect(panel).toContainText('Saved locally.');expect(state.posts).toHaveLength(2);expect(state.posts[1].key).toBe(state.posts[0].key);expect(state.posts[1].body).toBe(state.posts[0].body);expect(state.unknown).toEqual([]);
});

test('mocked tenant documents clear sensitive drafts on a selected-company context conflict',async({page})=>{
 const {state,panel}=await syntheticDocumentFixture(page);state.mode='context';await panel.getByLabel('Document title').fill('Private stale draft');await panel.getByLabel('Plaintext document').fill('Never copy into another company');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('Document access changed');await expect(panel.getByLabel('Document title')).toHaveCount(0);await expect(panel).not.toContainText('Private stale draft');expect(state.posts).toHaveLength(1);expect(state.unknown).toEqual([]);
});

test('administrator local document revisions and archival survive reload with original text retained',async({page})=>{
 await signIn(page,'owner');const session=await (await page.request.get('/api/auth/session')).json(),member=session.actor.membership_id,headers={'X-CSRF-Token':session.csrf_token,'X-Expected-Membership-Id':member,'Idempotency-Key':crypto.randomUUID()},base='/api/tenant-settings/knowledge-documents';
 const title='Canonical local document '+crypto.randomUUID(),text='\ufefforiginal\r\n\u0000<script>synthetic</script>';
 const created=await page.request.post(base,{headers,data:{title,source_version:'opaque\u0000',text}});expect(created.status()).toBe(201);const initial=await created.json();
 await page.getByRole('button',{name:'Administration',exact:true}).click();await page.getByRole('button',{name:'Documents',exact:true}).click();let panel=page.getByLabel('Tenant documents');await panel.getByRole('button',{name:title+' · Local draft',exact:true}).click();await expect(panel.getByLabel('Document title')).toHaveValue(title);await panel.getByLabel('Document title').fill(title+' revised');await panel.getByRole('button',{name:'Save new local revision',exact:true}).click();await expect(panel).toContainText('Saved locally.');
 const latest=await (await page.request.get(base+'/'+initial.document.document_id,{headers:{'X-Expected-Membership-Id':member}})).json();expect(latest.current_revision_id).not.toBe(initial.command.target_revision_id);const saved=await (await page.request.get(base+'/'+latest.document_id+'/revisions/'+latest.current_revision_id+'/original',{headers:{'X-Expected-Membership-Id':member}})).json();expect(saved.text).toBe(text);expect(saved.source_version).toBe('opaque\u0000');
 await page.reload();await page.getByRole('button',{name:'Administration',exact:true}).click();await page.getByRole('button',{name:'Documents',exact:true}).click();panel=page.getByLabel('Tenant documents');await panel.getByRole('button',{name:title+' revised · Local draft',exact:true}).click();await panel.getByRole('button',{name:'View document history'}).click();await expect(panel.getByRole('button',{name:/Read original/})).toHaveCount(2);await panel.getByRole('button',{name:'Archive locally',exact:true}).click();await page.getByRole('dialog',{name:'Archive local document'}).getByRole('button',{name:'Confirm local archival'}).click();await expect(panel).toContainText('LOCAL_ARCHIVAL_REQUESTED');
 const retained=await page.request.get(base+'/'+latest.document_id+'/revisions/'+initial.command.target_revision_id+'/original',{headers:{'X-Expected-Membership-Id':member}});expect(retained.status()).toBe(200);expect((await retained.json()).text).toBe(text);await expect(panel).toContainText('not indexed and not used by AI');
});

test('mocked tenant documents cannot submit old editor text after a selected original fails to load',async({page})=>{
 const {state,panel,documentId}=await syntheticDocumentFixture(page);await panel.getByLabel('Plaintext document').fill('Unrelated old editor text');page.on('dialog',dialog=>void dialog.accept());await page.route(`**/api/tenant-settings/knowledge-documents/${documentId}/revisions/*/original`,route=>route.fulfill({status:503,json:{error:{code:'KNOWLEDGE_DOCUMENTS_UNAVAILABLE',message:'Unavailable.'}}}));await panel.getByRole('button',{name:/Synthetic original · Local draft/}).click();await expect(panel).toContainText('Documents are temporarily unavailable');await expect(panel.getByLabel('Plaintext document')).toHaveValue('');await expect(panel.getByRole('button',{name:'Save new local revision'})).toBeDisabled();expect(state.posts).toHaveLength(0);expect(state.unknown).toEqual([]);
});

test('mocked tenant documents distinguish older committed command from a newer current revision',async({page})=>{
 const {state,panel}=await syntheticDocumentFixture(page);state.mode='lost';await panel.getByLabel('Document title').fill('Older accepted intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('save outcome is unknown');state.latest='20000000-0000-4000-8000-000000000002';state.reconciliation='COMMITTED';await panel.getByRole('button',{name:'Check original command'}).click();await expect(panel).toContainText('current revision is shown separately');await expect(panel.getByRole('button',{name:'Save new local revision'})).toBeDisabled();await expect(panel.getByRole('button',{name:'Load latest document and keep my draft'})).toBeVisible();expect(state.posts).toHaveLength(1);expect(state.unknown).toEqual([]);
});

test('mocked tenant documents ignore a held committed response after sign-out',async({page})=>{
 const {state,panel,envelope}=await syntheticDocumentFixture(page);state.mode='hold';await panel.getByLabel('Document title').fill('Private held intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect.poll(()=>state.posts.length).toBe(1);await page.route('**/api/auth/logout',route=>route.fulfill({json:{signed_out:true}}));page.on('dialog',dialog=>void dialog.accept());await page.getByRole('button',{name:'Account menu for Synthetic Owner'}).click();await page.getByRole('menuitem',{name:'Sign out',exact:true}).click();await expect(panel).toHaveCount(0);await state.posts[0].route.fulfill({json:envelope(state.posts[0].key)});await expect(page.getByText('Private held intent',{exact:true})).toHaveCount(0);await expect(page.getByText(/^Saved locally\./)).toHaveCount(0);expect(state.posts).toHaveLength(1);expect(state.unknown).toEqual([]);
});


test('mocked tenant documents refresh current CSRF without carrying a cleared stale intent',async({page})=>{
 const {state,panel}=await syntheticDocumentFixture(page);state.mode='context';await panel.getByLabel('Document title').fill('Cleared stale intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('Document access changed');state.csrf='fresh-synthetic-csrf';state.mode='success';await page.route('**/api/auth/session',route=>route.fulfill({json:{authenticated:true,identity:{id:'i',display_name:'Synthetic Owner'},actor:{identity_id:'i',membership_id:'owner',company_id:'c',display_name:'Synthetic Owner',role:'COMPANY_OWNER'},csrf_token:state.csrf,membership_state:'ACTIVE'}}));await panel.getByRole('button',{name:'Refresh authorized document context'}).click();await expect(panel.getByLabel('Document title')).toHaveValue('');await panel.getByLabel('Document title').fill('Explicit fresh intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('Saved locally.');expect(state.posts).toHaveLength(2);expect(state.posts[1].key).not.toBe(state.posts[0].key);expect(JSON.parse(state.posts[1].body).title).toBe('Explicit fresh intent');expect(state.unknown).toEqual([]);
});

test('mocked tenant documents ignore an old A response after A to B to A membership remounts',async({page})=>{
 const {state,panel,envelope}=await syntheticDocumentFixture(page);state.mode='hold';await panel.getByLabel('Document title').fill('Old private A intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect.poll(()=>state.posts.length).toBe(1);
 const current=()=>({authenticated:true,identity:{id:'i',display_name:state.company==='c'?'Synthetic Owner':'Synthetic B Owner'},actor:{identity_id:'i',membership_id:state.membership,company_id:state.company,display_name:state.company==='c'?'Synthetic Owner':'Synthetic B Owner',role:'COMPANY_OWNER'},csrf_token:state.csrf,membership_state:'ACTIVE'});
 await page.route('**/api/auth/session',route=>route.fulfill({json:current()}));await page.route('**/api/profile',route=>route.fulfill({json:{profile:{display_name:state.company==='c'?'Synthetic Owner':'Synthetic B Owner'}}}));
 async function switchThroughFreshSession(company:string,membership:string,label:string){await page.getByRole('button',{name:/Account menu for/}).click();await page.getByRole('menuitem',{name:'My profile',exact:true}).click();await page.getByText('My profile',{exact:true}).last().click();await page.locator('.profile-editor:visible').getByLabel('Display name',{exact:true}).fill(label);state.company=company;state.membership=membership;await page.getByRole('button',{name:'Save profile',exact:true}).click();await expect(page.getByRole('button',{name:company==='c'?'Account menu for Synthetic Owner':'Account menu for Synthetic B Owner'})).toBeVisible();await page.getByRole('button',{name:'Administration',exact:true}).click();await page.getByRole('button',{name:'Documents',exact:true}).click();await expect(page.getByLabel('Tenant documents').getByLabel('Document title')).toHaveValue('')}
 await switchThroughFreshSession('other-company','other-member','Changed B profile');await switchThroughFreshSession('c','owner','Changed A profile');await state.posts[0].route.fulfill({json:envelope(state.posts[0].key)});await expect(page.getByLabel('Tenant documents').getByLabel('Document title')).toHaveValue('');await expect(page.getByText('Old private A intent',{exact:true})).toHaveCount(0);await expect(page.getByText(/^Saved locally\./)).toHaveCount(0);expect(state.posts).toHaveLength(1);expect(state.unknown).toEqual([]);
});

test('mocked tenant documents mobile archive dialog traps focus and cannot close during a pending write',async({page})=>{
 await page.setViewportSize({width:375,height:667});const {state,panel,envelope}=await syntheticDocumentFixture(page);await panel.getByRole('button',{name:/Synthetic original · Local draft/}).click();await expect(panel.getByLabel('Document title')).toHaveValue('Synthetic original');await panel.getByRole('button',{name:'View document history'}).click();await expect(panel.getByRole('button',{name:'Read original revision 1'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 const opener=panel.getByRole('button',{name:'Archive locally',exact:true});await opener.focus();await page.keyboard.press('Enter');let dialog=page.getByRole('dialog',{name:'Archive local document'});await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeFocused();await page.keyboard.press('Shift+Tab');await expect(dialog.getByRole('button',{name:'Confirm local archival'})).toBeFocused();await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(opener).toBeFocused();state.mode='hold';await opener.focus();await page.keyboard.press('Enter');dialog=page.getByRole('dialog',{name:'Archive local document'});await dialog.getByRole('button',{name:'Confirm local archival'}).click();await expect.poll(()=>state.posts.length).toBe(1);await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeDisabled();await page.keyboard.press('Escape');await expect(dialog).toBeVisible();const result=envelope(state.posts[0].key,'ARCHIVE');await state.posts[0].route.fulfill({json:{...result,document:{...result.document,current_revision_id:null,current_revision:null,local_state:'LOCAL_ARCHIVAL_REQUESTED'}}});await expect(dialog).toHaveCount(0);await expect(panel).toContainText('LOCAL_ARCHIVAL_REQUESTED');await expect(panel).toContainText('does not delete provider content');expect(state.unknown).toEqual([]);
});


test('mocked tenant documents retain the exact intent after a malformed success acknowledgement',async({page})=>{
 const {state,panel}=await syntheticDocumentFixture(page);state.mode='malformed';await panel.getByLabel('Document title').fill('Uncertain protocol acknowledgement');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('save outcome is unknown');await panel.getByRole('button',{name:'Check original command'}).click();await expect(panel).toContainText('does not prove failure');state.mode='success';await panel.getByRole('button',{name:'Retry same original command'}).click();await expect(panel).toContainText('Saved locally.');expect(state.posts).toHaveLength(2);expect(state.posts[1].key).toBe(state.posts[0].key);expect(state.posts[1].body).toBe(state.posts[0].body);expect(state.unknown).toEqual([]);
});


// Owner-initiated abandonment requires an explicit choice; security cleanup does not.
async function documentAbandonmentBoundary(page:Page,context:import('@playwright/test').BrowserContext){
 const unexpected:string[]=[];await context.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin===new URL(test.info().project.use.baseURL!).origin&&!u.pathname.startsWith('/api/')&&['GET','HEAD'].includes(route.request().method()))await route.continue();else{unexpected.push(u.pathname);await route.abort()}});return unexpected;
}
for(const mode of ['dirty','pending','unknown'] as const)test(`mocked document abandonment cancellation preserves ${mode} work and explicit signout remains available`,async({page,context})=>{
 const unexpected=await documentAbandonmentBoundary(page,context);const {state,panel,envelope}=await syntheticDocumentFixture(page);const dialogs:string[]=[];let accept=false;page.on('dialog',async dialog=>{dialogs.push(dialog.message());if(accept)await dialog.accept();else await dialog.dismiss()});let logoutCalls=0;
 await page.route('**/api/auth/logout',async route=>{logoutCalls++;await route.fulfill({json:{signed_out:true}})});
 await panel.getByLabel('Document title').fill('Unsaved synthetic text');await panel.getByLabel('Plaintext document').fill('Original synthetic draft');
 if(mode!=='dirty'){state.mode=mode==='pending'?'hold':'lost';await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect.poll(()=>state.posts.length).toBe(1);if(mode==='unknown')await expect(panel).toContainText('The save outcome is unknown.')}
 const frozen=state.posts[0]?{key:state.posts[0].key,body:state.posts[0].body}:null;
 const signout=async()=>{await page.getByRole('button',{name:'Account menu for Synthetic Owner'}).click();await page.getByRole('menuitem',{name:'Sign out',exact:true}).click()};
 await signout();expect(dialogs).toHaveLength(1);expect(logoutCalls).toBe(0);await expect(panel.getByLabel('Document title')).toHaveValue('Unsaved synthetic text');await expect(panel.getByLabel('Plaintext document')).toHaveValue('Original synthetic draft');
 if(mode==='pending'){await state.posts[0].route.fulfill({json:envelope(frozen!.key)});await expect(panel).toContainText('Saved locally.');expect(state.posts).toHaveLength(1);expect(state.posts[0].key).toBe(frozen!.key);expect(state.posts[0].body).toBe(frozen!.body)}
 if(mode==='unknown'){await panel.getByRole('button',{name:'Check original command',exact:true}).click();await expect(panel.getByRole('button',{name:'Retry same original command',exact:true})).toBeVisible();state.mode='success';await panel.getByRole('button',{name:'Retry same original command',exact:true}).click();await expect(panel).toContainText('Saved locally.');expect(state.posts).toHaveLength(2);expect(state.posts[1].key).toBe(frozen!.key);expect(state.posts[1].body).toBe(frozen!.body)}
 accept=true;await signout();await expect(panel).toHaveCount(0);expect(logoutCalls).toBe(1);expect(dialogs).toHaveLength(mode==='dirty'?2:1);expect(state.unknown).toEqual([]);expect(unexpected).toEqual([]);
});
test('mocked clean document signout requires no abandonment warning',async({page,context})=>{
 const unexpected=await documentAbandonmentBoundary(page,context);const {panel,state}=await syntheticDocumentFixture(page);const dialogs:string[]=[];page.on('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.dismiss()});let logoutCalls=0;await page.route('**/api/auth/logout',async route=>{logoutCalls++;await route.fulfill({json:{signed_out:true}})});await page.getByRole('button',{name:'Account menu for Synthetic Owner'}).click();await page.getByRole('menuitem',{name:'Sign out',exact:true}).click();await expect(panel).toHaveCount(0);expect(logoutCalls).toBe(1);expect(dialogs).toEqual([]);expect(state.unknown).toEqual([]);expect(unexpected).toEqual([]);
});
for(const status of [401,403])test(`mocked document abandonment forced ${status} clears sensitive state without warning`,async({page,context})=>{
 const unexpected=await documentAbandonmentBoundary(page,context);const {panel,state}=await syntheticDocumentFixture(page);const dialogs:string[]=[];page.on('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.dismiss()});await panel.getByLabel('Document title').fill('Expired private draft');await page.route('**/api/tenant-settings/knowledge-documents',route=>route.fulfill({status,json:{error:{code:status===401?'AUTHENTICATION_REQUIRED':'FORBIDDEN',message:'Document access ended.'}}}));await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('Document access changed');await expect(panel.getByLabel('Document title')).toHaveCount(0);await expect(panel).not.toContainText('Expired private draft');expect(dialogs).toEqual([]);expect(state.unknown).toEqual([]);expect(unexpected).toEqual([]);
});
test('mocked document abandonment explicit confirmation leaves unresolved command without replay',async({page,context})=>{
 const unexpected=await documentAbandonmentBoundary(page,context);const {panel,state}=await syntheticDocumentFixture(page);state.mode='lost';await panel.getByLabel('Document title').fill('Unresolved original intent');await panel.getByRole('button',{name:'Save local draft',exact:true}).click();await expect(panel).toContainText('The save outcome is unknown.');const key=state.posts[0].key,body=state.posts[0].body;let confirmations=0,logoutCalls=0;page.on('dialog',async dialog=>{confirmations++;expect(dialog.message()).toContain('may already be committed');await dialog.accept()});await page.route('**/api/auth/logout',async route=>{logoutCalls++;await route.fulfill({json:{signed_out:true}})});await page.getByRole('button',{name:'Home',exact:true}).click();await page.getByRole('button',{name:'Account menu for Synthetic Owner'}).click();await page.getByRole('menuitem',{name:'Sign out',exact:true}).click();await expect(panel).toHaveCount(0);expect(confirmations).toBe(1);expect(logoutCalls).toBe(1);expect(state.posts).toHaveLength(1);expect(state.posts[0].key).toBe(key);expect(state.posts[0].body).toBe(body);expect(state.unknown).toEqual([]);expect(unexpected).toEqual([]);
});

test('admin explicitly reads agent details from saved settings and sees unknown metadata warnings',async({page})=>{
 let reads=0,settingsVersion=0;
 await page.route('**/api/tenant-settings',async route=>{const response=await route.fetch(),value=await response.json();settingsVersion=value.version;value.settings.provider_profile={profile_id:'synthetic-foundry',protocol:'FOUNDRY_AGENT_RESPONSES',endpoint:'https://provider.invalid/api/projects/configured-project/agents/configured-agent/endpoint/protocols/openai/responses',model_or_deployment:'configured-agent',api_version:'v1',region:'configured-region',prompt_version:'configured-prompt',configuration_id:'configured',capabilities:{structured_output:true,vision:false},max_calls_per_operation:2,max_input_characters:1000,max_output_tokens:128,time_budget_seconds:10,request_timeout_seconds:5,retry_limit:0};value.credential={status:'NOT_CONFIGURED',maskedValue:null,updatedAt:null,canReplace:false,canRotate:false,authMode:'ENTRA'};await route.fulfill({response,json:value})});
 await page.route('**/api/tenant-settings/agent-details',async route=>{reads++;await route.fulfill({json:{status:'METADATA_OBSERVED_ONLY',settings_version:settingsVersion,agent:'configured-agent',configuredVersion:null,modelDeployment:null,storedInstructionUtf8Bytes:null,toolTypes:[],warnings:['AGENT_VERSION_NOT_CONFIGURED','ENDPOINT_SELECTOR_UNKNOWN']}})});
 await signIn(page,'owner');await page.getByRole('button',{name:'Administration',exact:true}).click();
 const admin=page.getByLabel('Tenant administration');
 await expect(admin.getByText(/Configured metadata version: Unknown/)).toBeVisible();expect(reads).toBe(0);
 await admin.getByRole('button',{name:'Read agent details',exact:true}).click();
 await expect(admin.getByText('Metadata warning: ENDPOINT_SELECTOR_UNKNOWN')).toBeVisible();
 await expect(admin.getByText(/Model deployment: Unknown/)).toBeVisible();
 await expect(admin.getByText(/Server authentication capability is unavailable/)).toBeVisible();expect(reads).toBe(1);
});

for(const outcome of ['conflict','uncertain-known','uncertain-unavailable'] as const)test(`restore recovery probe ${outcome}`,async({page})=>{
 const {state,version}=await syntheticSettingsDialogFixture(page),admin=page.getByLabel('Tenant administration');
 await admin.getByRole('button',{name:/Branding & organisation/}).click();await admin.getByLabel('Display name',{exact:true}).fill('Preserved restore recovery draft');await admin.getByRole('button',{name:/AI & models/}).click();
 await admin.getByText('Settings history',{exact:true}).click();await admin.getByRole('button',{name:'Review restore',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Restore tenant settings'});await dialog.getByRole('button',{name:'Restore as new version',exact:true}).click();await expect.poll(()=>Boolean(state.held)).toBe(true);
 await page.route('**/api/tenant-settings',route=>route.request().method()==='GET'?outcome==='uncertain-unavailable'?route.fulfill({status:503,json:{error:{code:'TEMPORARY',message:'Synthetic current unavailable'}}}):route.fulfill({json:version(3)}):route.abort());
 if(outcome==='conflict')await state.held!.fulfill({status:409,json:{error:{code:'VERSION_CONFLICT',message:'Synthetic stale restore'}}});else await state.held!.abort();
 await expect(dialog).toHaveCount(0);
 if(outcome==='conflict'){await expect(admin.getByRole('button',{name:'Load latest settings and keep my draft'})).toBeVisible();await admin.getByRole('button',{name:'Load latest settings and keep my draft'}).click();await expect(admin).toContainText('Current effective version 3')}
 else if(outcome==='uncertain-known'){await expect(admin).toContainText('Current effective version 3');await expect(admin).toContainText('restore response could not be confirmed')}
 else{await expect(admin.getByRole('button',{name:'Check current settings before another save'})).toBeVisible();await expect(admin.getByRole('button',{name:'Review restore',exact:true})).toBeDisabled()}
 await admin.getByRole('button',{name:/Branding & organisation/}).click();await expect(admin.getByLabel('Display name',{exact:true})).toHaveValue('Preserved restore recovery draft');expect(state.posts).toEqual(['/api/tenant-settings/restore']);
});

test('uncertain restore pauses writes until explicit successful current-settings read',async({page})=>{
 const {state,version}=await syntheticSettingsDialogFixture(page),admin=page.getByLabel('Tenant administration');
 await admin.getByRole('button',{name:/Branding & organisation/}).click();await admin.getByLabel('Display name',{exact:true}).fill('Retained uncertain restore draft');await admin.getByRole('button',{name:/AI & models/}).click();
 await admin.getByText('Settings history',{exact:true}).click();await admin.getByRole('button',{name:'Review restore',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Restore as new version',exact:true}).click();await expect.poll(()=>Boolean(state.held)).toBe(true);
 let unavailable=true;
 await page.route('**/api/tenant-settings',route=>route.request().method()==='GET'?unavailable?route.fulfill({status:503,json:{error:{code:'TEMPORARY',message:'Synthetic read unavailable'}}}):route.fulfill({json:version(3)}):route.abort());
 await state.held!.fulfill({status:503,json:{error:{code:'TEMPORARY',message:'Synthetic restore response unavailable'}}});
 await expect(page.getByRole('dialog')).toHaveCount(0);const reconcile=admin.getByRole('button',{name:'Check current settings before another save'});await expect(reconcile).toBeVisible();await reconcile.click();await expect(admin).toContainText('The current policy is still unavailable');await expect(admin.getByRole('button',{name:'Review restore',exact:true})).toBeDisabled();
 unavailable=false;await reconcile.click();await expect(admin).toContainText('Current effective version 3');await expect(reconcile).toHaveCount(0);await expect(admin.getByRole('button',{name:'Review restore',exact:true})).toBeEnabled();await admin.getByRole('button',{name:/Branding & organisation/}).click();await expect(admin.getByLabel('Display name',{exact:true})).toHaveValue('Retained uncertain restore draft');expect(state.posts).toEqual(['/api/tenant-settings/restore']);
});

test('one restore dispatch retains committed success when history read fails',async({page})=>{
 const {state,version}=await syntheticSettingsDialogFixture(page),admin=page.getByLabel('Tenant administration');
 await admin.getByText('Settings history',{exact:true}).click();await admin.getByRole('button',{name:'Review restore',exact:true}).click();const dialog=page.getByRole('dialog');await expect(dialog).toContainText('restores all non-secret settings');await expect(dialog).toContainText('discards unsaved section drafts after success');
 await dialog.getByRole('button',{name:'Restore as new version',exact:true}).evaluate(button=>{(button as HTMLButtonElement).click();(button as HTMLButtonElement).click()});await expect.poll(()=>Boolean(state.held)).toBe(true);expect(state.posts).toEqual(['/api/tenant-settings/restore']);expect(state.held!.request().postDataJSON()).toEqual({source_version:1,expected_version:2,confirm_consequences:true});
 await page.route('**/api/tenant-settings/history',route=>route.fulfill({status:503,json:{error:{code:'TEMPORARY',message:'Synthetic history unavailable'}}}));await state.held!.fulfill({json:version(3)});await expect(dialog).toHaveCount(0);await expect(admin).toContainText('Current effective version 3');await expect(admin).toContainText('the committed restore remains effective');await expect(admin).not.toContainText('restore response could not be confirmed');expect(state.posts).toEqual(['/api/tenant-settings/restore']);
});
