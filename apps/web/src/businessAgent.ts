import {ApiError,savedAzureApi,type CaseFileAvailability,type NativeTask,type NativeAnswer,type NativeReceipt,type NativeContractCheck,type NativeAnalysisPreview,type DurableQuestion} from './api';

export class BusinessJourneyError extends Error {constructor(message:string,readonly safeToRecheck=false,readonly accessError?:ApiError){super(message);}}
export const requireCurrent=(current:()=>boolean)=>{if(!current())throw new BusinessJourneyError('This report changed. Reopen its current requirements before continuing.');};
export function agentAvailabilityMessage(input:CaseFileAvailability):string|null {
 if(!input.ready){
  if(input.files.some(file=>file.reason==='APBRA_WORKBOOK_ROUTE_NOT_IMPLEMENTED'))return 'Your Excel file is saved, but sending the original workbook to AI is not supported by this connection yet. Your administrator needs to resolve file delivery before AI can review it.';
  if(input.reason==='MODEL_INPUT_BUDGET_EXCEEDED')return 'Your complete requirements and files exceed the configured AI input limit. Nothing has been shortened or sent. Contact your administrator.';
  return 'AI cannot receive all the saved supporting information yet. Your work is safe. Ask your administrator to check the connection and supported files.';
 }
 if(input.receive_available!==true||!input.connection_id)return 'AI is not available for this request yet. Your administrator needs to enable an approved connection and spending allowance. Nothing has been sent.';
 if(!Number.isInteger(input.input_characters)||input.input_characters!<=0||input.input_limit===null||input.input_characters!>input.input_limit)return 'The complete AI request could not be checked against the configured limit. Nothing has been sent.';
 return null;
}
export function nativeAnalysisPreview(check:NativeContractCheck,receiptId:string,version:number):NativeAnalysisPreview|null {
 const preview=check.analysis_preview;if(!preview)return null;
 if(!check.recognized||!check.current||check.task!=='REQUIREMENT_ANALYSIS'||check.receipt_id!==receiptId||check.context_version!==version||preview.admission!=='NOT_ADMITTED'||preview.receipt_id!==receiptId||preview.context_version!==version)throw new BusinessJourneyError('The AI discussion does not match this request.');
 return preview;
}
export const canReviewNativeGoal=(preview:NativeAnalysisPreview|null,version:number,admin:boolean)=>Boolean(admin&&preview?.context_version===version&&preview.ai_state==='READY_FOR_CONFIRMATION'&&preview.questions.every(question=>!question.required));
export const answerDraft=(answers:Record<string,string>,id:string):string=>{const value=Object.prototype.hasOwnProperty.call(answers,id)?answers[id]:undefined;return typeof value==='string'?value:'';};
export const discussionReply=(question:DurableQuestion|undefined,answer:string)=>question?`AI question: ${question.question}\n\nMy answer: ${answer}`:answer;
export type AgentRun={receipt:NativeReceipt;answer:NativeAnswer;settingsId:string};
// Uses the existing case/tenant/settings/one-response lease. Never creates an
// access grant, reserves money, changes an endpoint or retries an uncertain POST.
export async function runBusinessAgent({caseId,contextVersion,csrfToken,task,contractId,current,storage,progress}:{caseId:string;contextVersion:number;csrfToken:string;task:NativeTask;contractId?:string;current:()=>boolean;storage:Pick<Storage,'getItem'|'setItem'>;progress:(value:string)=>void}):Promise<AgentRun>{
 requireCurrent(current);
 const input=await savedAzureApi.input(caseId,task,contractId);requireCurrent(current);
 if(input.context_version!==contextVersion)throw new BusinessJourneyError('Your requirements changed. Review the current version before continuing.');
 const unavailable=agentAvailabilityMessage(input);if(unavailable)throw new BusinessJourneyError(unavailable,true);
 const key='apbra-native-attempt:'+caseId+':'+input.connection_id;
 if(storage.getItem(key)!==null)throw new BusinessJourneyError('An AI request already started on this connection. Its result must be checked before another request is authorized. No automatic retry was made.');
 const command=crypto.randomUUID();storage.setItem(key,command);requireCurrent(current);
 progress(task==='REQUIREMENT_ANALYSIS'?'AI is reviewing your saved goal, answers and supporting information…':'AI is generating your report from the confirmed requirements…');
 let result;
 try{result=await savedAzureApi.receive(caseId,contextVersion,input.settings_id,command,csrfToken,{task,...(contractId?{confirmed_contract_id:contractId}:{})});}
 catch(error){throw new BusinessJourneyError('The AI request did not return a confirmed result. Your work remains saved. Ask your administrator to check its status before another attempt; it has not been retried.',false,error instanceof ApiError&&[401,403,404].includes(error.status)?error:undefined);}
 requireCurrent(current);const receipt=result.native_response;
 if(receipt.context_version!==contextVersion||receipt.state!=='RECEIVED'||receipt.http_status!==200||receipt.provider_status!=='completed'||!receipt.receipt_id)throw new BusinessJourneyError('AI did not complete this request. Your requirements remain saved. Your administrator can review the recorded failure; no automatic retry was made.');
 const answer=await savedAzureApi.view(caseId,receipt.receipt_id);requireCurrent(current);
 if(answer.receipt_id!==receipt.receipt_id||answer.context_version!==contextVersion)throw new BusinessJourneyError('The AI answer does not match the current request. No result was applied.');
 return {receipt,answer,settingsId:input.settings_id};
}
