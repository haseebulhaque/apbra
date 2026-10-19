import {stringifyExactNumbers} from './aiGeometry';
export type Actor={identity_id:string;membership_id:string;company_id:string;display_name:string;role:string};
export type IdentityProviderOption={profile_id:string;display_label:string};
export type IdentityProviders={items:IdentityProviderOption[];development_identities:string[]};
export type Session={authenticated:boolean;identity?:{id:string;display_name:string};actor?:Actor;csrf_token?:string;membership_state?:'ACTIVE'|'COMPANY_SELECTION_REQUIRED'|'COMPANY_CREATION_AVAILABLE'|'INVITATION_AVAILABLE'|'MEMBERSHIP_INACTIVE';available_companies?:Array<{membership_id:string;company_id:string;name:string}>};
export type RequestVersion={id:string;sequence:number;request_text:string;created_at:string};
export type CaseRecord={id:string;company_id:string;creator_membership_id:string;current_request_version_id:string;version:number;semantic_context_version:number;report_title?:string;created_at:string;updated_at:string;current_request:RequestVersion};
export type CaseSummary=CaseRecord;
export type Invitation={id:string;company_id:string;subject:string;role:string;expires_at:string};
export type InvitationInspection={invitation:Invitation;status?:string};
export type IssuedInvitation={invitation:Invitation;token:string};
export type Membership={id:string;display_name:string;subject:string;role:string;active:boolean};
export type MembershipRoleChange={id:string;role:'MEMBER'|'COMPANY_ADMIN';active:boolean};
export type CompanyCreation={company:{id:string;name:string};membership:{id:string;role:'COMPANY_OWNER'}};
export type Profile={display_name:string};
export type CaseAccess={membership_id:string;display_name:string;subject:string;access_level:'OWNER'|'EDITOR'|'VIEWER';active:boolean};
export type ConversationEvent={id:string;sequence:number;kind:'USER_MESSAGE'|'RAW_ANSWER'|'CORRECTION'|'CLARIFICATION_CYCLE_STARTED'|'CLARIFICATION_QUESTION'|'AI_ANALYSIS'|'ALTERNATIVE_PROPOSED'|'ALTERNATIVE_ACCEPTED'|'ALTERNATIVE_DECLINED';payload:Record<string,unknown>;created_at:string;semantic_context_version?:number};
export type ObservedEvidenceSchema={kind:'REQUEST_DATA_STRUCTURE';tables:Array<{name:string;rowCount:number;columns:Array<{name:string;type:string}>}>};
export type EvidenceItem={id:string;request_version_id:string;filename:string;format:'CSV'|'XLSX';content_digest:string;schema_digest:string;observed_schema:ObservedEvidenceSchema;created_at:string;semantic_context_version?:number};
export type ReferenceMaterial={id:string;request_version_id:string;filename:string;media_type:'image/png'|'image/jpeg';content_digest:string;interpretation_state:'NOT_INTERPRETED'|'VISION_AVAILABLE';capability_profile_id:string|null;created_at:string;semantic_context_version?:number};
export type DurableQuestion={id:string;question:string;reason:string;required:boolean;suggestions:Array<{id:string;label:string}>;allowFreeText:boolean};
export type DurableInterpretation={id:string;state:'NEEDS_CLARIFICATION'|'READY_FOR_CONFIRMATION'|'CONFIRMED'|'HUMAN_REVIEW_REQUIRED'|'UNSUPPORTED'|'OUT_OF_SCOPE';current:boolean;context_version:number;confirmation_summary:{objective:string;businessQuestions:string[];kpiDefinitions:string[];scopeAndTime:string[];dimensionsAndFilters:string[];lifecycleDefinitions:string[];materialPolicyDecisions:string[]};interpretation:Record<string,unknown>;questions:DurableQuestion[];unresolved_ambiguities:string[];simulation:'LOCAL_DETERMINISTIC_NO_MODEL_CALL'|'QUALIFIED_SERVER_MODEL'};
export type DurableContract={id:string;interpretation_id:string;schema_version:2;accepted_at:string;contract:Record<string,unknown>;current:boolean};
export type ClarificationState={cycle_id:string|null;cycle_number:number;rounds_used_in_cycle:number;rounds_used_overall:number;max_rounds_per_cycle:number|null;max_rounds_overall:number|null;clarification_enabled:boolean;per_cycle_limit_reached:boolean;overall_limit_reached:boolean};
export type AcceptanceState={interpretation:DurableInterpretation|null;confirmed_contract:DurableContract|null;clarification?:ClarificationState};
export type TenantProviderProfile={profile_id:string;protocol:'OPENAI_CHAT_COMPATIBLE'|'AZURE_OPENAI_CHAT_COMPATIBLE'|'FOUNDRY_AGENT_RESPONSES';endpoint:string;model_or_deployment:string;api_version:string;agent_version?:string|null;region:string;prompt_version:string;configuration_id:string;capabilities:{structured_output:boolean;vision:boolean};max_calls_per_operation:number;max_input_characters:number;max_output_tokens:number;time_budget_seconds:number;request_timeout_seconds:number;retry_limit:number};
export type TenantGenerationPolicy={organisation:{name:string;displayName:string;locale:string;timezone:string};branding:{primary:string;accent:string;reportNaming:string;pageNaming:string;executiveConvention:string;themeName:string};generation:{enabled:boolean;supportedCapabilities:string[];supportedTrendGrains:Array<'DAY'|'MONTH'|'QUARTER'|'YEAR'>;validationRequired:boolean;policy:string};governance:{requireKnowledge:boolean;requireAccessibility:boolean;requireValidation:boolean;maxVisualsPerPage:number;maxPages:number;humanReviewAtVisuals:number}};
export type TenantSettingsDocument={clarification_enabled:boolean;max_clarification_rounds_per_cycle:number;max_clarification_rounds_overall:number;expert_escalation_enabled:boolean;automatic_generation_enabled:boolean;invitation_ttl_days:number;upload_policy:{data_extensions:string[];reference_extensions:string[];max_file_bytes:number;max_files_per_selection:number;max_data_items_per_report:number;max_reference_items_per_report:number};clarification_policy:{max_questions_per_round:number;max_answer_characters:number};generation_policy:TenantGenerationPolicy;provider_profile:TenantProviderProfile|null;delivery_guide_policy:{enabled:true;include_handover_instructions:boolean};conventions:{report_naming:string;semantic_modelling:string;accessibility:string;terminology:Record<string,string>}};
export type TenantSettingsVersion={id:string;version:number;digest:string;validation_status:'PASS';applicability:'COMPANY_NEW_OR_REVALIDATED_OPERATIONS';settings:TenantSettingsDocument;credential:{status:'CONFIGURED'|'NOT_CONFIGURED';maskedValue:'***'|null;updatedAt:string|null;canReplace:boolean;canRotate:boolean;authMode?:'ENTRA'};};
export type TenantSettingsHistory={id:string;version:number;created_at:string;changed_keys:string[];safe_changes:Record<string,unknown>;restored_from_version_id:string|null;current:boolean;validation_status:string};
export type TenantSettingsSection='ai_models'|'responses_standards'|'budgets_limits'|'branding_organisation';
export type WorkspaceBranding={version:number;primary:string;accent:string};
export type ReviewedDesign={id:string;confirmed_contract_id:string;summary:{page_count:number;visual_count:number;description:string};origin:'AUTO_ELIGIBLE'|'EXPERT_REVIEWED';provenance_label:string;reviewed_at:string};
export type ProviderGrounding={mode:'PROVIDER_MANAGED';scope:'SHARED_STANDARDS'|'TENANT_PRIVATE';profileId:string;configurationId:string;knowledgeBinding:string;agentVersion:string|null;qualification:'OFFLINE_FIXTURE'|'LIVE_METADATA_VERIFIED';references:string[];observedToolCount:number;retrievalEvidence:'OBSERVED_TOOL_TRACE'|'ANNOTATIONS_ONLY'|'NO_OBSERVED_RETRIEVAL'};
export type ProviderUsage={prompt_tokens?:number|null;completion_tokens?:number|null;total_tokens?:number|null;latency_ms?:number;call_count?:number;grounding?:ProviderGrounding;observed_prompt_tokens?:number;observed_completion_tokens?:number;observed_total_tokens?:number;prompt_tokens_reported_calls?:number;completion_tokens_reported_calls?:number;total_tokens_reported_calls?:number};
export type AutomaticDesignAttempt={id:string;confirmed_contract_id:string;status:'RUNNING'|'ELIGIBLE'|'FAILED'|'CANCELLED';provider_profile_id:string|null;model_or_deployment:string|null;prompt_version:string|null;configuration_id:string|null;capability_profile:Record<string,boolean>;usage:ProviderUsage;failure:{code:string;message:string}|null;validation:Record<string,unknown>|null;created_at:string;completed_at:string|null};
export type UploadCapabilities={data_extensions:string[];reference_extensions:string[];max_file_bytes:number;max_files_per_selection:number;max_answer_characters:number};
export type GenerationAttempt={id:string;case_id:string;confirmed_contract_id:string;reviewed_design_id:string|null;interpretation_id:string;request_version_id:string;status:'PENDING'|'RUNNING'|'SUCCEEDED'|'FAILED'|'CANCELLED';attempt_number:number;retry_of_attempt_id:string|null;supersedes_attempt_id:string|null;provenance:{mode:string;pipeline:string;runtimeEvidence:Record<string,string>;providerGrounding?:ProviderGrounding};validation:Record<string,unknown>|null;failure:{code:string;message:string}|null;created_at:string;started_at:string|null;completed_at:string|null;cancelled_at:string|null;artifact:{id:string;filename:string;content_digest:string;guide_digest?:string|null;byte_size:number;validation_status:'PASS';created_at:string}|null};
export type ErrorReference={support_reference?:string;recorded?:boolean;correlation_id?:string};
export type ApiErrorBody={error?:{code?:string;message?:string}&ErrorReference};

export class ApiError extends Error{
  readonly status:number;readonly code:string;readonly support_reference?:string;readonly recorded?:boolean;readonly correlation_id?:string;
  constructor(status:number,code:string,message:string,reference:ErrorReference={}){super(message);this.name='ApiError';this.status=status;this.code=code;this.support_reference=reference?.support_reference;this.recorded=reference?.recorded;this.correlation_id=reference?.correlation_id}
}

const jsonHeaders={'Accept':'application/json','Content-Type':'application/json'};
async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const response=await fetch(path,{credentials:'same-origin',...init,headers:{...jsonHeaders,...init.headers}});
  const body=await response.json().catch(()=>({})) as T&ApiErrorBody;
  if(!response.ok)throw new ApiError(response.status,body.error?.code??'REQUEST_FAILED',body.error?.message??'The request could not be completed.',body.error);
  return body;
}

function csrfHeaders(csrfToken:string){return{'X-CSRF-Token':csrfToken}}
export const authApi={
  providers:()=>request<IdentityProviders>('/api/auth/providers'),
  session:()=>request<Session>('/api/auth/session'),
  loginUrl:(options:{profileId?:string;identity?:string;returnTo?:string}={})=>`/api/auth/login?${new URLSearchParams({...options.profileId?{profile_id:options.profileId}:{},...options.identity?{identity:options.identity}:{},return_to:options.returnTo??'/'})}`,
  selectCompany:(membershipId:string,csrfToken:string)=>request<{selected:boolean}>('/api/auth/select-company',{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({membership_id:membershipId})}),
  logout:(csrfToken:string)=>request<void>('/api/auth/logout',{method:'POST',headers:csrfHeaders(csrfToken)}),
};
export const companiesApi={
  create:(name:string,idempotencyKey:string,csrfToken:string)=>request<CompanyCreation>('/api/companies',{method:'POST',headers:{...csrfHeaders(csrfToken),'Idempotency-Key':idempotencyKey},body:JSON.stringify({name})}),
};
export const profileApi={
  current:()=>request<{profile:Profile}>('/api/profile').then(value=>value.profile),
  update:(displayName:string,csrfToken:string)=>request<{profile:Profile}>('/api/profile',{method:'PATCH',headers:csrfHeaders(csrfToken),body:JSON.stringify({display_name:displayName})}).then(value=>value.profile),
};
export const capabilitiesApi={uploads:()=>request<UploadCapabilities>('/api/cases/capabilities/uploads')};
export const workspaceBrandingApi={
  current:()=>request<WorkspaceBranding>('/api/workspace/branding',{method:'GET'}),
};
export const tenantSettingsApi={
  current:()=>request<TenantSettingsVersion>('/api/tenant-settings'),
  agentDetails:()=>request<AgentDetails>('/api/tenant-settings/agent-details'),
  qualifiedProfiles:()=>request<{items:TenantProviderProfile[]}>('/api/tenant-settings/qualified-profiles').then(value=>value.items),
  history:()=>request<{items:TenantSettingsHistory[]}>('/api/tenant-settings/history').then(value=>value.items),
  update:(settings:TenantSettingsDocument,expectedVersion:number,csrfToken:string)=>request<TenantSettingsVersion>('/api/tenant-settings',{method:'PUT',headers:csrfHeaders(csrfToken),body:JSON.stringify({settings,expected_version:expectedVersion})}),
  updateSection:(section:TenantSettingsSection,changes:Record<string,unknown>,expectedVersion:number,csrfToken:string)=>request<TenantSettingsVersion>(`/api/tenant-settings/sections/${section}`,{method:'PATCH',headers:csrfHeaders(csrfToken),body:JSON.stringify({expected_version:expectedVersion,changes})}),
  restore:(sourceVersion:number,expectedVersion:number,csrfToken:string)=>request<TenantSettingsVersion>('/api/tenant-settings/restore',{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({source_version:sourceVersion,expected_version:expectedVersion,confirm_consequences:true})}),
  replaceCredential:(newCredential:string,expectedVersion:number,csrfToken:string)=>request<TenantSettingsVersion>('/api/tenant-settings/credential',{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({new_credential:newCredential,expected_version:expectedVersion,confirm_disruption:true})}),
};
export type KnowledgeOriginalDraft={title:string;source_version:string;text:string};
export type KnowledgeCapabilities={company_id:string;membership_id:string;maximum_request_bytes:number;storage:'LOCAL_DRAFT_DATABASE';provider_write_outcome:'NOT_SENT';indexed:false;used_by_ai:false};
export type KnowledgeRevision={revision_id:string;predecessor_revision_id:string|null;title:string;source_version:string;text_sha256:string;text_byte_count:number;created_at:string;local_state:'LOCAL_DRAFT'|'LOCAL_ARCHIVAL_REQUESTED';provider_write_outcome:'NOT_SENT';used_by_ai:false};
export type KnowledgeDocument={company_id:string;document_id:string;current_revision_id:string|null;current_operation_id:string|null;current_revision:KnowledgeRevision|null;local_state:'LOCAL_DRAFT'|'LOCAL_ARCHIVAL_REQUESTED';provider_write_outcome:'NOT_SENT';used_by_ai:false};
export type KnowledgeCommand={command_key:string;operation_id:string;document_id:string;kind:'CREATE'|'REVISION'|'ARCHIVE';target_revision_id:string;expected_current_revision_id:string|null;created_at:string;provider_write_outcome:'NOT_SENT'};
export type KnowledgeCommandEnvelope={company_id:string;disposition:'APPLIED'|'REPLAY';command:KnowledgeCommand;document:KnowledgeDocument};
export type KnowledgeReconciliation={company_id:string;reconciliation:'COMMITTED'|'NOT_OBSERVED';command:KnowledgeCommand|null;document:KnowledgeDocument|null};
export type KnowledgeHistory={company_id:string;document:KnowledgeDocument;revisions:KnowledgeRevision[];operations:KnowledgeCommand[]};
export type KnowledgeOriginal=KnowledgeOriginalDraft&{company_id:string;document_id:string;revision_id:string;text_sha256:string;text_byte_count:number;created_at:string};
const knowledgePath='/api/tenant-settings/knowledge-documents';
const knowledgeHeaders=(membershipId:string)=>({'X-Expected-Membership-Id':membershipId});
export const knowledgeDocumentsApi={
  capabilities:()=>request<KnowledgeCapabilities>(`${knowledgePath}/capabilities`),
  list:(membershipId:string)=>request<{company_id:string;items:KnowledgeDocument[]}>(knowledgePath,{headers:knowledgeHeaders(membershipId)}),
  context:(id:string,membershipId:string)=>request<KnowledgeDocument>(`${knowledgePath}/${encodeURIComponent(id)}`,{headers:knowledgeHeaders(membershipId)}),
  history:(id:string,membershipId:string)=>request<KnowledgeHistory>(`${knowledgePath}/${encodeURIComponent(id)}/history`,{headers:knowledgeHeaders(membershipId)}),
  original:(id:string,revisionId:string,membershipId:string)=>request<KnowledgeOriginal>(`${knowledgePath}/${encodeURIComponent(id)}/revisions/${encodeURIComponent(revisionId)}/original`,{headers:knowledgeHeaders(membershipId)}),
  reconcile:(key:string,membershipId:string)=>request<KnowledgeReconciliation>(`${knowledgePath}/commands/${encodeURIComponent(key)}`,{headers:knowledgeHeaders(membershipId)}),
  // The caller freezes this selected request JSON once per intent; retry uses the exact same body/key.
  submit:(kind:KnowledgeCommand['kind'],id:string|null,body:string,key:string,membershipId:string,csrfToken:string)=>request<KnowledgeCommandEnvelope>(kind==='CREATE'?knowledgePath:`${knowledgePath}/${encodeURIComponent(id!)}/${kind==='REVISION'?'revisions':'archive'}`,{method:'POST',headers:{...knowledgeHeaders(membershipId),...csrfHeaders(csrfToken),'Idempotency-Key':key},body}),
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
  changeRole:(membershipId:string,role:'MEMBER'|'COMPANY_ADMIN',csrfToken:string)=>request<{membership:MembershipRoleChange}>(`/api/memberships/${encodeURIComponent(membershipId)}/role`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({role})}).then(value=>value.membership),
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
export const referenceMaterialApi={
  list:(caseId:string)=>request<{items:ReferenceMaterial[]}>(`/api/cases/${encodeURIComponent(caseId)}/reference-material`),
  add:async(caseId:string,file:File,expectedContextVersion:number,csrfToken:string)=>{
    const query=new URLSearchParams({filename:file.name,expected_context_version:String(expectedContextVersion)}),response=await fetch(`/api/cases/${encodeURIComponent(caseId)}/reference-material?${query}`,{method:'POST',credentials:'same-origin',headers:{'Accept':'application/json','Content-Type':'application/octet-stream',...csrfHeaders(csrfToken)},body:file}),body=await response.json().catch(()=>({})) as {reference_material:ReferenceMaterial}&ApiErrorBody;
    if(!response.ok)throw new ApiError(response.status,body.error?.code??'REQUEST_FAILED',body.error?.message??'The reference material could not be added.');return body.reference_material;
  },
};
export const acceptanceApi={
  state:(caseId:string)=>request<AcceptanceState>(`/api/cases/${encodeURIComponent(caseId)}/acceptance`),
  prepare:(caseId:string,expectedContextVersion:number,csrfToken:string)=>request<{interpretation:DurableInterpretation}>(`/api/cases/${encodeURIComponent(caseId)}/interpretations`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({expected_context_version:expectedContextVersion})}).then(value=>value.interpretation),
  confirm:(caseId:string,interpretationId:string,expectedContextVersion:number,csrfToken:string)=>request<{confirmed_contract:DurableContract}>(`/api/cases/${encodeURIComponent(caseId)}/confirm`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({interpretation_id:interpretationId,expected_context_version:expectedContextVersion})}).then(value=>value.confirmed_contract),
  refine:(caseId:string,expectedContextVersion:number,enhancement:string,commandKey:string,csrfToken:string)=>request<{clarification:ClarificationState;semantic_context_version:number}>(`/api/cases/${encodeURIComponent(caseId)}/clarification-cycles`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({expected_context_version:expectedContextVersion,enhancement,command_key:commandKey})}),
};
export const reviewedDesignApi={
  list:(caseId:string,confirmedContractId:string)=>request<{items:ReviewedDesign[];can_build:boolean;can_submit:boolean}>(`/api/cases/${encodeURIComponent(caseId)}/reviewed-designs?${new URLSearchParams({confirmed_contract_id:confirmedContractId})}`),
  intake:(caseId:string,confirmedContractId:string,reportDesign:Record<string,unknown>,csrfToken:string)=>request<{reviewed_design:ReviewedDesign}>(`/api/cases/${encodeURIComponent(caseId)}/reviewed-designs`,{method:'POST',headers:csrfHeaders(csrfToken),body:stringifyExactNumbers({confirmed_contract_id:confirmedContractId,report_design:reportDesign})}).then(value=>value.reviewed_design),
};
export const automaticDesignApi={
  list:(caseId:string,confirmedContractId:string)=>request<{items:AutomaticDesignAttempt[]}>(`/api/cases/${encodeURIComponent(caseId)}/automatic-designs?${new URLSearchParams({confirmed_contract_id:confirmedContractId})}`),
  propose:(caseId:string,confirmedContractId:string,commandKey:string,csrfToken:string)=>request<{attempt:AutomaticDesignAttempt;reviewed_design:ReviewedDesign|null}>(`/api/cases/${encodeURIComponent(caseId)}/automatic-designs`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({confirmed_contract_id:confirmedContractId,command_key:commandKey})}),
};
export const generationApi={
  list:(caseId:string)=>request<{items:GenerationAttempt[]}>(`/api/cases/${encodeURIComponent(caseId)}/generation`),
  start:(caseId:string,confirmedContractId:string,reviewedDesignId:string,commandKey:string,csrfToken:string,mode:'BUILD'|'RETRY'|'REGENERATE'='BUILD',sourceAttemptId?:string)=>request<{attempt:GenerationAttempt}>(`/api/cases/${encodeURIComponent(caseId)}/generation`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({confirmed_contract_id:confirmedContractId,reviewed_design_id:reviewedDesignId,command_key:commandKey,mode,source_attempt_id:sourceAttemptId})}).then(value=>value.attempt),
  cancel:(caseId:string,attemptId:string,csrfToken:string)=>request<{attempt:GenerationAttempt}>(`/api/cases/${encodeURIComponent(caseId)}/generation/${encodeURIComponent(attemptId)}/cancel`,{method:'POST',headers:csrfHeaders(csrfToken)}).then(value=>value.attempt),
  artifactUrl:(caseId:string,attemptId:string)=>`/api/cases/${encodeURIComponent(caseId)}/generation/${encodeURIComponent(attemptId)}/artifact`,
  download:async(caseId:string,attemptId:string)=>{
    const response=await fetch(`/api/cases/${encodeURIComponent(caseId)}/generation/${encodeURIComponent(attemptId)}/artifact`,{credentials:'same-origin',headers:{Accept:'application/zip'}});
    if(!response.ok){const body=await response.json().catch(()=>({})) as ApiErrorBody;throw new ApiError(response.status,body.error?.code??'ARTIFACT_NOT_FOUND','This report file is unavailable or you no longer have access. Reload the case or ask for help.');}
    return response.blob();
  },
};

export type RedactedDiagnostic={operation:string;exception_type:string;message:string;message_truncated:boolean;frames:Array<{file:string;function:string;line:number}>};
export type AgentDetails={status:string;settings_version:number;agent:string|null;configuredVersion:string|null;observedVersion?:string|null;metadataSource?:'CONFIGURED_VERSION'|'AZURE_LATEST'|null;diagnostic?:RedactedDiagnostic;modelDeployment:string|null;storedInstructionUtf8Bytes:number|null;toolTypes:string[];warnings:string[]};

export type HistoryFilters={from?:string;to?:string;module?:string;actor_id?:string;operation?:string;outcome?:string;support_reference?:string;cursor?:string};
export type AuditEvent={id:string;occurred_at:string;module:string;operation:string;outcome:string;actor_id:string|null;target_type:string|null;target_id:string|null;details?:Record<string,string|number|boolean|null>;details_withheld?:boolean};
export type ProviderFailureFacts={http_status?:number;http_reason?:string;request_id?:string;provider_code?:string;provider_type?:string;provider_message?:string;provider_message_redacted?:boolean;provider_param?:string;provider_target?:string;provider_code_redacted?:boolean;provider_type_redacted?:boolean;provider_param_redacted?:boolean;provider_target_redacted?:boolean;transport_attempted?:boolean;response_received?:boolean;exception_type?:string;cause_type?:string};
export type DiagnosticStack={exception_type:string;frames:Array<{module:string;function:string;line:number}>};
export type ProcessingError=AuditEvent&{support_reference:string;category:string;message:string;correlation_id:string;case_id:string|null;source_kind:string|null;source_id:string|null;technical?:{diagnostic:DiagnosticStack&{provider?:ProviderFailureFacts;causes?:DiagnosticStack[]};truncated:boolean}|null};
export type HistoryPage<T>={company_id:string;case_id?:string;items:T[];next_cursor:string|null};
function historyQuery(filters:HistoryFilters){const query=new URLSearchParams();for(const name of ['from','to','module','actor_id','operation','outcome','support_reference','cursor'] as const){const value=filters[name];if(value)query.set(name,value)}return query.size?`?${query}`:''}
const historyPath='/api/tenant-settings';
export const observabilityApi={
  audit:(membershipId:string,filters:HistoryFilters={})=>request<HistoryPage<AuditEvent>>(`${historyPath}/audit-events${historyQuery(filters)}`,{headers:knowledgeHeaders(membershipId)}),
  auditDetail:(membershipId:string,id:string)=>request<AuditEvent>(`${historyPath}/audit-events/${encodeURIComponent(id)}`,{headers:knowledgeHeaders(membershipId)}),
  errors:(membershipId:string,filters:HistoryFilters={})=>request<HistoryPage<ProcessingError>>(`${historyPath}/errors${historyQuery(filters)}`,{headers:knowledgeHeaders(membershipId)}),
  errorDetail:(membershipId:string,id:string)=>request<ProcessingError>(`${historyPath}/errors/${encodeURIComponent(id)}`,{headers:knowledgeHeaders(membershipId)}),
  caseErrors:(caseId:string,filters:HistoryFilters={})=>request<HistoryPage<ProcessingError>>(`/api/cases/${encodeURIComponent(caseId)}/errors${historyQuery(filters)}`),
};

export type NativeReceipt={operation_id:string;state:string;context_version:number;http_status:number|null;provider_status:string|null;receipt_id:string|null;bytes:number|null;sha256:string|null};
export type NativeAnswer={receipt_id:string;context_version:number;texts:string[];bytes:number;sha256:string};
export type CaseFileAvailability={receive_available?:boolean;receive_reason?:string;connection_id?:string|null;ready:boolean;reason:string|null;scope:string;request_version_id:string;context_version:number;settings_id:string;input_characters:number|null;input_limit:number|null;files:Array<{id:string;filename:string;status:string;reason:string|null;bytes?:number;transport:string;contentDigest:string;serviceFileUploaded:false;processingVerified:false}>};
export type NativeTask='REQUIREMENT_ANALYSIS'|'REPORT_DESIGN';
export type NativeContractDiagnostic={code:string;phase:string;findings:Array<{path:string;reason:string}>};
export type NativeContractCheck={recognized:boolean;current:boolean;task:NativeTask|null;context_version:number;settings_id:string;reason:string|null;receipt_id:string;diagnostic?:NativeContractDiagnostic|null;warnings?:Array<{path:string;reason:string}>};
export const savedAzureApi={
 list:(caseId:string)=>request<{items:NativeReceipt[]}>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts`),
 view:(caseId:string,receiptId:string)=>request<NativeAnswer>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}/view`),
 input:(caseId:string,task?:NativeTask,contractId?:string)=>request<CaseFileAvailability>(`/api/cases/${encodeURIComponent(caseId)}/native-response-input${task?'?'+new URLSearchParams({task,...(contractId?{confirmed_contract_id:contractId}:{})}):''}`),
 receive:(caseId:string,contextVersion:number,settingsId:string,commandKey:string,csrfToken:string,stage?:{task:NativeTask;confirmed_contract_id?:string})=>request<{native_response:NativeReceipt}>(`/api/cases/${encodeURIComponent(caseId)}/native-response-checks`,{method:'POST',headers:{'X-CSRF-Token':csrfToken},body:JSON.stringify({expected_context_version:contextVersion,expected_settings_id:settingsId,command_key:commandKey,...stage})}),
 contract:(caseId:string,receiptId:string)=>request<NativeContractCheck>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}/contract`),
 intake:(caseId:string,receiptId:string,contextVersion:number,settingsId:string,csrfToken:string)=>request<{accepted:boolean;reason?:string;task?:NativeTask;diagnostic?:NativeContractDiagnostic|null}>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}/contract`,{method:'POST',headers:{'X-CSRF-Token':csrfToken},body:JSON.stringify({expected_context_version:contextVersion,expected_settings_id:settingsId})}),
 download:(caseId:string,receiptId:string)=>`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}`,
};

export type RequestOutput={id:string;case_id:string;request_version_id:string;context_version:number;filename:string;origin:string;bytes:number;sha256:string;native_receipt_id:string|null;content_verification:'NOT_RUN';created_at:string};
export const requestOutputsApi={
 list:(caseId:string,before?:string)=>request<{items:RequestOutput[];has_more:boolean;next_cursor?:string|null;maximum_bytes:number}>(`/api/cases/${encodeURIComponent(caseId)}/outputs${before?'?'+new URLSearchParams({before}):''}`),
 upload:(caseId:string,file:File,context:number,command:string,csrfToken:string)=>request<{output:RequestOutput;replayed:boolean}>(`/api/cases/${encodeURIComponent(caseId)}/outputs?${new URLSearchParams({filename:file.name,expected_context_version:String(context),command_key:command})}`,{method:'POST',headers:{...csrfHeaders(csrfToken),'Content-Type':'application/octet-stream'},body:file}),
 saveNative:(caseId:string,receiptId:string,context:number,command:string,csrfToken:string)=>request<{output:RequestOutput;replayed:boolean}>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}/output`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({expected_context_version:context,command_key:command})}),
 download:(caseId:string,id:string)=>`/api/cases/${encodeURIComponent(caseId)}/outputs/${encodeURIComponent(id)}/download`,
};

export type NativeGeneratedFile={index:number;filename:string;savable:boolean};
export const nativeFilesApi={
 list:(caseId:string,receiptId:string)=>request<{items:NativeGeneratedFile[];retrieval_configured:boolean;content_verification:'NOT_RUN'}>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}/files`),
 save:(caseId:string,receiptId:string,index:number,context:number,command:string,csrfToken:string)=>request<{output:RequestOutput;replayed:boolean}>(`/api/cases/${encodeURIComponent(caseId)}/native-response-receipts/${encodeURIComponent(receiptId)}/files/${index}/output`,{method:'POST',headers:csrfHeaders(csrfToken),body:JSON.stringify({expected_context_version:context,command_key:command})}),
};
