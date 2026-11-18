import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,expect,it} from 'vitest';
import {AdminDialog,providerCursorState,ProviderReadPanel,AdminPageHeader,AdminState,AdminTableRegion,Pagination,paginationModel,PAGE_SIZES} from './AdminUI';
import {settingDisplayValue,SettingsHistoryPanel} from './EnterpriseApp';

describe('native administration semantics',()=>{
 it('announces loading without announcing an error or success',()=>{const html=renderToStaticMarkup(<AdminState kind="loading" title="Loading settings"><p>Checking current access.</p></AdminState>);expect(html).toContain('role="status"');expect(html).not.toContain('role="alert"');expect(html).toContain('aria-hidden="true"')});
 it('distinguishes a failed or denied read from a valid empty list',()=>{for(const kind of ['error','denied'] as const)expect(renderToStaticMarkup(<AdminState kind={kind} title="Unavailable"/>)).toContain('role="alert"');const empty=renderToStaticMarkup(<AdminState kind="empty" title="No matching occurrences"/>);expect(empty).not.toContain('role="alert"');expect(empty).not.toContain('role="status"')});
 it('makes an overflowing table region keyboard-reachable with an accessible name',()=>{const html=renderToStaticMarkup(<AdminTableRegion label="Settings version history"><table><caption>Retained versions</caption><tbody><tr><th scope="row">Version 1</th></tr></tbody></table></AdminTableRegion>);expect(html).toContain('role="region"');expect(html).toContain('tabindex="0"');expect(html).toContain('aria-label="Settings version history"');expect(html).toContain('<caption>Retained versions</caption>')});
 it('renders service or user strings as text, never executable markup',()=>{const html=renderToStaticMarkup(<AdminPageHeader title={'<img src="outside.invalid">'} description="<script>unsafe()</script>"/>);expect(html).toContain('&lt;img');expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<img');expect(html).not.toContain('<script>')});
 it('uses a labelled native modal without pretending that server rendering has opened it',()=>{const html=renderToStaticMarkup(<AdminDialog title="Review user change" busy onClose={()=>{}}><p>Current and proposed role.</p></AdminDialog>);expect(html).toContain('<dialog');expect(html).toContain('aria-labelledby=');expect(html).toContain('aria-busy="true"');expect(html).not.toMatch(/\sopen[=>\s]/);expect(html).toContain('disabled=""')});
 it('preserves exact non-secret settings values in the before and after review',()=>{expect(settingDisplayValue(false)).toBe('false');expect(settingDisplayValue(0)).toBe('0');expect(settingDisplayValue('')).toBe('');expect(settingDisplayValue(undefined)).toBe('Unavailable');expect(JSON.parse(settingDisplayValue({name:'A',items:['B']}))).toEqual({name:'A',items:['B']})});
});

describe('record pagination',()=>{
 it('partitions complete collections without duplicates, missing records or invented counts',()=>{
  for(const pageSize of PAGE_SIZES)for(const total of [0,1,9,10,11,25,99,100,101,237]){
   const source=Array.from({length:total},(_,index)=>index),received:number[]=[];
   const first=paginationModel(total,1,pageSize);
   for(let page=1;page<=first.pages;page++){const model=paginationModel(total,page,pageSize);received.push(...source.slice(model.offset,model.end));expect(model.end-model.offset).toBeLessThanOrEqual(pageSize);expect(model.total).toBe(total)}
   expect(received).toEqual(source);
  }
 });
 it('clamps a page after a collection shrinks and describes empty results accurately',()=>{
  expect(paginationModel(23,3,10)).toMatchObject({page:3,start:21,end:23,pages:3});
  expect(paginationModel(5,3,10)).toMatchObject({page:1,start:1,end:5,pages:1});
  expect(paginationModel(0,3,10)).toMatchObject({page:1,start:0,end:0,pages:1});
 });
 it('keeps page-number controls bounded for very large collections',()=>{
  const model=paginationModel(1_000_000,50_000,10);expect(model.numbers).toEqual([1,49_999,50_000,50_001,100_000]);
 });
 it('rejects invalid or imprecise pagination values instead of fabricating a count',()=>{
  for(const total of [-1,NaN,Infinity,1.5,Number.MAX_SAFE_INTEGER+1])expect(()=>paginationModel(total,1,10)).toThrow(RangeError);
  for(const page of [0,-1,NaN,1.5])expect(()=>paginationModel(10,page,10)).toThrow(RangeError);
  expect(()=>paginationModel(10,1,20 as 10)).toThrow(RangeError);
 });
 it('exposes all four sizes, numbered navigation, live counts and honest empty controls',()=>{
  const html=renderToStaticMarkup(<Pagination label="Users" total={0} page={1} pageSize={10} onPage={()=>{}} onPageSize={()=>{}}/>);
  for(const size of PAGE_SIZES)expect(html).toContain(`value="${size}"`);
  expect(html).toContain('0–0 of 0');expect(html).toContain('Page 1 of 1');expect(html).toContain('aria-label="Users pagination"');expect(html).not.toContain('aria-current="page"');expect(html).toContain('Previous users page');expect(html).toContain('Next users page');
 });
 it('starts the actual settings history collapsed and renders only ten of its retained versions',()=>{
  const items=Array.from({length:23},(_,index)=>({id:`version-${23-index}`,version:23-index,created_at:'2026-11-05T00:00:00+00:00',changed_keys:[],safe_changes:{},restored_from_version_id:null,current:index===0,validation_status:'PASS'}));
  const html=renderToStaticMarkup(<SettingsHistoryPanel items={items} scope="tenant-a:owner-a" onRefresh={()=>{}} onRestore={()=>{}}/>);
  expect(html).toContain('<details class="admin-settings-history">');expect(html).not.toMatch(/<details[^>]*\sopen(?:=|\s|>)/);expect(html.match(/<th scope="row">Version /g)).toHaveLength(10);expect(html).toContain('1–10 of 23');expect(html).toContain('Page 1 of 3');expect(html).not.toContain('<th scope="row">Version 1</th>');
 });
});


describe('provider read panel initial boundary',()=>{
 it('never fetches automatically or claims an empty source before a read',()=>{let calls=0;const html=renderToStaticMarkup(<ProviderReadPanel title="Agents" scope="tenant:member:settings" expectedVersion={4} kind="agents" load={async()=>{calls++;throw Error('Must not auto fetch')}}/>);expect(calls).toBe(0);expect(html).toContain('Read metadata');expect(html).not.toContain('No records returned');expect(html).not.toContain('Page 1');for(const size of PAGE_SIZES)expect(html).toContain(`value="${size}"`);expect(html).toContain('does not verify report-generation permission')});
 it('distinguishes current file observations from content or full history',()=>{const html=renderToStaticMarkup(<ProviderReadPanel title="Files" scope="tenant:member:store" expectedVersion={4} kind="files" load={async()=>{throw Error('No IO')}}/>);expect(html).toContain('not file content or a complete revision, deletion or audit history');expect(html).not.toContain('Save');expect(html).not.toContain('Delete')});
});


describe('provider cursor navigation',()=>{
 it('accepts a known successor when going back, revisiting a page or refreshing',()=>{const cursors=[undefined,'next-1','next-2'];expect(providerCursorState(cursors,0,'next-1',true)).toEqual(cursors);expect(providerCursorState(cursors,1,'next-2',true)).toEqual(cursors)});
 it('discards stale later page markers when the successor changes or pages end',()=>{expect(providerCursorState([undefined,'old-1','old-2'],0,'new-1',true)).toEqual([undefined]);expect(providerCursorState([undefined,'next-1','next-2'],1,null,false)).toEqual([undefined,'next-1'])});
 it('rejects missing markers and loops back to current or earlier pages',()=>{for(const next of [null,'next-1','next-2'])expect(()=>providerCursorState([undefined,'next-1','next-2'],2,next,true)).toThrow();expect(()=>providerCursorState([undefined],0,null,true)).toThrow()});
});
