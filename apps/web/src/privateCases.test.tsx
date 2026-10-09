import {providerAuthenticationLabel} from './EnterpriseApp';
import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {ApiError,type CaseRecord} from './api';
import {CaseEditor,CaseList,ReportCreationWizard,personalColorMode,tenantPresentationTokens,presentationContrast,CompanyCreationForm,CompanySelection,SignedOut,clearedCompanyContext,companyCreationErrorMessage,profileErrorMessage,protectedErrorMessage} from './privateCases';

const record:CaseRecord={id:'case-1',company_id:'company-1',creator_membership_id:'member-1',current_request_version_id:'request-2',version:2,semantic_context_version:1,created_at:'2026-09-23T00:00:00Z',updated_at:'2026-09-23T01:00:00Z',current_request:{id:'request-2',sequence:2,request_text:'Updated business request',created_at:'2026-09-23T01:00:00Z'}};

it('renders a truthful signed-out boundary without company or role inputs',()=>{const html=renderToStaticMarkup(<SignedOut providers={{items:[{profile_id:'entra-test',display_label:'External ID email sign-in'}],development_identities:[]}}/>);expect(html).toContain('Sign in to continue');expect(html).toContain('checks active company membership and private-case access');expect(html).toContain('External ID email sign-in');expect(html).not.toMatch(/company id|select role|Local development identities/i)});
it('shows deterministic identity choices only when the server lists them',()=>{const html=renderToStaticMarkup(<SignedOut providers={{items:[{profile_id:'local-test',display_label:'Local development identity'}],development_identities:['owner','member']}}/>);expect(html).toContain('Local development identities');expect(html).toContain('identity=owner');expect(html).not.toContain('uninvited')});
it('offers bounded company creation without browser-authored authority or initial settings',()=>{const html=renderToStaticMarkup(<CompanyCreationForm name="Example Workspace" onName={()=>{}} onCreate={()=>{}} busy={false}/>);expect(html).toContain('Company or workspace name');expect(html).toContain('Create Company / Workspace');expect(html).toContain('does not verify legal or domain ownership');expect(html).not.toMatch(/name="(?:identity|issuer|subject|role|company_id|tenant_id|provider|settings|domain)"/)});
it('distinguishes duplicate company display names by immutable company identity',()=>{const html=renderToStaticMarkup(<CompanySelection companies={[{membership_id:'member-a',company_id:'company-aaaa',name:'Example Workspace'},{membership_id:'member-b',company_id:'company-bbbb',name:'Example Workspace'}]} busy={false} onSelect={()=>{}}/>);expect(html.match(/Example Workspace/g)).toHaveLength(2);expect(html).toContain('Workspace ID: company-aaaa');expect(html).toContain('Workspace ID: company-bbbb');expect(html).not.toContain('member-a')});
it('scrubs all report content and draft state before a company context transition',()=>{expect(clearedCompanyContext()).toEqual({active:null,versions:[],draft:'',cases:[],view:'home',caseReportReady:false,newRequest:''})});
it('disables empty or busy company creation and exposes safe retry errors',()=>{const blank=renderToStaticMarkup(<CompanyCreationForm name="   " onName={()=>{}} onCreate={()=>{}} busy={false}/>),busy=renderToStaticMarkup(<CompanyCreationForm name="Example" onName={()=>{}} onCreate={()=>{}} busy/>);expect(blank).toMatch(/button[^>]*disabled=""/);expect(busy).toContain('Creating company…');expect(busy).toMatch(/button[^>]*disabled=""/);expect(companyCreationErrorMessage(new ApiError(422,'COMPANY_NAME_INVALID','internal'))).toContain('Enter a company name');expect(companyCreationErrorMessage(new ApiError(409,'COMPANY_CREATION_NOT_AVAILABLE','internal'))).toContain('access changed');expect(companyCreationErrorMessage(new ApiError(409,'IDEMPOTENCY_CONFLICT','internal'))).toContain('already used');expect(companyCreationErrorMessage(new ApiError(500,'INTERNAL','sensitive'))).not.toContain('sensitive')});
it('does not echo profile validation or internal errors',()=>{expect(profileErrorMessage(new ApiError(422,'PROFILE_INVALID','internal claim'))).toContain('Enter a display name');expect(profileErrorMessage(new ApiError(500,'INTERNAL','sensitive detail'))).not.toContain('sensitive detail')});
it('renders only supplied authorized case summaries with a clear selected state',()=>{const html=renderToStaticMarkup(<CaseList items={[record]} activeId="case-1" onOpen={()=>{}}/>);expect(html).toContain('Updated business request');expect(html).toContain('Request v2');expect(html).toContain('Reports available to your current membership.');expect(html).toContain('aria-current="page"')});
it('makes an empty workspace actionable without claiming a report exists',()=>{const html=renderToStaticMarkup(<CaseList items={[]} onOpen={()=>{}}/>);expect(html).toContain('No reports in progress');expect(html).toContain('Start with a business question');expect(html).not.toContain('aria-current="page"')});
it('renders immutable request history separately from the editable current request',()=>{const html=renderToStaticMarkup(<CaseEditor record={record} versions={[{id:'request-1',sequence:1,request_text:'Original business request',created_at:'2026-09-23T00:00:00Z'},record.current_request]} requestText={record.current_request.request_text} onRequestText={()=>{}} onSave={()=>{}} onRefresh={()=>{}} busy={false}/>);expect(html).toContain('Original business request');expect(html).toContain('Updated business request');expect(html).toContain('Earlier request versions · 2');expect(html).toContain('require a fresh confirmation');expect(html).not.toContain('expected_version')});
it('does not disclose whether a protected foreign or private report exists',()=>{expect(protectedErrorMessage(new ApiError(404,'CASE_NOT_FOUND','hidden'))).toBe('That report is unavailable or you no longer have access.');expect(protectedErrorMessage(new ApiError(401,'AUTH_REQUIRED','expired'))).toContain('session has expired');expect(protectedErrorMessage(new ApiError(409,'STALE_VERSION','stale'))).toContain('changed in another session')});

it('opens the wizard at Goal and distinguishes viewing a step from completing an action',()=>{
  const html=renderToStaticMarkup(<ReportCreationWizard goal={<p>Saved business goal</p>}>{step=><p>Saved journey view: {step}</p>}</ReportCreationWizard>);
  expect(html).toContain('aria-label="Report steps"');
  expect(html.match(/aria-current="step"/g)).toHaveLength(1);
  expect(html).toContain('Step 1 of 6');
  expect(html).toContain('Next: Information');
  expect(html).toMatch(/button[^>]*disabled=""[^>]*>Back/);
  expect(html).toContain('<div hidden=""><p>Saved journey view: information</p></div>');
  expect(html).toContain('Use each step’s action to save, review, confirm or build.');
  expect(html).not.toContain('Complete');
});
it('keeps an unsaved reporting goal visible as a warning without claiming it was saved',()=>{
  const html=renderToStaticMarkup(<ReportCreationWizard hasUnsavedGoal goal={<p>Draft business question</p>}>{()=>null}</ReportCreationWizard>);
  expect(html).toContain('Your goal has unsaved changes.');
  expect(html).toContain('save the new version before reviewing the updated requirements');
});
it('bounds personal appearance to light, dark or system',()=>{
  expect(personalColorMode('light')).toBe('light');
  expect(personalColorMode('dark')).toBe('dark');
  expect(personalColorMode('system')).toBe('system');
  for(const value of ['arbitrary',null,{},'DARK'])expect(personalColorMode(value)).toBe('system');
});

it('derives readable presentation variants without mutating tenant branding',()=>{
  const colours=['#17635E','#2D7D9A','#FFFFFF','#000000','#FFFF00','#00FF00','#FF0000','#0000FF','#FF00FF','#777777','#EDF2FA','#172338'];
  for(const primary of colours)for(const accent of colours){
    const branding=Object.freeze({primary,accent});const tokens=tenantPresentationTokens(branding) as Record<string,string>;
    expect(tokens['--tenant-primary-original']).toBe(primary.toLowerCase());expect(tokens['--tenant-accent-original']).toBe(accent.toLowerCase());
    for(const dark of [false,true]){
      const mode=dark?'dark':'light',surfaces=dark?['#101927','#172338','#1c2b43']:['#f4f7fd','#ffffff','#edf2fa'];
      const token=(name:string)=>tokens[`--tenant-${name}-${mode}`];
      for(const surface of surfaces){
        expect(presentationContrast(token('brand'),surface)).toBeGreaterThanOrEqual(3);
        expect(presentationContrast(token('hover'),surface)).toBeGreaterThanOrEqual(3);
        expect(presentationContrast(token('link'),surface)).toBeGreaterThanOrEqual(4.5);
        expect(presentationContrast(token('focus'),surface)).toBeGreaterThanOrEqual(3);
      }
      for(const fill of ['brand','hover'])expect(presentationContrast(token(fill),token('on-brand'))).toBeGreaterThanOrEqual(4.5);
      expect(presentationContrast(token('soft'),dark?'#edf3fc':'#19283f')).toBeGreaterThanOrEqual(4.5);
    }
    expect(branding).toEqual({primary,accent});
  }
});
it('rejects CSS-shaped colour values and uses bounded presentation fallbacks',()=>{
  const tokens=tenantPresentationTokens({primary:'url(https://example.invalid)',accent:'red;display:none'}) as Record<string,string>;
  expect(tokens['--tenant-primary-original']).toBe('#245de5');expect(tokens['--tenant-accent-original']).toBe('#245de5');
  expect(Object.values(tokens).every(value=>/^#[\da-f]{6}$/.test(value))).toBe(true);
});

it('distinguishes the Entra-only configured agent route from protected legacy keys',()=>{
 expect(providerAuthenticationLabel('FOUNDRY_AGENT_RESPONSES')).toContain('Microsoft Entra server identity');
 expect(providerAuthenticationLabel('OPENAI_CHAT_COMPATIBLE')).toBe('Protected provider credential');
});
