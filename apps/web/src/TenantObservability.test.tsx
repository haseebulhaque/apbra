import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {ApiError,type ProcessingError} from './api';
import {HistoryFacts,ReportErrorHistory,TenantObservability,historyReadError} from './TenantObservability';
const occurrence:ProcessingError={id:'event-1',occurred_at:'2026-10-15T12:00:00Z',module:'Reports',operation:'generation',outcome:'FAILED',actor_id:'actor-1',target_type:'report',target_id:'case-1',support_reference:'11111111-1111-4111-8111-111111111111',category:'PROCESSING_FAILED',message:'The operation could not be completed.',correlation_id:'22222222-2222-4222-8222-222222222222',case_id:'case-1',source_kind:'generation',source_id:'attempt-1',technical:{diagnostic:{exception_type:'RuntimeError',frames:[{module:'safe.module',function:'safe_function',line:10}]},truncated:true}};
it('business report facts omit administrative diagnostics even if a server supplies them',()=>{
 const html=renderToStaticMarkup(<HistoryFacts record={occurrence}/>);expect(html).toContain(occurrence.support_reference);expect(html).toContain('Copy support reference');expect(html).not.toMatch(/safe\.module|safe_function|RuntimeError|Redacted technical|Open affected report/);
});
it('administrative details expose bounded diagnostics and an explicitly authorized report-open callback',()=>{
 const html=renderToStaticMarkup(<HistoryFacts record={occurrence} technical onOpenReport={()=>{}}/>);expect(html).toContain('Redacted technical diagnostics');expect(html).toContain('safe_function');expect(html).toContain('Diagnostic frames were bounded');expect(html).toContain('Open affected report');
});
it('escapes untrusted safe messages and audit details rather than rendering markup',()=>{
 const html=renderToStaticMarkup(<HistoryFacts record={{...occurrence,message:'<script>bad()</script>'} as ProcessingError}/>);expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<script>');
 const {support_reference,category,message,correlation_id,case_id,source_kind,source_id,technical,...audit}=occurrence;void [support_reference,category,message,correlation_id,case_id,source_kind,source_id,technical];
 const rendered=renderToStaticMarkup(<HistoryFacts record={{...audit,details:{action:'<script>bad()</script>'},details_withheld:true}}/>);expect(rendered).toContain('&lt;script&gt;');expect(rendered).toContain('Private details are withheld.');expect(rendered).not.toContain('Copy support reference');
});
it('keeps important activity separate from persistent processing failures and offers bounded search navigation',()=>{
 const audit=renderToStaticMarkup(<TenantObservability kind="audit" companyId="company-1" membershipId="member-1" onError={()=>{}}/>),errors=renderToStaticMarkup(<TenantObservability kind="errors" companyId="company-1" membershipId="member-1" onError={()=>{}}/>);
 expect(audit).toContain('Tenant audit history');expect(audit).toContain('Important company activity');expect(audit).not.toContain('Support reference');expect(errors).toContain('Tenant error history');expect(errors).toContain('Support reference');expect(errors).not.toMatch(/export|delete|resolve error|retention/i);expect(errors).toContain('From (UTC)');expect(errors).toContain('Reset history search');
});
it('does not mount report history while its retained report workspace is hidden',()=>{expect(renderToStaticMarkup(<ReportErrorHistory companyId="c" membershipId="m" caseId="r" visible={false} onError={()=>{}}/>)).toBe('')});
it('never reflects error messages into history read failures or confirms private record existence',()=>{
 for(const status of [401,403,404,409,422,500])expect(historyReadError(new ApiError(status,'INTERNAL','secret raw content'))).not.toContain('secret');expect(historyReadError(new ApiError(403,'X','x'))).toBe(historyReadError(new ApiError(404,'Y','y')));expect(historyReadError(new Error('sensitive stack'))).toBe('History could not be loaded. Retry the read.');
});

it('offers only outcomes accepted by the history backend',()=>{
 const html=renderToStaticMarkup(<TenantObservability kind="audit" companyId="company-1" membershipId="member-1" onError={()=>{}}/>);
 const outcome=html.match(/<select aria-label="Outcome"[^>]*>(.*?)<\/select>/)?.[1]??'';
 expect([...outcome.matchAll(/<option(?: value="[^"]*")?[^>]*>([^<]*)<\/option>/g)].map(match=>match[1])).toEqual(['All outcomes','SUCCEEDED','FAILED','REJECTED','UNSPECIFIED']);
});

it('labels persisted timestamps with their supplied offset',()=>{const html=renderToStaticMarkup(<HistoryFacts record={{...occurrence,occurred_at:'2026-10-15T10:00:00+10:00'}}/>);expect(html).toContain('Time (with UTC offset)');expect(html).toContain('2026-10-15T10:00:00+10:00');expect(html).not.toContain('Time (UTC)')});

it('keeps report history closed until an explicit read is requested',()=>{const html=renderToStaticMarkup(<ReportErrorHistory companyId="c" membershipId="m" caseId="r" visible onError={()=>{}}/>);expect(html).toContain('Show report error history');expect(html).toContain('aria-expanded="false"');expect(html).not.toMatch(/Search history|Loading history|From \(UTC\)|role="alert"/)});

it('shows captured HTTP facts and cause stack only in administrative technical details',()=>{
 const record:ProcessingError={...occurrence,technical:{diagnostic:{exception_type:'AnalysisAttemptFailed',frames:[],provider:{http_status:403,http_reason:'Forbidden',provider_code:'PermissionDenied',request_id:'cd493a40-07f1-43bf-94e8-c144b31fa603',provider_message_redacted:true,response_received:true},causes:[{exception_type:'ProviderCallError',frames:[{module:'model_provider',function:'structured',line:1400}]}]},truncated:false}};
 const admin=renderToStaticMarkup(<HistoryFacts record={record} technical/>),business=renderToStaticMarkup(<HistoryFacts record={record}/>);
 expect(admin).toContain('HTTP status');expect(admin).toContain('403');expect(admin).toContain('PermissionDenied');expect(admin).toContain('cd493a40-07f1-43bf-94e8-c144b31fa603');expect(admin).toContain('ProviderCallError');expect(admin).toContain('model_provider');expect(admin).not.toContain('[object Object]');expect(admin).toContain('withheld to protect private content');
 expect(business).not.toMatch(/PermissionDenied|cd493a40|ProviderCallError|model_provider|HTTP status/);
});

it('shows only retained public parameter facts and withholding notices in admin details',()=>{
 const record:ProcessingError={...occurrence,technical:{diagnostic:{exception_type:'AnalysisAttemptFailed',frames:[],provider:{http_status:400,provider_param:'text.format',provider_target:'max_output_tokens',provider_message_redacted:true,provider_code_redacted:true,provider_type_redacted:false,provider_param_redacted:false,provider_target_redacted:false}},truncated:false}};
 const admin=renderToStaticMarkup(<HistoryFacts record={record} technical/>),business=renderToStaticMarkup(<HistoryFacts record={record}/>);
 expect(admin).toContain('Provider parameter');expect(admin).toContain('text.format');expect(admin).toContain('Provider target');expect(admin).toContain('max_output_tokens');expect(admin).toContain('Unrecognized provider code, type or parameter identifiers were withheld');expect(business).not.toMatch(/text\.format|max_output_tokens|Provider parameter|Unrecognized provider/);
});


it('renders the retained non-sensitive invalid-parameter message alongside structured facts',()=>{
 const record:ProcessingError={...occurrence,technical:{diagnostic:{exception_type:'AnalysisAttemptFailed',frames:[],provider:{http_status:400,provider_type:'invalid_request_error',provider_message:'Invalid parameter.',provider_message_redacted:false,provider_param:'text.format',provider_target:'max_output_tokens'}},truncated:false}};
 const admin=renderToStaticMarkup(<HistoryFacts record={record} technical/>),business=renderToStaticMarkup(<HistoryFacts record={record}/>);
 expect(admin).toContain('Invalid parameter.');expect(admin).toContain('text.format');expect(admin).toContain('max_output_tokens');expect(admin).not.toContain('message contained unrecognized free text');expect(business).not.toContain('Invalid parameter.');
});
