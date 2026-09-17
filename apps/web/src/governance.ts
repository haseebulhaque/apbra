import type {Candidate,ProjectFiles} from './powerbi';
import {validateCandidate,sha256,type Validation} from './validation';
export type DemoActor='requester'|'reviewer'|'trusted'|'outsider';
export type DemoSession=Readonly<{mode:'SIMULATED_IDENTITY'}>;
export type Decision='APPROVE'|'REQUEST_CHANGES'|'DECLINE';
type State='VALIDATION_FAILED'|'PENDING_REVIEW'|'TRUSTED_ELIGIBLE'|'APPROVED'|'CHANGES_REQUESTED'|'DECLINED'|'STALE'|'PACKAGED';
type Review={actor:DemoActor;decision:Decision;reason:string;revision:number;digest:string};
type Operation={id:string;revision:number;requester:DemoActor;tenant:string;candidate:Candidate;validation:Validation;status:State;review:Review|null};
export type OperationView=Pick<Operation,'id'|'revision'|'requester'|'status'|'review'|'validation'>;
export type Release={files:ProjectFiles;manifest:{mode:'ISOLATED_DEMO';operationId:string;revision:number;candidateSha256:string;governance:string;identityEvidence:'SIMULATED';fileHashes:Record<string,string>;runtime:Validation['runtime']}};
/** In-memory isolated demo adapter. Session issuance is a visible simulation,
 * never production authentication. Caller-supplied roles/claims are ignored. */
export function createDemoGovernance(){
 const members:Record<DemoActor,{tenant:string;active:boolean;reviewer:boolean;trusted:boolean}>={requester:{tenant:'synthetic',active:true,reviewer:false,trusted:false},reviewer:{tenant:'synthetic',active:true,reviewer:true,trusted:false},trusted:{tenant:'synthetic',active:true,reviewer:false,trusted:true},outsider:{tenant:'other',active:true,reviewer:false,trusted:false}};
 const sessions=new WeakMap<object,DemoActor>(),ops=new Map<string,Operation>();
 const audit:unknown[]=[];const event=(kind:string,data:unknown)=>audit.push({kind,data:structuredClone(data),identityEvidence:'SIMULATED'});
 function actor(session:DemoSession){const id=sessions.get(session);if(!id||!members[id].active)throw new Error('DEMO_CONTEXT_DENIED');return {id,...members[id]};}
 function operation(session:DemoSession,id:string){const a=actor(session),op=ops.get(id);if(!op||op.tenant!==a.tenant)throw new Error('DEMO_OPERATION_DENIED');return {a,op};}
 function view(op:Operation):OperationView{return structuredClone({id:op.id,revision:op.revision,requester:op.requester,status:op.status,review:op.review,validation:op.validation});}
 const eligible=(op:Operation)=>op.validation.status==='PASS'&&op.validation.candidateSha256!==null;
 function authorize(op:Operation){
  const owner=members[op.requester];if(!owner.active||!eligible(op))throw new Error('RELEASE_VALIDATION_OR_MEMBERSHIP_DENIED');
  if(op.status==='TRUSTED_ELIGIBLE'&&owner.trusted)return 'DEMO_TRUSTED_POLICY';
  const review=op.review;
  if(op.status==='APPROVED'&&review?.decision==='APPROVE'&&review.actor!==op.requester&&members[review.actor].active&&members[review.actor].reviewer&&members[review.actor].tenant===op.tenant&&review.revision===op.revision&&review.digest===op.validation.candidateSha256)return 'DEMO_BUSINESS_REVIEW';
  throw new Error('RELEASE_GOVERNANCE_DENIED');
 }
 return {
  issueDemoSession(id:DemoActor):DemoSession{if(!Object.hasOwn(members,id))throw new Error('UNKNOWN_DEMO_ACTOR');const session=Object.freeze({mode:'SIMULATED_IDENTITY' as const});sessions.set(session,id);return session;},
  revokeDemoMember(id:DemoActor){if(!Object.hasOwn(members,id))throw new Error('UNKNOWN_DEMO_ACTOR');members[id].active=false;event('MEMBER_REVOKED',{id});},
  async submit(session:DemoSession,candidate:Candidate):Promise<OperationView>{
   const a=actor(session),copy=structuredClone(candidate),validation=await validateCandidate(copy);actor(session);
   const op:Operation={id:crypto.randomUUID(),revision:1,requester:a.id,tenant:a.tenant,candidate:copy,validation,status:validation.status==='PASS'?(a.trusted?'TRUSTED_ELIGIBLE':'PENDING_REVIEW'):'VALIDATION_FAILED',review:null};ops.set(op.id,op);event('SUBMITTED',op);return view(op);
  },
  async resubmit(session:DemoSession,id:string,revision:number,candidate:Candidate):Promise<OperationView>{
   const {a,op}=operation(session,id);if(op.requester!==a.id||op.revision!==revision||op.status==='PACKAGED'||op.status==='STALE')throw new Error('RESUBMISSION_DENIED');
   const priorStatus=op.status;const copy=structuredClone(candidate),validation=await validateCandidate(copy);actor(session);if(op.revision!==revision||ops.get(id)?.status!==priorStatus)throw new Error('STALE_REVISION');
   op.revision++;op.candidate=copy;op.validation=validation;op.review=null;op.status=validation.status==='PASS'?(a.trusted?'TRUSTED_ELIGIBLE':'PENDING_REVIEW'):'VALIDATION_FAILED';event('RESUBMITTED',op);return view(op);
  },
  review(session:DemoSession,id:string,revision:number,digest:string,decision:Decision,reason:string):OperationView{
   const {a,op}=operation(session,id);if(!a.reviewer||a.id===op.requester)throw new Error('REVIEWER_DENIED');
   if(op.status!=='PENDING_REVIEW'||op.revision!==revision||op.validation.candidateSha256!==digest||!eligible(op))throw new Error('STALE_OR_INELIGIBLE_REVIEW');
   if(!['APPROVE','REQUEST_CHANGES','DECLINE'].includes(decision)||typeof reason!=='string'||!reason.trim()||reason.length>1000)throw new Error('REASON_REQUIRED');
   op.review={actor:a.id,decision,reason:reason.trim(),revision,digest};op.status=decision==='APPROVE'?'APPROVED':decision==='DECLINE'?'DECLINED':'CHANGES_REQUESTED';event('REVIEWED',view(op));return view(op);
  },
  invalidate(id:string){const op=ops.get(id);if(op){op.status='STALE';event('INVALIDATED',view(op));}},
  inspect(session:DemoSession,id:string){return view(operation(session,id).op);},
  async package(session:DemoSession,id:string,revision:number):Promise<Release>{
   const {a,op}=operation(session,id);if(a.id!==op.requester||revision!==op.revision)throw new Error('PACKAGE_CONTEXT_DENIED');
   const governance=authorize(op),candidate=structuredClone(op.candidate),fresh=await validateCandidate(candidate);
   const fileHashes:Record<string,string>={};for(const [path,text] of Object.entries(candidate.files))fileHashes[path]=await sha256(text);
   actor(session);if(op.revision!==revision||fresh.status!=='PASS'||fresh.candidateSha256!==op.validation.candidateSha256||authorize(op)!==governance)throw new Error('STALE_OR_FAILED_CANDIDATE');
   const manifest={mode:'ISOLATED_DEMO' as const,operationId:id,revision,candidateSha256:fresh.candidateSha256!,governance,identityEvidence:'SIMULATED' as const,requester:op.requester,review:structuredClone(op.review),policyVersion:'demo-governance-1',fileHashes,runtime:fresh.runtime};
   const files={...candidate.files,'release-manifest.json':JSON.stringify(manifest,null,2)+'\n','validation.json':JSON.stringify(fresh,null,2)+'\n','handover.txt':'ISOLATED CAPSTONE DEMO PACKAGE. Identity and approval actors are simulated fixture principals, not authenticated people.\nSource checks passed for pinned golden profile. Power BI Desktop open/refresh, numeric DAX, RLS and deployment remain NOT_RUN. Package is not production ready. Extract all files; use a compatible Windows Desktop with PBIP/PBIR preview enabled for actual runtime verification. Embedded synthetic data requires no external credentials. No tenant publishing performed.\n'};
   op.status='PACKAGED';event('PACKAGED',{manifest,review:op.review});return {files,manifest};
  },
  exportEvidence(){return structuredClone({mode:'ISOLATED_DEMO',policyVersion:'demo-governance-1',audit});},
 };
}
