import {afterEach,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {RequestOutputs} from './RequestOutputs';
import {requestOutputsApi} from './api';
afterEach(()=>vi.unstubAllGlobals());
it('makes no calls on mount and describes unverified opaque custody',()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
 const html=renderToStaticMarkup(<RequestOutputs caseId="case" contextVersion={1} csrfToken="synthetic" onError={()=>{}}/>);
 expect(fetch).not.toHaveBeenCalled();expect(html).toContain('ZIP files remain unopened');expect(html).toContain('has not verified report completeness');expect(html).toMatch(/disabled=""[^>]*>Save generated file/);expect(html).not.toContain('Save selected answer output');
});
it('disables writes for an unsaved goal while keeping history available',()=>{
 const html=renderToStaticMarkup(<RequestOutputs caseId="case" contextVersion={1} csrfToken="synthetic" receiptId="receipt" unsavedGoal onError={()=>{}}/>);
 expect(html).toContain('Save your edited goal');expect(html.match(/disabled=""/g)).toHaveLength(3);expect(html).toContain('Show saved output files');
});
it('sends opaque original file bytes with CSRF and explicit request bindings',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({})});vi.stubGlobal('fetch',fetch);
 const file=new File(['unverified synthetic bytes'],'A & B.zip');
 await requestOutputsApi.upload('case/one',file,3,'synthetic-command','synthetic-csrf');
 expect(fetch).toHaveBeenCalledTimes(1);const [path,init]=fetch.mock.calls[0];expect(path).toContain('/case%2Fone/outputs?');expect(new URLSearchParams(path.split('?')[1]).get('filename')).toBe('A & B.zip');expect(init.body).toBe(file);expect(init.headers['X-CSRF-Token']).toBe('synthetic-csrf');expect(init.headers['Content-Type']).toBe('application/octet-stream');expect(init.credentials).toBe('same-origin');
});
it('uses the saved native receipt without triggering provider or compiler routes',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({})});vi.stubGlobal('fetch',fetch);
 await requestOutputsApi.saveNative('case','receipt/id',3,'command','csrf');
 const [path,init]=fetch.mock.calls[0];expect(path).toBe('/api/cases/case/native-response-receipts/receipt%2Fid/output');expect(JSON.parse(init.body)).toEqual({expected_context_version:3,command_key:'command'});expect(fetch).toHaveBeenCalledTimes(1);
 expect(requestOutputsApi.download('case/one','output/id')).toBe('/api/cases/case%2Fone/outputs/output%2Fid/download');
});
it('lists saved response file references without provider dispatch and saves only a receipt index',async()=>{
 const {nativeFilesApi}=await import('./api');const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[]})});vi.stubGlobal('fetch',fetch);
 await nativeFilesApi.list('case/one','receipt/two');
 expect(fetch.mock.calls[0][0]).toBe('/api/cases/case%2Fone/native-response-receipts/receipt%2Ftwo/files');expect(fetch.mock.calls[0][1].method).toBeUndefined();
 await nativeFilesApi.save('case/one','receipt/two',2,3,'command-four','synthetic-csrf');
 const [path,init]=fetch.mock.calls[1];expect(path).toBe('/api/cases/case%2Fone/native-response-receipts/receipt%2Ftwo/files/2/output');expect(init.headers['X-CSRF-Token']).toBe('synthetic-csrf');expect(JSON.parse(init.body)).toEqual({expected_context_version:3,command_key:'command-four'});expect(fetch).toHaveBeenCalledTimes(2);
});
