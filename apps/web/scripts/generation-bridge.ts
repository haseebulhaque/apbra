import {validateConfirmedRequirementContract,type ConfirmedRequirementContract} from '../src/confirmedRequirements';
import {validateConfirmedMeasureAuthority,validateReportDesign,type AIResult,type RequirementInterpretation} from '../src/foundry';
import {compilePowerBI,validateGenericCandidate} from '../src/genericPowerBI';
import {evaluateGuardrails} from '../src/guardrail';
import {retrieveKnowledge,type Embedder} from '../src/rag';
import {inspectLayoutRepairSemantics,normalizeReportDesign} from '../src/reportDesignNormalization';
import type {DataStructure} from '../src/schemaIngestion';
import type {TenantSettings} from '../src/tenant';

type Request={operation?:'knowledge'|'generate';contract:unknown;dataStructure:unknown;reportDesign?:unknown;binding:unknown;execution?:unknown;generationPolicy?:unknown};
const encoder=new TextEncoder();

function deterministicVector(text:string){const values=new Array<number>(48).fill(0);for(const [index,value] of encoder.encode(text.normalize('NFKC').toLocaleLowerCase('en-US')).entries())values[(value+index*17)%values.length]+=((value%29)+1)/29;const norm=Math.sqrt(values.reduce((sum,value)=>sum+value*value,0))||1;return values.map(value=>value/norm)}
const localEmbedder:Embedder=async(input:string[]):Promise<AIResult<number[][]>>=>({value:input.map(deterministicVector),metrics:{model:'LOCAL_DETERMINISTIC_HASH_EMBEDDING_NO_MODEL_CALL',latencyMs:0,promptTokens:null,completionTokens:null,totalTokens:null}});

function respond(value:unknown){process.stdout.write(`${JSON.stringify({ok:true,value})}\n`)}
function fail(error:unknown){const message=error instanceof Error?error.message:'Generation failed.';process.stdout.write(`${JSON.stringify({ok:false,error:{code:'GENERATION_PIPELINE_FAILED',message:message.slice(0,500)}})}\n`)}
function qualifiedPolicy(value:unknown):TenantSettings{if(!value||typeof value!=='object')throw new Error('GENERATION_CONFIGURATION_REQUIRED');const policy=value as Record<string,unknown>,generation=policy.generation as Record<string,unknown>|undefined,organisation=policy.organisation as Record<string,unknown>|undefined,branding=policy.branding as Record<string,unknown>|undefined,governance=policy.governance as Record<string,unknown>|undefined;if(!generation||!organisation||!branding||!governance||!Array.isArray(generation.supportedTrendGrains)||generation.supportedTrendGrains.some(item=>!['NONE','DAY','WEEK','MONTH','QUARTER','YEAR'].includes(String(item)))||typeof organisation.locale!=='string'||typeof branding.themeName!=='string'||typeof branding.primary!=='string'||typeof branding.accent!=='string')throw new Error('GENERATION_CONFIGURATION_INVALID');return structuredClone(value) as TenantSettings}

async function main(){
 const chunks:Buffer[]=[];for await(const chunk of process.stdin)chunks.push(Buffer.from(chunk));const bytes=Buffer.concat(chunks);if(bytes.length>20_000_000)throw new Error('GENERATION_INPUT_LIMIT');
 const input=JSON.parse(bytes.toString('utf8')) as Request,dataStructure=input.dataStructure as DataStructure,contract=validateConfirmedRequirementContract(input.contract as ConfirmedRequirementContract,dataStructure),tenant=qualifiedPolicy(input.generationPolicy);
 const query=[contract.objective,contract.audience,...contract.businessQuestions.map(item=>item.question),...contract.obligations.flatMap(item=>[...item.measureNames,...item.fields])].join('\n');
 const retrieval=await retrieveKnowledge(query,50,localEmbedder),knowledge=retrieval.retrieved.map(({citation,text})=>({citation,text}));if(!knowledge.length)throw new Error('GOVERNED_KNOWLEDGE_UNAVAILABLE');
 if(input.operation==='knowledge'){respond({knowledge});return}
 if(input.operation!=='generate')throw new Error('GENERATION_OPERATION_REQUIRED');
 if(!input.execution)throw new Error('GENERATION_EXECUTION_BINDING_REQUIRED');
 if(input.reportDesign===undefined||input.reportDesign===null)throw new Error('TRUSTED_REPORT_DESIGN_REQUIRED: no ReportDesign was supplied for local no-model generation.');
 const original=validateReportDesign(input.reportDesign,knowledge.map(item=>item.citation),dataStructure,tenant.generation.supportedTrendGrains);validateConfirmedMeasureAuthority(original,contract);
 const normalization=normalizeReportDesign(original,dataStructure);if(normalization.status==='FAILED')throw new Error(`REPORT_DESIGN_NORMALIZATION_FAILED: ${normalization.normalizationFindings.map(item=>item.code).join(',')}`);
 const design=normalization.normalizedReportDesign,semanticInspection=inspectLayoutRepairSemantics(original,design,contract);if(semanticInspection.status!=='PASS')throw new Error(`REPORT_DESIGN_SEMANTICS_FAILED: ${semanticInspection.findings.filter(item=>item.result==='FAIL').map(item=>item.code).join(',')}`);
 const interpretation=contract.provenance.interpretation as RequirementInterpretation,guardrails=evaluateGuardrails(interpretation,design,dataStructure,tenant);if(guardrails.generation!=='AVAILABLE')throw new Error(`GUARDRAILS_BLOCKED: ${guardrails.outcome}`);
 const candidate=compilePowerBI(design,dataStructure,tenant),candidateValidation=validateGenericCandidate(candidate,design,dataStructure);if(candidateValidation.status!=='PASS')throw new Error('CANDIDATE_VALIDATION_FAILED');
 respond({projectName:candidate.projectName,files:candidate.files,validation:{status:'PASS',pipelineVersion:'protected-generation-1',stages:{contract:'PASS',governedKnowledge:'PASS',reportDesign:'PASS',normalization:normalization.status,semanticPreservation:'PASS',guardrails:guardrails.outcome,compiler:'PASS',candidate:'PASS'},candidate:candidateValidation,runtime:{providerCalls:0,powerBiDesktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN',deployment:'NOT_RUN'}},provenance:{mode:'LOCAL_DETERMINISTIC_NO_MODEL_CALL',retrieval:{strategy:retrieval.strategy,citations:design.standardsApplied.map(item=>item.citation),embeddingModel:retrieval.embeddingModel},binding:input.binding,execution:input.execution,reportDesign:design}})
}

main().catch(error=>{fail(error);process.exitCode=1});
