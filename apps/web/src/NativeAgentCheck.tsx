import {useEffect,useRef,useState} from 'react';
import {ApiError,acceptanceApi,savedAzureApi,type NativeTask,type CaseFileAvailability,type NativeReceipt} from './api';

export function NativeAgentCheck({caseId,contextVersion,csrfToken,unsavedGoal=false,onSaved,onError}:{caseId:string;contextVersion:number;csrfToken:string;unsavedGoal?:boolean;onSaved:()=>void;onError:(error:unknown)=>void}){
 const [task,setTask]=useState<NativeTask>('REQUIREMENT_ANALYSIS'),[contractId,setContractId]=useState<string|undefined>();
 const [input,setInput]=useState<CaseFileAvailability|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[receipt,setReceipt]=useState<NativeReceipt|null>(null),[attempted,setAttempted]=useState(false);
 const epoch=useRef(0),mounted=useRef(false),running=useRef(false);
 const binding=caseId+':'+contextVersion+':'+csrfToken+':'+unsavedGoal+':'+task;
 const current=useRef(binding);current.current=binding;
 useEffect(()=>{mounted.current=true;epoch.current++;setInput(null);setReceipt(null);setMessage('');setAttempted(false);setBusy(false);return()=>{mounted.current=false;epoch.current++}},[binding]);
 const key=(id:string)=>'apbra-native-attempt:'+caseId+':'+id;
 function valid(at:number,context:string){return mounted.current&&at===epoch.current&&context===current.current}
 function failed(error:unknown){if(error instanceof ApiError&&[401,403,404].includes(error.status))onError(error)}
 async function inspect(){
  if(running.current||unsavedGoal)return;running.current=true;setBusy(true);const at=++epoch.current,context=current.current;
  setInput(null);setMessage('');setReceipt(null);
  try{let confirmed:string|undefined;
   if(task==='REPORT_DESIGN'){const state=await acceptanceApi.state(caseId);if(!valid(at,context))return;if(!state.confirmed_contract?.current)throw new Error('CURRENT_CONFIRMATION_REQUIRED');confirmed=state.confirmed_contract.id}
   const value=await (task==='REPORT_DESIGN'?savedAzureApi.input(caseId,task,confirmed):savedAzureApi.input(caseId));if(!valid(at,context))return;
   if(value.context_version!==contextVersion)throw new Error('CONTEXT_CHANGED');
   let previous=false;
   if(value.connection_id){try{previous=sessionStorage.getItem(key(value.connection_id))!==null}catch{throw new Error('ATTEMPT_STORAGE_UNAVAILABLE')}}
   setAttempted(previous);setInput(value);setContractId(confirmed);
   setMessage(previous?'An attempt was already started on this connection. Inspect saved answers and error history; do not send again.':value.receive_available===true?'A private connection authorizes one response for this saved report. Sending may incur the approved charge.':'A fresh private connection and bounded authorization are required before sending. Saved answers remain available.');
  }catch(error){if(valid(at,context)){setMessage(task==='REPORT_DESIGN'?'A current explicitly confirmed contract and complete sources are required for a design request. No request was sent.':'Could not verify the current saved input and connection. No request was sent.');failed(error)}}
  finally{running.current=false;if(valid(at,context))setBusy(false)}
 }
 async function send(){
  if(running.current||attempted||unsavedGoal||!input?.ready||input.receive_available!==true||!input.connection_id||input.context_version!==contextVersion||!Number.isInteger(input.input_characters)||input.input_characters!<=0||input.input_limit===null||input.input_characters!>input.input_limit)return;
  running.current=true;setBusy(true);const at=++epoch.current,context=current.current;
  try{
   // Record before POST; a lost response must never offer a fresh paid retry.
   const storageKey=key(input.connection_id);
   if(sessionStorage.getItem(storageKey)!==null){setAttempted(true);setMessage('An attempt already started. Inspect saved answers and error history.');return}
   const commandKey=crypto.randomUUID();sessionStorage.setItem(storageKey,commandKey);setAttempted(true);
   setMessage('Waiting for the agent. Keep the private connection open. No automatic retry.');
   const result=await savedAzureApi.receive(caseId,contextVersion,input.settings_id,commandKey,csrfToken,task==='REPORT_DESIGN'?{task,confirmed_contract_id:contractId}:undefined);
   if(!valid(at,context))return;
   if(!result.native_response?.operation_id||result.native_response.context_version!==contextVersion)throw new Error('RECEIPT_UNAVAILABLE');
   setReceipt(result.native_response);setMessage('The attempt was recorded. Check its status below; any saved response remains available.');onSaved();
  }catch(error){if(valid(at,context)){setAttempted(true);setMessage('The attempt could not be confirmed. Do not resend. Inspect saved answers and this report’s error history.');failed(error)}}
  finally{running.current=false;if(valid(at,context))setBusy(false)}
 }
 const ready=!!input?.ready&&input.receive_available===true&&!!input.connection_id&&Number.isInteger(input.input_characters)&&input.input_characters!>0&&input.input_limit!==null&&input.input_characters!<=input.input_limit;
 return <section aria-label="Agent response"><h3>Ask the configured agent</h3><p>Send the current saved requirements and complete supported sources once. The agent owns its answer. Receiving an answer does not confirm requirements or create a report artifact.</p>{unsavedGoal&&<p>Save your edited goal before checking or sending.</p>}<label>Request stage <select value={task} disabled={busy||unsavedGoal} onChange={event=>setTask(event.target.value as NativeTask)}><option value="REQUIREMENT_ANALYSIS">Requirements analysis</option><option value="REPORT_DESIGN">Design after confirmation</option></select></label><button type="button" disabled={busy||unsavedGoal} onClick={()=>void inspect()}>Check agent connection and input</button>{input&&<p>{input.ready?'Complete saved sources fit the configured input limit.':'Complete saved sources are unavailable; no request can be sent.'} {input.input_characters!==null&&input.input_limit!==null&&`${input.input_characters} / ${input.input_limit} characters`}</p>}<button type="button" disabled={busy||attempted||unsavedGoal||!ready} onClick={()=>void send()}>Send once to agent</button>{message&&<p role="status">{message}</p>}{receipt&&<p>Attempt {receipt.operation_id} · {receipt.state} · HTTP {receipt.http_status??'unavailable'} · Agent {receipt.provider_status??'unavailable'}{receipt.receipt_id?' · Original response saved.':' · No saved response body confirmed.'}</p>}</section>;
}
