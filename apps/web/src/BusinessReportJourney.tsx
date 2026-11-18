import {Pagination,usePagedItems,type PageSize} from './AdminUI';
import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ApiError,validRequestOutputPage,acceptanceApi,conversationApi,nativeFilesApi,requestOutputsApi,savedAzureApi,type AcceptanceState,type CaseRecord,type DurableQuestion,type NativeAnswer,type NativeAnalysisPreview,type RequestOutput,type RequestOutputPage} from './api';
import {DurableConversation} from './durableConversation';
import {BusinessJourneyError,requireCurrent,runBusinessAgent,nativeAnalysisPreview,discussionReply,answerDraft,canReviewNativeGoal} from './businessAgent';

type Step='goal'|'information'|'understanding'|'confirm'|'generate'|'report';
const steps:Array<[Step,string]>=[['goal','Goal'],['information','Supporting information'],['understanding','Understanding'],['confirm','Confirm'],['generate','Generate'],['report','Download']];
const empty:AcceptanceState={interpretation:null,confirmed_contract:null};
export const currentAIUnderstanding=(state:AcceptanceState,version:number)=>Boolean(state.interpretation?.current&&state.interpretation.context_version===version&&state.interpretation.simulation==='QUALIFIED_SERVER_MODEL');
export const canConfirmAIUnderstanding=(state:AcceptanceState,version:number,reviewed:boolean,unsaved:boolean)=>currentAIUnderstanding(state,version)&&state.interpretation?.state==='READY_FOR_CONFIRMATION'&&state.interpretation.questions.every(question=>!question.required)&&reviewed&&!unsaved;
export function BusinessReportJourney({record,csrfToken,actorRole,goal,initialInformation=false,visible=true,unsavedGoal=false,onContextChanged,onReportReady,onError}:{record:CaseRecord;csrfToken:string;actorRole:string;goal:React.ReactNode;initialInformation?:boolean;visible?:boolean;unsavedGoal?:boolean;onContextChanged:(version:number)=>void;onReportReady:(ready:boolean)=>void;onError:(error:unknown)=>void}){
 const [informationPending,setInformationPending]=useState(false);
 const informationPendingChange=useCallback((value:boolean)=>setInformationPending(value),[]);
 const [step,setStep]=useState<Step>(initialInformation?'information':'goal'),[state,setState]=useState<AcceptanceState>(empty),[loaded,setLoaded]=useState(false),[analysisSaved,setAnalysisSaved]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState(''),[error,setError]=useState(''),[recheck,setRecheck]=useState(false),[reviewed,setReviewed]=useState(false),[answers,setAnswers]=useState<Record<string,string>>({}),[refinement,setRefinement]=useState(''),[original,setOriginal]=useState<NativeAnswer|null>(null),[outputs,setOutputs]=useState<RequestOutput[]>([]),[reportReceipts,setReportReceipts]=useState<string[]>([]),[filePage,setFilePage]=useState<RequestOutputPage|null>(null),[reportAvailable,setReportAvailable]=useState(false);
 const [preview,setPreview]=useState<NativeAnalysisPreview|null>(null);
 const binding=[record.company_id,record.id,record.semantic_context_version,csrfToken,actorRole].join(':'),active=useRef(binding),mounted=useRef(false),flight=useRef(false),auto=useRef(''),pending=useRef<{signature:string;key:string}|null>(null),heading=useRef<HTMLHeadingElement>(null);
 const focusScope=[record.company_id,record.id,csrfToken,actorRole].join(':'),returnFocus=useRef<string|null>(null);
 active.current=binding;
 const admin=['COMPANY_OWNER','COMPANY_ADMIN'].includes(actorRole);
 const current=()=>mounted.current&&active.current===binding;
 function failure(value:unknown){if(!current())return;setStatus('');setRecheck(value instanceof BusinessJourneyError&&value.safeToRecheck);setError(value instanceof BusinessJourneyError?value.message:'This action could not be completed. Your saved work is safe. Ask your administrator to review the failure before trying again.');if(value instanceof ApiError&&[401,403,404].includes(value.status))onError(value);if(value instanceof BusinessJourneyError&&value.accessError)onError(value.accessError);}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 useEffect(()=>{let alive=true;setLoaded(false);setAnalysisSaved(false);setState(empty);setReviewed(false);setAnswers({});setOriginal(null);setPreview(null);setOutputs([]);setReportReceipts([]);setFilePage(null);setReportAvailable(false);setError('');setStatus('');onReportReady(false);
  void Promise.all([acceptanceApi.state(record.id),requestOutputsApi.page(record.id),admin?savedAzureApi.list(record.id):Promise.resolve({items:[]})]).then(async([acceptance,files,receipts])=>{
   if(!alive||!current())return;
   if(!validRequestOutputPage(files,record.id,record.semantic_context_version,record.company_id))throw new BusinessJourneyError('Saved file context changed. Reopen this report.');
   let accepted=acceptance;
   // File history is independently retained; failed analysis recovery must not
   // hide already authorized downloads.
   setState(acceptance);setOutputs(files.items);setFilePage(files);setReportAvailable(files.current_context_version===record.semantic_context_version&&files.current_report_available);
   setReportReceipts(receipts.items.filter(item=>item.task==='REPORT_DESIGN'&&item.state==='RECEIVED'&&item.provider_status==='completed'&&item.context_version===record.semantic_context_version&&item.receipt_id).map(item=>item.receipt_id!));
   const prior=receipts.items.find(item=>item.task==='REQUIREMENT_ANALYSIS'&&item.context_version===record.semantic_context_version);
   setAnalysisSaved(!!prior);
   if(prior?.receipt_id){
    const saved=await savedAzureApi.view(record.id,prior.receipt_id);if(!alive||!current())return;
    if(saved.receipt_id!==prior.receipt_id||saved.context_version!==record.semantic_context_version)throw new BusinessJourneyError('The saved AI answer does not match this request.');
    setOriginal(saved);
    // Recover interrupted local admission from retained bytes; never send AI
    // again and never confirm requirements on the user's behalf.
    if(!currentAIUnderstanding(accepted,record.semantic_context_version)&&prior.state==='RECEIVED'&&prior.provider_status==='completed'){
     const check=await savedAzureApi.contract(record.id,prior.receipt_id);if(!alive||!current())return;
     if(check.recognized&&check.current&&check.task==='REQUIREMENT_ANALYSIS'&&check.context_version===record.semantic_context_version){
      if(check.analysis_preview){
       setPreview(nativeAnalysisPreview(check,prior.receipt_id,record.semantic_context_version));
      }else{
      const intake=await savedAzureApi.intake(record.id,prior.receipt_id,record.semantic_context_version,check.settings_id,csrfToken);if(!alive||!current())return;
      if(!intake.accepted)throw new BusinessJourneyError('Your saved AI answer could not be prepared for review. Nothing was confirmed or sent again.');
      accepted=await acceptanceApi.state(record.id);if(!alive||!current())return;
      }
     }
    }
   }else if(prior){setError('An earlier AI request needs an administrator to check its status. It has not been retried.')}
   setState(accepted);setOutputs(files.items);setFilePage(files);setReportAvailable(files.current_context_version===record.semantic_context_version&&files.current_report_available);
   setReportReceipts(receipts.items.filter(item=>item.task==='REPORT_DESIGN'&&item.state==='RECEIVED'&&item.provider_status==='completed'&&item.context_version===record.semantic_context_version&&item.receipt_id).map(item=>item.receipt_id!));setLoaded(true);
  }).catch(value=>{if(alive&&current()){setLoaded(true);failure(value)}});
  return()=>{alive=false};
 },[binding]);
 const interpretation=currentAIUnderstanding(state,record.semantic_context_version)?state.interpretation:null;
 const previewReady=canReviewNativeGoal(preview,record.semantic_context_version,admin);
 const confirmed=Boolean(interpretation&&state.confirmed_contract?.current&&state.confirmed_contract.interpretation_id===interpretation?.id);
 const acknowledgedPage=usePagedItems(outputs,binding);
 const displayedOutputs=filePage?outputs:acknowledgedPage.items;
 const readyOutputs=outputs.filter(item=>item.context_version===record.semantic_context_version&&item.delivery_kind==='GENERATED_FILE'&&(item.native_task==='REPORT_DESIGN'||!!item.native_receipt_id&&reportReceipts.includes(item.native_receipt_id)));
 const displayedReadyOutputs=displayedOutputs.filter(item=>readyOutputs.some(ready=>ready.id===item.id));
 const hasReport=reportAvailable||readyOutputs.length>0;
 useEffect(()=>{onReportReady(hasReport)},[hasReport]);
 useEffect(()=>{if(visible)heading.current?.focus()},[step,visible]);
 useEffect(()=>{
  if(returnFocus.current!==null&&returnFocus.current!==focusScope)returnFocus.current=null;
  if(returnFocus.current&&!busy&&loaded&&!flight.current){returnFocus.current=null;if(visible&&document.activeElement===document.body)heading.current?.focus()}
 });
 async function operate(action:()=>Promise<void>){if(flight.current)return;returnFocus.current=focusScope;flight.current=true;setBusy(true);setError('');setRecheck(false);try{await action()}catch(value){failure(value)}finally{flight.current=false;if(mounted.current)setBusy(false);if(current())setStatus('')}}
 async function analyze(){
  if(!admin){setError('This AI workflow currently requires an authorized company administrator. Your requirements and files remain saved.');return;}
  await operate(async()=>{
   const result=await runBusinessAgent({caseId:record.id,contextVersion:record.semantic_context_version,csrfToken,task:'REQUIREMENT_ANALYSIS',current,storage:sessionStorage,progress:setStatus});
   setOriginal(result.answer);
   const check=await savedAzureApi.contract(record.id,result.answer.receipt_id);requireCurrent(current);
   if(!check.recognized||!check.current||check.task!=='REQUIREMENT_ANALYSIS'||check.context_version!==record.semantic_context_version)throw new BusinessJourneyError('AI returned an answer, shown below, but it could not be prepared for confirmation. It has been saved unchanged. Your administrator needs to resolve this response format; nothing was confirmed.');
   if(check.analysis_preview){
    setPreview(nativeAnalysisPreview(check,result.answer.receipt_id,record.semantic_context_version));setReviewed(false);return;
   }
   const intake=await savedAzureApi.intake(record.id,result.answer.receipt_id,record.semantic_context_version,check.settings_id,csrfToken);requireCurrent(current);
   if(!intake.accepted)throw new BusinessJourneyError('The AI answer remains saved, but it could not be used as the current understanding. Nothing was confirmed.');
   const next=await acceptanceApi.state(record.id);requireCurrent(current);
   if(!currentAIUnderstanding(next,record.semantic_context_version))throw new BusinessJourneyError('The AI understanding could not be verified for this request. Nothing was confirmed.');
   setState(next);setReviewed(false);
  });
 }
 useEffect(()=>{if(!visible||step!=='understanding'||!loaded||unsavedGoal||interpretation||preview||analysisSaved||busy||flight.current||auto.current===binding)return;auto.current=binding;void analyze()},[visible,step,loaded,binding,unsavedGoal,busy,analysisSaved]);
 async function addAnswer(question?:DurableQuestion,suggestion?:{id:string;label:string}){
  const text=(suggestion?.label??(question?answerDraft(answers,question.id):refinement)).trim();if(!text||unsavedGoal)return;
  const authoritative=Boolean(question&&interpretation);
  const message=discussionReply(question,text);
  const payload=question&&interpretation?{questionId:question.id,interpretationId:interpretation.id,rawAnswer:text,suggestionId:suggestion?.id??'',decision:suggestion?'ACCEPT':'FREE_TEXT'}:{text:message};
  const signature=JSON.stringify([binding,payload]);if(pending.current?.signature!==signature)pending.current={signature,key:crypto.randomUUID()};
  await operate(async()=>{setStatus('Saving your answer…');const event=await conversationApi.append(record.id,authoritative?'RAW_ANSWER':'USER_MESSAGE',payload,record.semantic_context_version,pending.current!.key,csrfToken);requireCurrent(current);
   if(!event.semantic_context_version||event.semantic_context_version<=record.semantic_context_version)throw new BusinessJourneyError('The updated request could not be verified. Reload your saved report before continuing.');
   pending.current=null;setAnswers({});setRefinement('');setReviewed(false);setStep('understanding');onContextChanged(event.semantic_context_version);
  });
 }
 async function continueToConfirmation(){
  if(busy||unsavedGoal||!reviewed||Object.values(answers).some(value=>value.trim())||refinement.trim())return;
  if(interpretation){if(canConfirmAIUnderstanding(state,record.semantic_context_version,reviewed,unsavedGoal))setStep('confirm');return;}
  if(!previewReady||!preview)return;
  await operate(async()=>{
   setStatus('Preparing your reviewed AI understanding…');
   const check=await savedAzureApi.contract(record.id,preview.receipt_id);requireCurrent(current);
   const fresh=nativeAnalysisPreview(check,preview.receipt_id,record.semantic_context_version);
   if(!fresh||JSON.stringify(fresh)!==JSON.stringify(preview))throw new BusinessJourneyError('The AI understanding changed. Review the current answer before confirming.');
   const intake=await savedAzureApi.intake(record.id,preview.receipt_id,record.semantic_context_version,check.settings_id,csrfToken);requireCurrent(current);
   if(!intake.accepted||!intake.interpretation)throw new BusinessJourneyError('Your AI understanding could not be prepared for confirmation. Nothing was confirmed.');
   const next=await acceptanceApi.state(record.id);requireCurrent(current);
   if(!currentAIUnderstanding(next,record.semantic_context_version)||next.interpretation?.id!==intake.interpretation.id||!canConfirmAIUnderstanding(next,record.semantic_context_version,true,false))throw new BusinessJourneyError('The current AI understanding could not be verified. Nothing was confirmed.');
   setState(next);setPreview(null);setStep('confirm');
  });
 }
 async function confirm(){if(!interpretation||!canConfirmAIUnderstanding(state,record.semantic_context_version,reviewed,unsavedGoal)||Object.values(answers).some(value=>value.trim())||refinement.trim())return;
  await operate(async()=>{setStatus('Saving your confirmation…');const contract=await acceptanceApi.confirm(record.id,interpretation.id,record.semantic_context_version,csrfToken);requireCurrent(current);setState(previous=>({...previous,confirmed_contract:contract}));setStep('generate')});
 }
 async function outputPage(number:number,size:PageSize,snapshot?:string){
  await operate(async()=>{setStatus('Loading saved files…');const page=await requestOutputsApi.page(record.id,number,size,snapshot);requireCurrent(current);
   if(!validRequestOutputPage(page,record.id,record.semantic_context_version,record.company_id))throw new BusinessJourneyError('Saved file context changed. Reopen this report.');
   setOutputs(page.items);setFilePage(page);setReportAvailable(page.current_report_available);
  });
 }
 async function generate(){if(!confirmed||unsavedGoal||!state.confirmed_contract)return;
  await operate(async()=>{const result=await runBusinessAgent({caseId:record.id,contextVersion:record.semantic_context_version,csrfToken,task:'REPORT_DESIGN',contractId:state.confirmed_contract!.id,current,storage:sessionStorage,progress:setStatus});setOriginal(result.answer);setReportReceipts(previous=>[...previous,result.answer.receipt_id]);
   const files=await nativeFilesApi.list(record.id,result.answer.receipt_id);requireCurrent(current);
   if(!files.retrieval_configured||!files.items.some(file=>file.savable))throw new BusinessJourneyError('AI returned an answer, but no downloadable report file is available. The answer is saved unchanged. Your administrator can review the delivery problem.');
   setStatus('Saving the files returned by AI…');
   const acknowledged:RequestOutput[]=[];
   for(const file of files.items.filter(file=>file.savable)){requireCurrent(current);const saved=await nativeFilesApi.save(record.id,result.answer.receipt_id,file.index,record.semantic_context_version,crypto.randomUUID(),csrfToken);requireCurrent(current);acknowledged.push(saved.output);setFilePage(null);setOutputs([...acknowledged]);setReportAvailable(true);}
   requireCurrent(current);setStep('report');
   try{const page=await requestOutputsApi.page(record.id);requireCurrent(current);if(!validRequestOutputPage(page,record.id,record.semantic_context_version,record.company_id))throw new BusinessJourneyError('Saved file context changed.');setOutputs(page.items);setFilePage(page);setReportAvailable(page.current_report_available)}catch{requireCurrent(current);setError('Files were saved. The list could not refresh; reopen this report to reload its full history.')}
   if(files.items.some(file=>!file.savable))setError('Some files returned by AI could not be delivered. Available files are shown; your administrator can review the remaining delivery problem.');
  });
 }
 const index=steps.findIndex(([key])=>key===step);
 const display=interpretation??(admin&&preview?.context_version===record.semantic_context_version?preview:null);
 const summary=display?.confirmation_summary;
 return <section className="report-wizard business-report-journey" aria-label="Create your report" aria-busy={busy}>
  <nav aria-label="Report steps"><ol className="journey-steps">{steps.map(([key,label],i)=><li key={key} className={key===step?'active':'available'}><button type="button" disabled={busy||informationPending&&key!=='information'||key==='confirm'&&!confirmed&&!canConfirmAIUnderstanding(state,record.semantic_context_version,reviewed,unsavedGoal)||key==='generate'&&!confirmed} aria-current={key===step?'step':undefined} onClick={()=>setStep(key)}><span className="step-number" aria-hidden="true">{i+1}</span><strong>{label}</strong></button></li>)}</ol></nav>
  <div className="wizard-step-heading"><span className="eyebrow">Step {index+1} of {steps.length}</span><h2 ref={heading} tabIndex={-1}>{steps[index][1]}</h2></div>
  {unsavedGoal&&<p role="status" className="state-callout warning">Save your goal changes before AI reviews this request or you confirm it.</p>}
  {busy&&<div role="status" aria-live="polite" className="state-callout info"><span className="processing-spinner" aria-hidden="true"/>{status||'Working…'}</div>}
  {error&&<p role="alert" className="state-callout danger">{error}</p>}{error&&recheck&&step==='understanding'&&<button disabled={busy||unsavedGoal||!admin} onClick={()=>void analyze()}>Continue AI review when available</button>}
  <div hidden={step!=='goal'}>{goal}</div>
  <div hidden={step!=='information'}><DurableConversation record={record} csrfToken={csrfToken} actorRole={actorRole} visibleStep="information" businessInformationOnly onInformationPendingChange={informationPendingChange} onContextChanged={onContextChanged} onError={onError}/></div>
  {['understanding','confirm'].includes(step)&&<section aria-label="AI understanding">
   {!loaded&&<p role="status">Loading your saved requirements…</p>}
   {summary?<><h3>Here’s what AI understands</h3><p>{summary.objective}</p><div className="understanding-grid">{[{label:'Business questions',items:summary.businessQuestions},{label:'Measures',items:summary.kpiDefinitions},{label:'Scope and timing',items:summary.scopeAndTime},{label:'Ways to explore',items:summary.dimensionsAndFilters},{label:'Business definitions',items:summary.lifecycleDefinitions},{label:'Policy decisions',items:summary.materialPolicyDecisions}].filter(group=>group.items.length).map(group=><div key={group.label}><h4>{group.label}</h4><ul>{group.items.map((text,i)=><li key={i}>{text}</li>)}</ul></div>)}</div>
   {display&&['requestedScope','deliverableScope','suggestedAlternatives','assumptions','limitations','omittedScope','unsupportedScope'].map(key=>Array.isArray(display.interpretation[key])&&<section key={key}><h4>{({requestedScope:'Requested scope',deliverableScope:'What AI proposes to deliver',suggestedAlternatives:'Suggested alternatives',assumptions:'Assumptions',limitations:'Limitations',omittedScope:'Not included',unsupportedScope:'Unsupported requests'} as Record<string,string>)[key]}</h4><ul>{(display.interpretation[key] as unknown[]).filter((value):value is string=>typeof value==='string').map((value,i)=><li key={i}>{value}</li>)}</ul></section>)}
   {display?.unresolved_ambiguities?.length!==0&&<ul>{display?.unresolved_ambiguities?.map((text,i)=><li key={i}>{text}</li>)}</ul>}
   {display?.questions.map(question=><section key={question.id} className="clarification-panel"><h4>{question.question}</h4><p>{question.reason}</p>{question.suggestions.map(option=><button type="button" key={option.id} disabled={busy||unsavedGoal} onClick={()=>void addAnswer(question,option)}>{option.label}</button>)}{question.allowFreeText&&<><label htmlFor={'ai-answer-'+question.id}>Your answer</label><textarea id={'ai-answer-'+question.id} value={answerDraft(answers,question.id)} disabled={busy} onChange={event=>{setAnswers(previous=>({...previous,[question.id]:event.target.value}));setReviewed(false)}}/><button disabled={busy||unsavedGoal||!(answerDraft(answers,question.id)).trim()} onClick={()=>void addAnswer(question)}>Send answer and update understanding</button></>}</section>)}
   <label htmlFor="ai-refinement">Anything to change or add?</label><textarea id="ai-refinement" value={refinement} disabled={busy} onChange={event=>{setRefinement(event.target.value);setReviewed(false)}} placeholder="For example: focus on monthly costs rather than individual transactions."/><button disabled={busy||unsavedGoal||!refinement.trim()} onClick={()=>void addAnswer()}>Update my requirements</button>
   {!interpretation&&!previewReady?<p role="status">This is an early AI discussion. You can answer its questions, refine your goal or add supporting information. Your requirements have not been confirmed.</p>:confirmed?<p role="status">Your current requirements are confirmed. Changes will need a new AI review and confirmation.</p>:<><p>Your requirements have not been confirmed.</p><label><input type="checkbox" checked={reviewed} disabled={busy} onChange={event=>setReviewed(event.target.checked)}/>I have reviewed this understanding, its questions and assumptions.</label><p>AI may offer optional questions. Confirm only when you are ready to proceed with the understanding shown.</p>{step==='confirm'?<button disabled={busy||unsavedGoal||!canConfirmAIUnderstanding(state,record.semantic_context_version,reviewed,unsavedGoal)||Object.values(answers).some(value=>value.trim())||refinement.trim().length>0} onClick={()=>void confirm()}>Confirm requirements</button>:<button disabled={busy||unsavedGoal||!(canConfirmAIUnderstanding(state,record.semantic_context_version,reviewed,unsavedGoal)||previewReady&&reviewed)||Object.values(answers).some(value=>value.trim())||refinement.trim().length>0} onClick={()=>void continueToConfirmation()}>Continue to confirmation</button>}{!previewReady&&(interpretation?.state!=='READY_FOR_CONFIRMATION'||interpretation.questions.some(question=>question.required))&&<p>AI has not provided an understanding ready for confirmation. Answer its questions or refine your requirements.</p>}</>}
   </>:loaded&&!busy&&!error&&<p>AI will review your saved goal and supporting information when you open Understanding. No report has been generated yet.</p>}
   {original&&!summary&&<><label htmlFor="ai-early-answer">Your answer or additional information</label><textarea id="ai-early-answer" value={refinement} disabled={busy} onChange={event=>setRefinement(event.target.value)}/><button disabled={busy||unsavedGoal||!refinement.trim()} onClick={()=>void addAnswer()}>Send answer to AI</button><p>You can continue this conversation or add supporting data. Confirmation is available only when AI provides a current understanding that can be reviewed.</p></>}
   {original&&!summary&&<section aria-label="AI response"><h3>AI response</h3>{original.texts.map((text,i)=><p key={i} style={{whiteSpace:'pre-wrap'}}>{text}</p>)}</section>}
  </section>}
  {step==='generate'&&<section><h3>Generate your report with AI</h3><p>AI uses your confirmed requirements and saved supporting information to create the output. APBRA saves and delivers the returned files unchanged.</p><button disabled={busy||unsavedGoal||!confirmed||!admin} onClick={()=>void generate()}>Generate report</button>{!confirmed&&<p>Review and confirm the current AI understanding first.</p>}{!admin&&<p>This AI workflow is currently limited to authorized company administrators.</p>}</section>}
  {step==='report'&&<section aria-label="Report downloads"><h3>{hasReport?'Saved files returned by AI':'Your report is not available yet'}</h3><p>{hasReport?'These files are retained for the current requirements. APBRA has not certified their business correctness or Power BI compatibility.':'Confirm your requirements and generate a report to receive downloadable files.'}</p><ul>{displayedReadyOutputs.map(file=><li key={file.id}><a href={requestOutputsApi.download(record.id,file.id)} download>{file.filename}</a></li>)}</ul>{displayedOutputs.some(file=>!readyOutputs.some(ready=>ready.id===file.id))&&<details><summary>Other saved files</summary><p>Earlier or informational files remain available unchanged. They are not presented as a newly generated report.</p><ul>{displayedOutputs.filter(file=>!readyOutputs.some(ready=>ready.id===file.id)).map(file=><li key={file.id}><a href={requestOutputsApi.download(record.id,file.id)} download>{file.filename}</a></li>)}</ul></details>}{hasReport&&displayedReadyOutputs.length===0&&<p>No current-report file is on this page. Use the page controls to find saved files.</p>}{filePage&&<Pagination label="Saved files" total={filePage.total} page={filePage.page} pageSize={filePage.page_size as PageSize} disabled={busy} onPage={number=>void outputPage(number,filePage.page_size as PageSize,filePage.snapshot)} onPageSize={size=>void outputPage(1,size)}/>}{!filePage&&outputs.length>0&&<><p>Files acknowledged in this action. Reopen the report to refresh its full saved history.</p><Pagination label="Files just saved" total={acknowledgedPage.total} page={acknowledgedPage.page} pageSize={acknowledgedPage.pageSize} onPage={acknowledgedPage.onPage} onPageSize={acknowledgedPage.onPageSize}/></>}</section>}
  <div className="wizard-navigation"><button type="button" className="subtle" disabled={busy||index===0} onClick={()=>setStep(steps[index-1][0])}>Back</button>{step==='goal'&&<button disabled={busy||unsavedGoal} onClick={()=>setStep('information')}>Continue to supporting information</button>}{step==='information'&&<button disabled={busy||unsavedGoal||informationPending} onClick={()=>setStep('understanding')}>Review my requirements with AI</button>}{step==='confirm'&&confirmed&&<button disabled={busy} onClick={()=>setStep('generate')}>Continue to generation</button>}{step==='generate'&&hasReport&&<button disabled={busy} onClick={()=>setStep('report')}>View saved files</button>}</div>
 </section>;
}
