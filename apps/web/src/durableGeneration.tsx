import React,{useEffect,useRef,useState} from 'react';
import {ApiError,generationApi,reviewedDesignApi,type DurableContract,type GenerationAttempt,type ReviewedDesign} from './api';

type Mode='BUILD'|'RETRY'|'REGENERATE';
const statusLabel=(status:GenerationAttempt['status'])=>({PENDING:'Waiting to build',RUNNING:'Building',SUCCEEDED:'Report ready',FAILED:'Build failed',CANCELLED:'Cancelled'}[status]);

export function DurableGeneration({caseId,contract,csrfToken,actorRole='MEMBER',onError}:{caseId:string;contract:DurableContract|null;csrfToken:string;actorRole?:string;onError:(error:unknown)=>void}){
  const [attempts,setAttempts]=useState<GenerationAttempt[]>([]);
  const [designs,setDesigns]=useState<ReviewedDesign[]>([]);
  const [canSubmit,setCanSubmit]=useState(false);
  const [selected,setSelected]=useState('');
  const [expertDraft,setExpertDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const [reviewBusy,setReviewBusy]=useState(false);
  const [cancelling,setCancelling]=useState<string|null>(null);
  const [downloading,setDownloading]=useState<string|null>(null);
  const [downloadError,setDownloadError]=useState('');
  const buildCommand=useRef<{signature:string;key:string}|null>(null);
  const activeKey=useRef('');
  const key=caseId+':'+(contract?.current?contract.id:'not-current');
  activeKey.current=key;

  const refresh=async()=>{
    const [history,available]=await Promise.all([
      generationApi.list(caseId),
      contract?.current?reviewedDesignApi.list(caseId,contract.id):Promise.resolve({items:[] as ReviewedDesign[],can_submit:false}),
    ]);
    if(activeKey.current!==key)return;
    setAttempts(history.items);
    setDesigns(available.items);
    setCanSubmit(available.can_submit);
    setSelected(current=>available.items.some(item=>item.id===current)?current:(available.items[0]?.id??''));
  };
  useEffect(()=>{
    setAttempts([]);
    setDesigns([]);
    setCanSubmit(false);
    setSelected('');
    setDownloadError('');
    buildCommand.current=null;
    void refresh().catch(onError);
  },[caseId,contract?.id,contract?.current]);
  useEffect(()=>{
    if(!busy)return;
    const timer=window.setInterval(()=>void refresh().catch(onError),1000);
    return()=>window.clearInterval(timer);
  },[busy,caseId,contract?.id]);

  async function run(mode:Mode,source?:GenerationAttempt){
    if(!contract?.current)return;
    const designId=mode==='RETRY'?source?.reviewed_design_id:selected;
    if(!designId)return;
    const signature=[contract.id,designId,mode,source?.id??''].join(':');
    if(!buildCommand.current||buildCommand.current.signature!==signature){
      buildCommand.current={signature,key:crypto.randomUUID()};
    }
    setBusy(true);
    try{
      const attempt=await generationApi.start(caseId,contract.id,designId,buildCommand.current.key,csrfToken,mode,source?.id);
      buildCommand.current=null;
      if(activeKey.current!==key)return;
      setAttempts(current=>[attempt,...current.filter(item=>item.id!==attempt.id)]);
      await refresh();
    }catch(error){onError(error)}finally{setBusy(false)}
  }

  async function cancel(attempt:GenerationAttempt){
    setCancelling(attempt.id);
    try{
      const updated=await generationApi.cancel(caseId,attempt.id,csrfToken);
      if(activeKey.current===key)setAttempts(current=>current.map(item=>item.id===updated.id?updated:item));
    }catch(error){onError(error)}finally{setCancelling(null)}
  }

  async function submitExpertReview(){
    if(actorRole!=='EXPERT'||!canSubmit||!contract?.current||!expertDraft.trim())return;
    setReviewBusy(true);
    try{
      const parsed:unknown=JSON.parse(expertDraft);
      if(typeof parsed!=='object'||parsed===null||Array.isArray(parsed))throw new Error('The expert report plan must be a JSON object.');
      await reviewedDesignApi.intake(caseId,contract.id,parsed as Record<string,unknown>,csrfToken);
      if(activeKey.current!==key)return;
      setExpertDraft('');
      await refresh();
    }catch(error){onError(error)}finally{setReviewBusy(false)}
  }

  async function download(attempt:GenerationAttempt){
    if(!attempt.artifact)return;
    setDownloading(attempt.id);
    setDownloadError('');
    try{
      const blob=await generationApi.download(caseId,attempt.id);
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');
      link.href=url;
      link.download=attempt.artifact.filename;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){
      setDownloadError(error instanceof ApiError?error.message:'The download could not be completed. Check your connection and retry, or ask for help.');
    }finally{setDownloading(null)}
  }

  const latest=attempts[0];
  const latestForContract=contract?.current?attempts.find(item=>item.confirmed_contract_id===contract.id):undefined;
  const current=contract?.current?attempts.find(item=>item.status==='SUCCEEDED'&&item.confirmed_contract_id===contract.id):undefined;
  const retryable=latestForContract&&['FAILED','CANCELLED'].includes(latestForContract.status)&&latestForContract.reviewed_design_id&&designs.some(item=>item.id===latestForContract.reviewed_design_id);
  return <section className="generation-panel" aria-labelledby={'generation-'+caseId}>
    <div className="section-title"><div><h3 id={'generation-'+caseId}>Build and find reports</h3><p>Only a confirmed request with an expert-reviewed report plan can be built. Completed candidate files stay private.</p></div><span className="status-badge">{attempts.length} build{attempts.length===1?'':'s'}</span></div>
    {!contract?.current?<p role="status"><strong>Review and confirm the current understanding before building.</strong> Earlier reports remain available below.</p>:designs.length===0?<p role="status" className="review-needed"><strong>Expert review needed.</strong> An authorised expert must supply and review a report plan for this exact confirmed request. You can still read earlier build history.</p>:<div className="build-readiness"><label htmlFor={'reviewed-plan-'+caseId}>Reviewed report plan</label><select id={'reviewed-plan-'+caseId} value={selected} onChange={event=>setSelected(event.target.value)}>{designs.map((item,index)=><option key={item.id} value={item.id}>Plan {designs.length-index} · {item.summary.page_count} page{item.summary.page_count===1?'':'s'} · {item.summary.visual_count} visual{item.summary.visual_count===1?'':'s'} · reviewed {new Date(item.reviewed_at).toLocaleDateString()}</option>)}</select><p className="supporting-copy">This plan was reviewed for the current request and evidence. APBRA checks its eligibility again when you build.</p><div className="command-bar"><button disabled={busy||!selected} onClick={()=>void run(current?'REGENERATE':'BUILD')}>{busy?'Building report…':current?'Build another version':'Build report'}</button>{retryable&&<button className="subtle" disabled={busy} onClick={()=>void run('RETRY',latestForContract)}>Retry failed build</button>}</div></div>}
    {latestForContract&&['PENDING','RUNNING'].includes(latestForContract.status)&&<div role="status" aria-live="polite"><p>{statusLabel(latestForContract.status)}. You may cancel this attempt; it will remain in history.</p><button className="subtle" disabled={cancelling===latestForContract.id} onClick={()=>void cancel(latestForContract)}>{cancelling===latestForContract.id?'Cancelling…':'Cancel build'}</button></div>}
    {latestForContract&&['FAILED','CANCELLED'].includes(latestForContract.status)&&!retryable&&<p role="status">This earlier plan is no longer eligible for retry. Ask an authorised expert to review a current plan.</p>}
    {current?<div className="current-report" aria-label="Current report"><h4>Current report · version {current.attempt_number}</h4><p>{current.artifact?'Validated candidate available for inspection. It has not been published or deployed.':'This completed build has no available file. Its history remains saved; build another version or ask for help.'}</p>{current.artifact&&<button disabled={downloading===current.id} onClick={()=>void download(current)}>{downloading===current.id?'Preparing download…':'Download current report candidate'}</button>}</div>:<p role="status">No completed report is available for the current request yet. Earlier candidates remain in history.</p>}
    {downloadError&&<p role="alert" className="review-needed">{downloadError}</p>}
    <details className="report-history"><summary>Earlier builds and history · {attempts.length}</summary>{attempts.length===0?<p>No report builds yet.</p>:<ol className="generation-history">{attempts.map(attempt=><li key={attempt.id}><div><strong>Version {attempt.attempt_number} · {attempt.status==='SUCCEEDED'&&!attempt.artifact?'Completed, file unavailable':statusLabel(attempt.status)}{attempt.id===current?.id?' · current':''}</strong><small>{new Date(attempt.created_at).toLocaleString()}</small></div>{attempt.failure&&<p role="alert">{attempt.failure.message}</p>}{attempt.status==='SUCCEEDED'&&!attempt.artifact&&<p role="status">This earlier file is unavailable. The build record remains saved.</p>}{attempt.artifact&&attempt.id!==current?.id&&<button className="subtle" disabled={downloading===attempt.id} onClick={()=>void download(attempt)}>{downloading===attempt.id?'Preparing download…':'Download earlier report candidate'}</button>}</li>)}</ol>}</details>
    <details className="expert-details"><summary>Details for experts</summary><p>This local validation does not call an AI design model. The supplied plan passes through the existing canonical validation and generation pipeline at build time. Power BI Desktop, DAX, RLS, publication and deployment validation are not run.</p>{actorRole==='EXPERT'&&contract?.current&&(canSubmit?<div className="expert-intake"><h4>Submit a reviewed report plan</h4><p>Only an active expert with edit access to this private case may submit a complete design. Successful server intake records the expert review; it does not claim the design will pass build validation.</p><label htmlFor={'expert-plan-'+caseId}>Expert report plan JSON</label><textarea id={'expert-plan-'+caseId} value={expertDraft} onChange={event=>setExpertDraft(event.target.value)} rows={8}/><button disabled={reviewBusy||!expertDraft.trim()} onClick={()=>void submitExpertReview()}>{reviewBusy?'Recording expert review…':'Submit reviewed plan'}</button></div>:<p>Report-plan submission requires expert edit access to this private case. Ask the case owner for access if you need to submit a plan.</p>)}{attempts.length>0&&<p>Latest attempt reference: {latest?.id}. Historical candidate digests are available from protected downloads.</p>}</details>
  </section>;
}
