import {validateConfirmedRequirementContract,type ConfirmedRequirementContract} from '../src/confirmedRequirements';
import {createHash} from 'node:crypto';
import {createBoundDeliveryGuideText} from '../src/deploymentGuide';
import {validateReportDesign,reportDesignFailureDiagnostic,type AIResult,type RequirementInterpretation} from '../src/foundry';
import {compilePowerBI,validateCompilerCapabilities,validateGenericCandidate} from '../src/genericPowerBI';
import {evaluateGuardrails} from '../src/guardrail';
import {retrieveKnowledge,type Embedder} from '../src/rag';
import {normalizeReportDesign,orderVisualsForCompilerGrid} from '../src/reportDesignNormalization';
import type {DataStructure} from '../src/schemaIngestion';
import type {TenantSettings} from '../src/tenant';

type Request={operation?:'knowledge'|'validate-design'|'generate';contract:unknown;dataStructure:unknown;reportDesign?:unknown;binding:unknown;execution?:unknown;generationPolicy?:unknown;tenantConventions?:unknown;deliveryGuidePolicy?:{enabled:true;include_handover_instructions:boolean}};
const encoder=new TextEncoder();

function deterministicVector(text:string){const values=new Array<number>(48).fill(0);for(const [index,value] of encoder.encode(text.normalize('NFKC').toLocaleLowerCase('en-US')).entries())values[(value+index*17)%values.length]+=((value%29)+1)/29;const norm=Math.sqrt(values.reduce((sum,value)=>sum+value*value,0))||1;return values.map(value=>value/norm)}
const localEmbedder:Embedder=async(input:string[]):Promise<AIResult<number[][]>>=>({value:input.map(deterministicVector),metrics:{model:'LOCAL_DETERMINISTIC_HASH_EMBEDDING_NO_MODEL_CALL',latencyMs:0,promptTokens:null,completionTokens:null,totalTokens:null}});

function respond(value:unknown){process.stdout.write(`${JSON.stringify({ok:true,value})}\n`)}
const digest=(value:unknown)=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const diagnosticCodes=new Set(['CONFIRMED_REQUIREMENT_CONTRACT_INVALID','GENERATION_CONFIGURATION_REQUIRED','GENERATION_CONFIGURATION_INVALID','GOVERNED_KNOWLEDGE_UNAVAILABLE','GENERATION_INPUT_LIMIT','GENERATION_OPERATION_REQUIRED','GENERATION_EXECUTION_BINDING_REQUIRED','TRUSTED_REPORT_DESIGN_REQUIRED','REPORT_DESIGN_NORMALIZATION_FAILED','REPORT_DESIGN_SEMANTICS_FAILED','GUARDRAILS_BLOCKED','CANDIDATE_VALIDATION_FAILED']);
let diagnosticStage='INPUT';
function fail(error:unknown){
 const typed=reportDesignFailureDiagnostic(error);
 const raw=error instanceof Error?error.message:'',prefix=raw.split(':',1)[0];
 if(typed||!diagnosticCodes.has(prefix)){
  const code=typed?.code??(diagnosticStage==='REPORT_DESIGN'?'REPORT_DESIGN_INVALID':'GENERATION_PIPELINE_FAILED');
  const findings=typed?.findings??[],detail={stage:diagnosticStage,findings,truncated:typed?.truncated??false};
  while(JSON.stringify(detail).length>480&&findings.length){findings.pop();detail.truncated=true}
  process.stdout.write(`${JSON.stringify({ok:false,error:{code,message:JSON.stringify(detail)}})}\n`);return;
 }
 process.stdout.write(`${JSON.stringify({ok:false,error:{code:prefix,message:raw.slice(0,500)}})}\n`);
}
function qualifiedPolicy(value:unknown):TenantSettings{if(!value||typeof value!=='object')throw new Error('GENERATION_CONFIGURATION_REQUIRED');const policy=value as Record<string,unknown>,generation=policy.generation as Record<string,unknown>|undefined,organisation=policy.organisation as Record<string,unknown>|undefined,branding=policy.branding as Record<string,unknown>|undefined,governance=policy.governance as Record<string,unknown>|undefined;if(!generation||!organisation||!branding||!governance||!Array.isArray(generation.supportedTrendGrains)||typeof organisation.locale!=='string'||typeof branding.themeName!=='string'||typeof branding.primary!=='string'||typeof branding.accent!=='string')throw new Error('GENERATION_CONFIGURATION_INVALID');const tenant=structuredClone(value) as TenantSettings;validateCompilerCapabilities(tenant);return tenant}

async function main(){
 const chunks:Buffer[]=[];for await(const chunk of process.stdin)chunks.push(Buffer.from(chunk));const bytes=Buffer.concat(chunks);if(bytes.length>20_000_000)throw new Error('GENERATION_INPUT_LIMIT');
 const input=JSON.parse(bytes.toString('utf8')) as Request,dataStructure=input.dataStructure as DataStructure,contract=validateConfirmedRequirementContract(input.contract as ConfirmedRequirementContract,dataStructure),tenant=qualifiedPolicy(input.generationPolicy);
 const query=[contract.objective,contract.audience,...contract.businessQuestions.map(item=>item.question),...contract.obligations.flatMap(item=>[...item.measureNames,...item.fields])].join('\n');
 const retrieval=await retrieveKnowledge(query,50,localEmbedder),knowledge=retrieval.retrieved.map(({citation,text})=>({citation,text}));if(!knowledge.length)throw new Error('GOVERNED_KNOWLEDGE_UNAVAILABLE');
 if(input.operation==='knowledge'){respond({knowledge});return}
 if(input.operation!=='generate'&&input.operation!=='validate-design')throw new Error('GENERATION_OPERATION_REQUIRED');
 if(input.operation==='generate'&&!input.execution)throw new Error('GENERATION_EXECUTION_BINDING_REQUIRED');
 if(input.reportDesign===undefined||input.reportDesign===null)throw new Error('TRUSTED_REPORT_DESIGN_REQUIRED: no ReportDesign was supplied for local no-model generation.');
 diagnosticStage='REPORT_DESIGN';
 const original=validateReportDesign(input.reportDesign,knowledge.map(item=>item.citation),dataStructure,tenant.generation.supportedTrendGrains);
 diagnosticStage='NORMALIZATION';
 const maxVisualsPerPage=tenant.governance.maxVisualsPerPage;let normalization=normalizeReportDesign(original,dataStructure,maxVisualsPerPage),layoutOrder={applied:false,pageIndexes:[] as number[]};if(normalization.status==='FAILED'&&normalization.normalizationFindings.length>0&&normalization.normalizationFindings.every(item=>item.code==='LAYOUT_CAPACITY_EXCEEDED')){const ordered=orderVisualsForCompilerGrid(original,maxVisualsPerPage),orderedNormalization=normalizeReportDesign(ordered.reportDesign,dataStructure,maxVisualsPerPage);if(ordered.pageIndexes.length&&orderedNormalization.status!=='FAILED'){normalization=orderedNormalization;layoutOrder={applied:true,pageIndexes:ordered.pageIndexes}}}if(normalization.status==='FAILED')throw new Error(`REPORT_DESIGN_NORMALIZATION_FAILED: ${JSON.stringify(normalization.normalizationFindings.map(item=>{const pageIndex=original.pages.findIndex(page=>page.id===item.pageId),visualIndex=pageIndex<0?-1:original.pages[pageIndex].visuals.findIndex(visual=>visual.id===item.visualId);return{code:item.code,pageIndex,visualIndex,requestedResultingVisuals:item.requestedResultingVisuals,pageBounds:item.pageBounds,overflow:item.attemptedLayoutSlots?.map(({type,index,right,bottom})=>({type,index,right,bottom}))}}))}`);
 const design=normalization.normalizedReportDesign;
 // Compile and validate actual draft references; business coverage is advisory.

 diagnosticStage='GUARDRAILS';
 const interpretation=contract.provenance.interpretation as RequirementInterpretation,guardrails=evaluateGuardrails(interpretation,design,dataStructure,tenant);if(guardrails.generation!=='AVAILABLE')throw new Error(`GUARDRAILS_BLOCKED: ${guardrails.outcome}`);
 diagnosticStage='COMPILER';
 const candidate=compilePowerBI(design,dataStructure,tenant);diagnosticStage='CANDIDATE_FILES';const candidateValidation=validateGenericCandidate(candidate,design,dataStructure);if(candidateValidation.status!=='PASS')throw new Error('CANDIDATE_VALIDATION_FAILED');
 if(input.operation==='validate-design'){
  respond({projectName:candidate.projectName,files:candidate.files,validation:{status:'PASS',pipelineVersion:'protected-generation-1',stages:{contract:'PASS',governedKnowledge:'PASS',reportDesign:'PASS',normalization:layoutOrder.applied?'NORMALIZED':normalization.status,businessQuality:'NOT_CERTIFIED',draft:'EDITABLE_FIRST_DRAFT',guardrails:guardrails.outcome,compiler:'PASS',candidate:'PASS'},candidate:candidateValidation,runtime:{providerCalls:0,powerBiDesktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN',deployment:'NOT_RUN'}},provenance:{mode:'LOCAL_DETERMINISTIC_NO_MODEL_CALL',retrieval:{strategy:retrieval.strategy,citations:design.standardsApplied.map(item=>item.citation),embeddingModel:retrieval.embeddingModel},binding:input.binding,execution:input.execution,layoutOrder,reportDesign:design}});return
 }
 const binding=input.binding as Record<string,unknown>,execution=input.execution as Record<string,unknown>;
 if(!binding||!execution||typeof binding.settingsVersionId!=='string'||typeof execution.attemptId!=='string')throw new Error('GENERATION_EXECUTION_BINDING_REQUIRED');
 if(input.deliveryGuidePolicy?.enabled!==true||typeof input.deliveryGuidePolicy.include_handover_instructions!=='boolean')throw new Error('GENERATION_CONFIGURATION_INVALID');
 diagnosticStage='DELIVERY_GUIDE';
 const guide=createBoundDeliveryGuideText({design,interpretation:contract.provenance.interpretation as unknown as Record<string,unknown>,binding,execution,settings:{conventions:input.tenantConventions},includeHandoverInstructions:input.deliveryGuidePolicy.include_handover_instructions,reportDesignDigest:digest(design),candidateFilesDigest:digest(candidate.files)});
 candidate.files['Delivery-Guide.md']=guide;
 const guideDigest=createHash('sha256').update(guide).digest('hex');
 respond({projectName:candidate.projectName,files:candidate.files,guideDigest,validation:{status:'PASS',pipelineVersion:'protected-generation-1',stages:{contract:'PASS',governedKnowledge:'PASS',reportDesign:'PASS',normalization:layoutOrder.applied?'NORMALIZED':normalization.status,businessQuality:'NOT_CERTIFIED',draft:'EDITABLE_FIRST_DRAFT',guardrails:guardrails.outcome,compiler:'PASS',candidate:'PASS',deliveryGuide:'PASS'},candidate:candidateValidation,runtime:{providerCalls:0,powerBiDesktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN',deployment:'NOT_RUN'}},provenance:{mode:'LOCAL_DETERMINISTIC_NO_MODEL_CALL',retrieval:{strategy:retrieval.strategy,citations:design.standardsApplied.map(item=>item.citation),embeddingModel:retrieval.embeddingModel},binding:input.binding,execution:input.execution,layoutOrder,reportDesign:design,guideDigest}})
}

main().catch(error=>{fail(error);process.exitCode=1});
