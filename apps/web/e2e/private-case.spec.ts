import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page,identity:'owner'|'member'|'uninvited'|'foreign'){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:identity,exact:true}).click();
}

test('ordinary invited member creates, saves, refreshes and reopens a private case',async({page})=>{
  await signIn(page,'member');
  await expect(page.getByRole('heading',{name:'Clarity starts with a question.'})).toBeVisible();
  await expect(page.locator('main').getByRole('button',{name:'Create report'})).toHaveCount(1);
  await page.getByRole('button',{name:'Create report'}).first().click();

  const request='Compare synthetic distribution performance by depot and month.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Compare synthetic distribution performance by depot and month'})).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading',{name:'Clarity starts with a question.'})).toBeVisible();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByLabel('Current business request')).toHaveValue(request);

  await page.getByLabel('Current business request').fill(`${request} Include carrier category.`);
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Your updated request was saved.')).toBeVisible();
  await expect(page.getByText('Earlier request versions · 2')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Private report access'})).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
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
  const upload=page.getByRole('button',{name:'Add data sources or reference material'});
  await upload.focus();
  await expect(upload).toBeFocused();
  await expect(page.locator('label.upload-button')).toBeVisible();
  await expect(page.locator('.journey-steps li.unavailable')).toHaveCount(5);
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
  await expect(page.getByRole('heading',{name:'Clarity starts with a question.'})).toBeVisible();
  await page.getByRole('button',{name:'Create report'}).first().click();

  const sessionControl=await context.newPage();
  await sessionControl.goto('/');
  await sessionControl.getByRole('button',{name:'Sign out'}).click();
  await expect(sessionControl.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();

  await page.getByLabel('Your reporting goal').fill('Review synthetic marketing effectiveness by channel.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByRole('heading',{name:'Sign in to continue'})).toBeVisible();
  await expect(page.getByText('Your APBRA session has expired. Sign in again to continue.')).toBeVisible();
});

test('an invited identity accepts the exact single-use invitation through OIDC and the UI',async({page,browser})=>{
  await signIn(page,'owner');
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByText('Manage company access').click();
  await page.getByLabel('External subject').fill('dev-uninvited');
  await page.getByLabel('Application role').selectOption('EXPERT');
  await page.getByRole('button',{name:'Issue invitation'}).click();
  const invitationLink=await page.getByLabel('One-time invitation link').inputValue();
  expect(invitationLink).toMatch(/\/invite#token=/);

  const inviteeContext=await browser.newContext();
  const inviteePage=await inviteeContext.newPage();
  await signIn(inviteePage,'uninvited');
  await expect(inviteePage.getByRole('heading',{name:'Create Company / Workspace'})).toBeVisible();
  await expect(inviteePage.getByRole('button',{name:'Create Company / Workspace (not yet available)'})).toBeDisabled();

  await inviteePage.goto(invitationLink);
  await expect(inviteePage).not.toHaveURL(/token=/);
  await expect(inviteePage.getByRole('heading',{name:'Accept your invitation'})).toBeVisible();
  await inviteePage.getByRole('button',{name:'Accept invitation'}).click();
  await expect(inviteePage.getByText('Invitation accepted. Your APBRA membership is active.')).toBeVisible();
  await expect(inviteePage.getByRole('heading',{name:'Clarity starts with a question.'})).toBeVisible();
  await inviteeContext.close();
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
