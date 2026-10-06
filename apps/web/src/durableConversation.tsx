import React,{useEffect,useRef,useState} from 'react';
import {acceptanceApi,capabilitiesApi,conversationApi,evidenceApi,referenceMaterialApi,type AcceptanceState,type CaseRecord,type ConversationEvent,type DurableQuestion,type EvidenceItem,type ReferenceMaterial,type UploadCapabilities} from './api';
import {DurableGeneration} from './durableGeneration';

const emptyAcceptance:AcceptanceState={interpretation:null,confirmed_contract:null};
const eventLabel=(kind:ConversationEvent['kind'])=>({
  USER_MESSAGE:'Additional requirement',RAW_ANSWER:'Your answer',CORRECTION:'Correction',
  CLARIFICATION_CYCLE_STARTED:'Further clarification',
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
  return 'Saved report requirement';
};
type PendingFile={id:string;file:File;kind:'DATA_SOURCE'|'REFERENCE_MATERIAL';status:'READY'|'UPLOADING'|'FAILED';error?:string};

export function DurableConversation({record,csrfToken,actorRole='MEMBER',onContextChanged,onReportReady,onError}:{record:CaseRecord;csrfToken:string;actorRole?:string;onContextChanged:(version:number)=>void;onReportReady?:(ready:boolean)=>void;onError:(error:unknown)=>void}){
  const [events,setEvents]=useState<ConversationEvent[]>([]);
  const [evidence,setEvidence]=useState<EvidenceItem[]>([]);
  const [references,setReferences]=useState<ReferenceMaterial[]>([]);
  const [capabilities,setCapabilities]=useState<UploadCapabilities|null>(null);
  const [pendingFiles,setPendingFiles]=useState<PendingFile[]>([]);
  const [dragging,setDragging]=useState(false);
  const [acceptance,setAcceptance]=useState<AcceptanceState>(emptyAcceptance);
  const [message,setMessage]=useState('');
  const [answer,setAnswer]=useState('');
  const [contextVersion,setContextVersion]=useState(record.semantic_context_version);
  const [busy,setBusy]=useState(false);
  const [busyStep,setBusyStep]=useState<string|null>(null);
  const [actionError,setActionError]=useState('');
  const [reportReady,setReportReady]=useState(false);
  const fileRef=useRef<HTMLInputElement>(null);
  const refreshGeneration=useRef(0);
  const caseIdRef=useRef(record.id);
  const contextVersionRef=useRef(record.semantic_context_version);
  const messageCommand=useRef<{text:string;key:string}|null>(null);
  const answerCommand=useRef<{signature:string;key:string}|null>(null);
  const refinementCommand=useRef<{text:string;key:string}|null>(null);

  const refresh=async()=>{
    const generation=++refreshGeneration.current;
    const [transcript,items,referenceItems,state]=await Promise.all([
      conversationApi.list(record.id),evidenceApi.list(record.id),referenceMaterialApi.list(record.id),acceptanceApi.state(record.id),
    ]);
    if(generation!==refreshGeneration.current)return;
    setEvents(transcript.items);
    setEvidence(items.items);
    setReferences(referenceItems.items);
    setAcceptance(state);
  };
  useEffect(()=>{
    caseIdRef.current=record.id;
    contextVersionRef.current=record.semantic_context_version;
    setActionError('');
    setContextVersion(record.semantic_context_version);
    setReportReady(false);
    setPendingFiles([]);
    onReportReady?.(false);
    void refresh().catch(onError);
    void capabilitiesApi.uploads().then(setCapabilities).catch(onError);
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
    setBusyStep('Saving your additional requirements');
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const event=await conversationApi.append(caseId,'USER_MESSAGE',{text},current,messageCommand.current.key,csrfToken);
      const next=event.semantic_context_version??current;
      if(!operationIsCurrent(caseId,current))return;
      setEvents(items=>items.some(item=>item.id===event.id)?items:[...items,event]);
      changed(next);
      setMessage('');
      messageCommand.current=null;
    }catch(error){onError(error)}finally{setBusy(false);setBusyStep(null)}
  }

  function selectFiles(files:File[]){
    if(!capabilities||!files.length)return;
    const room=Math.max(0,capabilities.max_files_per_selection-pendingFiles.length),accepted=files.slice(0,room).reduce<PendingFile[]>((items,file)=>{const extension=file.name.split('.').at(-1)?.toUpperCase()??'',kind:PendingFile['kind']|null=capabilities.data_extensions.includes(extension)?'DATA_SOURCE':capabilities.reference_extensions.includes(extension)?'REFERENCE_MATERIAL':null;if(!kind||file.size>capabilities.max_file_bytes){onError(new Error(`“${file.name}” is not an allowed file or exceeds the configured size limit.`));return items}items.push({id:crypto.randomUUID(),file,kind,status:'READY'});return items},[]);
    setPendingFiles(current=>[...current,...accepted]);
    if(files.length>room)onError(new Error(`Select no more than ${capabilities.max_files_per_selection} files at a time.`));
    if(fileRef.current)fileRef.current.value='';
  }

  async function uploadSelected(){
    if(!pendingFiles.length)return;
    refreshGeneration.current+=1;
    setBusy(true);
    setBusyStep('Saving and checking selected files');
    let version=contextVersionRef.current;
    for(const pending of pendingFiles){
      setPendingFiles(current=>current.map(item=>item.id===pending.id?{...item,status:'UPLOADING',error:undefined}:item));
      try{
        if(pending.kind==='DATA_SOURCE'){
          const item=await evidenceApi.add(record.id,pending.file,version,csrfToken);version=item.semantic_context_version??version;setEvidence(current=>current.some(existing=>existing.id===item.id)?current:[...current,item]);
        }else{
          const item=await referenceMaterialApi.add(record.id,pending.file,version,csrfToken);version=item.semantic_context_version??version;setReferences(current=>current.some(existing=>existing.id===item.id)?current:[...current,item]);
        }
        contextVersionRef.current=version;setPendingFiles(current=>current.filter(item=>item.id!==pending.id));
      }catch(error){const message=error instanceof Error?error.message:'Upload failed.';setPendingFiles(current=>current.map(item=>item.id===pending.id?{...item,status:'FAILED',error:message}:item));onError(error)}
    }
    changed(version);setBusy(false);setBusyStep(null);
  }

  async function prepare(){
    setBusy(true);
    setBusyStep('Checking your information and preparing the understanding');
    setActionError('');
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const interpretation=await acceptanceApi.prepare(caseId,current,csrfToken);
      if(operationIsCurrent(caseId,current))setAcceptance({...await acceptanceApi.state(caseId),interpretation,confirmed_contract:null});
    }catch(error){setActionError('The understanding could not be completed. Your saved request and files remain available. Review the error, then retry only when the required capability and budget are available. No requirements were confirmed.');onError(error)}finally{setBusy(false);setBusyStep(null)}
  }

  async function submitAnswer(question:DurableQuestion,input:{rawAnswer:string;suggestionId?:string;decision:'ACCEPT'|'DECLINE'|'FREE_TEXT'}){
    const rawAnswer=input.rawAnswer.trim(),interpretation=acceptance.interpretation;
    if(!rawAnswer||!interpretation?.current)return;
    const payload={questionId:question.id,interpretationId:interpretation.id,rawAnswer,suggestionId:input.suggestionId??'',decision:input.decision};
    const signature=JSON.stringify(payload);
    if(!answerCommand.current||answerCommand.current.signature!==signature)answerCommand.current={signature,key:crypto.randomUUID()};
    refreshGeneration.current+=1;
    setBusy(true);
    setBusyStep('Saving your answer and refreshing the understanding');
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
      setAcceptance({...await acceptanceApi.state(caseId),interpretation:nextInterpretation,confirmed_contract:null});
      const transcript=await conversationApi.list(caseId);
      if(operationIsCurrent(caseId,next))setEvents(transcript.items);
    }catch(error){onError(error)}finally{setBusy(false);setBusyStep(null)}
  }

  async function confirm(){
    const interpretation=acceptance.interpretation;
    if(!interpretation?.current)return;
    setBusy(true);
    setBusyStep('Confirming the current understanding');
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const contract=await acceptanceApi.confirm(caseId,interpretation.id,current,csrfToken);
      if(operationIsCurrent(caseId,current))setAcceptance({
        ...acceptance,interpretation:{...interpretation,state:'CONFIRMED'},confirmed_contract:contract,
      });
    }catch(error){onError(error)}finally{setBusy(false);setBusyStep(null)}
  }

  async function refine(){
    const enhancement=message.trim();
    if(!refinementCommand.current||refinementCommand.current.text!==enhancement)refinementCommand.current={text:enhancement,key:crypto.randomUUID()};
    setBusy(true);
    setBusyStep('Enhancing and rechecking the understanding');
    try{
      const caseId=record.id,current=contextVersionRef.current;
      const result=await acceptanceApi.refine(caseId,current,enhancement,refinementCommand.current.key,csrfToken);
      if(!operationIsCurrent(caseId,current))return;
      refinementCommand.current=null;
      changed(result.semantic_context_version);
      setMessage('');
      const next=await acceptanceApi.prepare(caseId,result.semantic_context_version,csrfToken);
      if(operationIsCurrent(caseId,result.semantic_context_version)){
        const transcript=await conversationApi.list(caseId);
        setEvents(transcript.items);
        setAcceptance({interpretation:next,confirmed_contract:null,clarification:(await acceptanceApi.state(caseId)).clarification});
      }
    }catch(error){onError(error)}finally{setBusy(false);setBusyStep(null)}
  }

  const interpretation=acceptance.interpretation;
  const summary=interpretation?.confirmation_summary;
  const stale=Boolean(interpretation&&!interpretation.current);
  const pendingQuestions=interpretation?.questions??[];
  const question=pendingQuestions[0];
  const clarification=acceptance.clarification;
  const canRefine=Boolean(clarification?.clarification_enabled&&!clarification.overall_limit_reached);
  const disclosedScope=interpretation?.interpretation??{};
  const scopeItems=(key:string)=>Array.isArray(disclosedScope[key])?(disclosedScope[key] as unknown[]).filter((item):item is string=>typeof item==='string'):[];
  const stage=reportReady?5:acceptance.confirmed_contract?.current?4:summary&&!stale&&interpretation?.state==='READY_FOR_CONFIRMATION'?3:summary&&!stale||evidence.length?2:events.length?1:0;
  const stages=['Goal','Information','Understanding','Confirm','Build','Report'];

  return <section className="durable-conversation" aria-label="Your report journey">
    <div className="journey-heading"><div><span className="eyebrow">Your report journey</span><h2>From question to candidate</h2><p>Each step stays with this private report. Review the meaning before any build begins.</p></div><span className="status-badge status-info">Private and saved</span></div>
    {busyStep&&<div className="state-callout info journey-progress" role="status" aria-live="polite"><span className="processing-spinner" aria-hidden="true"/><div><strong>{busyStep}…</strong><p>Keep this page open. A report is available only after the later build and validation steps succeed.</p></div></div>}
    {actionError&&<div className="state-callout danger" role="alert"><strong>Understanding not completed</strong><p>{actionError}</p></div>}
    <ol className="journey-steps" aria-label="Report journey">{stages.map((label,index)=><li key={label} className={index===stage?'active':index<stage?'complete':'unavailable'} aria-current={index===stage?'step':undefined} aria-disabled={index>stage||undefined}><span className="step-number" aria-hidden="true">{index<stage?'✓':index+1}</span><span className="step-copy"><small>{index<stage?'Complete':index===stage?stale&&index>=2?'Needs review':'Current':'Unavailable'}</small><strong>{label}</strong></span></li>)}</ol>
    <div className="journey-section-title"><div><span className="eyebrow">Working together</span><h3>Shape your report</h3><p>Explain what you need, add supporting information, then confirm that the understanding matches your goal.</p></div></div>
    <section className="conversation-step" aria-label="Report requirements">
      <div className="step-heading"><span className="step-icon" aria-hidden="true">✎</span><div><span className="eyebrow">Report requirements</span><h4>Tell us what else this report should cover</h4><p>Add priorities, business definitions, rules or corrections in everyday language. APBRA keeps the original request unchanged.</p></div></div>
      <div className="conversation-events" aria-live="polite">{events.length===0?<p className="quiet-empty">No additional requirements yet. Add detail only when it helps explain your goal.</p>:<ol>{events.map(event=><li key={event.id}><strong>{eventLabel(event.kind)}</strong><p>{eventText(event)}</p></li>)}</ol>}</div>
      <div className="message-composer"><label htmlFor={'case-message-'+record.id}>Add more requirements</label><textarea id={'case-message-'+record.id} rows={3} maxLength={12000} placeholder="For example: include monthly trends and let managers filter by region…" value={message} onChange={event=>setMessage(event.target.value)}/><div className="composer-footer"><span>Saved with this private report request</span><button disabled={busy||!message.trim()} onClick={()=>void addMessage()}>Add to report requirements <span aria-hidden="true">→</span></button></div></div>
    </section>
    <section className="evidence-step" aria-label="Supporting information">
      <div className="step-heading"><span className="step-icon" aria-hidden="true">▦</span><div><span className="eyebrow">Information</span><h4>Data and reference material</h4><p>Use CSV or XLSX as calculation data. Add screenshots, mock-ups, diagrams or sketches as reference material; images are never treated as calculation data.</p></div></div>
      <input ref={fileRef} id={'case-evidence-'+record.id} className="sr-only file-input" type="file" multiple accept={capabilities?[...capabilities.data_extensions,...capabilities.reference_extensions].map(item=>'.'+item.toLowerCase()).join(','):undefined} disabled={busy||!capabilities} onChange={event=>selectFiles(Array.from(event.target.files??[]))}/>
      <div className={'evidence-upload '+(dragging?'is-dragging':'')} role="button" tabIndex={0} aria-label="Add data sources or reference material" onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();fileRef.current?.click()}}} onDragEnter={event=>{event.preventDefault();setDragging(true)}} onDragOver={event=>event.preventDefault()} onDragLeave={()=>setDragging(false)} onDrop={event=>{event.preventDefault();setDragging(false);selectFiles(Array.from(event.dataTransfer.files))}}><span className="upload-symbol" aria-hidden="true">↑</span><div><strong>Drop files here or browse</strong><small>{capabilities?`${capabilities.data_extensions.join(', ')} data · ${capabilities.reference_extensions.join(', ')} reference · up to ${capabilities.max_files_per_selection} at once`:'Loading allowed file types…'}</small></div><label className="upload-button" htmlFor={'case-evidence-'+record.id}>Browse files</label></div>
      {pendingFiles.length>0&&<div className="pending-files" aria-live="polite"><div className="pending-files-heading"><strong>Ready to add</strong><button disabled={busy} onClick={()=>void uploadSelected()}>{busy?'Adding files…':pendingFiles.some(item=>item.status==='FAILED')?'Retry failed uploads':'Add selected files'}</button></div><ul>{pendingFiles.map(item=><li key={item.id}><div><strong>{item.file.name}</strong><small>{item.kind==='DATA_SOURCE'?'Data source':'Reference material'} · {(item.file.size/1024).toFixed(1)} KB · {item.status.toLowerCase()}</small>{item.error&&<span role="alert">{item.error}</span>}</div><button className="subtle" disabled={busy||item.status==='UPLOADING'} onClick={()=>setPendingFiles(current=>current.filter(file=>file.id!==item.id))}>Remove</button></li>)}</ul></div>}
      {(evidence.length>0||references.length>0)?<div className="evidence-attached"><span className="status-badge status-success">{evidence.length+references.length} saved</span><ul>{evidence.map(item=><li key={item.id}><span aria-hidden="true">▦</span><div><strong>{item.filename}</strong><small>Data source · {item.format} · {item.observed_schema.tables.length} table{item.observed_schema.tables.length===1?'':'s'}</small></div><details className="expert-details"><summary>Source details</summary><ul>{item.observed_schema.tables.map(table=><li key={table.name}>{table.name} · {table.rowCount} row{table.rowCount===1?'':'s'} · {table.columns.map(column=>column.name+' ('+column.type+')').join(', ')}</li>)}</ul></details></li>)}{references.map(item=><li key={item.id}><span aria-hidden="true">▧</span><div><strong>{item.filename}</strong><small>Reference material · {item.interpretation_state==='NOT_INTERPRETED'?'Saved, visual meaning not interpreted':'Qualified visual interpretation available'}</small></div></li>)}</ul></div>:<p className="evidence-note">No supporting information saved yet. Confirmation requires a qualified data source; reference images are optional.</p>}
    </section>
    <section className="acceptance-panel" aria-label="Review the understanding">
      <div className="step-heading"><span className="step-icon" aria-hidden="true">◇</span><div><span className="eyebrow">Review and confirm</span><h4>Current understanding</h4><p>Check the business meaning before confirming this exact version.</p></div></div>
      {stale&&<p role="status" className="state-callout warning"><strong>Reconfirmation required.</strong> The request, conversation or evidence changed after this understanding was prepared.</p>}
      {summary&&!stale?<div className="understanding-summary"><div className="understanding-objective"><span className="eyebrow">Here’s what APBRA understands</span><strong>{summary.objective}</strong></div><div className="understanding-grid">{([{title:'Business questions',items:summary.businessQuestions},{title:'Measures',items:summary.kpiDefinitions},{title:'Scope and timing',items:summary.scopeAndTime},{title:'Ways to explore',items:summary.dimensionsAndFilters}] as const).filter(group=>group.items.length>0).map(group=><div key={group.title}><h5>{group.title}</h5><ul>{group.items.map((item,index)=><li key={index+'-'+item}>{item}</li>)}</ul></div>)}</div><p className="supporting-copy">Review the accepted assumptions, limits and supported scope before proceeding. Optional questions do not prevent acceptance.</p>{['HUMAN_REVIEW_REQUIRED','UNSUPPORTED','OUT_OF_SCOPE'].includes(interpretation?.state??'')&&<div className="state-callout warning" role="status"><strong>Expert assistance is recommended</strong><p>APBRA cannot safely continue automatically with the current meaning. Your requirements and supporting information remain saved.</p></div>}</div>:<div className="understanding-empty"><span aria-hidden="true">◇</span><p>Prepare an understanding after adding supported information. APBRA may suggest optional refinements.</p></div>}
      {summary&&!stale&&['requestedScope','deliverableScope','unsupportedScope','omittedScope','limitations','suggestedAlternatives','assumptions'].some(key=>scopeItems(key).length>0)&&<div className="understanding-grid" aria-label="Disclosed report scope">{([['requestedScope','Requested scope'],['deliverableScope','What this candidate can deliver'],['unsupportedScope','Unsupported scope'],['omittedScope','Omitted scope'],['limitations','Limitations'],['suggestedAlternatives','Suggested alternatives'],['assumptions','Assumptions']] as const).filter(([key])=>scopeItems(key).length>0).map(([key,label])=><div key={key}><h5>{label}</h5><ul>{scopeItems(key).map((item,index)=><li key={`${key}-${index}`}>{item}</li>)}</ul></div>)}</div>}
      {question&&!stale&&<div className="clarification-panel"><p><strong>Optional refinement{pendingQuestions.length>1?'s':''}</strong> · You can accept the current understanding without answering.</p><p>{question.question}</p><p>{question.reason}</p>{question.suggestions.length>0&&<div>{question.suggestions.map(option=><button key={option.id} disabled={busy||Boolean(clarification?.overall_limit_reached)} onClick={()=>void submitAnswer(question,{rawAnswer:option.label,suggestionId:option.id,decision:'ACCEPT'})}>{option.label}</button>)}</div>}{question.allowFreeText&&<><label htmlFor={'clarification-answer-'+record.id}>Answer in business language</label><textarea id={'clarification-answer-'+record.id} rows={3} maxLength={capabilities?.max_answer_characters} value={answer} onChange={event=>setAnswer(event.target.value)}/><button disabled={busy||!answer.trim()||Boolean(clarification?.overall_limit_reached)} onClick={()=>void submitAnswer(question,{rawAnswer:answer,decision:'FREE_TEXT'})}>Save answer and update understanding</button></>}</div>}
      {clarification&&<p role="status" className="supporting-copy">Clarification cycle {clarification.cycle_number||1}: {clarification.rounds_used_in_cycle} of {clarification.max_rounds_per_cycle??'—'} turns · {clarification.rounds_used_overall} of {clarification.max_rounds_overall??'—'} overall.{clarification.overall_limit_reached?' Further AI clarification is unavailable; you can still accept the current understanding or ask an expert.':clarification.per_cycle_limit_reached?' Start a new cycle to enhance the requirements.':''}</p>}
      <div className="command-bar"><button disabled={busy||!evidence.length} onClick={()=>void prepare()}>{stale?'Review updated requirements':'Review my requirements'}</button>{summary&&!stale&&interpretation?.state==='READY_FOR_CONFIRMATION'&&!acceptance.confirmed_contract&&<button disabled={busy} onClick={()=>void confirm()}>Confirm requirements</button>}{summary&&!stale&&!acceptance.confirmed_contract&&<button className="subtle" disabled={busy||!canRefine} onClick={()=>void refine()}>Clarify / Enhance Requirements</button>}</div>
      {acceptance.confirmed_contract?.current&&<div className="confirmed-state" role="status"><strong>Your report requirements are confirmed</strong><p>Confirmed {new Date(acceptance.confirmed_contract.accepted_at).toLocaleString()}. If the request or supporting information changes, you will need to confirm the revised meaning.</p></div>}
    </section>
    <DurableGeneration caseId={record.id} contract={acceptance.confirmed_contract} csrfToken={csrfToken} actorRole={actorRole} onReportReady={ready=>{setReportReady(ready);onReportReady?.(ready)}} onError={onError}/>
  </section>;
}
