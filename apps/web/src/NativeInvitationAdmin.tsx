import React, {useEffect, useRef, useState} from 'react';
import {ApiError, nativeInvitationsApi, type NativeInviteRole, type NativeInviteRow} from './api';
import {nativeRoleName} from './NativeInvitation';

const labels:Record<string,string> = {SUBMITTED:'Submitted for delivery',PREPARED:'Awaiting submission',
  FAILED:'Submission failed', UNCONFIRMED:'Submission unconfirmed', ACCEPTED:'Accepted',
  REVOKED:'Revoked', EXPIRED:'Expired'};

export function NativeInvitationAdmin({csrf,companyId,membershipId}:{csrf:string;companyId:string;membershipId:string}) {
  const [email,setEmail]=useState(''), [role,setRole]=useState<NativeInviteRole>('MEMBER');
  const [items,setItems]=useState<NativeInviteRow[]>([]),[next,setNext]=useState<string|null>(null);
  const [busy,setBusy]=useState(true),[notice,setNotice]=useState(''),[error,setError]=useState('');
  const [ready,setReady]=useState(false);
  const epoch=useRef(0),locked=useRef(true);
  const command=useRef<{email:string;role:NativeInviteRole;key:string}|null>(null);
  const current=(n:number)=>n===epoch.current;
  async function refresh(n:number,cursor?:string) {
    const result=await nativeInvitationsApi.list(csrf,membershipId,cursor);
    if(!current(n))return;
    setItems(previous=>cursor?[...previous,...result.items]:result.items);
    setNext(result.next_cursor);setReady(true);
  }
  useEffect(()=>{
    const n=++epoch.current;
    command.current=null; locked.current=true; setBusy(true); setReady(false); setItems([]);
    setNext(null);setError('');setNotice('');setEmail('');setRole('MEMBER');
    void refresh(n)
      .catch(()=>{if(current(n))setError('Invitations could not be loaded. Refresh to try again.')})
      .finally(()=>{if(current(n)){locked.current=false;setBusy(false)}});
    return ()=>{epoch.current++};
  },[companyId,membershipId,csrf]);
  async function run(action:'issue'|'revoke'|'refresh'|'more',id?:string) {
    if(locked.current)return;
    locked.current=true;setBusy(true);setNotice('');setError('');
    const n=epoch.current;
    try {
      if(action==='issue') {
        const address=email.trim();
        if(!command.current || command.current.email!==address || command.current.role!==role)
          command.current={email:address,role,key:crypto.randomUUID()};
        const {invitation}=await nativeInvitationsApi.issue(address,role,command.current.key,csrf,membershipId);
        if(!current(n))return;
        setNotice(labels[invitation.state] ?? invitation.state);
        setEmail('');command.current=null;
      } else if(action==='revoke' && id) {
        await nativeInvitationsApi.revoke(id,csrf,membershipId);
        if(!current(n))return;
        setNotice('Invitation revoked.');
      }
      await refresh(n,action==='more'?next??undefined:undefined);
    } catch(err) {
      if(current(n))setError(err instanceof ApiError ? err.message :
        'The result could not be confirmed. Refresh the invitation list. Retrying the same address and role checks the original request.');
    } finally {if(current(n)){locked.current=false;setBusy(false)}}
  }
  return <section className="native-invite-admin" aria-labelledby="colleague-invite">
    <h3 id="colleague-invite">Invite a colleague</h3>
    <form onSubmit={e=>{e.preventDefault();void run('issue')}}><fieldset disabled={!ready||busy}>
      <label>Colleague email<input type="email" required maxLength={320} autoComplete="off" value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label>Invitation role<select value={role} onChange={e=>setRole(e.target.value as NativeInviteRole)}>
        {(['MEMBER','COMPANY_ADMIN','EXPERT'] as const).map(r=><option value={r} key={r}>{nativeRoleName(r)}</option>)}
      </select></label><button type="submit">Send invitation</button></fieldset></form>
    {notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}
    <h4>Organisation invitations</h4>
    <button type="button" disabled={busy} onClick={()=>void run('refresh')}>Refresh invitations</button>
    {ready&&!items.length&&<p>No invitations yet.</p>}
    <ul>{items.map(item=><li key={item.id}><strong>{item.email}</strong> · {nativeRoleName(item.role)} · {labels[item.state]??item.state}
      {['PREPARED','SUBMITTED','FAILED','UNCONFIRMED'].includes(item.state)&&<button disabled={busy} type="button" aria-label={'Revoke invitation for '+item.email} onClick={()=>void run('revoke',item.id)}>Revoke</button>}</li>)}</ul>
    {next&&<button type="button" disabled={busy} onClick={()=>void run('more')}>More invitations</button>}
  </section>;
}
