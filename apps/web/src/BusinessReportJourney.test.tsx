import {afterEach,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {BusinessReportJourney,canConfirmAIUnderstanding,currentAIUnderstanding,isCurrentV10Report,v10ReportSource} from './BusinessReportJourney';
import {verifiedReportDownload,type AcceptanceState,type CaseRecord,type RequestOutput} from './api';
const record:CaseRecord={id:'case',company_id:'tenant',creator_membership_id:'owner',current_request_version_id:'request',version:1,semantic_context_version:3,created_at:'2026-11-04T00:00:00Z',updated_at:'2026-11-04T00:00:00Z',current_request:{id:'request',sequence:1,request_text:'Explain costs.',created_at:'2026-11-04T00:00:00Z'}};
const state:AcceptanceState={confirmed_contract:null,interpretation:{id:'ai',state:'READY_FOR_CONFIRMATION',current:true,context_version:3,confirmation_summary:{objective:'AI goal',businessQuestions:[],kpiDefinitions:[],scopeAndTime:[],dimensionsAndFilters:[],lifecycleDefinitions:[],materialPolicyDecisions:[]},interpretation:{assumptions:['AI uncertainty']},questions:[],unresolved_ambiguities:['Uncertainty'],simulation:'QUALIFIED_SERVER_MODEL'}};
it('offers a business journey without technical compiler/provider controls',()=>{const html=renderToStaticMarkup(<BusinessReportJourney record={record} csrfToken="csrf" actorRole="COMPANY_OWNER" goal={<p>Saved goal once</p>} onContextChanged={()=>{}} onReportReady={()=>{}} onError={()=>{}}/>);for(const title of ['Goal','Supporting information','Understanding','Confirm','Generate','Download'])expect(html).toContain(`<strong>${title}</strong>`);expect(html).not.toMatch(/ReportDesign compiler|Ask the configured agent|Saved Azure answer|Send once to agent|Show report error history/);expect(html).toContain('Saved goal once');});
it('new requests go to information without repeating goal entry',()=>{const html=renderToStaticMarkup(<BusinessReportJourney record={record} csrfToken="csrf" actorRole="COMPANY_OWNER" initialInformation goal={<p>Saved goal</p>} onContextChanged={()=>{}} onReportReady={()=>{}} onError={()=>{}}/>);expect(html).toContain('Step 2 of 6');expect(html).toContain('Review my requirements with AI');});
it('does not call simulator output AI',()=>{expect(currentAIUnderstanding(state,3)).toBe(true);expect(currentAIUnderstanding({...state,interpretation:{...state.interpretation!,simulation:'LOCAL_DETERMINISTIC_NO_MODEL_CALL'}},3)).toBe(false);});
it('accepts no-question AI-ready understanding despite visible uncertainty',()=>{expect(canConfirmAIUnderstanding(state,3,true,false)).toBe(true);});
it('requires current reviewed understanding, saved goal and AI-required answers',()=>{for(const [version,reviewed,unsaved] of [[4,true,false],[3,false,false],[3,true,true]] as const)expect(canConfirmAIUnderstanding(state,version,reviewed,unsaved)).toBe(false);expect(canConfirmAIUnderstanding({interpretation:null,confirmed_contract:null},3,true,false)).toBe(false);for(const required of [false,true])expect(canConfirmAIUnderstanding({...state,interpretation:{...state.interpretation!,questions:[{id:'q',required,question:'AI question',reason:'AI reason',suggestions:[],allowFreeText:true}]}},3,true,false)).toBe(!required);});

it('explains that supporting information is optional in the business journey',()=>{const html=renderToStaticMarkup(<BusinessReportJourney record={record} csrfToken="csrf" actorRole="COMPANY_OWNER" initialInformation goal={<p>Saved goal</p>} onContextChanged={()=>{}} onReportReady={()=>{}} onError={()=>{}}/>);expect(html).toContain('Supporting information is optional. AI will review your saved goal and ask for any details it needs.');expect(html).not.toContain('Confirmation requires a qualified data source');});

const original:RequestOutput={
 id:'file',case_id:record.id,request_version_id:record.current_request_version_id,
 context_version:record.semantic_context_version,filename:'Work Orders.zip',origin:'NATIVE_OUTPUT',
 v10_provenance:'OFFLINE_FIXTURE',native_task:'FULL_REPORT_ARTIFACT',delivery_kind:'V10_REPORT_ORIGINAL',content_verification:'PACKAGE_CHECKED',
 native_receipt_id:'report-receipt',bytes:3,sha256:'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
 created_at:record.created_at,
};
it('requires the current request, report purpose, qualified original and matched receipt',()=>{
 expect(isCurrentV10Report(original,record,'report-receipt')).toBe(true);
 expect(isCurrentV10Report(original,record,'analysis-receipt')).toBe(false);
 for(const override of [
  {case_id:'other'},{request_version_id:'older'},{context_version:2},{context_version:4},
  {native_task:'REPORT_DESIGN'},{native_task:'REQUIREMENT_ANALYSIS'},{native_receipt_id:null},
  {delivery_kind:'V10_SUPPORTING_ORIGINAL'},{delivery_kind:'GENERATED_FILE'},
  {origin:'MANUAL_UPLOAD'},{content_verification:'NOT_RUN'},{bytes:0},{sha256:'not-a-checksum'},
 ] satisfies Partial<RequestOutput>[]){
  expect(isCurrentV10Report({...original,...override},record)).toBe(false);
 }
});
it('distinguishes verified live service metadata from an offline fixture and fails closed for unknown provenance',()=>{
 expect(v10ReportSource('OFFLINE_FIXTURE')).toMatch(/Synthetic.*offline test fixture/);
 expect(v10ReportSource('LIVE_METADATA_VERIFIED')).toMatch(/Verified service records identify Foundry v10/);
 expect(isCurrentV10Report({...original,v10_provenance:'LIVE_METADATA_VERIFIED'},record)).toBe(true);
 for(const provenance of [undefined,null,'LIVE','offline_fixture']){
  expect(v10ReportSource(provenance)).toBeNull();
  const wireFile=JSON.parse(JSON.stringify({...original,v10_provenance:provenance}));
  expect(isCurrentV10Report(wireFile,record)).toBe(false);
 }
});
afterEach(()=>vi.unstubAllGlobals());
it('checks authenticated download bytes against the retained size and SHA-256',async()=>{
 const get=vi.fn(async()=>new Response('abc',{status:200}));
 vi.stubGlobal('fetch',get);
 expect(await (await verifiedReportDownload(record.id,original)).text()).toBe('abc');
 expect(get).toHaveBeenCalledWith('/api/cases/case/outputs/file/download',expect.objectContaining({credentials:'same-origin',redirect:'error',cache:'no-store'}));
 for(const override of [{bytes:4},{sha256:'0'.repeat(64)}]){
  await expect(verifiedReportDownload(record.id,{...original,...override})).rejects.toMatchObject({code:'REPORT_DIGEST_MISMATCH'});
 }
 get.mockImplementation(async()=>new Response(null,{status:403}));
 await expect(verifiedReportDownload(record.id,original)).rejects.toMatchObject({status:403});
});
