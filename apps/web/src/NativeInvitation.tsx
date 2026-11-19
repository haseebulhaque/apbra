import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {PasswordAccount} from './PasswordAccount';
import {ApiError, authApi, nativeInvitationsApi, passwordCommand, type NativeInviteResult} from './api';

export function invitationProof(fragment: string): string | null {
  const params = new URLSearchParams(fragment.replace(/^#/, ''));
  const values = params.getAll('native_invitation');
  return values.length === 1 && Array.from(params.keys()).length === 1 &&
    /^[A-Za-z0-9_-]{40,200}$/.test(values[0]) ? values[0] : null;
}

export function nativeRoleName(role: string) {
  return ({MEMBER:'Member', EXPERT:'Expert', COMPANY_ADMIN:'Company admin'} as Record<string,string>)[role] ?? role;
}

export function NativeInvitation() {
  const [proof,setProof] = useState(() => invitationProof(location.hash));
  const [signedIn,setSignedIn] = useState<boolean|null>(null);
  const [mode,setMode] = useState<'signin'|'signup'>('signin');
  const [view,setView] = useState<NativeInviteResult|null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const active = useRef(true), generation = useRef(0), pending = useRef(false);
  const acceptButton = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    active.current = true;
    function readLink() {
      if (!location.hash) return;
      const next = invitationProof(location.hash);
      history.replaceState(history.state, '', location.pathname + location.search);
      generation.current++;
      setView(null); setError(''); setProof(next); setBusy(false); pending.current=false;
    }
    readLink();
    window.addEventListener('hashchange', readLink);
    return () => {active.current=false; generation.current++; window.removeEventListener('hashchange',readLink)};
  },[]);
  useEffect(() => {
    let live=true;
    document.title='Organisation invitation · APBRA';
    fetch('/api/password/session',{credentials:'same-origin',cache:'no-store',redirect:'error'})
      .then(async r=>{if(!r.ok)throw Error();return r.json()})
      .then(v=>{if(live)setSignedIn(v.authenticated===true)})
      .catch(()=>{if(live)setError('Account access is unavailable. Reload this page to try again.')});
    return ()=>{live=false};
  },[]);
  useEffect(()=>{if (view?.status==='AVAILABLE') acceptButton.current?.focus()},[view]);

  async function act(command:'inspect'|'accept'|'open'|'signout') {
    if (pending.current || !proof) return;
    const epoch=generation.current;
    const current=()=>active.current && generation.current===epoch;
    pending.current=true; setBusy(true); setError('');
    try {
      if (command==='signout') {
        await passwordCommand('signout',{});
        if(current()){setSignedIn(false);setView(null);setMode('signin')}
      } else if(command==='open') {
        const receipt=view?.receipt;
        if(!receipt) throw Error();
        await passwordCommand('workspace',{});
        const session=await authApi.session();
        if(!current())return;
        if(!session.csrf_token)throw Error();
        await authApi.selectCompany(receipt.membership_id,session.csrf_token);
        const selected=await authApi.session();
        if(!current())return;
        if(selected.actor?.company_id!==receipt.company_id || selected.actor.membership_id!==receipt.membership_id)throw Error();
        // A full navigation drops every component and all prior private workspace data.
        location.replace('/');
      } else {
        const result = await nativeInvitationsApi[command](proof);
        if(!current())return;
        if(!result.invitation?.company_name ||
          (command==='accept' && !result.receipt?.membership_id)) throw Error();
        setView(result);
      }
    } catch(err) {
      if(!current())return;
      if(err instanceof ApiError && err.status===401){setSignedIn(false);setView(null)}
      if(err instanceof ApiError && err.code==='MEMBERSHIP_ALREADY_EXISTS')
        setError('You already belong to this organisation. Return to your workspace to open it.');
      else if(err instanceof ApiError && err.code==='MEMBERSHIP_UNAVAILABLE')
        setError('Your membership is inactive. Contact the organisation owner to review your access.');
      else if(err instanceof ApiError && err.status===429)
        setError('Too many attempts. Wait before trying again.');
      else if(err instanceof ApiError && err.status<500){
        setView(null);setError('This invitation is unavailable for this account. If the message just arrived, review it again. Check the intended address or ask the owner for a fresh invitation.');
      } else setError('The result could not be confirmed. Review the invitation again to check its current status.');
    } finally {if(current()){pending.current=false;setBusy(false)}}
  }

  return <main className="native-invite-page"><section className="native-invite-card" aria-labelledby="invite-title">
    <a className="native-home-brand" href="/account"><span className="brand-mark" aria-hidden="true">A</span>APBRA</a>
    <h1 id="invite-title">Organisation invitation</h1>
    {!proof ? <p>Open the original invitation link from your email to review it. If the link is missing, ask your organisation owner for a fresh invitation.</p>
      : signedIn===null ? <p role="status">Checking your account…</p>
      : !signedIn ? <>
        <p>Use the email address your colleague invited. You can review the organisation and role before joining.</p>
        <div className="native-invite-actions"><button type="button" aria-pressed={mode==='signin'} onClick={()=>setMode('signin')}>Sign in</button>
        <button type="button" aria-pressed={mode==='signup'} onClick={()=>setMode('signup')}>Create an account</button></div>
        {mode==='signup'&&<p>After verifying your account and signing in, reopen your original invitation email.</p>}
        <PasswordAccount mode={mode} onAuthenticated={()=>setSignedIn(true)}/>
      </> : <>
        {!view && <button type="button" className="auth-submit" disabled={busy} onClick={()=>void act('inspect')}>Review invitation</button>}
        {view && <><h2>{view.invitation.company_name}</h2><p>Invited role: <strong>{nativeRoleName(view.invitation.role)}</strong></p>
          {view.status==='AVAILABLE' ? <><p>Accept to join this organisation.</p>
            <button ref={acceptButton} className="auth-submit" disabled={busy} onClick={()=>void act('accept')}>Accept invitation</button></>
            : <><p role="status">Invitation accepted.</p>
              <button className="auth-submit" disabled={busy} onClick={()=>void act('open')}>Open organisation</button></>}
        </>}
        <p><button type="button" className="auth-text-button" disabled={busy} onClick={()=>void act('signout')}>Sign out and use another account</button></p>
      </>}
    {error&&<p role="alert" className="auth-message">{error}</p>}
    <a href="/home">Return to workspace</a>
  </section></main>;
}
