import React,{useEffect,useRef,useState} from 'react';
import {acceptanceApi,conversationApi,evidenceApi,type AcceptanceState,type CaseRecord,type ConversationEvent,type DurableQuestion,type EvidenceItem} from './api';
import {DurableGeneration} from './durableGeneration';

const emptyAcceptance:AcceptanceState={interpretation:null,confirmed_contract:null};
const eventLabel=(kind:ConversationEvent['kind'])=>({
  USER_MESSAGE:'Your message',RAW_ANSWER:'Your answer',CORRECTION:'Correction',
  CLARIFICATION_QUESTION:'Question',AI_ANALYSIS:'Understanding',
  ALTERNATIVE_PROPOSED:'Suggested alternative',
  ALTERNATIVE_ACCEPTED:'Accepted alternative',
  ALTERNATIVE_DECLINED:'Declined alternative',
}[kind]);
const eventText=(event:ConversationEvent)=>{
  const payload=event.payload;
  if(typeof payload.text==='string')return payload.text;
  if(typeof payload.rawAnswer==='string')return payload.rawAnswer;
  if(typeof payload.label==='string')return payload.label;
  return 'Saved case activity';
};

export function DurableConversation({record,csrfToken,actorRole='MEMBER',onContextChanged,onError}:{record:CaseRecord;csrfToken:string;actorRole?:string;onContextChanged:(version:number)=>void;onError:(error:unknown)=>void}){
  const [events,setEvents]=useState<ConversationEvent[]>([]);
  const [evidence,setEvidence]=useState<EvidenceItem[]>([]);
  const [acceptance,setAcceptance]=useState<AcceptanceState>(emptyAcceptance);
  const [message,setMessage]=useState('');
  const [answer,setAnswer]=useState('');
  const [contextVersion,setContextVersion]=useState(record.semantic_context_version);
  const [busy,setBusy]=useState(false);
  const fileRef=useRef<HTMLInputElement>(null);
  const refreshGeneration=useRef(0);
  const caseIdRef=useRef(record.id);
  const contextVersionRef=useRef(record.semantic_context_version);
  const messageCommand=useRef<{text:string;key:string}|null>(null);
  const answerCommand=useRef<{signature:string;key:string}|null>(null);

  const refresh=async()=>{
    const generation=++refreshGeneration.current;
    const [transcript,items,state]=await Promise.all([
      conversationApi.list(record.id),evidenceApi.list(record.id),acceptanceApi.state(record.id),
    ]);
    if(generation!==refreshGeneration.current)return;
    setEvents(transcript.items);
    setEvidence(items.items);
    setAcceptance(state);
  };
  useEffect(()=>{
    caseIdRef.current=record.id;
    contextVersionRef.current=record.semantic_context_version;
    setContextVersion(record.semantic_context_version);
    void refresh().catch(onError);
    return()=>{refreshGeneration.current+=1};
  },[record.id,record.semantic_context_version]);
  const operationIsCurrent=(caseId:string,version:number)=>caseIdRef.current===caseId&&contextVersionRef.current===version;
  const changed=(next:number)=>{
    contextVersionRef.current=next;
    setContextVersion(next);
    setAcceptance(current=>current.interpretation||current.confirmed_contract?{
      interpretation:current.interpretation?{...current.interpretation,current:false}:null,
      confirmed_contract:current.confirmed_contract?{...current.confirmed_contract,current:false}:null,
    }:current);
    onContextChanged(next);
  };

  async function addMessage(){
    const text=message.trim();
    if(!text)return;
    if(!messageCommand.current||messageCommand.current.text!==text)messageCommand.current={text,key:crypto.randomUUID()};
    refreshGeneration.current+=1;
    setBusy(true);
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const event=await conversationApi.append(caseId,'USER_MESSAGE',{text},current,messageCommand.current.key,csrfToken);
      const next=event.semantic_context_version??current;
      if(!operationIsCurrent(caseId,current))return;
      setEvents(items=>items.some(item=>item.id===event.id)?items:[...items,event]);
      changed(next);
      setMessage('');
      messageCommand.current=null;
    }catch(error){onError(error)}finally{setBusy(false)}
  }

  async function addEvidence(file:File|undefined){
    if(!file)return;
    refreshGeneration.current+=1;
    setBusy(true);
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const item=await evidenceApi.add(caseId,file,current,csrfToken);
      const next=item.semantic_context_version??current;
      if(!operationIsCurrent(caseId,current))return;
      setEvidence(items=>items.some(existing=>existing.id===item.id)?items:[...items,item]);
      changed(next);
    }catch(error){onError(error)}finally{setBusy(false);if(fileRef.current)fileRef.current.value=''}
  }

  async function prepare(){
    setBusy(true);
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const interpretation=await acceptanceApi.prepare(caseId,current,csrfToken);
      if(operationIsCurrent(caseId,current))setAcceptance({interpretation,confirmed_contract:null});
    }catch(error){onError(error)}finally{setBusy(false)}
  }

  async function submitAnswer(question:DurableQuestion,input:{rawAnswer:string;suggestionId?:string;decision:'ACCEPT'|'DECLINE'|'FREE_TEXT'}){
    const rawAnswer=input.rawAnswer.trim(),interpretation=acceptance.interpretation;
    if(!rawAnswer||!interpretation?.current)return;
    const payload={questionId:question.id,interpretationId:interpretation.id,rawAnswer,suggestionId:input.suggestionId??'',decision:input.decision};
    const signature=JSON.stringify(payload);
    if(!answerCommand.current||answerCommand.current.signature!==signature)answerCommand.current={signature,key:crypto.randomUUID()};
    refreshGeneration.current+=1;
    setBusy(true);
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const event=await conversationApi.append(caseId,'RAW_ANSWER',payload,current,answerCommand.current.key,csrfToken);
      const next=event.semantic_context_version??current;
      if(!operationIsCurrent(caseId,current))return;
      answerCommand.current=null;
      changed(next);
      setAnswer('');
      const nextInterpretation=await acceptanceApi.prepare(caseId,next,csrfToken);
      if(!operationIsCurrent(caseId,next))return;
      setAcceptance({interpretation:nextInterpretation,confirmed_contract:null});
      const transcript=await conversationApi.list(caseId);
      if(operationIsCurrent(caseId,next))setEvents(transcript.items);
    }catch(error){onError(error)}finally{setBusy(false)}
  }

  async function confirm(){
    const interpretation=acceptance.interpretation;
    if(!interpretation?.current)return;
    setBusy(true);
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const contract=await acceptanceApi.confirm(caseId,interpretation.id,current,csrfToken);
      if(operationIsCurrent(caseId,current))setAcceptance({
        interpretation:{...interpretation,state:'CONFIRMED'},confirmed_contract:contract,
      });
    }catch(error){onError(error)}finally{setBusy(false)}
  }

  const interpretation=acceptance.interpretation;
  const summary=interpretation?.confirmation_summary;
  const stale=Boolean(interpretation&&!interpretation.current);
  const question=interpretation?.state==='NEEDS_CLARIFICATION'?interpretation.questions.at(-1):undefined;
  const stage=acceptance.confirmed_contract?.current?3:summary&&!stale?2:evidence.length?1:0;
  const stages=['Describe your goal','Add supporting information','Review the understanding','Build and find reports'];

  return <section className="panel durable-conversation" aria-label="Your report journey">
    <ol className="journey-steps" aria-label="Report journey">{stages.map((label,index)=><li key={label} className={index===stage?'active':index<stage?'complete':''} aria-current={index===stage?'step':undefined}><span aria-hidden="true">{index+1}</span>{label}</li>)}</ol>
    <div className="section-title"><div><h3>Shape your report</h3><p>Explain what you need, add supporting information, then confirm that the understanding matches your goal.</p></div><span className="status-badge">Private and saved</span></div>
    <section className="conversation-step" aria-label="Business conversation">
      <h4>Describe what matters</h4>
      <div className="conversation-events" aria-live="polite">{events.length===0?<p>No saved messages yet.</p>:<ol>{events.map(event=><li key={event.id}><strong>{eventLabel(event.kind)}</strong><p>{eventText(event)}</p></li>)}</ol>}</div>
      <label htmlFor={'case-message-'+record.id}>Add a business message</label>
      <textarea id={'case-message-'+record.id} rows={3} maxLength={12000} value={message} onChange={event=>setMessage(event.target.value)}/>
      <div className="command-bar"><button disabled={busy||!message.trim()} onClick={()=>void addMessage()}>Save message</button></div>
    </section>
    <section className="evidence-step" aria-label="Supporting information">
      <h4>Supporting information</h4><p>Add a CSV or XLSX file to ground the understanding in observed fields. You can save the case without a file, but confirmation is unavailable until supported evidence is added.</p>
      <input ref={fileRef} id={'case-evidence-'+record.id} className="sr-only" type="file" accept=".csv,.xlsx" disabled={busy} onChange={event=>void addEvidence(event.target.files?.[0])}/>
      <label className="upload-button" htmlFor={'case-evidence-'+record.id}>Add CSV or XLSX evidence</label>
      <details className="evidence-list"><summary>Supporting information · {evidence.length}</summary>{evidence.length?<ul>{evidence.map(item=><li key={item.id}><strong>{item.filename}</strong> · {item.format}<details className="expert-details"><summary>Source details</summary><ul>{item.observed_schema.tables.map(table=><li key={table.name}>{table.name} · {table.rowCount} row{table.rowCount===1?'':'s'} · {table.columns.map(column=>column.name+' ('+column.type+')').join(', ')}</li>)}</ul></details></li>)}</ul>:<p>No supporting file has been added yet.</p>}</details>
    </section>
    <section className="acceptance-panel" aria-label="Review the understanding">
      <h4>Current understanding</h4>
      {stale&&<p role="status"><strong>Reconfirmation required.</strong> The request, conversation or evidence changed after this understanding was prepared.</p>}
      {question&&!stale?<div className="clarification-panel"><p><strong>Clarification required</strong></p><p>{question.question}</p><p>{question.reason}</p>{question.suggestions.length>0&&<div><p>Choose a supported interpretation:</p>{question.suggestions.map(option=><button key={option.id} disabled={busy} onClick={()=>void submitAnswer(question,{rawAnswer:option.label,suggestionId:option.id,decision:'ACCEPT'})}>{option.label}</button>)}<button className="subtle" disabled={busy} onClick={()=>void submitAnswer(question,{rawAnswer:'I decline the proposed supported choices.',decision:'DECLINE'})}>Decline these choices</button></div>}{question.allowFreeText&&<><label htmlFor={'clarification-answer-'+record.id}>Answer in business language</label><textarea id={'clarification-answer-'+record.id} rows={3} maxLength={500} value={answer} onChange={event=>setAnswer(event.target.value)}/><button disabled={busy||!answer.trim()} onClick={()=>void submitAnswer(question,{rawAnswer:answer,decision:'FREE_TEXT'})}>Save answer and update understanding</button></>}</div>:summary&&!stale&&interpretation?.state!=='NEEDS_CLARIFICATION'?<><p><strong>{summary.objective}</strong></p><ul>{[...summary.businessQuestions,...summary.kpiDefinitions,...summary.scopeAndTime,...summary.dimensionsAndFilters].map((item,index)=><li key={index+'-'+item}>{item}</li>)}</ul><p className="supporting-copy">This local preview uses deterministic rules to propose an understanding; no AI model was called.</p></>:<p>Prepare an understanding after adding supported information. If a material choice is unclear, APBRA will ask you.</p>}
      <div className="command-bar"><button disabled={busy||!evidence.length||Boolean(question&&!stale)} onClick={()=>void prepare()}>{stale?'Prepare updated understanding':'Prepare understanding'}</button>{summary&&!stale&&interpretation?.state==='READY_FOR_CONFIRMATION'&&!acceptance.confirmed_contract&&<button disabled={busy} onClick={()=>void confirm()}>Confirm this exact meaning</button>}</div>
      {acceptance.confirmed_contract?.current&&<div className="confirmed-state" role="status"><strong>Your understanding is confirmed</strong><p>Accepted {new Date(acceptance.confirmed_contract.accepted_at).toLocaleString()}. If the request or supporting information changes, you will need to confirm the revised understanding.</p></div>}
    </section>
    <DurableGeneration caseId={record.id} contract={acceptance.confirmed_contract} csrfToken={csrfToken} actorRole={actorRole} onError={onError}/>
  </section>;
}
