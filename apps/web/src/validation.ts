import profile from './validationProfile.json';
import {canonical,validateDesignPlan} from './designPlan';
import type {Candidate} from './powerbi';
export type Finding={code:string;path:string;message:string};
export type Validation={kind:'CandidateValidation';validatorVersion:'capstone-validator-1';profileId:string;candidateSha256:string|null;status:'PASS'|'FAIL';findings:Finding[];declaredChecks:string[];completedChecks:string[];runtime:{desktop:'NOT_RUN';dax:'NOT_RUN';rls:'NOT_RUN'};nextAction:'GOVERNANCE_REQUIRED'|'HUMAN_ESCALATION'};
export async function sha256(text:string):Promise<string>{return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(b=>b.toString(16).padStart(2,'0')).join('');}
export async function candidateDigest(candidate:Candidate):Promise<string>{return sha256(canonical(candidate));}
/** No generator call and no model judgment. Closed exact-byte profile plus
 * independent relationships/references checks. Deliberately not a TMDL parser. */
export async function validateCandidate(input:unknown):Promise<Validation>{
 const completedChecks:string[]=[];const findings:Finding[]=[];const fail=(code:string,path:string,message:string)=>findings.push({code,path,message});
 let digest:string|null=null;
 const finish=():Validation=>({kind:'CandidateValidation',validatorVersion:'capstone-validator-1',profileId:profile.id,candidateSha256:digest,status:findings.length?'FAIL':'PASS',findings,completedChecks,declaredChecks:['CANDIDATE_ENVELOPE','FILE_SET','PINNED_SOURCE_SHA256','JSON_PARSE','DESIGN_BINDING','PROJECT_REFERENCE','RELATIONSHIPS'],runtime:{desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'},nextAction:findings.length?'HUMAN_ESCALATION':'GOVERNANCE_REQUIRED'});
 let c:Candidate;
 try{c=structuredClone(input) as Candidate;}catch{fail('INVALID_ENVELOPE','candidate','Candidate must be cloneable data');return finish();}
 if(!c||canonical(Object.keys(c).sort())!==canonical(['files','generatorVersion','kind','release','runtime'])||c.kind!=='PowerBICandidate'||c.generatorVersion!=='capstone-pbip-1'||c.release!=='NOT_ELIGIBLE'||canonical(c.runtime)!==canonical({desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'})||!c.files||typeof c.files!=='object'||Array.isArray(c.files)){
  fail('INVALID_ENVELOPE','candidate','Supported source candidate required; caller claims never authorize release');return finish();
 }
 completedChecks.push('CANDIDATE_ENVELOPE');
 const entries=Object.entries(c.files);
 if(entries.length>100||entries.some(([p,v])=>typeof v!=='string'||v.length>2_000_000||!/^[A-Za-z0-9_./-]+$/.test(p)||p.split('/').some(s=>!s||s==='.'||s==='..'))){fail('UNSAFE_FILES','files','Bounded relative UTF-8 source files required');return finish();}
 completedChecks.push('FILE_SET');
 digest=await candidateDigest(c);
 const hashes=profile.files as Record<string,string>;
 for(const path of Object.keys(hashes))if(!(path in c.files))fail('MISSING_FILE',path,'Required source file is absent');
 for(const [path,text] of entries){
  if(!(path in hashes)){fail('UNSUPPORTED_FILE',path,'File outside reviewed golden profile');continue;}
  if(await sha256(text)!==hashes[path])fail('SOURCE_BYTES_CHANGED',path,'Bytes differ from independently reviewed golden source profile');
  if(/\.(json|pbip|pbir|pbism)$/.test(path))try{JSON.parse(text);}catch{fail('INVALID_JSON',path,'Source JSON cannot be parsed');}
 }
 completedChecks.push('PINNED_SOURCE_SHA256','JSON_PARSE');
 try{validateDesignPlan(JSON.parse(c.files['DesignPlan.json']));}catch{fail('DESIGN_INVALID','DesignPlan.json','Missing, malformed or unsupported source plan');}
 try{
  const project=JSON.parse(c.files['SalesPerformance.pbip']);const report=JSON.parse(c.files['SalesPerformance.Report/definition.pbir']);
  if(project.artifacts[0].report.path!=='SalesPerformance.Report'||report.datasetReference.byPath.path!=='../SalesPerformance.SemanticModel')throw new Error();
 }catch{fail('BROKEN_PROJECT_REFERENCE','SalesPerformance.pbip','Project/report/model relative references must resolve to supported files');}
 completedChecks.push('DESIGN_BINDING','PROJECT_REFERENCE');
 const relationships=c.files['SalesPerformance.SemanticModel/definition/relationships.tmdl']??'';
 const bindings=[['SaleDate','DimDate','Date'],['ProductId','DimProduct','ProductId'],['RegionId','DimRegion','RegionId'],['BusinessAreaId','DimBusinessArea','BusinessAreaId'],['CustomerId','DimCustomer','CustomerId']];
 for(const [from,table,to] of bindings){const block=relationships.split(/\n\s*\n/).find(b=>b.includes(`fromColumn: FactSales.${from}\n`)&&b.includes(`toColumn: ${table}.${to}\n`));if(!block)fail('MISSING_RELATIONSHIP','SalesPerformance.SemanticModel/definition/relationships.tmdl',`Required FactSales.${from} -> ${table}.${to} is absent`);}
 completedChecks.push('RELATIONSHIPS');
 return finish();
}
export const failureCase={id:'MISSING_DATE_RELATIONSHIP_V1',mutation:'Remove golden-1 relationship block from a cloned generated candidate',expectedCode:'MISSING_RELATIONSHIP',repair:'NOT_IMPLEMENTED; HUMAN_ESCALATION'} as const;
export function createFailureCandidate(original:Candidate):Candidate{
 const copy=structuredClone(original),path='SalesPerformance.SemanticModel/definition/relationships.tmdl';
 const blocks=copy.files[path].split(/\n\s*\n/);if(!blocks[0].includes('fromColumn: FactSales.SaleDate'))throw new Error('FAILURE_FIXTURE_PRECONDITION');
 copy.files[path]=blocks.slice(1).join('\n\n');return copy;
}

export type ValidationAttempt={caseId:string;original:Candidate;candidate:Candidate|null;outcome:'COMPLETE'|'INCOMPLETE';result:Validation|null;error:string|null};
/** Capture source before mutation or async work, including failure-first and
 * crashed checks. Incomplete attempts never carry a passing result. */
export async function runValidationAttempt(source:Candidate,failure:boolean):Promise<ValidationAttempt>{
 const original=structuredClone(source);
 const record:ValidationAttempt={caseId:failure?failureCase.id:'GOLDEN_SOURCE',original,candidate:null,outcome:'INCOMPLETE',result:null,error:null};
 try{record.candidate=failure?createFailureCandidate(original):structuredClone(original);record.result=await validateCandidate(record.candidate);record.outcome='COMPLETE';}
 catch{record.error='VALIDATION_INCOMPLETE: mandatory checks did not complete; human escalation required';}
 return record;
}
