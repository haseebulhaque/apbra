import {applyClarificationAnalysis,beginClarificationAnalysis,confirmClarificationUnderstanding,createClarificationSession,submitClarificationAnswers,type ClarificationSession,type IterativeClarificationQuestion} from '../src/clarification';
import {
  materializeIterativeConfirmedRequirements,
  validateIterativeConfirmationReadiness,
} from '../src/confirmedRequirements';

type BridgeRequest={
  operation:'simulate'|'readiness'|'confirm';
  dataStructure:unknown;
  session:unknown;
  confirmedAt?:string;
  readinessBinding?:string;
  contextBinding?:string;
  sessionId?:string;
  originalRequest?:string;
  analysedAt?:string;
};

function respond(value:unknown){
  process.stdout.write(`${JSON.stringify({ok:true,value})}\n`);
}

function fail(error:unknown){
  const message=error instanceof Error?error.message:'Semantic validation failed.';
  process.stdout.write(`${JSON.stringify({ok:false,error:{code:'SEMANTIC_VALIDATION_FAILED',message}})}\n`);
}

async function main(){
  const chunks:Buffer[]=[];
  for await(const chunk of process.stdin)chunks.push(Buffer.from(chunk));
  if(Buffer.concat(chunks).length>1_000_000)throw new Error('Semantic bridge input exceeds the bounded limit.');
  const input=JSON.parse(Buffer.concat(chunks).toString('utf8')) as BridgeRequest;
  if(input.operation==='simulate'){
    if(!input.sessionId||!input.originalRequest||!input.contextBinding||!input.analysedAt)throw new Error('Server-derived simulation inputs are required.');
    const structure=input.dataStructure as {tables?:Array<{name?:string;columns?:Array<{name?:string;type?:string}>}>};
    const request=input.originalRequest,candidates=(structure.tables??[]).flatMap(table=>(table.columns??[]).map(column=>({table:String(table.name??''),column:String(column.name??''),type:String(column.type??'')}))).filter(item=>item.table&&item.column);
    let binding:unknown;
    try{binding=JSON.parse(input.contextBinding)}catch{throw new Error('Server-derived context binding is malformed.')}
    const context=binding as {requestVersionId?:string;semanticContextVersion?:number;conversation?:Array<{kind?:string;payload?:{questionId?:string;rawAnswer?:string;suggestionId?:string;decision?:string;requestVersionId?:string;interpretationContextVersion?:number;text?:string}}>} ;
    if(typeof context.requestVersionId!=='string'||!context.requestVersionId||!Number.isInteger(context.semanticContextVersion))throw new Error('Server-derived request/context-version binding is missing.');
    const answers=(context.conversation??[]).filter(item=>item.kind==='RAW_ANSWER').map(item=>item.payload??{}).filter(item=>typeof item.questionId==='string'&&typeof item.rawAnswer==='string'&&item.requestVersionId===context.requestVersionId);
    const textFor=(answerCount:number)=>[request,...answers.slice(0,answerCount).filter(item=>item.decision!=='DECLINE').map(item=>String(item.rawAnswer))].join(' ').toLocaleLowerCase();
    const selected=(answerCount:number)=>{const lower=textFor(answerCount),mentioned=candidates.filter(item=>lower.includes(item.column.toLocaleLowerCase()));return{numeric:mentioned.filter(item=>['integer','decimal'].includes(item.type)),dimensions:mentioned.filter(item=>item.type==='text')}};
    const provisional={request_kind:'POWER_BI_REPORT',objective:request,businessQuestions:[],kpis:[],dimensions:[],filters:[],audience:'Business users',pages:['Summary'],assumptions:[],ambiguities:['The business measure and comparison category must be confirmed from qualified evidence.'],clarifications:[],coverageRequirements:[],businessQuestionCoverage:[]} as const;
    const emptySummary={objective:request,businessQuestions:[],kpiDefinitions:[],scopeAndTime:['Use all rows in the currently qualified evidence set.'],dimensionsAndFilters:[],lifecycleDefinitions:[],materialPolicyDecisions:['This local deterministic preview used no AI/model call.']};
    const options=candidates.filter(item=>['integer','decimal'].includes(item.type)).flatMap((metric,metricIndex)=>candidates.filter(item=>item.type==='text').map((dimension,dimensionIndex)=>({id:`observed-fields-${metricIndex}-${dimensionIndex}`,label:`Summarise ${metric.column} and compare it by ${dimension.column}`,metric,dimension}))).slice(0,3);
    const questionFor=(round:number,contextVersion=context.semanticContextVersion):IterativeClarificationQuestion=>({id:`field-meaning-${context.requestVersionId}-${contextVersion}-${round}`,category:'METRIC_DEFINITION',question:'Which observed numeric field represents the business measure, and which observed category should managers compare it by?',reason:'APBRA must not invent which observed fields carry the material business meaning.',required:true,suggestions:options.map(({id,label})=>({id,label})),allowFreeText:true});
    let session:ClarificationSession=beginClarificationAnalysis(createClarificationSession({sessionId:input.sessionId,mode:'BUSINESS',originalRequest:request,limits:{maxRounds:3,maxQuestionsPerRound:3,maxAnswerCharacters:500},contextBinding:input.contextBinding}));
    let chosen=selected(0),answerIndex=0,acceptedChoice:{numeric:typeof candidates;dimensions:typeof candidates}|null=null;
    while((chosen.numeric.length!==1||chosen.dimensions.length!==1)&&answerIndex<answers.length){
      const answer=answers[answerIndex];
      if(!Number.isInteger(answer.interpretationContextVersion))throw new Error('A durable answer is missing its server-issued context binding.');
      const question=questionFor(session.rounds.length+1,answer.interpretationContextVersion);
      session=applyClarificationAnalysis(session,{state:'NEEDS_CLARIFICATION',interpretation:structuredClone(provisional),questions:[question],unresolvedAmbiguities:[...provisional.ambiguities],confirmationSummary:emptySummary,conflictReasons:[],analysedAt:input.analysedAt});
      answerIndex+=1;
      if(answer.questionId!==question.id)throw new Error('A durable answer does not match the current server-issued question.');
      const decision=answer.decision??'FREE_TEXT',suggestionId=typeof answer.suggestionId==='string'?answer.suggestionId:'';
      if(!['ACCEPT','DECLINE','FREE_TEXT'].includes(decision))throw new Error('A durable answer has an unsupported decision.');
      if(decision==='ACCEPT'){
        const suggestion=question.suggestions.find(item=>item.id===suggestionId);
        if(!suggestion||answer.rawAnswer!==suggestion.label)throw new Error('An accepted answer is not bound to the exact server-issued choice.');
        const option=options.find(item=>item.id===suggestionId);
        if(!option)throw new Error('An accepted answer does not identify qualified observed fields.');
        acceptedChoice={numeric:[option.metric],dimensions:[option.dimension]};
      }else if(suggestionId){throw new Error('Only an accepted answer may reference a suggested choice.');}
      session=submitClarificationAnswers(session,{answers:[{questionId:question.id,rawAnswer:String(answer.rawAnswer),suggestionId:decision==='ACCEPT'?suggestionId:''}],answeredAt:input.analysedAt});
      chosen=acceptedChoice??selected(answerIndex);
    }
    if(chosen.numeric.length!==1||chosen.dimensions.length!==1){
      const question=questionFor(session.rounds.length+1);
      session=applyClarificationAnalysis(session,{state:'NEEDS_CLARIFICATION',interpretation:structuredClone(provisional),questions:[question],unresolvedAmbiguities:[...provisional.ambiguities],confirmationSummary:emptySummary,conflictReasons:[],analysedAt:input.analysedAt});
      respond({session});return;
    }
    const numeric=chosen.numeric,dimensions=chosen.dimensions;
    const metric=numeric[0],dimension=dimensions[0],field=`${metric.table}.${metric.column}`,dimensionField=`${dimension.table}.${dimension.column}`,measureName=`Total ${metric.column}`,question=`How does ${measureName.toLocaleLowerCase()} vary by ${dimension.column}?`;
    const measure={id:'local-measure-1',name:measureName,businessDefinition:`Sum of observed ${field}.`,aggregation:'SUM',field,numeratorMeasureId:'',denominatorMeasureId:'',format:'decimal',filterField:'',filterValue:'',contextField:''} as const;
    const kpi={id:'local-kpi-1',kind:'KPI',measureNames:[measureName],fields:[],pageNames:['Summary'],required:true,minimumRepresentations:1,measures:[measure],timeGrain:'NONE',lifecycleValues:[]} as const;
    const breakdown={...kpi,id:'local-breakdown-1',kind:'BREAKDOWN',fields:[dimensionField]} as const;
    const interpretation={request_kind:'POWER_BI_REPORT',objective:request,businessQuestions:[question],kpis:[measureName],dimensions:[dimension.column],filters:[],audience:'Business users',pages:['Summary'],assumptions:['Use all rows in the currently qualified evidence set.'],ambiguities:[],clarifications:[],coverageRequirements:[kpi,breakdown],businessQuestionCoverage:[{question,coverageRequirementIds:[kpi.id,breakdown.id]}]} as const;
    const summary={objective:request,businessQuestions:[question],kpiDefinitions:[`${measureName} is the sum of ${field}.`],scopeAndTime:['Use all rows in the currently qualified evidence set.'],dimensionsAndFilters:[`${dimension.column} is the confirmed breakdown.`],lifecycleDefinitions:[],materialPolicyDecisions:['This local deterministic preview used no AI/model call.']};
    session=applyClarificationAnalysis(session,{state:'READY_FOR_CONFIRMATION',interpretation:structuredClone(interpretation),questions:[],unresolvedAmbiguities:[],confirmationSummary:summary,conflictReasons:[],analysedAt:input.analysedAt});
    respond({session});return;
  }
  if(input.operation==='readiness'){
    const session=input.session as Parameters<typeof validateIterativeConfirmationReadiness>[0]['session'];
    const authority=validateIterativeConfirmationReadiness({dataStructure:input.dataStructure,session});
    respond({authority,readinessBinding:session.readinessBinding,contextBinding:session.contextBinding,confirmationSummary:session.confirmationSummary});
    return;
  }
  if(input.operation==='confirm'){
    if(!input.confirmedAt||!input.readinessBinding||!input.contextBinding)throw new Error('Exact confirmation inputs are required.');
    const session=confirmClarificationUnderstanding(
      input.session as Parameters<typeof confirmClarificationUnderstanding>[0],
      {confirmedAt:input.confirmedAt,readinessBinding:input.readinessBinding,contextBinding:input.contextBinding},
    );
    respond({session,contract:materializeIterativeConfirmedRequirements({dataStructure:input.dataStructure,session})});
    return;
  }
  throw new Error('Unsupported semantic bridge operation.');
}

main().catch(error=>{fail(error);process.exitCode=1});
