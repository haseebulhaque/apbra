import type {ConfirmedRequirementInterpretation} from './foundry';

export type InteractionMode='BUSINESS'|'ADVANCED';
export type ClarificationState='REQUEST'|'ANALYSING'|'NEEDS_CLARIFICATION'|'READY_FOR_CONFIRMATION'|'CONFIRMED'|'HUMAN_REVIEW_REQUIRED'|'UNSUPPORTED'|'OUT_OF_SCOPE';
export type KnowledgeClassification='PLATFORM_POLICY'|'TENANT_GOVERNED'|'DEMO_FIXTURE';
export type ClarificationSuggestion={id:string;label:string};
export type IterativeClarificationQuestion={id:string;category:'METRIC_DEFINITION'|'TIME_COMPARISON'|'SECURITY'|'AUDIENCE'|'PAGE_SCOPE'|'FILTER_SCOPE'|'OTHER';question:string;reason:string;required:boolean;suggestions:ClarificationSuggestion[];allowFreeText:boolean};
export type ClarificationAnswer={questionId:string;rawAnswer:string;suggestionId:string;answeredAt:string};
export type ClarificationRound={round:number;askedAt:string;questions:IterativeClarificationQuestion[];answers:ClarificationAnswer[]};
export type MaterialConfirmationSummary={objective:string;businessQuestions:string[];kpiDefinitions:string[];scopeAndTime:string[];dimensionsAndFilters:string[];lifecycleDefinitions:string[];materialPolicyDecisions:string[]};
export type ClarificationLimits={maxRounds:number;maxQuestionsPerRound:number;maxAnswerCharacters:number};
export type ClarificationAnalysisRecord={analysedAt:string;proposedState:Exclude<ClarificationState,'REQUEST'|'ANALYSING'|'CONFIRMED'>;interpretation:ConfirmedRequirementInterpretation;unresolvedAmbiguities:string[];confirmationSummary:MaterialConfirmationSummary;conflictReasons:string[]};
export type ClarificationSession={
  schemaVersion:1;
  sessionId:string;
  mode:InteractionMode;
  state:ClarificationState;
  originalRequest:string;
  limits:ClarificationLimits;
  rounds:ClarificationRound[];
  analyses:ClarificationAnalysisRecord[];
  corrections:Array<{rawCorrection:string;correctedAt:string}>;
  currentInterpretation:ConfirmedRequirementInterpretation|null;
  unresolvedAmbiguities:string[];
  confirmationSummary:MaterialConfirmationSummary|null;
  conflictReasons:string[];
  confirmedAt:string;
};

export class ClarificationStateError extends Error{constructor(message:string){super(`CLARIFICATION_STATE_INVALID: ${message}`);this.name='ClarificationStateError'}}

const clean=(value:string)=>value.trim();
const clone=<T,>(value:T):T=>structuredClone(value);
function validLimits(limits:ClarificationLimits){return Number.isInteger(limits.maxRounds)&&limits.maxRounds>0&&Number.isInteger(limits.maxQuestionsPerRound)&&limits.maxQuestionsPerRound>0&&Number.isInteger(limits.maxAnswerCharacters)&&limits.maxAnswerCharacters>0}

export function createClarificationSession(input:{sessionId:string;mode:InteractionMode;originalRequest:string;limits:ClarificationLimits}):ClarificationSession{
  if(!clean(input.sessionId)||!clean(input.originalRequest)||!validLimits(input.limits))throw new ClarificationStateError('A session identity, original request, and positive configured limits are required.');
  return{schemaVersion:1,sessionId:input.sessionId,mode:input.mode,state:'REQUEST',originalRequest:input.originalRequest,limits:clone(input.limits),rounds:[],analyses:[],corrections:[],currentInterpretation:null,unresolvedAmbiguities:[],confirmationSummary:null,conflictReasons:[],confirmedAt:''};
}

export function beginClarificationAnalysis(session:ClarificationSession):ClarificationSession{
  if(session.state!=='REQUEST')throw new ClarificationStateError(`Cannot begin initial analysis from ${session.state}.`);
  return{...clone(session),state:'ANALYSING',confirmedAt:''};
}

export function submitClarificationAnswers(session:ClarificationSession,input:{answers:Array<{questionId:string;rawAnswer:string;suggestionId?:string}>;answeredAt:string}):ClarificationSession{
  if(session.state!=='NEEDS_CLARIFICATION')throw new ClarificationStateError(`Answers are not accepted from ${session.state}.`);
  const next=clone(session),round=next.rounds.at(-1);if(!round||round.answers.length)throw new ClarificationStateError('The active clarification round is missing or already answered.');
  const answers=input.answers.map(answer=>({questionId:clean(answer.questionId),rawAnswer:answer.rawAnswer,suggestionId:clean(answer.suggestionId??''),answeredAt:input.answeredAt}));
  if(new Set(answers.map(answer=>answer.questionId)).size!==answers.length)throw new ClarificationStateError('Answers must reference unique questions.');
  for(const question of round.questions){const answer=answers.find(item=>item.questionId===question.id);if(question.required&&!answer?.rawAnswer.trim())throw new ClarificationStateError(`Required question '${question.id}' has no answer.`);if(!answer)continue;if(answer.rawAnswer.length>next.limits.maxAnswerCharacters)throw new ClarificationStateError(`Answer '${question.id}' exceeds the configured length limit.`);if(answer.suggestionId&&!question.suggestions.some(item=>item.id===answer.suggestionId))throw new ClarificationStateError(`Answer '${question.id}' references an unknown suggestion.`);if(!question.allowFreeText&&!answer.suggestionId)throw new ClarificationStateError(`Question '${question.id}' requires one of its suggested answers.`)}
  if(answers.some(answer=>!round.questions.some(question=>question.id===answer.questionId)))throw new ClarificationStateError('An answer references an unknown question.');
  round.answers=answers;next.state='ANALYSING';return next;
}

export function applyClarificationAnalysis(session:ClarificationSession,input:{state:Exclude<ClarificationState,'REQUEST'|'ANALYSING'|'CONFIRMED'>;interpretation:ConfirmedRequirementInterpretation;questions:IterativeClarificationQuestion[];unresolvedAmbiguities:string[];confirmationSummary:MaterialConfirmationSummary;conflictReasons:string[];analysedAt:string}):ClarificationSession{
  if(session.state!=='ANALYSING')throw new ClarificationStateError(`AI analysis is not accepted from ${session.state}.`);
  const next=clone(session),questionIds=input.questions.map(item=>clean(item.id));
  if(questionIds.some(id=>!id)||new Set(questionIds).size!==questionIds.length)throw new ClarificationStateError('Question IDs must be non-empty and unique within a round.');
  if(input.questions.length>next.limits.maxQuestionsPerRound)throw new ClarificationStateError('AI returned more questions than the configured per-round limit.');
  if(input.questions.some(item=>!clean(item.question)||!clean(item.reason)||(!item.allowFreeText&&!item.suggestions.length)||new Set(item.suggestions.map(option=>option.id)).size!==item.suggestions.length))throw new ClarificationStateError('AI returned a malformed clarification question.');
  next.analyses.push(clone({analysedAt:input.analysedAt,proposedState:input.state,interpretation:input.interpretation,unresolvedAmbiguities:input.unresolvedAmbiguities,confirmationSummary:input.confirmationSummary,conflictReasons:input.conflictReasons}));next.currentInterpretation=clone(input.interpretation);next.unresolvedAmbiguities=clone(input.unresolvedAmbiguities);next.confirmationSummary=clone(input.confirmationSummary);next.conflictReasons=clone(input.conflictReasons);
  if(input.state==='NEEDS_CLARIFICATION'){
    if(!input.questions.length||!input.unresolvedAmbiguities.length)throw new ClarificationStateError('Clarification requires questions and unresolved material ambiguity.');
    if(next.rounds.length>=next.limits.maxRounds){next.state='HUMAN_REVIEW_REQUIRED';next.conflictReasons=[...next.conflictReasons,'Configured clarification-round limit exhausted while material ambiguity remains.'];return next}
    next.rounds.push({round:next.rounds.length+1,askedAt:input.analysedAt,questions:clone(input.questions),answers:[]});next.state='NEEDS_CLARIFICATION';return next;
  }
  if(input.questions.length)throw new ClarificationStateError(`${input.state} cannot include unanswered clarification questions.`);
  if(input.state==='READY_FOR_CONFIRMATION'&&(input.unresolvedAmbiguities.length||input.interpretation.ambiguities.length||input.interpretation.request_kind!=='POWER_BI_REPORT'))throw new ClarificationStateError('Ready for confirmation requires a Power BI interpretation with no unresolved material ambiguity.');
  if(input.state==='OUT_OF_SCOPE'&&input.interpretation.request_kind!=='OUT_OF_SCOPE')throw new ClarificationStateError('OUT_OF_SCOPE requires an out-of-scope interpretation.');
  next.state=input.state;return next;
}

export function correctClarificationUnderstanding(session:ClarificationSession,rawCorrection:string,correctedAt:string):ClarificationSession{
  if(session.state!=='READY_FOR_CONFIRMATION')throw new ClarificationStateError(`Correction is not accepted from ${session.state}.`);if(!rawCorrection.trim()||rawCorrection.length>session.limits.maxAnswerCharacters)throw new ClarificationStateError('A bounded correction is required.');const next=clone(session);next.corrections.push({rawCorrection,correctedAt});next.state='ANALYSING';next.confirmedAt='';return next;
}

export function confirmClarificationUnderstanding(session:ClarificationSession,confirmedAt:string):ClarificationSession{
  if(session.state!=='READY_FOR_CONFIRMATION'||!session.currentInterpretation||!session.confirmationSummary||!clean(confirmedAt))throw new ClarificationStateError('Only a complete ready understanding can be confirmed.');const next=clone(session);next.state='CONFIRMED';next.confirmedAt=confirmedAt;return next;
}
