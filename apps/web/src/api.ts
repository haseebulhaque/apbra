export type Actor={identity_id:string;membership_id:string;company_id:string;display_name:string;role:string};
export type Session={authenticated:boolean;actor?:Actor;csrf_token?:string};
export type RequestVersion={id:string;sequence:number;request_text:string;created_at:string};
export type CaseRecord={id:string;company_id:string;creator_membership_id:string;current_request_version_id:string;version:number;semantic_context_version:number;created_at:string;updated_at:string;current_request:RequestVersion};
export type CaseSummary=CaseRecord;
export type Invitation={id:string;company_id:string;subject:string;role:string;expires_at:string};
export type InvitationInspection={invitation:Invitation;status?:string};
export type IssuedInvitation={invitation:Invitation;token:string};
export type Membership={id:string;display_name:string;subject:string;role:string;active:boolean};
export type CaseAccess={membership_id:string;display_name:string;subject:string;access_level:'OWNER'|'EDITOR'|'VIEWER';active:boolean};
export type ConversationEvent={id:string;sequence:number;kind:'USER_MESSAGE'|'RAW_ANSWER'|'CORRECTION'|'CLARIFICATION_QUESTION'|'AI_ANALYSIS'|'ALTERNATIVE_PROPOSED'|'ALTERNATIVE_ACCEPTED'|'ALTERNATIVE_DECLINED';payload:Record<string,unknown>;created_at:string;semantic_context_version?:number};
export type ObservedEvidenceSchema={kind:'REQUEST_DATA_STRUCTURE';tables:Array<{name:string;rowCount:number;columns:Array<{name:string;type:string}>}>};
export type EvidenceItem={id:string;request_version_id:string;filename:string;format:'CSV'|'XLSX';content_digest:string;schema_digest:string;observed_schema:ObservedEvidenceSchema;created_at:string;semantic_context_version?:number};
export type DurableQuestion={id:string;question:string;reason:string;required:boolean;suggestions:Array<{id:string;label:string}>;allowFreeText:boolean};
export type DurableInterpretation={id:string;state:'NEEDS_CLARIFICATION'|'READY_FOR_CONFIRMATION'|'CONFIRMED';current:boolean;context_version:number;confirmation_summary:{objective:string;businessQuestions:string[];kpiDefinitions:string[];scopeAndTime:string[];dimensionsAndFilters:string[];lifecycleDefinitions:string[];materialPolicyDecisions:string[]};interpretation:Record<string,unknown>;questions:DurableQuestion[];unresolved_ambiguities:string[];simulation:'LOCAL_DETERMINISTIC_NO_MODEL_CALL'};
export type DurableContract={id:string;interpretation_id:string;schema_version:2;accepted_at:string;contract:Record<string,unknown>;current:boolean};
export type AcceptanceState={interpretation:DurableInterpretation|null;confirmed_contract:DurableContract|null};
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
export const conversationApi={
  list:(caseId:string)=>request<{items:ConversationEvent[]}>(`/api/cases/${encodeURIComponent(caseId)}/conversation`),
  append:(caseId:string,kind:ConversationEvent['kind'],payload:Record<string,unknown>,expectedContextVersion:number,commandKey:string,csrfToken:string)=>request<{event:ConversationEvent}>(`/api/cases/${encodeURIComponent(caseId)}/conversation`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({kind,payload,expected_context_version:expectedContextVersion,command_key:commandKey})}).then(value=>value.event),
};
export const evidenceApi={
  list:(caseId:string)=>request<{items:EvidenceItem[]}>(`/api/cases/${encodeURIComponent(caseId)}/evidence`),
  add:async(caseId:string,file:File,expectedContextVersion:number,csrfToken:string)=>{
    const query=new URLSearchParams({filename:file.name,expected_context_version:String(expectedContextVersion)}),response=await fetch(`/api/cases/${encodeURIComponent(caseId)}/evidence?${query}`,{method:'POST',credentials:'same-origin',headers:{'Accept':'application/json','Content-Type':'application/octet-stream',...csrfHeaders(csrfToken)},body:file}),body=await response.json().catch(()=>({})) as {evidence:EvidenceItem}&ApiErrorBody;
    if(!response.ok)throw new ApiError(response.status,body.error?.code??'REQUEST_FAILED',body.error?.message??'The evidence could not be added.');return body.evidence;
  },
};
export const acceptanceApi={
  state:(caseId:string)=>request<AcceptanceState>(`/api/cases/${encodeURIComponent(caseId)}/acceptance`),
  prepare:(caseId:string,expectedContextVersion:number,csrfToken:string)=>request<{interpretation:DurableInterpretation}>(`/api/cases/${encodeURIComponent(caseId)}/interpretations`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({expected_context_version:expectedContextVersion})}).then(value=>value.interpretation),
  confirm:(caseId:string,interpretationId:string,expectedContextVersion:number,csrfToken:string)=>request<{confirmed_contract:DurableContract}>(`/api/cases/${encodeURIComponent(caseId)}/confirm`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({interpretation_id:interpretationId,expected_context_version:expectedContextVersion})}).then(value=>value.confirmed_contract),
};
