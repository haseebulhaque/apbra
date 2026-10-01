import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page,identity:'owner'|'member'|'foreign'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
}

test('owner edits and restores a versioned clarification policy without exposing a credential',async({page})=>{
  await signIn(page,'owner');
  const admin=page.getByLabel('Tenant administration');
  await admin.getByText('Tenant Settings · Owner/Admin').click();
  await expect(admin.getByRole('heading',{name:'Tenant Settings'})).toBeVisible();
  await expect(admin.getByText('Not configured')).toBeVisible();
  await expect(admin.getByText(/Current effective version 1 · Validation PASS · Applies to this company’s new and revalidated operations/)).toBeVisible();
  await expect(admin.getByRole('button',{name:/Reveal|Show key|Copy existing key/i})).toHaveCount(0);
  const turns=admin.getByLabel('Turns per cycle',{exact:false});
  const original=Number(await turns.inputValue());
  await turns.fill(String(original+1));
  await admin.getByRole('button',{name:'Review settings changes'}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  await expect(review).toContainText('max_clarification_rounds_per_cycle');
  await expect(review).toContainText('future clarification');
  await expect((await page.request.get('/api/tenant-settings')).json()).resolves.toMatchObject({version:1});
  await review.getByRole('button',{name:'Cancel'}).click();
  await expect((await page.request.get('/api/tenant-settings')).json()).resolves.toMatchObject({version:1});
  await admin.getByRole('button',{name:'Review settings changes'}).click();
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
  await admin.getByText('Tenant Settings · Owner/Admin').click();
  await expect(admin.locator('.status-badge',{hasText:'Version 3'})).toBeVisible();
});

test('ordinary member cannot see owner settings and narrow admin form does not overflow',async({page})=>{
  await signIn(page,'member');
  await expect(page.getByLabel('Tenant administration')).toHaveCount(0);
  await page.getByRole('button',{name:'Sign out'}).click();
  await signIn(page,'owner');
  await page.setViewportSize({width:375,height:812});
  const admin=page.getByLabel('Tenant administration');
  await admin.getByText('Tenant Settings · Owner/Admin').click();
  await expect(admin.getByRole('button',{name:'Review settings changes'})).toBeVisible();
  const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth}));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
});

test('high-impact draft changes show their keys and consequences before any commit on mobile',async({page})=>{
  await signIn(page,'owner');
  await page.setViewportSize({width:375,height:812});
  const admin=page.getByLabel('Tenant administration');
  await admin.getByText('Tenant Settings · Owner/Admin').click();
  const before=(await (await page.request.get('/api/tenant-settings')).json()).version;
  await admin.getByRole('combobox').selectOption('synthetic-e2e-profile');
  await admin.getByLabel('Calls per operation',{exact:false}).fill('1');
  await admin.getByLabel('Retry limit',{exact:false}).fill('0');
  await admin.getByLabel('Visuals per page',{exact:false}).fill('5');
  await admin.getByLabel('Turns overall',{exact:false}).fill('9');
  await admin.getByRole('textbox',{name:/^report naming Applies/}).fill('Synthetic test naming convention');
  await admin.getByRole('checkbox',{name:/Expert assistance/}).uncheck();
  await admin.getByRole('checkbox',{name:/Automatic intelligent generation/}).check();
  await admin.getByRole('button',{name:'Review settings changes'}).click();
  const review=page.getByRole('dialog',{name:'Review tenant settings changes'});
  for(const key of ['provider_profile','automatic_generation_enabled','generation_policy.governance.maxVisualsPerPage','max_clarification_rounds_overall','conventions.report_naming','expert_escalation_enabled'])await expect(review).toContainText(key);
  await expect(review).toContainText('protected credential');
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(before);
  const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth}));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
  await review.getByRole('button',{name:'Cancel'}).click();
  expect((await (await page.request.get('/api/tenant-settings')).json()).version).toBe(before);
});

test('owner configures and rotates a synthetic protected credential without revealing it',async({page})=>{
  await signIn(page,'owner');
  const initialVersion=(await (await page.request.get('/api/tenant-settings')).json()).version;
  const admin=page.getByLabel('Tenant administration');
  await admin.getByText('Tenant Settings · Owner/Admin').click();
  await admin.getByRole('combobox').selectOption('synthetic-e2e-profile');
  await expect(admin.getByText(/Qualified deployment: synthetic-e2e-model/)).toBeVisible();
  await expect(admin.getByLabel('Profile identity')).toHaveCount(0);
  await admin.getByRole('button',{name:'Review settings changes'}).click();
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
  await admin.getByRole('button',{name:'Review settings changes'}).click();
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
  await admin.getByText('Tenant Settings · Owner/Admin').click();
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
