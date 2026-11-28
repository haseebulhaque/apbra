import {expect, test, type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';

// Local inbox pages contain synthetic bearer links. They must never appear in a trace or video.
test.use({trace: 'off', screenshot: 'off', video: 'off'});

const phrase = 'Synthetic orchard river compass 617!';

async function submitForm(page: Page, endpoint: string, expected: number) {
  const result=page.waitForResponse(r=>new URL(r.url()).pathname===endpoint && r.request().method()==='POST');
  const button=page.locator('form button[type="submit"]').first();
  await button.focus();
  await page.keyboard.press('Enter');
  expect((await result).status()).toBe(expected);
}

async function openMessage(page: Page,email: string,purpose: string) {
  await page.goto('/__demo/inbox');
  const row=page.getByRole('listitem').filter({has:page.getByText(email,{exact:true})});
  const link=row.getByRole('link',{name:purpose,exact:true}).first();
  await link.focus();
  await page.keyboard.press('Enter');
  await expect.poll(()=>new URL(page.url()).pathname).toBe(purpose==='Verify email'?'/account':'/invitation');
  await expect.poll(()=>Boolean(new URL(page.url()).hash)).toBe(false);
}

async function signup(page:Page,email:string,fromInvitation=false) {
  if(fromInvitation) await page.getByRole('button',{name:'Create an account',exact:true}).click();
  else {
    await page.goto('/account');
    await page.getByRole('navigation',{name:'Account access'}).getByRole('button',{name:'Create account'}).click();
  }
  await page.getByLabel('Email address',{exact:true}).fill(email);
  if(fromInvitation){
    await page.getByLabel('Password',{exact:true}).fill('short');
    await page.locator('form button[type="submit"]').first().click();
    await expect(page.getByRole('alert')).toContainText('Use at least 15 characters');
    await expect(page.getByRole('region',{name:'Account email help'})).toHaveCount(0);
  }
  await page.getByLabel('Password',{exact:true}).fill(phrase);
  await submitForm(page,'/api/password/signup',202);
  await expect(page.getByRole('link',{name:'Open local test inbox'})).toHaveAttribute('href','/__demo/inbox');
  await expect(page.getByText(/Check your spam folder/)).toHaveCount(0);
  await openMessage(page,email,'Verify email');
  await page.getByLabel('Password',{exact:true}).fill(phrase);
  await submitForm(page,'/api/password/verify',200);
}

async function signin(page:Page,email:string) {
  await page.getByLabel('Email address',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill(phrase);
  await submitForm(page,'/api/password/signin',200);
}

async function userManagement(page:Page) {
  const nav=page.getByRole('button',{name:'Open workspace navigation',exact:true});
  await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
  if((page.viewportSize()?.width??1280)<=768)await nav.click();
  await page.getByRole('button',{name:'Administration',exact:true}).click();
  const destination=page.getByRole('navigation',{name:'Administration sections',exact:true}).getByRole('button',{name:'User management',exact:true});
  if(!await destination.isVisible())await page.getByRole('button',{name:/^Administration sections/}).click();
  await destination.click();
  await expect(page.getByRole('heading',{name:'Invite a colleague'})).toBeVisible();
}

for(const journey of ['verified colleague','new colleague on mobile'] as const) {
  test(journey+' explicitly joins only the intended organisation through captured mail',async({browser,baseURL})=>{
    test.setTimeout(70_000);
    const mobile=journey==='new colleague on mobile';
    const view=mobile?{width:320,height:800}:{width:1280,height:850};
    const a=await browser.newContext({baseURL,viewport:view}),b=await browser.newContext({baseURL,viewport:view});
    try {
      const owner=await a.newPage(), colleague=await b.newPage();
      const tag=randomUUID().slice(0,8), issuer='owner-'+tag+'@example.org', target='colleague-'+tag+'@example.org';
      const organisation='Orchard '+tag;
      await signup(owner,issuer);
      await signin(owner,issuer);
      await owner.getByRole('button',{name:'Create organisation',exact:true}).click();
      await owner.getByLabel('Organisation name').fill(organisation);
      await submitForm(owner,'/api/password/organisation',201);
      await userManagement(owner);
      if(!mobile)await signup(colleague,target);
      await owner.getByLabel('Colleague email').fill(target);
      await owner.getByLabel('Invitation role').selectOption('MEMBER');
      await submitForm(owner,'/api/native-invitations',201);
      await expect(owner.getByText(target,{exact:true})).toBeVisible();
      await openMessage(colleague,target,'Review invitation');
      if(mobile) {
        await signup(colleague,target,true);
        await signin(colleague,target);
        await expect(colleague.getByRole('button',{name:'Create organisation',exact:true})).toBeVisible();
        await openMessage(colleague,target,'Review invitation');
      } else {
        // Opening the account page in another tab refreshes its HttpOnly pre-auth challenge.
        // The original invitation form must obtain a current challenge when it submits.
        await expect(colleague.getByLabel('Email address',{exact:true})).toBeEnabled();
        const secondTab=await b.newPage();
        await secondTab.goto('/account');
        await expect(secondTab.getByLabel('Email address',{exact:true})).toBeEnabled();
        await secondTab.close();
        await signin(colleague,target);
      }
      const review=colleague.getByRole('button',{name:'Review invitation',exact:true});
      await review.focus();
      await colleague.keyboard.press('Enter');
      await expect(colleague.getByRole('heading',{name:organisation})).toBeVisible();
      const accept=colleague.getByRole('button',{name:'Accept invitation',exact:true});
      await expect(accept).toBeFocused();
      // Inspection and navigation alone have created no workspace access.
      expect((await b.request.get('/api/cases')).status()).toBe(401);
      expect(await colleague.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await colleague.keyboard.press('Enter');
      await expect(colleague.getByText('Invitation accepted.',{exact:true})).toBeVisible();
      await colleague.getByRole('button',{name:'Open organisation'}).focus();
      await colleague.keyboard.press('Enter');
      await expect.poll(()=>new URL(colleague.url()).pathname).toBe('/');
      await expect(colleague.getByRole('heading',{name:'Your reports'})).toBeVisible();
      await owner.reload();
      await userManagement(owner);
      const userTable=owner.getByRole('region',{name:'Company users table'});
      const invitedRow=userTable.getByRole('row').filter({has:owner.getByText(target,{exact:true})});
      await expect(invitedRow.getByRole('button',{name:'Deactivate '+target,exact:true})).toBeVisible();
      const actor=(await (await b.request.get('/api/auth/session')).json()).actor;
      expect(actor.company_name).toBe(organisation); expect(actor.role).toBe('MEMBER');
      await colleague.reload();
      expect((await (await b.request.get('/api/auth/session')).json()).actor.membership_id).toBe(actor.membership_id);
      expect(await (await b.request.get('/api/cases')).json()).toEqual({items:[]});
      await openMessage(colleague,target,'Review invitation');
      await colleague.getByRole('button',{name:'Review invitation',exact:true}).click();
      await expect(colleague.getByText('Invitation accepted.',{exact:true})).toBeVisible();
      await colleague.reload();
      await expect(colleague.getByText(/Open the original invitation link/)).toBeVisible();
    } finally {await b.close();await a.close()}
  });
}

test('revocation and account binding protect private reports when a colleague already owns another organisation',async({browser,baseURL})=>{
  test.setTimeout(70_000);
  const ownerContext=await browser.newContext({baseURL}),readerContext=await browser.newContext({baseURL});
  try {
    const owner=await ownerContext.newPage(),reader=await readerContext.newPage();
    const tag=randomUUID().slice(0,8);
    const issuer='isolated-owner-'+tag+'@example.org',target='isolated-reader-'+tag+'@example.org';
    const company='Orchard '+tag,otherCompany='Garden '+tag;
    async function start(page:Page,email:string,name:string) {
      await signup(page,email);await signin(page,email);
      await page.getByRole('button',{name:'Create organisation',exact:true}).click();
      await page.getByLabel('Organisation name').fill(name);
      await submitForm(page,'/api/password/organisation',201);
      await expect(page.getByRole('heading',{name:'Your reports'})).toBeVisible();
      const session=await (await page.request.get('/api/auth/session')).json();
      const response=await page.request.post('/api/cases',{data:{request_text:'Private report for '+name},
        headers:{'X-CSRF-Token':session.csrf_token,'Idempotency-Key':randomUUID()}});
      expect(response.status()).toBe(201);
      return (await response.json()).case.id as string;
    }
    let releaseInitial!:()=>void;
    const holdInitial=new Promise<void>(resolve=>{releaseInitial=resolve});
    await owner.route('**/api/native-invitations',async route=>{
      if(route.request().method()==='GET')await holdInitial;
      await route.continue();
    });
    const ownerPrivate=await start(owner,issuer,company),previousPrivate=await start(reader,target,otherCompany);
    try {
      await userManagement(owner);
      await expect(owner.getByRole('button',{name:'Refresh invitations'})).toBeDisabled();
      await expect(owner.getByRole('button',{name:'Send invitation'})).toBeDisabled();
    } finally { releaseInitial() }
    await expect(owner.getByRole('button',{name:'Refresh invitations'})).toBeEnabled();
    await owner.unroute('**/api/native-invitations');
    async function send() {
      await owner.getByLabel('Colleague email').fill(target);
      await submitForm(owner,'/api/native-invitations',201);
    }
    await send();
    // A different signed-in account can open local mail but cannot inspect a colleague's grant.
    const wrong=await ownerContext.newPage();await openMessage(wrong,target,'Review invitation');
    await wrong.getByRole('button',{name:'Review invitation',exact:true}).click();
    await expect(wrong.getByRole('alert')).toContainText('unavailable for this account');
    await expect(wrong.getByRole('button',{name:'Accept invitation'})).toHaveCount(0);
    await wrong.close();
    const revoke=owner.getByRole('button',{name:'Revoke invitation for '+target});
    await revoke.click();await expect(owner.getByText('Invitation revoked.',{exact:true})).toBeVisible();
    await openMessage(reader,target,'Review invitation');await reader.getByRole('button',{name:'Review invitation',exact:true}).click();
    await expect(reader.getByRole('alert')).toContainText('unavailable for this account');
    await send();await openMessage(reader,target,'Review invitation');
    await reader.getByRole('button',{name:'Review invitation',exact:true}).click();
    await expect(reader.getByRole('heading',{name:company})).toBeVisible();
    await reader.getByRole('button',{name:'Accept invitation',exact:true}).click();
    await reader.getByRole('button',{name:'Open organisation'}).click();
    await expect(reader.getByRole('heading',{name:'Your reports'})).toBeVisible();
    const session=await (await reader.request.get('/api/auth/session')).json();
    expect(session.actor.company_name).toBe(company);expect(session.actor.role).toBe('MEMBER');
    expect(await (await reader.request.get('/api/cases')).json()).toEqual({items:[]});
    for(const id of [ownerPrivate,previousPrivate])expect([403,404]).toContain((await reader.request.get('/api/cases/'+id)).status());
    await reader.reload();await expect(reader.getByRole('heading',{name:'Your reports'})).toBeVisible();
    await expect(reader.getByText('Private report for '+otherCompany)).toHaveCount(0);
    await reader.getByRole('button',{name:/^Account menu for /}).click();
    await reader.getByRole('menuitem',{name:'Sign out',exact:true}).click();
    await expect.poll(async()=>(await reader.request.get('/api/cases')).status()).toBe(401);
  }finally{await readerContext.close();await ownerContext.close()}
});
