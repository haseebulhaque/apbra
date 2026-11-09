import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect} from 'vitest';
import {acceptDateDisplay,canonicalTimeZone,formatTenantTimestamp,localTimeCandidates,TenantTime,TimeZoneSelector,tenantTimeZoneOptions,validTimeZone} from './TenantDateTime';

describe('tenant date display',()=>{
 it.each(['Australia/Sydney','Australia/Perth','America/New_York','Europe/London','Asia/Kolkata','Pacific/Auckland','UTC'])('accepts real IANA zone %s',zone=>expect(validTimeZone(zone)).toBe(true));
 it.each(['','Sydney','Australia/Invalid',' Australia/Sydney','UTC+11','+11:00','../../etc/passwd',null,1])('rejects invalid zone %s',zone=>expect(validTimeZone(zone)).toBe(false));
 it('uses DST for each instant and labels the tenant zone and actual UTC offset',()=>{
  expect(formatTenantTimestamp('2026-01-01T00:00:00Z','Australia/Sydney','en-AU')).toContain('11:00:00 GMT+11:00');
  expect(formatTenantTimestamp('2026-07-01T00:00:00Z','Australia/Sydney','en-AU')).toContain('10:00:00 GMT+10:00');
  expect(formatTenantTimestamp('2026-07-01T00:00:00Z','Australia/Perth','en-AU')).toContain('08:00:00 GMT+08:00');
 });
 it('distinguishes repeated wall times by offset',()=>{
  const before=formatTenantTimestamp('2026-11-01T05:30:00Z','America/New_York','en-US'),after=formatTenantTimestamp('2026-11-01T06:30:00Z','America/New_York','en-US');
  expect(before).toContain('01:30:00 GMT-04:00');expect(after).toContain('01:30:00 GMT-05:00');expect(before).not.toBe(after);
 });
 it('changes calendar date across the date line without changing the original instant',()=>{
  expect(formatTenantTimestamp('2026-01-01T00:15:00Z','America/Los_Angeles','en-GB')).toContain('31 Dec 2025');
  expect(formatTenantTimestamp('2026-01-01T00:15:00Z','Pacific/Auckland','en-GB')).toContain('1 Jan 2026');
 });
 it('never guesses UTC for naive legacy timestamps',()=>{
  expect(formatTenantTimestamp('2026-11-01T01:30:00','Australia/Sydney')).toBe('2026-11-01T01:30:00 (time zone not recorded)');
  expect(formatTenantTimestamp('2026-11-01','Australia/Sydney')).toContain('time zone not recorded');
  expect(formatTenantTimestamp('garbageZ','UTC')).toContain('time zone not recorded');
 });
 it('rejects malformed aware timestamps or unknown display zones',()=>{
  expect(formatTenantTimestamp('2026-99-99T00:00:00Z','UTC')).toBe('Invalid recorded date');
  expect(()=>formatTenantTimestamp('2026-01-01T00:00:00Z','invalid')).toThrow(RangeError);
 });
 it('binds preferences to exact tenant and monotonic version',()=>{
  const value={company_id:'tenant-a',version:4,time_zone:'Europe/London'};
  expect(acceptDateDisplay(value,'tenant-a',3)).toBe(true);expect(acceptDateDisplay(value,'tenant-b')).toBe(false);expect(acceptDateDisplay(value,'tenant-a',5)).toBe(false);
  for(const version of [-1,1.5,NaN,Infinity])expect(acceptDateDisplay({...value,version},'tenant-a')).toBe(false);
  expect(acceptDateDisplay({...value,time_zone:'invalid'},'tenant-a')).toBe(false);
  expect(acceptDateDisplay({...value,version:0,time_zone:null},'tenant-a')).toBe(true);
 });
 it('preserves the original timestamp in semantic markup without exposing hidden state',()=>{
  const html=renderToStaticMarkup(<TenantTime value="2026-11-01T05:30:00Z"/>);
  expect(html).toContain('dateTime="2026-11-01T05:30:00Z"');expect(html).toContain('UTC');expect(html).not.toContain('tenant-a');
 });
 it('resolves normal, half-hour and quarter-hour zones exactly',()=>{
  expect(localTimeCandidates('2026-07-01T10:00','Australia/Sydney')).toEqual(['2026-07-01T00:00:00.000Z']);
  expect(localTimeCandidates('2026-07-01T05:30','Asia/Kolkata')).toEqual(['2026-07-01T00:00:00.000Z']);
  expect(localTimeCandidates('2026-07-01T05:45','Asia/Kathmandu')).toEqual(['2026-07-01T00:00:00.000Z']);
 });
 it('rejects nonexistent DST times and exposes both overlap instants',()=>{
  expect(localTimeCandidates('2026-03-08T02:30','America/New_York')).toEqual([]);
  expect(localTimeCandidates('2026-11-01T01:30','America/New_York')).toEqual(['2026-11-01T05:30:00.000Z','2026-11-01T06:30:00.000Z']);
  expect(localTimeCandidates('2026-10-04T02:15','Australia/Lord_Howe')).toEqual([]);
  expect(localTimeCandidates('2026-04-05T01:45','Australia/Lord_Howe')).toEqual(['2026-04-04T14:45:00.000Z','2026-04-04T15:15:00.000Z']);
 });
 it.each(['2026-02-30T10:00','2026-01-01T24:00','garbage','2026-01-01','2026-01-01T01:60'])('rejects malformed local input %s',value=>expect(localTimeCandidates(value,'UTC')).toEqual([]));
});

it('canonicalizes case-insensitive browser input to a real IANA identifier before saving',()=>{expect(canonicalTimeZone('australia/sydney')).toBe('Australia/Sydney');expect(acceptDateDisplay({company_id:'a',version:0,time_zone:'Australia/Sydney'},'a')).toBe(false);expect(formatTenantTimestamp('2026-02-30T00:00:00Z','UTC')).toBe('Invalid recorded date')});

describe('searchable tenant time-zone catalogue',()=>{
 it('offers the browser IANA catalogue rather than a small hardcoded shortlist',()=>{const choices=tenantTimeZoneOptions(new Date('2026-01-15T12:00:00Z'));expect(choices.length).toBeGreaterThan(300);expect(new Set(choices.map(item=>item.zone)).size).toBe(choices.length);expect(choices.find(item=>item.zone==='UTC')?.label).toContain('UTC+00:00');expect(choices.some(item=>item.zone==='Australia/Sydney')).toBe(true)});
 it('computes offsets for the applicable date, including daylight saving and fractional zones',()=>{const jan=tenantTimeZoneOptions(new Date('2026-01-15T12:00:00Z')),jul=tenantTimeZoneOptions(new Date('2026-07-15T12:00:00Z'));expect(jan.find(item=>item.zone==='Australia/Sydney')?.label).toContain('UTC+11:00');expect(jul.find(item=>item.zone==='Australia/Sydney')?.label).toContain('UTC+10:00');expect(jan.find(item=>item.zone==='America/New_York')?.label).toContain('UTC-05:00');expect(jul.find(item=>item.zone==='America/New_York')?.label).toContain('UTC-04:00');expect(jan.some(item=>item.label.startsWith('UTC+05:45'))).toBe(true)});
 it('labels a real editable combobox and does not expose fake selected options in closed state',()=>{const html=renderToStaticMarkup(<TimeZoneSelector value="Australia/Perth" onChange={()=>{}}/>);expect(html).toContain('role="combobox"');expect(html).toContain('aria-expanded="false"');expect(html).toContain('Australia/Perth');expect(html).not.toContain('role="listbox"');expect(html).not.toContain('<datalist')});
});
