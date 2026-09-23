import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {ApiError,authApi,casesApi,invitationsApi} from './api';

afterEach(()=>vi.unstubAllGlobals());
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
const playwrightCli=fileURLToPath(new URL('../node_modules/@playwright/test/cli.js',import.meta.url));
const inspectPlaywrightConfig=(databaseUrl:string,environment:Record<string,string|undefined>={})=>spawnSync(process.execPath,[playwrightCli,'test','--list'],{
  cwd:fileURLToPath(new URL('..',import.meta.url)),
  encoding:'utf8',
  env:{...process.env,PGHOST:undefined,PGHOSTADDR:undefined,PGPORT:undefined,PGDATABASE:undefined,PGSERVICE:undefined,PGSERVICEFILE:undefined,PGSYSCONFDIR:undefined,APBRA_E2E_DATABASE_URL:databaseUrl,APBRA_E2E_SESSION_SECRET:'synthetic-config-validation-material',APBRA_DATABASE_URL:'postgresql+psycopg://apbra:unused@127.0.0.1:54321/apbra',APBRA_TEST_DATABASE_URL:'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test',...environment},
});

describe('APBRA isolated browser-test configuration',()=>{
  it('admits only the exact loopback apbra_e2e database target',()=>{const result=inspectPlaywrightConfig('postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e');expect(result.status,`${result.stdout}\n${result.stderr}`).toBe(0);expect(result.stdout).toContain('Total: 5 tests')});
  it.each([
    'postgresql+psycopg://apbra:unused@localhost:54321/apbra',
    'postgresql+psycopg://apbra:unused@database.internal:5432/apbra_e2e',
    'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e?host=127.0.0.1',
    'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e?hostaddr=127.0.0.1',
    'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e?dbname=apbra_e2e',
    'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e?port=54322',
    'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e?service=preview',
    'postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e?host=one&host=two',
    'postgresql+psycopg://apbra:unused@127.0.0.1/apbra_e2e',
    'sqlite:///apbra_e2e',
  ])('rejects an unsafe reset target before a browser server starts: %s',(databaseUrl)=>{const result=inspectPlaywrightConfig(databaseUrl),output=`${result.stdout}\n${result.stderr}`;expect(result.status).not.toBe(0);expect(output).toMatch(/locked postgresql\+psycopg driver|explicit loopback PostgreSQL database named apbra_e2e/)});
  it.each(['PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGSERVICE','PGSERVICEFILE','PGSYSCONFDIR'])('rejects inherited %s before a browser server starts',(name)=>{const result=inspectPlaywrightConfig('postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e',{[name]:'preview'}),output=`${result.stdout}\n${result.stderr}`;expect(result.status).not.toBe(0);expect(output).toContain(`Playwright rejects inherited libpq target settings: ${name}.`) });
  it.each([
    ['APBRA_DATABASE_URL','postgresql://apbra:unused@127.0.0.1:54322/apbra_e2e','must be separate'],
    ['APBRA_DATABASE_URL','postgresql://apbra:unused@database.internal:6432/apbra_e2e','must be separate'],
    ['APBRA_DATABASE_URL','postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra?dbname=apbra_e2e','must expose an unambiguous'],
    ['APBRA_TEST_DATABASE_URL','postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_test?host=preview','must expose an unambiguous'],
  ])('rejects an ambiguous or equivalent %s before a browser server starts',(name,value,expected)=>{const result=inspectPlaywrightConfig('postgresql+psycopg://apbra:unused@127.0.0.1:54322/apbra_e2e',{[name]:value}),output=`${result.stdout}\n${result.stderr}`;expect(result.status).not.toBe(0);expect(output).toContain(expected)});
});

describe('APBRA API client',()=>{
  it('derives identity only from the server session and includes same-origin credentials',async()=>{const fetch=vi.fn(async()=>response({authenticated:true,actor:{identity_id:'i',membership_id:'m',company_id:'c',display_name:'Member',role:'MEMBER'},csrf_token:'csrf'}));vi.stubGlobal('fetch',fetch);await expect(authApi.session()).resolves.toMatchObject({authenticated:true,actor:{company_id:'c'}});expect(fetch).toHaveBeenCalledWith('/api/auth/session',expect.objectContaining({credentials:'same-origin'}))});
  it('binds create idempotency and CSRF headers without sending company or role authority',async()=>{const fetch=vi.fn(async()=>response({case:{id:'case-1'}},201));vi.stubGlobal('fetch',fetch);await casesApi.create('Build a report','idem-1','csrf-1');const calls=fetch.mock.calls as unknown as Array<[RequestInfo|URL,RequestInit|undefined]>,[,init]=calls[0];expect(init).toMatchObject({method:'POST',headers:expect.objectContaining({'Idempotency-Key':'idem-1','X-CSRF-Token':'csrf-1'}),body:JSON.stringify({request_text:'Build a report'})});expect(String(init?.body)).not.toMatch(/company|role|membership/)});
  it('sends optimistic expected version and preserves stale conflict meaning',async()=>{const fetch=vi.fn(async()=>response({error:{code:'STALE_VERSION',message:'changed'}},409));vi.stubGlobal('fetch',fetch);await expect(casesApi.update('case/1','Changed',2,'csrf')).rejects.toMatchObject({status:409,code:'STALE_VERSION'});const calls=fetch.mock.calls as unknown as Array<[RequestInfo|URL,RequestInit|undefined]>;expect(calls[0][0]).toBe('/api/cases/case%2F1');expect(calls[0][1]?.body).toBe(JSON.stringify({request_text:'Changed',expected_version:2}))});
  it('grants and revokes named private-case access without sending company authority',async()=>{const fetch=vi.fn(async(input:RequestInfo|URL)=>String(input).endsWith('/revoke')?response({revoked:true}):response({granted:true}));vi.stubGlobal('fetch',fetch);await casesApi.grantAccess('case/1','member/1','VIEWER','csrf');await casesApi.revokeAccess('case/1','member/1','csrf');const calls=fetch.mock.calls as unknown as Array<[RequestInfo|URL,RequestInit|undefined]>;expect(calls[0]).toEqual(['/api/cases/case%2F1/access',expect.objectContaining({method:'POST',headers:expect.objectContaining({'X-CSRF-Token':'csrf'}),body:JSON.stringify({membership_id:'member/1',access_level:'VIEWER'})})]);expect(String(calls[0][1]?.body)).not.toMatch(/company|role/);expect(calls[1][0]).toBe('/api/cases/case%2F1/access/member%2F1/revoke')});
  it('keeps invitation bearer tokens out of paths and submits them only in POST bodies',async()=>{const fetch=vi.fn(async()=>response({invitation:{id:'invite'}}));vi.stubGlobal('fetch',fetch);await invitationsApi.inspect('secret/value');const calls=fetch.mock.calls as unknown as Array<[RequestInfo|URL,RequestInit|undefined]>;expect(calls[0][0]).toBe('/api/invitations/inspect');expect(calls[0][1]).toMatchObject({method:'POST',body:JSON.stringify({token:'secret/value'})})});
  it('issues and revokes invitations through fixed authenticated endpoints',async()=>{const fetch=vi.fn(async(input:RequestInfo|URL)=>String(input).endsWith('/revoke')?response({revoked:true}):response({invitation:{id:'invite-1'},token:'one-time'}));vi.stubGlobal('fetch',fetch);await invitationsApi.issue('dev-uninvited','MEMBER','csrf');await invitationsApi.revoke('invite/1','csrf');const calls=fetch.mock.calls as unknown as Array<[RequestInfo|URL,RequestInit|undefined]>;expect(calls[0]).toEqual(['/api/invitations',expect.objectContaining({method:'POST',headers:expect.objectContaining({'X-CSRF-Token':'csrf'}),body:JSON.stringify({subject:'dev-uninvited',role:'MEMBER'})})]);expect(calls[1][0]).toBe('/api/invitations/invite%2F1/revoke')});
  it('normalizes safe API errors without echoing response bodies',async()=>{vi.stubGlobal('fetch',vi.fn(async()=>response({error:{code:'CASE_NOT_FOUND',message:'Not found'}},404)));await expect(casesApi.get('hidden')).rejects.toEqual(expect.any(ApiError));await expect(casesApi.get('hidden')).rejects.toMatchObject({status:404,code:'CASE_NOT_FOUND',message:'Not found'})});
});
