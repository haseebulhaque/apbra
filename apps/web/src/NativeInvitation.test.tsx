import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {NativeInvitation, invitationProof, nativeRoleName} from './NativeInvitation';

afterEach(() => vi.unstubAllGlobals());

describe('Native invitation links', () => {
  const sample = 'z'.repeat(64);
  it('recognises a single dedicated proof and rejects ambiguous or unrelated fragments', () => {
    expect(invitationProof('#native_invitation='+sample)).toBe(sample);
    for (const hash of ['', '#proof='+sample, '#native_invitation=short',
      '#native_invitation='+sample+'&account_action=verify',
      '#native_invitation='+sample+'&native_invitation='+sample]) {
      expect(invitationProof(hash)).toBeNull();
    }
  });
  it('offers the original email when the proof was lost on reload', () => {
    vi.stubGlobal('location', {hash:''});
    const markup=renderToStaticMarkup(<NativeInvitation/>);
    expect(markup).toContain('Open the original invitation link');
    expect(markup).not.toContain('Accept invitation');
  });
  it('checks the current account without placing the bearer or an automatic accept action in the page', () => {
    vi.stubGlobal('location', {hash:'#native_invitation='+sample});
    const markup=renderToStaticMarkup(<NativeInvitation/>);
    expect(markup).toContain('Checking your account');
    expect(markup).not.toContain(sample);
    expect(markup).not.toContain('Accept invitation');
    expect(nativeRoleName('COMPANY_ADMIN')).toBe('Company admin');
    expect(nativeRoleName('EXPERT')).toBe('Expert');
  });
});
