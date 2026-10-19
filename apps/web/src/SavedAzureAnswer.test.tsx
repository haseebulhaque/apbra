import {afterEach,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {SavedAnswerText,FileHandoffFacts,SavedAzureAnswer,SavedContractAction} from './SavedAzureAnswer';
import {savedAzureApi,type NativeAnswer,type CaseFileAvailability} from './api';
const answer:NativeAnswer={receipt_id:'receipt-1',context_version:2,texts:['# Original\n<script>bad()</script>\n[link](https://secret.invalid?token=private)\n  spacing  '],bytes:123,sha256:'a'.repeat(64)};
afterEach(()=>vi.unstubAllGlobals());
it('shows verbatim text as escaped inert text without links or lifecycle claims',()=>{
 const html=renderToStaticMarkup(<SavedAnswerText caseId="case-1" answer={answer} currentContext={3}/>);
 expect(html).toContain('# Original\n&lt;script&gt;bad()&lt;/script&gt;');expect(html).toContain('\n  spacing  ');expect(html).not.toContain('<script>');expect(html).not.toContain('href="https://secret');expect(html).toContain('earlier report context');expect(html).toContain('does not confirm requirements, generate a report or validate an artifact');expect(html).toContain('/api/cases/case-1/native-response-receipts/receipt-1');expect(html).toContain('Download original Azure response (.bin)');expect(html).not.toContain('dangerouslySetInnerHTML');
});
it('keeps original download available when assistant text is absent',()=>{
 const html=renderToStaticMarkup(<SavedAnswerText caseId="case-1" answer={{...answer,texts:[]}} currentContext={2}/>);expect(html).toContain('No assistant text');expect(html).toContain('Download original');
});
it('offers lazy read actions and never dispatches during render',()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch);const html=renderToStaticMarkup(<SavedAzureAnswer caseId="case-1" contextVersion={3} onError={()=>{}}/>);expect(html).toContain('Show saved answers');expect(html).toContain('Check complete file handoff');expect(fetch).not.toHaveBeenCalled();expect(html).not.toMatch(/Generate|Retry analysis/);
});
it('states blocked file route and preserves the distinction between transport and processing',()=>{
 const value:CaseFileAvailability={ready:false,reason:'COMPLETE_FILE_HANDOFF_UNAVAILABLE',scope:'CURRENT_REQUEST_VERSION',request_version_id:'r',context_version:3,settings_id:'s',input_characters:null,input_limit:5000,files:[{id:'x',filename:'<img src=x onerror=bad()>.xlsx',status:'UNAVAILABLE',reason:'QUALIFIED_FILE_INPUT_OR_TOOL_REQUIRED',transport:'NONE',contentDigest:'a'.repeat(64),serviceFileUploaded:false,processingVerified:false}]};const html=renderToStaticMarkup(<FileHandoffFacts value={value}/>);expect(html).toContain('Complete file handoff is unavailable');expect(html).toContain('qualified file input or a file tool');expect(html).toContain('does not prove that the agent processed every row');expect(html).toContain('&lt;img');expect(html).not.toContain('<img');
});
it('saved-answer API makes only scoped GET reads and keeps original download separate',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[]})});vi.stubGlobal('fetch',fetch);await savedAzureApi.list('case/one');await savedAzureApi.view('case/one','receipt/two');await savedAzureApi.input('case/one');expect(fetch.mock.calls.map(call=>call[0])).toEqual(['/api/cases/case%2Fone/native-response-receipts','/api/cases/case%2Fone/native-response-receipts/receipt%2Ftwo/view','/api/cases/case%2Fone/native-response-input']);for(const call of fetch.mock.calls)expect(call[1].method??'GET').toBe('GET');expect(fetch).toHaveBeenCalledTimes(3);
});

it('describes ready binary image bytes without calling them UTF8 CSV source',()=>{
 const value:CaseFileAvailability={ready:true,reason:null,scope:'CURRENT_REQUEST_VERSION',request_version_id:'r',context_version:3,settings_id:'s',input_characters:100,input_limit:5000,files:[{id:'x',filename:'synthetic.png',status:'READY',reason:null,transport:'INLINE_ORIGINAL_IMAGE',contentDigest:'a'.repeat(64),serviceFileUploaded:false,processingVerified:false}]};const html=renderToStaticMarkup(<FileHandoffFacts value={value}/>);expect(html).toContain('Original image bytes can be sent as image input.');expect(html).not.toContain('Complete UTF-8 source can be included');expect(html).toContain('not service file uploads');
});

it('native contract intake is explicit and performs no request on render',()=>{const fetch=vi.fn();vi.stubGlobal('fetch',fetch);const html=renderToStaticMarkup(<SavedContractAction caseId="synthetic" receiptId="receipt" currentContext={2} csrfToken="synthetic-csrf" onError={()=>{}}/>);expect(fetch).not.toHaveBeenCalled();expect(html).toContain('Inspect saved contract');expect(html).not.toContain('Validate and use saved');expect(html).toContain('send no provider request')});
it('intake sends only the receipt scope, CSRF and optimistic bindings, never candidate edits',async()=>{const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({accepted:true})});vi.stubGlobal('fetch',fetch);await savedAzureApi.intake('case/one','receipt/two',2,'settings-id','synthetic-csrf');const [url,options]=fetch.mock.calls[0];expect(url).toBe('/api/cases/case%2Fone/native-response-receipts/receipt%2Ftwo/contract');expect(JSON.parse(options.body)).toEqual({expected_context_version:2,expected_settings_id:'settings-id'});expect(options.headers['X-CSRF-Token']).toBe('synthetic-csrf')});

it('unsaved edits prevent saved-contract inspection and intake',()=>{const fetch=vi.fn();vi.stubGlobal('fetch',fetch);const html=renderToStaticMarkup(<SavedContractAction caseId="synthetic" receiptId="receipt" currentContext={2} csrfToken="synthetic-csrf" unsavedGoal onError={()=>{}}/>);expect(html).toContain('Save your edited goal');expect(html).toMatch(/button disabled=""[^>]*>Inspect saved contract/);expect(fetch).not.toHaveBeenCalled()});

it('shows only closed saved-contract code/path diagnostics and retains original',async()=>{
 const {nativeContractDiagnosticMessage:format}=await import('./SavedAzureAnswer');
 expect(format({code:'MODEL_GROUNDING_INVALID',phase:'NATIVE_CONTRACT',findings:[{path:'/standardsApplied/0/citation',reason:'CITATION_NOT_OBSERVED'}]})).toBe(' Saved contract diagnostic: MODEL_GROUNDING_INVALID at /standardsApplied/0/citation (CITATION_NOT_OBSERVED). The original answer is retained.');
 expect(format({code:'PRIVATE_CANARY',phase:'NATIVE_CONTRACT',findings:[]})).toBe('');
 expect(format({code:'MODEL_GROUNDING_INVALID',phase:'PRIVATE_CANARY',findings:[]})).toBe('');
 expect(format({code:'MODEL_GROUNDING_INVALID',phase:'NATIVE_CONTRACT',findings:[{path:'/PRIVATE_CANARY',reason:'PRIVATE_CANARY'}]})).not.toContain('PRIVATE_CANARY');
 expect(format(null)).toBe('');
});
