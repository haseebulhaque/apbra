export type AIMetrics={model:string;latencyMs:number;promptTokens:number|null;completionTokens:number|null;totalTokens:number|null};
export type AIResult<T>={value:T;metrics:AIMetrics};
export type FoundryStatus={configured:boolean;chatDeployment:string;embeddingDeployment:string;apiMode:string};

export type ClarificationCategory='METRIC_DEFINITION'|'TIME_COMPARISON'|'SECURITY'|'AUDIENCE'|'PAGE_SCOPE'|'FILTER_SCOPE'|'OTHER';
export type RequirementInterpretation={
  request_kind:'POWER_BI_REPORT'; objective:string; kpis:string[]; dimensions:string[]; filters:string[]; pages:string[];
  assumptions:string[]; clarifications:Array<{id:string;category:ClarificationCategory;question:string;reason:string;required:boolean}>;
};

export type AIDesignPlan={
  artifact_kind:'AIDesignPlan';schema_version:1;objective:string;
  semantic_model:{grain:string;date_table:string;relationships:string[];measures:Array<{name:string;business_definition:string;formula_guidance:string}>};
  pages:Array<{name:string;purpose:string;visuals:Array<{type:string;title:string;fields:string[]}>;slicers:string[]}>;
  applied_standards:Array<{citation:string;application:string}>;assumptions:string[];limitations:string[];
};

const interpretationSchema={type:'object',additionalProperties:false,required:['request_kind','objective','kpis','dimensions','filters','pages','assumptions','clarifications'],properties:{
  request_kind:{type:'string',enum:['POWER_BI_REPORT']},objective:{type:'string'},kpis:{type:'array',items:{type:'string'}},dimensions:{type:'array',items:{type:'string'}},filters:{type:'array',items:{type:'string'}},pages:{type:'array',items:{type:'string'}},assumptions:{type:'array',items:{type:'string'}},clarifications:{type:'array',items:{type:'object',additionalProperties:false,required:['id','category','question','reason','required'],properties:{id:{type:'string'},category:{type:'string',enum:['METRIC_DEFINITION','TIME_COMPARISON','SECURITY','AUDIENCE','PAGE_SCOPE','FILTER_SCOPE','OTHER']},question:{type:'string'},reason:{type:'string'},required:{type:'boolean'}}}}
}};
const designSchema={type:'object',additionalProperties:false,required:['artifact_kind','schema_version','objective','semantic_model','pages','applied_standards','assumptions','limitations'],properties:{
  artifact_kind:{type:'string',enum:['AIDesignPlan']},schema_version:{type:'integer',enum:[1]},objective:{type:'string'},semantic_model:{type:'object',additionalProperties:false,required:['grain','date_table','relationships','measures'],properties:{grain:{type:'string'},date_table:{type:'string'},relationships:{type:'array',items:{type:'string'}},measures:{type:'array',items:{type:'object',additionalProperties:false,required:['name','business_definition','formula_guidance'],properties:{name:{type:'string'},business_definition:{type:'string'},formula_guidance:{type:'string'}}}}}},pages:{type:'array',items:{type:'object',additionalProperties:false,required:['name','purpose','visuals','slicers'],properties:{name:{type:'string'},purpose:{type:'string'},visuals:{type:'array',items:{type:'object',additionalProperties:false,required:['type','title','fields'],properties:{type:{type:'string'},title:{type:'string'},fields:{type:'array',items:{type:'string'}}}}},slicers:{type:'array',items:{type:'string'}}}}},applied_standards:{type:'array',items:{type:'object',additionalProperties:false,required:['citation','application'],properties:{citation:{type:'string'},application:{type:'string'}}}},assumptions:{type:'array',items:{type:'string'}},limitations:{type:'array',items:{type:'string'}}
}};

function object(value:unknown):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('AI_RESPONSE_INVALID');return value as Record<string,unknown>}
function strings(value:unknown){if(!Array.isArray(value)||!value.every(v=>typeof v==='string'))throw new Error('AI_RESPONSE_INVALID');return value as string[]}
export function validateInterpretation(value:unknown):RequirementInterpretation{
  const v=object(value);if(v.request_kind!=='POWER_BI_REPORT'||typeof v.objective!=='string')throw new Error('AI_RESPONSE_INVALID');
  const clarifications=(Array.isArray(v.clarifications)?v.clarifications:[]).map(item=>{const q=object(item);if(typeof q.id!=='string'||typeof q.question!=='string'||typeof q.reason!=='string'||typeof q.required!=='boolean'||!['METRIC_DEFINITION','TIME_COMPARISON','SECURITY','AUDIENCE','PAGE_SCOPE','FILTER_SCOPE','OTHER'].includes(String(q.category)))throw new Error('AI_RESPONSE_INVALID');return q as RequirementInterpretation['clarifications'][number]});
  if(new Set(clarifications.map(q=>q.id)).size!==clarifications.length||clarifications.some(q=>!q.id.trim()||!q.question.trim()))throw new Error('AI_RESPONSE_INVALID');
  return {request_kind:'POWER_BI_REPORT',objective:v.objective,kpis:strings(v.kpis),dimensions:strings(v.dimensions),filters:strings(v.filters),pages:strings(v.pages),assumptions:strings(v.assumptions),clarifications};
}
export function validateAIDesignPlan(value:unknown,allowedCitations:readonly string[]):AIDesignPlan{
  const v=object(value),model=object(v.semantic_model);if(v.artifact_kind!=='AIDesignPlan'||v.schema_version!==1||typeof v.objective!=='string'||typeof model.grain!=='string'||typeof model.date_table!=='string')throw new Error('AI_DESIGN_INVALID');
  const applied=(Array.isArray(v.applied_standards)?v.applied_standards:[]).map(item=>object(item));const allowed=new Set(allowedCitations);
  if(!applied.length||applied.some(x=>typeof x.citation!=='string'||typeof x.application!=='string'||!allowed.has(x.citation)))throw new Error('AI_DESIGN_CITATION_INVALID');
  return v as unknown as AIDesignPlan;
}

async function post(path:string,body:unknown){const start=performance.now();let response:Response;try{response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}catch{throw new Error('AI_SERVICE_UNAVAILABLE')};const latencyMs=Math.round(performance.now()-start);const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(`AI_SERVICE_UNAVAILABLE: ${String(data?.error?.code??response.status)}`);return {data,latencyMs};}
export async function foundryStatus():Promise<FoundryStatus>{const response=await fetch('/api/ai/status');if(!response.ok)throw new Error('AI_SERVICE_UNAVAILABLE');return response.json()}
async function structured<T>(name:string,schema:unknown,messages:Array<{role:'system'|'user';content:string}>,validate:(v:unknown)=>T):Promise<AIResult<T>>{
  const {data,latencyMs}=await post('/api/ai/chat',{messages,response_format:{type:'json_schema',json_schema:{name,strict:true,schema}}});
  const content=data?.choices?.[0]?.message?.content;if(typeof content!=='string')throw new Error('AI_RESPONSE_INVALID');let parsed:unknown;try{parsed=JSON.parse(content)}catch{throw new Error('AI_RESPONSE_INVALID')};
  return {value:validate(parsed),metrics:{model:String(data.model??'configured deployment'),latencyMs,promptTokens:data.usage?.prompt_tokens??null,completionTokens:data.usage?.completion_tokens??null,totalTokens:data.usage?.total_tokens??null}};
}
export async function interpretRequirement(prompt:string,schema:unknown){
  const system='You are a Power BI solution architect. Interpret the supplied request against the supplied synthetic schema. Return only the required JSON. Ask at most five concise targeted questions for material ambiguities that affect metric definitions, time comparisons, security versus filtering, audience, pages, or filters. Combine related metric questions when practical. A requested metric is materially ambiguous when the schema offers multiple monetary or count interpretations; ask which field and aggregation defines it. For year-over-year or other time comparisons, clarify coverage, grain, and missing-prior-period behaviour when unspecified and classify that question as TIME_COMPARISON. If users must filter by a security-sensitive organisational dimension such as Region or Business Area and the request does not state whether this is only a slicer or access control, ask a SECURITY clarification. Derive every question from the actual input and schema; do not assume fixture answers and do not invent schema fields.';
  return structured('power_bi_requirement_interpretation',interpretationSchema,[{role:'system',content:system},{role:'user',content:JSON.stringify({request:prompt,schema})}],validateInterpretation);
}
export async function generateGroundedDesignPlan(snapshot:unknown,schema:unknown,chunks:Array<{citation:string;text:string}>){
  const allowed=chunks.map(c=>c.citation);const system='You are a Power BI solution architect. Produce the required structured design using the confirmed requirements, schema, and retrieved customer standards. Use only supplied citations for customer policy, distinguish requirements from recommendations, never invent customer policy, and put unknown or unsupported items in limitations. Formula guidance is advisory text, never executable authority.';
  return structured('grounded_power_bi_design_plan',designSchema,[{role:'system',content:system},{role:'user',content:JSON.stringify({confirmedRequirements:snapshot,schema,retrievedStandards:chunks})}],v=>validateAIDesignPlan(v,allowed));
}
export async function embedTexts(input:string[]):Promise<AIResult<number[][]>>{
  const {data,latencyMs}=await post('/api/ai/embeddings',{input});const vectors=Array.isArray(data.data)?data.data.map((x:any)=>x.embedding):null;if(!vectors||vectors.length!==input.length||vectors.some((v:unknown)=>!Array.isArray(v)||!v.every(n=>typeof n==='number')))throw new Error('EMBEDDING_RESPONSE_INVALID');
  return {value:vectors,metrics:{model:String(data.model??'configured deployment'),latencyMs,promptTokens:data.usage?.prompt_tokens??null,completionTokens:null,totalTokens:data.usage?.total_tokens??null}};
}
