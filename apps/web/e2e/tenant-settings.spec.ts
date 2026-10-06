import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page,identity:'owner'|'member'|'foreign'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
}

test('owner edits and restores a versioned clarification policy without exposing a credential',async({page})=>{
  await signIn(page,'owner');
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.getByRole('heading',{name:'Tenant Settings'})).toBeVisible();
  await admin.getByRole('button',{name:/AI & models/}).click();
  await expect(admin.getByText('Not configured')).toBeVisible();
  await expect(admin.getByText(/Current effective version 1 · Validation PASS · Applies to this company’s new and revalidated operations/)).toBeVisible();
  await expect(admin.getByRole('button',{name:/Reveal|Show key|Copy existing key/i})).toHaveCount(0);
  await admin.getByRole('button',{name:/Budgets & limits/}).click();
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
  await expect(admin.locator('.status-badge',{hasText:'Version 3'})).toBeVisible();
});

test('ordinary member cannot see owner settings and narrow admin form does not overflow',async({page})=>{
  await signIn(page,'member');
  await expect(page.getByLabel('Tenant administration')).toHaveCount(0);
  await page.getByRole('button',{name:'Sign out'}).click();
  await signIn(page,'owner');
  await page.setViewportSize({width:375,height:812});
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.getByRole('button',{name:/Review .* changes/})).toBeVisible();
  const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth}));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
});

test('high-impact changes remain in separate section drafts and each review excludes unrelated fields',async({page})=>{
  await signIn(page,'owner');
  await page.setViewportSize({width:375,height:812});
  const admin=page.getByLabel('Tenant administration');
  await page.getByRole('button',{name:'Administration'}).click();
  const before=(await (await page.request.get('/api/tenant-settings')).json()).version;
  await admin.getByRole('combobox').selectOption('synthetic-e2e-profile');
  await admin.getByLabel('Calls per operation',{exact:false}).fill('1');
  await admin.getByLabel('Retry limit',{exact:false}).fill('0');
  await admin.getByRole('checkbox',{name:/Expert assistance/}).uncheck();
  await admin.getByRole('checkbox',{name:/Automatic intelligent generation/}).check();
  await admin.getByRole('button',{name:/Responses & standards/}).click();
  await admin.getByLabel('Visuals per page',{exact:false}).fill('5');
  await admin.getByRole('textbox',{name:/^report naming Applies/}).fill('Synthetic test naming convention');
  await admin.getByRole('button',{name:/Budgets & limits/}).click();
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

test('saving one section leaves another unsaved draft out of the committed version',async({page})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const admin=page.getByLabel('Tenant administration');
  const before=await (await page.request.get('/api/tenant-settings')).json();
  const expert=admin.getByRole('checkbox',{name:/Expert assistance/});
  if(before.settings.expert_escalation_enabled)await expert.uncheck();else await expert.check();
  await admin.getByRole('button',{name:/Budgets & limits/}).click();
  const lifetime=admin.getByLabel('Invitation lifetime (days)');
  await lifetime.fill(String(before.settings.invitation_ttl_days+1));
  await admin.getByRole('button',{name:/Review .* changes/}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(review).toContainText('invitation_ttl_days');
  await expect(review).not.toContainText('expert_escalation_enabled');
  await review.getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(admin.getByText(`Tenant settings version ${before.version+1} is now effective.`,{exact:false})).toBeVisible();
  const saved=await (await page.request.get('/api/tenant-settings')).json();
  expect(saved.version).toBe(before.version+1);
  expect(saved.settings.invitation_ttl_days).toBe(before.settings.invitation_ttl_days+1);
  expect(saved.settings.expert_escalation_enabled).toBe(before.settings.expert_escalation_enabled);
  await admin.getByRole('button',{name:/AI & models/}).click();
  await expect(admin.getByRole('checkbox',{name:/Expert assistance/})).toHaveJSProperty('checked',!before.settings.expert_escalation_enabled);
  await page.getByRole('button',{name:'Home'}).click();
  await page.getByRole('button',{name:'Administration'}).click();
  await expect(admin.getByRole('checkbox',{name:/Expert assistance/})).toHaveJSProperty('checked',!before.settings.expert_escalation_enabled);
  await admin.getByRole('button',{name:'Cancel section changes'}).click();
  await expect(admin.getByRole('checkbox',{name:/Expert assistance/})).toHaveJSProperty('checked',before.settings.expert_escalation_enabled);
});

test('stale section saves fail closed and explicitly reload current policy',async({page,context})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
  const original=await (await page.request.get('/api/tenant-settings')).json();
  const first=page.getByLabel('Tenant administration');
  await first.getByRole('button',{name:/Budgets & limits/}).click();
  await first.getByLabel('Invitation lifetime (days)').fill(String(original.settings.invitation_ttl_days+1));

  const secondPage=await context.newPage();
  await secondPage.goto('/');
  await secondPage.getByRole('button',{name:'Administration'}).click();
  const second=secondPage.getByLabel('Tenant administration');
  await second.getByRole('button',{name:/Budgets & limits/}).click();
  const files=second.getByLabel('Files per selection');
  await files.fill(String(original.settings.upload_policy.max_files_per_selection+1));
  await second.getByRole('button',{name:/Review .* changes/}).click();
  await secondPage.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(second.getByText(`Tenant settings version ${original.version+1} is now effective.`,{exact:false})).toBeVisible();

  await first.getByRole('button',{name:/Review .* changes/}).click();
  await page.getByRole('dialog',{name:'Review tenant settings changes'}).getByRole('button',{name:'Confirm and save new version'}).click();
  await expect(first.getByRole('alert')).toContainText('rejected this stale version');
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(original.version+1);
  await first.getByRole('button',{name:'Discard drafts and load latest settings'}).click();
  await expect(first.getByLabel('Invitation lifetime (days)')).toHaveValue(String(original.settings.invitation_ttl_days));
  await expect(first.getByLabel('Files per selection')).toHaveValue(String(original.settings.upload_policy.max_files_per_selection+1));
  await secondPage.close();
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
  await admin.getByRole('button',{name:'Replace / rotate credential'}).click();
  await dialog.getByLabel('New credential').fill('synthetic-e2e-secret-second');
  await dialog.getByRole('button',{name:'Replace credential'}).click();
  await expect(admin.getByText(/Protected credential replaced in settings version/)).toBeVisible();
  await expect(page.locator('body')).not.toContainText('synthetic-e2e-secret-second');
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
  await page.getByRole('button',{name:'Sign out'}).click();
  await signIn(page,'foreign');
  const foreign=await (await page.request.get('/api/tenant-settings')).json();
  expect(foreign.id).not.toBe(owner.id);
  expect(foreign.settings.provider_profile).toBeNull();
  await page.getByRole('button',{name:'Sign out'}).click();
  await signIn(page,'member');
  await expect(page.getByLabel('Tenant administration')).toHaveCount(0);
  expect((await page.request.get('/api/tenant-settings')).status()).toBe(403);
  expect((await page.request.get('/api/tenant-settings/history')).status()).toBe(403);
  expect((await page.request.get('/api/tenant-settings/qualified-profiles')).status()).toBe(403);
});
