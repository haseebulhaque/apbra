import {afterEach,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {NativeAgentCheck} from './NativeAgentCheck';
import {savedAzureApi} from './api';
afterEach(()=>vi.unstubAllGlobals());
it('requires explicit readiness and never sends on mount; describes the answer truthfully',()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
 const html=renderToStaticMarkup(<NativeAgentCheck caseId="synthetic-case" contextVersion={2} csrfToken="synthetic-csrf" onSaved={()=>{}} onError={()=>{}}/>);
 expect(fetch).not.toHaveBeenCalled();expect(html).toContain('Send once to agent');expect(html).toMatch(/button type="button" disabled=""[^>]*>Send once/);expect(html).toContain('does not confirm requirements or create a report artifact');
});
it('blocks checks when a goal edit is unsaved',()=>{
 const html=renderToStaticMarkup(<NativeAgentCheck caseId="synthetic-case" contextVersion={2} csrfToken="synthetic-csrf" unsavedGoal onSaved={()=>{}} onError={()=>{}}/>);
 expect(html).toContain('Save your edited goal');expect(html.match(/disabled=""/g)).toHaveLength(3);expect(html).toMatch(/select[^>]*disabled=""/);
});
it('sends only the existing native command with CSRF and optimistic bindings, no formatting overrides',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({native_response:{}})});vi.stubGlobal('fetch',fetch);
 await savedAzureApi.receive('case/one',2,'settings-two','command-three','synthetic-csrf');
 expect(fetch).toHaveBeenCalledTimes(1);const [url,options]=fetch.mock.calls[0];expect(url).toBe('/api/cases/case%2Fone/native-response-checks');expect(options.method).toBe('POST');expect(options.headers['X-CSRF-Token']).toBe('synthetic-csrf');expect(JSON.parse(options.body)).toEqual({expected_context_version:2,expected_settings_id:'settings-two',command_key:'command-three'});
});
