import {expect,test,type Page} from '@playwright/test';

async function setAppearance(page:Page,mode:string){const button=page.getByRole('button',{name:mode==='system'?'Use system appearance':mode==='light'?'Light appearance':'Dark appearance',exact:true});if(!await button.isVisible())await page.getByRole('button',{name:/^Account menu for /}).click();await button.click();const menu=page.getByRole('menu',{name:'Account',exact:true});if(await menu.isVisible()){await page.keyboard.press('Escape');await expect(menu).toHaveCount(0)}}

async function signOut(page:Page){
  const account=page.getByRole('button',{name:/^Account menu for /});
  await expect(account.or(page.getByRole('button',{name:'Sign out',exact:true}))).toBeVisible();
  if(await account.count()){await account.click();await page.getByRole('menuitem',{name:'Sign out',exact:true}).click()}
  else await page.getByRole('button',{name:'Sign out',exact:true}).click();
}

async function signIn(page:Page,identity:'owner'|'member'|'uninvited'|'foreign'|'creator'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
  const navigation=page.getByRole('button',{name:'Open workspace navigation',exact:true});
  if((page.viewportSize()?.width??1280)<=768){await expect(navigation).toBeVisible();await navigation.click();}
}

test('ordinary invited member creates, saves, refreshes and reopens a private case',async({page})=>{
  const protectedSettingsReads:string[]=[];
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/tenant-settings')protectedSettingsReads.push(request.method())});
  await signIn(page,'member');
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  await expect(page.locator('main').getByRole('button',{name:'Create report'})).toHaveCount(1);
  await page.getByRole('button',{name:'Create report'}).first().click();

  const request='Compare synthetic distribution performance by depot and month.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Compare synthetic distribution performance by depot and month'})).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByLabel('Current business request')).toHaveValue(request);

  await page.getByLabel('Current business request').fill(`${request} Include carrier category.`);
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Your updated request was saved.')).toBeVisible();
  await expect(page.getByText('Earlier request versions · 2')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Private report access'})).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(protectedSettingsReads).toEqual([]);
});

test('business workspace remains keyboard navigable and contained on a small screen',async({page},testInfo)=>{
  await page.setViewportSize({width:375,height:812});
  await signIn(page,'member');
  const skip=page.getByRole('link',{name:'Skip to reporting workspace'});
  await skip.focus();
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#workspace-main$/);
  await expect(page.getByRole('navigation',{name:'Workspace sections'})).toBeVisible();
  await page.getByRole('button',{name:'Create report'}).first().click();
  await expect(page.getByRole('heading',{name:'What would you like to understand?'})).toBeVisible();
  if(process.env.APBRA_VISUAL_CAPTURE)await page.screenshot({path:testInfo.outputPath('mobile-home.png'),fullPage:true});
  const overflow=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth,offenders:[...document.querySelectorAll('body *')].filter(element=>element.getBoundingClientRect().right>window.innerWidth+1&&!element.closest('.workspace-rail nav')).slice(0,8).map(element=>({tag:element.tagName,className:element.className,right:Math.round(element.getBoundingClientRect().right)}))}));
  expect(overflow.document,JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.viewport);
  await expect(page.getByText('ReportDesign JSON')).toHaveCount(0);
  await page.getByLabel('Your reporting goal').fill('Compare completed synthetic orders by depot.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await page.getByRole('button',{name:'Next: Information',exact:true}).click();
  const upload=page.getByRole('button',{name:'Add data sources or reference material'});
  await upload.focus();
  await expect(upload).toBeFocused();
  await expect(page.locator('label.upload-button')).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Report steps'}).locator('[aria-current=step]')).toHaveText('2Information');
});

test('stale edits are rejected through the UI and reload recovers the current version',async({page,context})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Assess synthetic customer retention by segment.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();

  const otherTab=await context.newPage();
  await otherTab.goto('/');
  await otherTab.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(otherTab.getByLabel('Current business request')).toHaveValue(request);

  const saved=`${request} Include subscription tier.`;
  await page.getByLabel('Current business request').fill(saved);
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Your updated request was saved.')).toBeVisible();

  await otherTab.getByLabel('Current business request').fill(`${request} Include support channel.`);
  await otherTab.getByRole('button',{name:'Save new version'}).click();
  await expect(otherTab.getByRole('alert')).toContainText('This report changed in another session. Reload it before saving your changes.');
  await otherTab.getByRole('button',{name:'Reload report'}).click();
  await expect(otherTab.getByLabel('Current business request')).toHaveValue(saved);
  await expect(otherTab.getByText('Earlier request versions · 2')).toBeVisible();
});

test('an expired application session is reported truthfully by the protected UI handler',async({page,context})=>{
  await signIn(page,'owner');
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  await page.getByRole('button',{name:'Create report'}).first().click();

  const sessionControl=await context.newPage();
  await sessionControl.goto('/');
  await signOut(sessionControl);
  await expect(sessionControl.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();

  await page.getByLabel('Your reporting goal').fill('Review synthetic marketing effectiveness by channel.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();
  await expect(page.getByText('Your APBRA session has expired. Sign in again to continue.')).toBeVisible();
});

test('an invited identity accepts the exact single-use invitation through OIDC and the UI',async({page,browser})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByRole('button',{name:'Administration'}).click();
    await page.getByRole('button',{name:'User management',exact:true}).click();
    await page.getByText('Invite user',{exact:true}).click();
  await page.getByLabel('External subject').fill('dev-uninvited');
  await page.getByLabel('Application role').selectOption('EXPERT');
  await page.getByRole('button',{name:'Issue invitation'}).click();
  const invitationLink=await page.getByLabel('One-time invitation link').inputValue();
  expect(invitationLink).toMatch(/\/invite#token=/);

  const inviteeContext=await browser.newContext();
  const inviteePage=await inviteeContext.newPage();
  await signIn(inviteePage,'uninvited');
  await expect(inviteePage.getByRole('heading',{name:'Open your invitation'})).toBeVisible();
  await expect(inviteePage.getByRole('textbox',{name:'Company or workspace name'})).toHaveCount(0);

  await inviteePage.goto(invitationLink);
  await expect(inviteePage).not.toHaveURL(/token=/);
  await expect(inviteePage.getByRole('heading',{name:'Accept your invitation'})).toBeVisible();
  await inviteePage.getByRole('button',{name:'Accept invitation'}).click();
  await expect(inviteePage.getByText('Invitation accepted. Your APBRA membership is active.')).toBeVisible();
  await expect(inviteePage.getByRole('heading',{name:'Your reports'})).toBeVisible();
  await inviteeContext.close();
});

test('an uninvited identity creates one company with owner and approved settings after a lost response',async({page,browser})=>{
  await signIn(page,'creator');
  await expect(page.getByRole('heading',{name:'Create Company / Workspace'})).toBeVisible();
  await expect(page.getByLabel('Company or workspace name')).toBeVisible();
  await expect(page.getByLabel(/domain|Microsoft tenant|provider|billing|role/i)).toHaveCount(0);
  const name='Creator Preview Workspace';
  await page.getByLabel('Company or workspace name').fill(name);
  let first=true;
  await page.route('**/api/companies',async route=>{
    if(!first){await route.continue();return}
    first=false;
    const committed=await route.fetch();
    expect(committed.status()).toBe(201);
    await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'TEMPORARY',message:'Synthetic response lost after commit'}})});
  });
  await page.getByRole('button',{name:'Create Company / Workspace'}).click();
  await expect(page.getByRole('alert')).toContainText('Company creation could not be completed. Please try again.');
  await page.getByRole('button',{name:'Create Company / Workspace'}).click();
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  await page.getByRole('button',{name:/^Account menu for /}).click();await expect(page.locator('.account-identity')).toContainText('company owner');await page.keyboard.press('Escape');
  const settings=await page.evaluate(async()=>{const response=await fetch('/api/tenant-settings',{credentials:'same-origin'});return{status:response.status,body:await response.json()}});
  expect(settings.status).toBe(200);
  expect(settings.body).toMatchObject({version:1,validation_status:'PASS',settings:{automatic_generation_enabled:false,provider_profile:null,generation_policy:{organisation:{name,displayName:name}}}});
  await page.reload();
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  await page.getByRole('button',{name:'My profile'}).click();
  await page.locator('.profile-editor summary').click();
  await page.locator('.profile-editor').getByLabel('Display name').fill('Casey Creator');
  await page.getByRole('button',{name:'Save profile'}).click();
  await expect(page.getByRole('button',{name:'Account menu for Casey Creator',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill('Review synthetic preview activity by month.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();
  const foreignContext=await browser.newContext(),foreignPage=await foreignContext.newPage();
  await signIn(foreignPage,'foreign');
  await expect(foreignPage.getByRole('button',{name:/Review synthetic preview activity by month/})).toHaveCount(0);
  await foreignContext.close();
});

test('an existing company member accepts a second exact invitation and selects each company on fresh sign-in',async({page,browser})=>{
  await signIn(page,'creator');
  await expect(page.getByRole('heading',{name:/Create Company \/ Workspace|Your reports/})).toBeVisible();
  if(await page.getByRole('heading',{name:'Create Company / Workspace'}).isVisible()){
    await page.getByLabel('Company or workspace name').fill('Creator Invitation Preview Workspace');
    await page.getByRole('button',{name:'Create Company / Workspace'}).click();
  }
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  const originalSession=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {actor:{company_id:string;membership_id:string;role:string}});
  expect(originalSession.actor.role).toBe('COMPANY_OWNER');
  const originalSavedSettings=await (await page.request.get('/api/tenant-settings')).json();
  const originalSavedHistory=await (await page.request.get('/api/tenant-settings/history')).json();
  const originalPalette={primary:originalSavedSettings.settings.generation_policy.branding.primary,accent:originalSavedSettings.settings.generation_policy.branding.accent},targetPalette={primary:'#654321',accent:'#ABCDEF'};
  expect(originalPalette.primary.toLowerCase()).not.toBe(targetPalette.primary.toLowerCase());
  expect(originalPalette.accent.toLowerCase()).not.toBe(targetPalette.accent.toLowerCase());
  let releaseOldBranding=()=>{};

  const privateRequest='Review synthetic creator-only activity by week.';
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill(privateRequest);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();
  const privateCaseId=await page.evaluate(async request=>{
    const response=await fetch('/api/cases',{credentials:'same-origin'});
    const body=await response.json() as {items:Array<{id:string;current_request:{request_text:string}}>};
    return body.items.find(item=>item.current_request.request_text===request)?.id;
  },privateRequest);
  expect(privateCaseId).toBeTruthy();

  const inviterContext=await browser.newContext();
  try{
    const inviterPage=await inviterContext.newPage();
    await signIn(inviterPage,'foreign');
    await expect(inviterPage.getByRole('heading',{name:'Your reports'})).toBeVisible();
    const targetSession=await inviterPage.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {actor:{company_id:string}});
    expect(targetSession.actor.company_id).not.toBe(originalSession.actor.company_id);
    const targetSavedSettings=await (await inviterPage.request.get('/api/tenant-settings')).json();
    const targetSavedHistory=await (await inviterPage.request.get('/api/tenant-settings/history')).json();
    await inviterPage.getByRole('button',{name:'Administration'}).click();
    await inviterPage.getByRole('button',{name:'User management',exact:true}).click();
    await inviterPage.getByText('Invite user',{exact:true}).click();
    await inviterPage.getByLabel('External subject').fill('dev-creator');
    await inviterPage.getByLabel('Application role').selectOption('MEMBER');
    await inviterPage.getByRole('button',{name:'Issue invitation'}).click();
    const invitationLink=await inviterPage.getByLabel('One-time invitation link').inputValue();
    expect(invitationLink).toMatch(/\/invite#token=/);

    let receivedOldBranding!:()=>void;
    const oldBrandingReady=new Promise<void>(resolve=>{receivedOldBranding=resolve});
    const heldOldBranding=new Promise<void>(resolve=>{releaseOldBranding=resolve});
    let holdOriginal=true;
    // Browser-only distinct palettes; API session/branding requests still use real tenant selection.
    await page.route('**/api/workspace/branding',async route=>{
      const state=await (await page.request.get('/api/auth/session')).json() as {actor?:{company_id:string}};
      const response=await route.fetch();
      if(response.status()!==200){await route.fulfill({response});return}
      const branding=await response.json();
      const isOriginal=state.actor?.company_id===originalSession.actor.company_id;
      expect(isOriginal||state.actor?.company_id===targetSession.actor.company_id).toBe(true);
      const palette=isOriginal?originalPalette:targetPalette;
      if(isOriginal&&holdOriginal){holdOriginal=false;branding.version+=100;receivedOldBranding();await heldOldBranding;}
      await route.fulfill({response,json:{...branding,...palette}});
    });
    await page.goto(invitationLink);
    await expect(page).not.toHaveURL(/token=/);
    await expect(page.getByRole('heading',{name:'Accept company invitation'})).toBeVisible();
    await oldBrandingReady;
    await page.getByRole('button',{name:'Accept invitation'}).click();
    await expect(page.getByText('Invitation accepted. Your APBRA membership is active.')).toBeVisible();
    const accepted=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {membership_state:string;actor:{company_id:string;membership_id:string;role:string}});
    expect(accepted.membership_state).toBe('ACTIVE');
    expect(accepted.actor.company_id).toBe(targetSession.actor.company_id);
    expect(accepted.actor.role).toBe('MEMBER');
    expect(accepted.actor.membership_id).not.toBe(originalSession.actor.membership_id);
    const displayedPrimary=()=>page.locator('.private-workspace').evaluate(root=>(root as HTMLElement).style.getPropertyValue('--tenant-primary-original'));
    await expect.poll(displayedPrimary).toBe(targetPalette.primary.toLowerCase());
    const oldReply=page.waitForResponse(response=>response.url().endsWith('/api/workspace/branding')&&response.status()===200);
    releaseOldBranding();await (await oldReply).finished();
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    expect(await displayedPrimary()).toBe(targetPalette.primary.toLowerCase());
    await expect(page.getByRole('button',{name:new RegExp(privateRequest)})).toHaveCount(0);
    expect((await page.request.get(`/api/cases/${privateCaseId}`)).status()).toBe(404);
    await page.reload();
    await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
    const refreshed=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {actor:{company_id:string}});
    expect(refreshed.actor.company_id).toBe(targetSession.actor.company_id);

    await signOut(page);
    await expect(page.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();
    await signIn(page,'creator');
    await expect(page.getByRole('heading',{name:'Choose your company'})).toBeVisible();
    const fresh=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {membership_state:string;actor?:unknown;available_companies:Array<{company_id:string;membership_id:string;name:string}>});
    expect(fresh.membership_state).toBe('COMPANY_SELECTION_REQUIRED');
    expect(fresh.actor).toBeUndefined();
    expect((await page.request.get('/api/workspace/branding')).status()).toBe(401);
    await expect(page.locator('.private-workspace')).toHaveCount(0);
    const original=fresh.available_companies.find(company=>company.company_id===originalSession.actor.company_id);
    const target=fresh.available_companies.find(company=>company.company_id===targetSession.actor.company_id);
    expect(original).toBeTruthy();
    expect(target).toBeTruthy();
    expect(fresh.available_companies).toHaveLength(2);
    await page.locator('.company-selection button').filter({hasText:original!.name}).click();
    await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
    const selectedOriginal=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {actor:{company_id:string;membership_id:string}});
    expect(selectedOriginal.actor.membership_id).toBe(originalSession.actor.membership_id);
    const originalBranding=await (await page.request.get('/api/workspace/branding')).json();
    expect(originalBranding).toEqual({version:originalSavedSettings.version,primary:originalSavedSettings.settings.generation_policy.branding.primary,accent:originalSavedSettings.settings.generation_policy.branding.accent});
    await expect.poll(displayedPrimary).toBe(originalPalette.primary.toLowerCase());
    expect(await (await page.request.get('/api/tenant-settings')).json()).toEqual(originalSavedSettings);
    expect(await (await page.request.get('/api/tenant-settings/history')).json()).toEqual(originalSavedHistory);
    await expect(page.getByRole('button',{name:new RegExp(privateRequest)})).toBeVisible();

    await signOut(page);
    await expect(page.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();
    await signIn(page,'creator');
    await expect(page.getByRole('heading',{name:'Choose your company'})).toBeVisible();
    await page.locator('.company-selection button').filter({hasText:target!.name}).click();
    await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
    const selectedTarget=await page.evaluate(async()=>await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {actor:{company_id:string;membership_id:string}});
    expect(selectedTarget.actor.membership_id).toBe(accepted.actor.membership_id);
    const targetBranding=await (await page.request.get('/api/workspace/branding')).json();
    expect(targetBranding).toEqual({version:targetSavedSettings.version,primary:targetSavedSettings.settings.generation_policy.branding.primary,accent:targetSavedSettings.settings.generation_policy.branding.accent});
    await expect.poll(displayedPrimary).toBe(targetPalette.primary.toLowerCase());
    expect(await (await inviterPage.request.get('/api/tenant-settings')).json()).toEqual(targetSavedSettings);
    expect(await (await inviterPage.request.get('/api/tenant-settings/history')).json()).toEqual(targetSavedHistory);
    await expect(page.getByRole('button',{name:new RegExp(privateRequest)})).toHaveCount(0);
    expect((await page.request.get(`/api/cases/${privateCaseId}`)).status()).toBe(404);
  }finally{releaseOldBranding();await inviterContext.close()}
});

test('company role controls protect the owner while allowing a bounded member-admin change',async({page,browser})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration'}).click();
    await page.getByRole('button',{name:'User management',exact:true}).click();
    await page.getByText('Invite user',{exact:true}).click();
  const owner=page.locator('.invitation-admin .membership-list li').filter({hasText:'Avery Owner'});
  const member=page.locator('.invitation-admin .membership-list li').filter({hasText:'Morgan Member'});
  await expect(owner.getByRole('button',{name:'Deactivate'})).toHaveCount(0);
  await member.getByText('Manage role for Morgan Member',{exact:true}).click();
  const role=member.getByLabel('Role for Morgan Member');
  await role.selectOption('COMPANY_ADMIN');
  await member.getByRole('button',{name:'Save role'}).click();
  await expect(member).toContainText('company admin');
  try{
    const adminContext=await browser.newContext(),adminPage=await adminContext.newPage();
    try{
      await signIn(adminPage,'member');
      await adminPage.getByRole('button',{name:'Administration'}).click();
    await adminPage.getByRole('button',{name:'User management',exact:true}).click();
    await adminPage.getByText('Invite user',{exact:true}).click();
      const ownerAsAdmin=adminPage.locator('.invitation-admin .membership-list li').filter({hasText:'Avery Owner'});
      await expect(ownerAsAdmin.getByRole('button',{name:'Deactivate'})).toHaveCount(0);
      const ownerId=await page.evaluate(async()=>{const response=await fetch('/api/memberships',{credentials:'same-origin'}),body=await response.json() as {items:Array<{id:string;role:string}>};return body.items.find(item=>item.role==='COMPANY_OWNER')?.id});
      expect(ownerId).toBeTruthy();
      const denial=await adminPage.evaluate(async membershipId=>{const session=await (await fetch('/api/auth/session',{credentials:'same-origin'})).json() as {csrf_token:string};const response=await fetch(`/api/memberships/${encodeURIComponent(membershipId)}/deactivate`,{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':session.csrf_token}});return response.status},ownerId!);
      expect(denial).toBe(403);
    }finally{await adminContext.close()}
  }finally{
    await role.selectOption('MEMBER');
    await member.getByRole('button',{name:'Save role'}).click();
    await expect(member).toContainText('member');
  }
});

test('hosted provider metadata never exposes deterministic identity controls',async({page})=>{
  await page.route('**/api/auth/session',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({authenticated:false})}));
  await page.route('**/api/auth/providers',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:[{profile_id:'entra-qualified',display_label:'External ID email sign-in'}],development_identities:[]})}));
  await page.goto('/');
  await expect(page.getByRole('link',{name:/External ID email sign-in/})).toBeVisible();
  await expect(page.getByText('Local development identities')).toHaveCount(0);
  await expect(page.getByRole('link',{name:'owner'})).toHaveCount(0);
});

test('case owner grants and revokes named private access through the real UI',async({page,browser})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Review synthetic clinical capacity by facility.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();

  await page.getByText('Manage private report access').click();
  await page.getByLabel('Company member').selectOption({label:'Morgan Member · dev-member'});
  await page.getByRole('button',{name:'Grant report access'}).click();
  await expect(page.getByText('dev-member · viewer')).toBeVisible();

  const memberContext=await browser.newContext();
  const memberPage=await memberContext.newPage();
  await signIn(memberPage,'member');
  await expect(memberPage.getByRole('button',{name:new RegExp(request)})).toBeVisible();
  await memberPage.getByRole('button',{name:new RegExp(request)}).click();
  await expect(memberPage.getByLabel('Current business request')).toHaveValue(request);

  await page.getByRole('button',{name:'Revoke'}).click();
  await memberPage.reload();
  await expect(memberPage.getByRole('button',{name:new RegExp(request)})).toHaveCount(0);
  await memberContext.close();
});

test('report step navigation preserves drafts and queued files without making API calls',async({page})=>{
  await signIn(page,'member');
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill('Compare synthetic workshop activity by month.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();
  await page.waitForLoadState('networkidle');
  const calls:string[]=[];
  page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/'))calls.push(request.method()+' '+new URL(request.url()).pathname)});
  const draft='Compare synthetic workshop activity by month. Include site comparisons.';
  await page.getByLabel('Current business request').fill(draft);
  await page.getByRole('button',{name:'Next: Information',exact:true}).click();
  await page.locator('input[type=file]').setInputFiles({name:'synthetic-workshop.csv',mimeType:'text/csv',buffer:Buffer.from('Month,Activity\n2026-01,12\n')});
  await expect(page.locator('.pending-files')).toContainText('synthetic-workshop.csv');
  for(const step of ['Understanding','Confirm','Build','Report']){
    await page.getByRole('button',{name:'Next: '+step,exact:true}).click();
    await expect(page.locator('.wizard-step-heading h2')).toHaveText(step);
    await expect(page.locator('.wizard-step-heading h2')).toBeFocused();
  }
  await expect(page.getByRole('button',{name:'Last step',exact:true})).toBeDisabled();
  for(let step=0;step<5;step++)await page.getByRole('button',{name:'Back',exact:true}).click();
  await expect(page.getByLabel('Current business request')).toHaveValue(draft);
  await expect(page.getByText('Your goal has unsaved changes.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Next: Information',exact:true}).click();
  await expect(page.locator('.pending-files')).toContainText('synthetic-workshop.csv');
  await setAppearance(page,'dark');
  await expect(page.locator('.private-workspace')).toHaveAttribute('data-color-mode','dark');
  expect(calls).toEqual([]);
  await page.reload();
  await expect(page.getByRole('button',{name:'Dark appearance',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.private-workspace')).toHaveAttribute('data-color-mode','dark');
  await setAppearance(page,'system');
});

test('personal appearance has readable core text, system fallback and narrow reflow',async({page},testInfo)=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Administration',exact:true}).click();
  for(const mode of ['light','dark'] as const){
    await setAppearance(page,mode);
    const ratios=await page.locator('.private-workspace').evaluate(element=>{
      const style=getComputedStyle(element);
      const rgb=(name:string)=>{const probe=document.createElement('span');probe.style.color=style.getPropertyValue(name);element.append(probe);const values=getComputedStyle(probe).color.match(/\d+(?:\.\d+)?/g)!.slice(0,3).map(Number);probe.remove();return values};
      const luminance=(values:number[])=>values.map(v=>{const n=v/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);
      const background=luminance(rgb('--surface'));
      return ['--ink','--text-secondary','--muted'].map(name=>{const text=luminance(rgb(name));return (Math.max(text,background)+.05)/(Math.min(text,background)+.05)});
    });
    for(const ratio of ratios)expect(ratio).toBeGreaterThanOrEqual(4.5);
    await expect(page.getByRole('button',{name:'Administration',exact:true})).toHaveCSS('color',mode==='dark'?'rgb(237, 243, 252)':'rgb(25, 40, 63)');
    await page.screenshot({path:testInfo.outputPath('settings-'+mode+'.png'),fullPage:true,animations:'disabled'});
  }
  await setAppearance(page,'system');
  await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
  await expect(page.locator('.private-workspace')).toHaveCSS('color-scheme','dark');
  await page.emulateMedia({colorScheme:'light'});
  await expect(page.locator('.private-workspace')).toHaveCSS('color-scheme','light');
  await page.setViewportSize({width:320,height:800});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.screenshot({path:testInfo.outputPath('settings-320px.png'),fullPage:true,animations:'disabled'});
  await page.setViewportSize({width:1280,height:800});
  await page.locator('.private-workspace').evaluate(element=>{(element as HTMLElement).style.fontSize='200%'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
});

test('Clear Glass mobile navigation is keyboard operable, dismissible and preserves the current draft',async({page})=>{
  await page.setViewportSize({width:320,height:800});
  await page.goto('/');await page.getByText('Local development identities').click();await page.getByRole('link',{name:'member',exact:true}).click();
  const menu=page.locator('.workspace-menu-toggle');
  await expect(menu).toHaveAccessibleName('Open workspace navigation');
  await expect(page.getByRole('navigation',{name:'Workspace sections'})).toBeHidden();
  await menu.focus();await page.keyboard.press('Enter');
  await expect(menu).toHaveAttribute('aria-expanded','true');
  await expect(page.getByRole('navigation',{name:'Workspace sections'})).toBeVisible();
  const create=page.getByRole('navigation',{name:'Workspace sections'}).getByRole('button',{name:'Create report',exact:true});
  await create.focus();await page.keyboard.press('Enter');
  await expect(page.locator('#workspace-main')).toBeFocused();
  await expect(menu).toHaveAttribute('aria-expanded','false');
  await page.getByLabel('Your reporting goal').fill('Synthetic Clear Glass draft survives interrupted navigation.');
  let writes=0;page.on('request',request=>{if(request.method()==='POST'&&new URL(request.url()).pathname.startsWith('/api/'))writes++});
  for(let n=0;n<3;n++){await menu.click();await page.keyboard.press('Escape');await expect(menu).toBeFocused();await expect(menu).toHaveAttribute('aria-expanded','false');}
  await expect(page.getByLabel('Your reporting goal')).toHaveValue('Synthetic Clear Glass draft survives interrupted navigation.');
  await menu.click();await page.setViewportSize({width:1280,height:800});
  await expect(menu).toHaveAttribute('aria-expanded','false');await expect(menu).toBeHidden();
  await expect(page.getByRole('navigation',{name:'Workspace sections'})).toBeVisible();
  await page.setViewportSize({width:320,height:800});await expect(page.getByRole('navigation',{name:'Workspace sections'})).toBeHidden();
  expect(writes).toBe(0);
});

test('Clear Glass has solid readable surfaces, a non-blur fallback and reduced motion',async({page})=>{
  await signIn(page,'owner');await page.getByRole('button',{name:'Administration',exact:true}).click();
  const root=page.locator('.private-workspace');await expect(root).toHaveAttribute('data-theme','clear-glass');
  for(const mode of ['light','dark'] as const){
    await setAppearance(page,mode);
    await expect(page.locator('.tenant-admin-surface>.panel')).toHaveCSS('background-color',mode==='dark'?'rgb(23, 35, 56)':'rgb(255, 255, 255)');
    await expect(page.locator('.tenant-settings-grid fieldset:visible').first()).toHaveCSS('border-radius','18px');
    for(const width of [1280,768,640,320]){
      await page.setViewportSize({width,height:900});
      const clipped=await page.locator('.tenant-section-tabs').evaluate(nav=>{const errors:string[]=[];for(const button of nav.querySelectorAll('button')){const bounds=button.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(button);for(const text of range.getClientRects())if(text.width&&(text.left<bounds.left-1||text.right>bounds.right+1||text.top<bounds.top-1||text.bottom>bounds.bottom+1))errors.push(button.textContent??'section');}return errors});
      expect(clipped).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
  }
  await setAppearance(page,'light');
  // Simulate an engine without backdrop-filter support by removing only its
  // conditional enhancement. The shipped base rules must remain usable.
  await page.evaluate(()=>{for(const sheet of document.styleSheets){for(let n=sheet.cssRules.length-1;n>=0;n--){const rule=sheet.cssRules[n];if(rule instanceof CSSSupportsRule&&rule.conditionText.includes('backdrop-filter'))sheet.deleteRule(n)}}});
  // At narrow widths the transparent utility wrapper places the avatar over the solid compact rail header.
  await expect(page.locator('.workspace-topbar')).toHaveCSS('position','absolute');
  await expect(page.locator('.workspace-topbar')).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
  await expect(page.locator('.workspace-rail')).toHaveCSS('background-color','rgb(244, 248, 255)');
  await page.setViewportSize({width:1280,height:900});
  await expect(page.locator('.workspace-topbar')).toHaveCSS('background-color','rgb(244, 248, 255)');
  await expect(page.locator('.workspace-topbar')).toHaveCSS('backdrop-filter','none');
  await page.emulateMedia({reducedMotion:'reduce'});
  await expect(page.locator('.workspace-rail')).toHaveCSS('backdrop-filter','none');
  const duration=await page.locator('.workspace-rail .rail-link').first().evaluate(element=>getComputedStyle(element).transitionDuration);
  expect(duration).toBe('0s');
});

test('wizard and composer labels fit their controls at narrow widths and with long text',async({page})=>{
  await signIn(page,'member');
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill('Compare synthetic workshop activity across locations.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();
  await page.getByRole('button',{name:'Next: Information',exact:true}).click();
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.keyboard.press('Tab');await page.getByLabel('Add more requirements').focus();await expect(page.getByLabel('Add more requirements')).toHaveCSS('outline-style','solid');
  const assertLabelsFit=async()=>{
    const violations=await page.locator('.report-wizard').evaluate(wizard=>{
      const errors:string[]=[];
      const check=(element:Element,container:Element,label:string)=>{
        const bounds=container.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(element);
        for(const rect of Array.from(range.getClientRects()))if(rect.width>0&&(rect.left<bounds.left-1||rect.right>bounds.right+1||rect.top<bounds.top-1||rect.bottom>bounds.bottom+1))errors.push(label);
      };
      wizard.querySelectorAll('.journey-steps button').forEach(button=>{
        const label=button.querySelector('strong')!;check(label,button,label.textContent??'step');
        if((label as HTMLElement).scrollWidth>(label as HTMLElement).clientWidth+1)errors.push('Clipped step text');
      });
      const button=wizard.querySelector('.message-composer .composer-footer button')!;
      check(button,button,'Composer button text');check(button,button.closest('.message-composer')!,'Composer boundary');
      return [...new Set(errors)];
    });
    expect(violations).toEqual([]);
    expect(await renderedTextContrast(page)).toEqual([]);
  };
  for(const mode of ['light','dark']){
    await setAppearance(page,mode);
    for(const width of [1920,1601,1600,1440,1280,1024,768,701,700,600,550,320]){
      await page.setViewportSize({width,height:900});await assertLabelsFit();
      const wrapped=await page.locator('.journey-steps strong').evaluateAll(labels=>labels.filter(label=>{const range=document.createRange();range.selectNodeContents(label);return range.getClientRects().length>1}).map(label=>label.textContent));
      expect(wrapped).toEqual([]);
    }
  }
  await page.locator('.journey-steps strong').nth(2).evaluate(element=>{element.textContent='Review the detailed report understanding and assumptions'});
  await page.locator('.message-composer .composer-footer button').evaluate(element=>{element.firstChild!.textContent='Add these detailed business requirements to this report '});
  for(const mode of ['light','dark']){
    await setAppearance(page,mode);
    for(const width of [1440,1280,320]){await page.setViewportSize({width,height:900});await assertLabelsFit();}
  }
});


async function renderedTextContrast(page:Page){
  return page.locator('.private-workspace').evaluate(root=>{
    const rgba=(value:string)=>(value.match(/[\d.]+/g)||[]).map(Number);
    const composite=(front:number[],back:number[])=>{const alpha=front[3]??1;return front.slice(0,3).map((value,index)=>value*alpha+back[index]*(1-alpha))};
    const background=(element:Element)=>{const ancestors:Element[]=[];for(let item:Element|null=element;item;item=item.parentElement)ancestors.unshift(item);return ancestors.reduce((back,item)=>composite(rgba(getComputedStyle(item).backgroundColor),back),[255,255,255])};
    const luminance=(color:number[])=>color.map(value=>{const n=value/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
    const errors:string[]=[];const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    while(walker.nextNode()){
      const node=walker.currentNode,element=node.parentElement;
      if(!element||!node.textContent?.trim()||element.closest('[hidden],[aria-hidden="true"],:disabled,script,style,option'))continue;
      const style=getComputedStyle(element),range=document.createRange();range.selectNodeContents(node);
      if(style.visibility==='hidden'||!range.getBoundingClientRect().width)continue;
      const surface=background(element),text=composite(rgba(style.color),surface),a=luminance(text),b=luminance(surface),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      const large=parseFloat(style.fontSize)>=24||parseFloat(style.fontSize)>=18.6667&&parseInt(style.fontWeight)>=700;
      if(ratio<(large?3:4.5))errors.push(`${element.tagName}.${element.className} ${node.textContent?.trim()}: ${ratio.toFixed(2)}:1 (${style.color} on ${surface.join(',')})`);
    }
    return [...new Set(errors)];
  });
}

test('rendered Clear Glass text stays readable across screens, themes, hover and focus',async({page},testInfo)=>{
  await signIn(page,'owner');await page.emulateMedia({reducedMotion:'reduce'});
  const check=async()=>{expect(await renderedTextContrast(page)).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width)};
  for(const scheme of ['light','dark'] as const){
    await page.emulateMedia({colorScheme:scheme,reducedMotion:'reduce'});
    for(const appearance of [scheme,'system']){
      await setAppearance(page,appearance);
      for(const width of [1280,768,320]){
        await page.setViewportSize({width,height:900});
        const navigate=async(name:string)=>{const menu=page.getByRole('button',{name:'Open workspace navigation',exact:true});if(await menu.isVisible())await menu.click();await page.getByRole('navigation',{name:'Workspace sections'}).getByRole('button',{name,exact:true}).click()};
        await navigate('Home');await check();for(const row of await page.locator('.case-row-copy small').all()){const marker=row.locator('span');await expect(marker).toHaveCSS('display','inline')}if(appearance===scheme&&width!==768)await page.screenshot({path:testInfo.outputPath(`home-${scheme}-${width}.png`),fullPage:true});
        await navigate('Create report');await check();if(appearance===scheme&&width!==768)await page.screenshot({path:testInfo.outputPath(`create-${scheme}-${width}.png`),fullPage:true});
        await page.getByRole('button',{name:/^Account menu for /}).click();const logout=page.getByRole('menuitem',{name:'Sign out',exact:true});await logout.hover();await check();await page.keyboard.press('ArrowUp');await expect(logout).toBeFocused();await expect(logout).toHaveCSS('outline-style','solid');await check();await page.keyboard.press('Escape');
        await page.mouse.move(0,0);
        const menu=page.getByRole('button',{name:'Open workspace navigation',exact:true});if(await menu.isVisible())await menu.click();
        await page.getByRole('button',{name:'Administration',exact:true}).click();
        for(const section of ['AI & models','Responses & report standards','Budget & limits','Branding & organisation']){await page.getByRole('navigation',{name:'Tenant Settings sections'}).getByRole('button',{name:section,exact:true}).click();await check();if(section==='AI & models'&&appearance===scheme&&width!==768)await page.screenshot({path:testInfo.outputPath(`settings-${scheme}-${width}.png`),fullPage:true})}
      }
    }
  }
});

async function renderedControlAudit(page:Page){
  return page.locator('.private-workspace').evaluate(root=>{
    const rgba=(value:string)=>(value.match(/[\d.]+/g)||[]).map(Number);
    const over=(front:number[],back:number[])=>front.slice(0,3).map((value,index)=>value*(front[3]??1)+back[index]*(1-(front[3]??1)));
    const background=(element:Element|null)=>{const parents:Element[]=[];for(let item=element;item;item=item.parentElement)parents.unshift(item);return parents.reduce((back,item)=>over(rgba(getComputedStyle(item).backgroundColor),back),[255,255,255])};
    const luminance=(colour:number[])=>colour.map(value=>{const n=value/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
    const contrast=(first:number[],second:number[])=>{const a=luminance(first),b=luminance(second);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
    const visible=(element:Element)=>{const closed=element.closest('details:not([open])');return element.getClientRects().length>0&&getComputedStyle(element).visibility!=='hidden'&&!element.closest('[hidden],[aria-hidden="true"]')&&(!closed||Boolean(closed.querySelector(':scope > summary')?.contains(element)))};
    const errors:string[]=[];
    for(const element of root.querySelectorAll('input:not([type="checkbox"]):not([type="file"]),textarea,select,button.subtle:not(:disabled),.new-report-card button:not(:disabled)')){
      if(!visible(element)||element.matches(':disabled'))continue;
      const style=getComputedStyle(element),outside=background(element.parentElement),fill=background(element);
      // Icon and menu actions are identified by their painted glyph/text, not an enclosing box.
      if(element.matches('.icon-button,[role="menuitem"]')){if(contrast(over(rgba(style.color),fill),fill)<(element.matches('.icon-button')?3:4.5))errors.push('Icon/menu action contrast');continue;}
      const boundary=parseFloat(style.borderTopWidth)>0?contrast(over(rgba(style.borderTopColor),outside),outside):0;
      if(Math.max(boundary,contrast(fill,outside))<3)errors.push(`Control boundary ${element.tagName}.${element.className}`);
      if(element.matches('input[placeholder],textarea[placeholder]')){const placeholder=getComputedStyle(element,'::placeholder');if(contrast(over(rgba(placeholder.color),fill),fill)<4.5)errors.push('Placeholder contrast');}
    }
    const focused=document.activeElement;if(focused&&root.contains(focused)){const style=getComputedStyle(focused);if(style.outlineStyle==='solid'&&contrast(over(rgba(style.outlineColor),background(focused.parentElement)),background(focused.parentElement))<3)errors.push('Focus contrast');}
    const controls=Array.from(root.querySelectorAll('button,a,input:not([type="file"]),textarea,select,summary')).filter(element=>visible(element)&&!element.classList.contains('skip-link'));
    for(let i=0;i<controls.length;i++)for(let j=i+1;j<controls.length;j++){
      const first=controls[i],second=controls[j];if(first.contains(second)||second.contains(first))continue;
      // The account popup intentionally covers page content; this is not a layout collision.
      const aPopup=first.closest('.account-popover'),bPopup=second.closest('.account-popover');if(aPopup!==bPopup&&(aPopup||bPopup))continue;
      const a=first.getBoundingClientRect(),b=second.getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)errors.push(`Overlapping controls ${first.tagName}/${second.tagName}`);
    }
    return [...new Set(errors)];
  });
}

test('tenant presentation variants preserve readable controls, borders and non-overlapping layouts',async({page},testInfo)=>{
  test.setTimeout(90_000);await signIn(page,'owner');await page.emulateMedia({reducedMotion:'reduce'});
  const before=(await (await page.request.get('/api/tenant-settings')).json());
  await expect.poll(()=>page.locator('.private-workspace').evaluate(root=>(root as HTMLElement).style.getPropertyValue('--tenant-primary-original'))).toBe(before.settings.generation_policy.branding.primary.toLowerCase());
  // Fixture only the browser's existing authorized GET response. Persisted
  // settings and report-generation policy are never written by this test.
  const palettes=[{primary:'#17635E',accent:'#2D7D9A'},{primary:'#FFFFFF',accent:'#000000'},{primary:'#000000',accent:'#FFFFFF'},{primary:'#FFFF00',accent:'#FF00FF'},{primary:'#0000FF',accent:'#00FF00'},{primary:'#777777',accent:'#777777'}];
  let palette=palettes[0];
  await page.route('**/api/tenant-settings',async route=>{const response=await route.fetch();const value=await response.json();value.settings.generation_policy.branding={...value.settings.generation_policy.branding,...palette};await route.fulfill({response,json:value})});
  await page.route('**/api/workspace/branding',async route=>{const response=await route.fetch();const value=await response.json();await route.fulfill({response,json:{...value,...palette}})});
  const navigate=async(name:string)=>{const menu=page.getByRole('button',{name:'Open workspace navigation',exact:true});if(await menu.isVisible())await menu.click();if(name==='Administration')await page.getByRole('button',{name,exact:true}).click();else await page.getByRole('navigation',{name:'Workspace sections'}).getByRole('button',{name,exact:true}).click()};
  for(const [index,branding] of palettes.entries()){
    palette=branding;await page.reload();await expect.poll(()=>page.locator('.private-workspace').evaluate(root=>(root as HTMLElement).style.getPropertyValue('--tenant-primary-original'))).toBe(branding.primary.toLowerCase());
    for(const mode of ['light','dark']){
      await setAppearance(page,mode);
      // The visible logo letter is aria-hidden; audit its painted colours too.
      const logoContrast=await page.locator('.rail-brand .brand-mark').evaluate(element=>{
        const style=getComputedStyle(element);
        const luminance=(colour:string)=>{const channels=colour.match(/[\d.]+/g)!.slice(0,3).map(Number).map(channel=>{const value=channel/255;return value<=.04045?value/12.92:((value+.055)/1.055)**2.4});return .2126*channels[0]+.7152*channels[1]+.0722*channels[2]};
        const foreground=luminance(style.color),background=luminance(style.backgroundColor);return (Math.max(foreground,background)+.05)/(Math.min(foreground,background)+.05);
      });
      expect(logoContrast).toBeGreaterThanOrEqual(4.5);
      for(const width of [1280,768,320]){
        await page.setViewportSize({width,height:900});await navigate('Create report');await page.getByLabel('Your reporting goal').fill('Synthetic presentation audit only');
        const create=page.locator('.new-report-card').getByRole('button',{name:/Create report/});await create.hover();await page.keyboard.press('Tab');await create.focus();
        expect(await renderedTextContrast(page)).toEqual([]);expect(await renderedControlAudit(page)).toEqual([]);
        expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        if(index===0||index===3)await page.screenshot({path:testInfo.outputPath(`tenant-${index}-${mode}-${width}.png`),fullPage:true});
        await page.mouse.move(0,0);await navigate('Administration');
        for(const section of ['AI & models','Responses & report standards','Budget & limits','Branding & organisation']){
          await page.getByRole('navigation',{name:'Tenant Settings sections'}).getByRole('button',{name:section,exact:true}).click();
          expect(await renderedTextContrast(page)).toEqual([]);expect(await renderedControlAudit(page)).toEqual([]);
          expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        }
      }
    }
  }
  const after=(await (await page.request.get('/api/tenant-settings')).json());expect(after.version).toBe(before.version);expect(after.settings.generation_policy.branding).toEqual(before.settings.generation_policy.branding);
});

async function syntheticWorkspace(page:Page,role='COMPANY_OWNER',users:'loaded'|'empty'|'error'='loaded'){
  const name='Alexandra Morgan with a long display name',membership='synthetic-'+role;
  const session={authenticated:true,identity:{id:'synthetic-identity',display_name:name},actor:{identity_id:'synthetic-identity',membership_id:membership,company_id:'synthetic-company',display_name:name,role},csrf_token:'synthetic-only',membership_state:'ACTIVE'};
  const record={id:'synthetic-report',company_id:'synthetic-company',creator_membership_id:membership,current_request_version_id:'synthetic-request',version:1,semantic_context_version:1,report_title:'Synthetic sales report',created_at:'2026-10-09T00:00:00Z',updated_at:'2026-10-09T00:00:00Z',current_request:{id:'synthetic-request',sequence:1,request_text:'Compare synthetic sales by month.',created_at:'2026-10-09T00:00:00Z'}};
  const calls:string[]=[];
  const members=[{id:membership,display_name:name,subject:'synthetic-owner-subject',role,active:true},{id:'synthetic-member',display_name:'Taylor Chen',subject:'synthetic-member-subject',role:'MEMBER',active:true},{id:'synthetic-inactive',display_name:'Jordan Lee',subject:'synthetic-inactive-subject',role:'MEMBER',active:false}];
  await page.route('**/api/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;calls.push(request.method()+' '+path);
    if(request.method()!=='GET'){await route.abort();return}
    const body:Record<string,unknown>={'/api/auth/session':session,'/api/auth/providers':{items:[],development_identities:[]},'/api/cases':{items:[record]},'/api/workspace/branding':{version:1,primary:'#17635E',accent:'#2D7D9A'},'/api/memberships':{items:users==='empty'?[]:members},'/api/cases/synthetic-report':{case:record},'/api/cases/synthetic-report/versions':{items:[record.current_request]},'/api/cases/synthetic-report/conversation':{items:[]},'/api/cases/synthetic-report/evidence':{items:[]},'/api/cases/synthetic-report/reference-material':{items:[]},'/api/cases/synthetic-report/acceptance':{interpretation:null,confirmed_contract:null}};
    const failure=path==='/api/memberships'&&users==='error';
    await route.fulfill({status:!failure&&path in body?200:503,contentType:'application/json',body:JSON.stringify(!failure&&path in body?body[path]:{error:{code:'UNAVAILABLE',message:'Synthetic unavailable state'}})});
  });
  await page.goto('/');await expect(page.getByRole('heading',{name:'Your reports',exact:true})).toBeVisible();
  return calls;
}

test('workspace chrome has named appearance icons, bounded geometry and a keyboard account menu',async({page},testInfo)=>{
  test.setTimeout(120_000);const calls=await syntheticWorkspace(page);
  const account=page.getByRole('button',{name:/^Account menu for /});
  for(const mode of ['light','dark'])for(const width of [1440,1024,768,375,320]){
    await page.setViewportSize({width,height:900});await setAppearance(page,mode);
    const geometry=await page.evaluate(()=>{const header=document.querySelector('.workspace-topbar')!,rail=document.querySelector('.workspace-rail')!,avatar=document.querySelector('.account-trigger')!;const h=header.getBoundingClientRect(),r=rail.getBoundingClientRect(),a=avatar.getBoundingClientRect();return {headerRadius:parseFloat(getComputedStyle(header).borderRadius),railRadius:parseFloat(getComputedStyle(rail).borderRadius),gap:h.left-r.right,avatarWithinRail:a.left>=r.left&&a.right<=r.right&&a.top>=r.top&&a.bottom<=r.bottom,overflow:document.documentElement.scrollWidth>innerWidth}});
    expect(geometry.overflow).toBe(false);expect(geometry.railRadius).toBeGreaterThan(0);
    if(width>768){expect(geometry.headerRadius).toBeGreaterThan(0);expect(geometry.gap).toBeGreaterThan(0)}else expect(geometry.avatarWithinRail).toBe(true);
    await account.focus();await page.keyboard.press('ArrowDown');const menu=page.getByRole('menu',{name:'Account',exact:true});const profile=menu.getByRole('menuitem',{name:'My profile',exact:true}),logout=menu.getByRole('menuitem',{name:'Sign out',exact:true});
    await expect(profile,JSON.stringify({mode,width,focus:await page.evaluate(()=>({tag:document.activeElement?.tagName,text:document.activeElement?.textContent,html:document.activeElement?.outerHTML.slice(0,300)}))})).toBeFocused();await page.keyboard.press('ArrowDown');await expect(logout).toBeFocused();await page.keyboard.press('ArrowUp');await expect(profile).toBeFocused();await page.keyboard.press('End');await expect(logout).toBeFocused();await page.keyboard.press('Home');await expect(profile).toBeFocused();
    await expect(page.locator('.account-identity')).toContainText('company owner');
    const icons=await page.locator('.appearance-controls:visible button').evaluateAll(buttons=>buttons.map(button=>{const s=getComputedStyle(button);const channels=(colour:string)=>(colour.match(/[\d.]+/g)??[]).slice(0,3).map(Number);const luminance=(values:number[])=>values.map(value=>{const n=value/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);let parent:Element|null=button;while(parent&&getComputedStyle(parent).backgroundColor==='rgba(0, 0, 0, 0)')parent=parent.parentElement;const a=luminance(channels(s.color)),b=luminance(channels(getComputedStyle(parent!).backgroundColor));return {label:button.getAttribute('aria-label'),tooltip:button.getAttribute('title'),selected:button.getAttribute('aria-pressed'),contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),width:button.getBoundingClientRect().width,height:button.getBoundingClientRect().height}}));
    expect(icons.filter(icon=>icon.selected==='true')).toHaveLength(1);for(const icon of icons){expect(icon.tooltip).toBe(icon.label);expect(icon.contrast).toBeGreaterThanOrEqual(3);expect(icon.width).toBeGreaterThanOrEqual(40);expect(icon.height).toBeGreaterThanOrEqual(40)}
    const popup=await page.locator('.account-popover').boundingBox();expect(popup!.x).toBeGreaterThanOrEqual(0);expect(popup!.x+popup!.width).toBeLessThanOrEqual(width);
    await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(account).toBeFocused();
    await account.click();await page.locator('.workspace-hero h2').click();await expect(menu).toHaveCount(0);
    await account.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Tab');await expect(menu).toHaveCount(0);
    if(width===1440||width===320)await page.screenshot({path:testInfo.outputPath(`chrome-${mode}-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:320,height:900});await account.click();await page.getByRole('button',{name:'Light appearance',exact:true}).focus();await page.keyboard.press('Escape');await expect(account).toBeFocused();
  expect(calls.every(call=>call.startsWith('GET '))).toBe(true);
});

test('user management remains tenant-scoped, truthful in empty/error states and hidden from business roles',async({page},testInfo)=>{
  test.setTimeout(90_000);
  for(const role of ['COMPANY_OWNER','COMPANY_ADMIN','MEMBER','EXPERT']){
    const calls=await syntheticWorkspace(page,role);
    if(role==='MEMBER'||role==='EXPERT'){
      const open=page.getByRole('button',{name:'Open workspace navigation',exact:true});if(await open.isVisible())await open.click();
      await expect(page.getByRole('button',{name:'Administration',exact:true})).toHaveCount(0);await expect(page.getByRole('heading',{name:'User management',exact:true})).toHaveCount(0);expect(calls.some(call=>/memberships|tenant-settings/.test(call))).toBe(false);continue;
    }
    for(const mode of ['light','dark'])for(const width of [1440,1024,768,375,320]){
      await page.setViewportSize({width,height:900});await setAppearance(page,mode);const open=page.getByRole('button',{name:'Open workspace navigation',exact:true});if(await open.isVisible())await open.click();
      await page.getByRole('button',{name:'Administration',exact:true}).click();await page.getByRole('button',{name:'User management',exact:true}).click();
      await expect(page.getByRole('heading',{name:'User management',exact:true})).toBeVisible();await expect(page.getByText('3 users',{exact:true})).toBeVisible();
      const list=page.locator('.membership-list');await expect(list.getByText('Taylor Chen',{exact:true})).toBeVisible();await expect(list.getByText('Deactivated',{exact:true})).toBeVisible();await expect(list.getByText('Provider subject: synthetic-member-subject',{exact:true})).toBeHidden();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);expect(await renderedTextContrast(page)).toEqual([]);expect(await renderedControlAudit(page)).toEqual([]);
      if(width===320)await page.screenshot({path:testInfo.outputPath(`users-${role}-${mode}.png`),fullPage:true});
    }
    await page.locator('html').evaluate(element=>(element as HTMLElement).style.fontSize='200%');expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);await expect(page.getByRole('button',{name:'Refresh users',exact:true})).toBeVisible();await page.locator('html').evaluate(element=>(element as HTMLElement).style.fontSize='');
    expect(calls.every(call=>call.startsWith('GET '))).toBe(true);
  }
  for(const state of ['empty','error'] as const){await syntheticWorkspace(page,'COMPANY_OWNER',state);await page.setViewportSize({width:1440,height:900});await page.getByRole('button',{name:'Administration',exact:true}).click();await page.getByRole('button',{name:'User management',exact:true}).click();await expect(page.getByText(state==='empty'?'No company users were returned. Refresh to check again.':'Users could not be loaded.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Refresh users',exact:true})).toBeEnabled()}
});

test('report wizard keeps meaningful step names and recoverable goal text without redundant action labels',async({page},testInfo)=>{
  test.setTimeout(90_000);const calls=await syntheticWorkspace(page,'MEMBER');await page.locator('.case-row').first().click();await expect(page.getByRole('heading',{name:'Synthetic sales report',exact:true})).toBeVisible();
  const goal=page.getByLabel('Current business request');await goal.fill('Synthetic unsaved goal that must survive UI navigation.');
  for(const mode of ['light','dark'])for(const width of [1440,1024,768,375,320]){
    await page.setViewportSize({width,height:900});await setAppearance(page,mode);const steps=page.getByRole('navigation',{name:'Report steps',exact:true});
    await expect(steps.getByText('Open step',{exact:true})).toHaveCount(0);await expect(steps.getByText('Viewing',{exact:true})).toHaveCount(0);
    for(const label of ['Information','Understanding','Confirm','Build','Report','Goal']){
      const button=steps.getByRole('button',{name:label,exact:true});await button.focus();await page.keyboard.press('Enter');await expect(button).toHaveAttribute('aria-current','step');await expect(steps.locator('[aria-current="step"]')).toHaveCount(1);
      const heading=page.locator('.wizard-step-heading h2');await expect(heading).toBeFocused();await expect(heading).toHaveText(label);
    }
    await expect(goal).toHaveValue('Synthetic unsaved goal that must survive UI navigation.');
    const clipped=await steps.evaluate(nav=>[...nav.querySelectorAll('button')].filter(button=>{const bounds=button.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(button.querySelector('strong')!);return [...range.getClientRects()].some(rect=>rect.width&&(rect.left<bounds.left-1||rect.right>bounds.right+1||rect.top<bounds.top-1||rect.bottom>bounds.bottom+1))}).map(button=>button.textContent));
    expect(clipped).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if(width===320||width===1440)await page.screenshot({path:testInfo.outputPath(`wizard-${mode}-${width}.png`),fullPage:true});
  }
  await page.locator('html').evaluate(element=>(element as HTMLElement).style.fontSize='200%');expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);await expect(goal).toHaveValue('Synthetic unsaved goal that must survive UI navigation.');
  expect(calls.every(call=>call.startsWith('GET '))).toBe(true);expect(calls.some(call=>/automatic-design|understanding\/analyse/.test(call))).toBe(false);
});


test('account menu keyboard actions use existing profile and CSRF sign-out transport',async({page})=>{
 const calls=await syntheticWorkspace(page);const account=page.getByRole('button',{name:/^Account menu for /});await account.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'My profile',exact:true})).toBeVisible();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Alexandra Morgan with a long display name');
 let signedOut=false;await page.route('**/api/auth/logout',async route=>{expect(route.request().method()).toBe('POST');expect(route.request().headers()['x-csrf-token']).toBe('synthetic-only');signedOut=true;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({logged_out:true})})});
 await account.focus();await page.keyboard.press('ArrowUp');await expect(page.getByRole('menuitem',{name:'Sign out',exact:true})).toBeFocused();await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'Sign in to continue',exact:true})).toBeVisible();expect(signedOut).toBe(true);expect(calls.every(call=>call.startsWith('GET '))).toBe(true);
});
