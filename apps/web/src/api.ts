export type Actor={identity_id:string;membership_id:string;company_id:string;display_name:string;role:string};
export type Session={authenticated:boolean;actor?:Actor;csrf_token?:string};
export type RequestVersion={id:string;sequence:number;request_text:string;created_at:string};
export type CaseRecord={id:string;company_id:string;creator_membership_id:string;current_request_version_id:string;version:number;created_at:string;updated_at:string;current_request:RequestVersion};
export type CaseSummary=CaseRecord;
export type Invitation={id:string;company_id:string;subject:string;role:string;expires_at:string};
export type InvitationInspection={invitation:Invitation;status?:string};
export type IssuedInvitation={invitation:Invitation;token:string};
export type Membership={id:string;display_name:string;subject:string;role:string;active:boolean};
export type CaseAccess={membership_id:string;display_name:string;subject:string;access_level:'OWNER'|'EDITOR'|'VIEWER';active:boolean};
export type ApiErrorBody={error?:{code?:string;message?:string}};

export class ApiError extends Error{
  readonly status:number;readonly code:string;
  constructor(status:number,code:string,message:string){super(message);this.name='ApiError';this.status=status;this.code=code}
}

const jsonHeaders={'Accept':'application/json','Content-Type':'application/json'};
async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const response=await fetch(path,{credentials:'same-origin',...init,headers:{...jsonHeaders,...init.headers}});
  const body=await response.json().catch(()=>({})) as T&ApiErrorBody;
  if(!response.ok)throw new ApiError(response.status,body.error?.code??'REQUEST_FAILED',body.error?.message??'The request could not be completed.');
  return body;
}

function csrfHeaders(csrfToken:string){return{'X-CSRF-Token':csrfToken}}
export const authApi={
  session:()=>request<Session>('/api/auth/session'),
  loginUrl:(identity?:string,returnTo='/')=>`/api/auth/login?${new URLSearchParams({...identity?{identity}:{},return_to:returnTo})}`,
  logout:(csrfToken:string)=>request<void>('/api/auth/logout',{method:'POST',headers:csrfHeaders(csrfToken)}),
};
export const casesApi={
  list:()=>request<{items:CaseSummary[]}>('/api/cases'),
  get:(caseId:string)=>request<{case:CaseRecord}>(`/api/cases/${encodeURIComponent(caseId)}`).then(value=>value.case),
  create:(requestText:string,idempotencyKey:string,csrfToken:string)=>request<{case:CaseRecord}>('/api/cases',{method:'POST',headers:{...csrfHeaders(csrfToken),'Idempotency-Key':idempotencyKey},body:JSON.stringify({request_text:requestText})}).then(value=>value.case),
  update:(caseId:string,requestText:string,expectedVersion:number,csrfToken:string)=>request<{case:CaseRecord}>(`/api/cases/${encodeURIComponent(caseId)}`,{method:'PUT',headers:csrfHeaders(csrfToken),body:JSON.stringify({request_text:requestText,expected_version:expectedVersion})}).then(value=>value.case),
  versions:(caseId:string)=>request<{items:RequestVersion[]}>(`/api/cases/${encodeURIComponent(caseId)}/versions`),
  access:(caseId:string)=>request<{items:CaseAccess[]}>(`/api/cases/${encodeURIComponent(caseId)}/access`),
  grantAccess:(caseId:string,membershipId:string,accessLevel:'EDITOR'|'VIEWER',csrfToken:string)=>request<{granted:boolean}>(`/api/cases/${encodeURIComponent(caseId)}/access`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({membership_id:membershipId,access_level:accessLevel})}),
  revokeAccess:(caseId:string,membershipId:string,csrfToken:string)=>request<{revoked:boolean}>(`/api/cases/${encodeURIComponent(caseId)}/access/${encodeURIComponent(membershipId)}/revoke`,{method:'POST',headers:csrfHeaders(csrfToken)}),
};
export const invitationsApi={
  inspect:(token:string)=>request<InvitationInspection>('/api/invitations/inspect',{method:'POST',body:JSON.stringify({token})}),
  accept:(token:string,csrfToken:string)=>request<unknown>('/api/invitations/accept',{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({token})}),
  issue:(subject:string,role:'COMPANY_ADMIN'|'MEMBER'|'EXPERT',csrfToken:string)=>request<IssuedInvitation>('/api/invitations',{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({subject,role})}),
  revoke:(invitationId:string,csrfToken:string)=>request<{revoked:boolean}>(`/api/invitations/${encodeURIComponent(invitationId)}/revoke`,{method:'POST',headers:csrfHeaders(csrfToken)}),
};
export const membershipsApi={
  list:()=>request<{items:Membership[]}>('/api/memberships'),
  deactivate:(membershipId:string,csrfToken:string)=>request<{deactivated:boolean}>(`/api/memberships/${encodeURIComponent(membershipId)}/deactivate`,{method:'POST',headers:csrfHeaders(csrfToken)}),
};
