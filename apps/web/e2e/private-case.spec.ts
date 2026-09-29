import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page,identity:'owner'|'member'|'uninvited'|'foreign'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
}

test('ordinary invited member creates, saves, refreshes and reopens a private case',async({page})=>{
  await signIn(page,'member');
  await expect(page.getByRole('heading',{name:'Reporting cases',exact:true})).toBeVisible();

  const request='Compare synthetic distribution performance by depot and month.';
  await page.getByLabel('Original business request').fill(request);
  await page.getByRole('button',{name:'Create case'}).click();
  await expect(page.getByText('Reporting case created and saved.')).toBeVisible();
  await expect(page.getByText(request,{exact:true}).first()).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading',{name:'Reporting cases',exact:true})).toBeVisible();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByLabel('Current business request')).toHaveValue(request);

  await page.getByLabel('Current business request').fill(`${request} Include carrier category.`);
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Your updated request was saved.')).toBeVisible();
  await expect(page.getByText('Earlier request versions · 2')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Private case access'})).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('business workspace remains keyboard navigable and contained on a small screen',async({page})=>{
  await page.setViewportSize({width:375,height:812});
  await signIn(page,'member');
  const skip=page.getByRole('link',{name:'Skip to reporting workspace'});
  await skip.focus();
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#workspace-main$/);
  await expect(page.getByRole('navigation',{name:'Workspace sections'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Describe your reporting goal'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await expect(page.getByText('ReportDesign JSON')).toHaveCount(0);
  await page.getByLabel('Original business request').fill('Compare completed synthetic orders by depot.');
  await page.getByRole('button',{name:'Create case'}).click();
  const upload=page.getByLabel('Add CSV or XLSX evidence');
  await upload.focus();
  await expect(upload).toBeFocused();
  await expect(page.locator('label.upload-button')).toHaveCSS('outline-style','solid');
});

test('stale edits are rejected through the UI and reload recovers the current version',async({page,context})=>{
  await signIn(page,'owner');
  const request='Assess synthetic customer retention by segment.';
  await page.getByLabel('Original business request').fill(request);
  await page.getByRole('button',{name:'Create case'}).click();
  await expect(page.getByText('Reporting case created and saved.')).toBeVisible();

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
  await expect(otherTab.getByRole('alert')).toContainText('This case changed in another session. Reload it before saving your changes.');
  await otherTab.getByRole('button',{name:'Reload'}).click();
  await expect(otherTab.getByLabel('Current business request')).toHaveValue(saved);
  await expect(otherTab.getByText('Earlier request versions · 2')).toBeVisible();
});

test('an expired application session is reported truthfully by the protected UI handler',async({page,context})=>{
  await signIn(page,'owner');
  await expect(page.getByRole('heading',{name:'Reporting cases',exact:true})).toBeVisible();

  const sessionControl=await context.newPage();
  await sessionControl.goto('/');
  await sessionControl.getByRole('button',{name:'Sign out'}).click();
  await expect(sessionControl.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();

  await page.getByLabel('Original business request').fill('Review synthetic marketing effectiveness by channel.');
  await page.getByRole('button',{name:'Create case'}).click();
  await expect(page.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();
  await expect(page.getByText('Your APBRA session has expired. Sign in again to continue.')).toBeVisible();
});

test('an invited identity accepts the exact single-use invitation through OIDC and the UI',async({page,browser})=>{
  await signIn(page,'owner');
  await page.getByText('Manage company access').click();
  await page.getByLabel('External subject').fill('dev-uninvited');
  await page.getByLabel('Application role').selectOption('EXPERT');
  await page.getByRole('button',{name:'Issue invitation'}).click();
  const invitationLink=await page.getByLabel('One-time invitation link').inputValue();
  expect(invitationLink).toMatch(/\/invite#token=/);

  const inviteeContext=await browser.newContext();
  const inviteePage=await inviteeContext.newPage();
  await signIn(inviteePage,'uninvited');
  await expect(inviteePage.getByRole('heading',{name:'An invitation is required'})).toBeVisible();

  await inviteePage.goto(invitationLink);
  await expect(inviteePage).not.toHaveURL(/token=/);
  await expect(inviteePage.getByRole('heading',{name:'Accept your invitation'})).toBeVisible();
  await inviteePage.getByRole('button',{name:'Accept invitation'}).click();
  await expect(inviteePage.getByText('Invitation accepted. Your APBRA membership is active.')).toBeVisible();
  await expect(inviteePage.getByRole('heading',{name:'Reporting cases',exact:true})).toBeVisible();
  await inviteeContext.close();
});

test('case owner grants and revokes named private access through the real UI',async({page,browser})=>{
  await signIn(page,'owner');
  const request='Review synthetic clinical capacity by facility.';
  await page.getByLabel('Original business request').fill(request);
  await page.getByRole('button',{name:'Create case'}).click();
  await expect(page.getByText('Reporting case created and saved.')).toBeVisible();

  await page.getByText('Manage private case access').click();
  await page.getByLabel('Company member').selectOption({label:'Morgan Member · dev-member'});
  await page.getByRole('button',{name:'Grant case access'}).click();
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
