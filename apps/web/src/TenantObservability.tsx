import {TenantDateFilter,TenantTime} from './TenantDateTime';
import React,{useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {ApiError,observabilityApi,type AuditEvent,type ProcessingError,type HistoryFilters,type HistoryPage,type ProviderFailureFacts} from './api';
import {AdminPageHeader,AdminState,AdminTableRegion,Pagination,type PageSize,containDialogFocus} from './AdminUI';

export const historyReadError=(error:unknown)=>error instanceof ApiError&&error.status===401?'Your session expired. Sign in again.':error instanceof ApiError&&[403,404,409].includes(error.status)?'This history is unavailable or your access changed. Refresh your authorized workspace.':error instanceof ApiError&&error.status===422?'Check the date range and reference filters, then search again.':'History could not be loaded. Retry the read.';
export const isProcessingError=(record:AuditEvent):record is ProcessingError=>'support_reference' in record;
function ProviderFailureDetails({facts}:{facts:ProviderFailureFacts}){
 const fields:Array<[string,string|number|boolean|undefined]>=[['HTTP status',facts.http_status],['HTTP reason',facts.http_reason],['Provider error code',facts.provider_code],['Provider error type',facts.provider_type],['Provider parameter',facts.provider_param],['Provider target',facts.provider_target],['Provider message',facts.provider_message],['Provider request ID',facts.request_id],['Transport attempted',facts.transport_attempted],['Response received',facts.response_received],['Transport exception',facts.exception_type],['Transport cause',facts.cause_type]];
 return <><dl>{fields.filter(([,value])=>value!==undefined).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}</dl>{facts.provider_message_redacted&&<p>The provider message contained unrecognized free text and was withheld to protect private content.</p>}{(facts.provider_code_redacted||facts.provider_type_redacted||facts.provider_param_redacted||facts.provider_target_redacted)&&<p>Unrecognized provider code, type or parameter identifiers were withheld to protect private content.</p>}</>;
}
export function HistoryFacts({record,technical=false,onOpenReport}:{record:AuditEvent;technical?:boolean;onOpenReport?:(id:string)=>void}){
  const [copy,setCopy]=useState('');
  return <div className="history-facts"><dl>{([['Time (with UTC offset)',<TenantTime key="time" value={record.occurred_at}/>],['Module',record.module],['Operation',record.operation],['Outcome',record.outcome],['Actor',record.actor_id??'System / unavailable'],['Target type',record.target_type??'Unavailable'],['Target reference',record.target_id??'Unavailable']] as Array<[string,React.ReactNode]>).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>{isProcessingError(record)&&<><p>{record.message}</p><dl><div><dt>Error category</dt><dd>{record.category}</dd></div><div><dt>Source operation type</dt><dd>{record.source_kind??'Unavailable'}</dd></div><div><dt>Source reference</dt><dd>{record.source_id??'Unavailable'}</dd></div><div><dt>Support reference</dt><dd>{record.support_reference}</dd></div><div><dt>Correlation reference</dt><dd>{record.correlation_id}</dd></div></dl><button type="button" onClick={()=>{if(!navigator.clipboard){setCopy('Copy unavailable. Select the support reference above.');return}void navigator.clipboard.writeText(record.support_reference).then(()=>setCopy('Support reference copied.'),()=>setCopy('Copy unavailable. Select the support reference above.'))}}>Copy support reference</button>{copy&&<p role="status">{copy}</p>}{record.case_id&&onOpenReport&&<button type="button" onClick={()=>onOpenReport(record.case_id!)}>Open affected report</button>}{technical&&record.technical&&<details><summary>Redacted technical diagnostics</summary><p>Exception category: {record.technical.diagnostic.exception_type}</p>{record.technical.diagnostic.provider&&<ProviderFailureDetails facts={record.technical.diagnostic.provider}/>}{record.technical.diagnostic.causes?.map((cause,index)=><div key={index}><p>Cause: {cause.exception_type}</p><ul>{cause.frames.map((frame,at)=><li key={at}>{frame.module} · {frame.function} · line {frame.line}</li>)}</ul></div>)}<ul>{record.technical.diagnostic.frames.map((frame,index)=><li key={index}>{frame.module} · {frame.function} · line {frame.line}</li>)}</ul>{record.technical.truncated&&<p>Diagnostic frames were bounded.</p>}</details>}</>}{!isProcessingError(record)&&record.details&&<dl>{Object.entries(record.details).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value??'Unavailable')}</dd></div>)}</dl>}{record.details_withheld&&<p>Private details are withheld.</p>}</div>
}

export function historyTimestamp(value:string):string{
  const date=new Date(value);
  return Number.isNaN(date.getTime())?value:new Intl.DateTimeFormat('en-AU',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZone:'UTC'}).format(date);
}
const outcomeTone=(outcome:string)=>outcome==='SUCCEEDED'?'success':outcome==='FAILED'?'danger':outcome==='REJECTED'?'warning':'neutral';
const outcomeLabel=(outcome:string)=>({SUCCEEDED:'Succeeded',FAILED:'Failed',REJECTED:'Rejected',UNSPECIFIED:'Unspecified'}[outcome]??outcome);
const accessChanged=(error:unknown)=>error instanceof ApiError&&[401,403,404,409].includes(error.status);
type DetailState={id:string;record:AuditEvent|null;loading:boolean;error:string};

function DetailDrawer({kind,state,opener,onClose,onRetry,onOpenReport,technical=true}:{kind:'audit'|'errors';state:DetailState;opener:HTMLElement|null;onClose:()=>void;onRetry:()=>void;onOpenReport?:(id:string)=>void;technical?:boolean}){
  const ref=useRef<HTMLDialogElement>(null),title=useId();
  useEffect(()=>{
    const element=ref.current!;
    element.showModal();
    element.querySelector<HTMLButtonElement>('button')?.focus();
    return()=>{element.close();if(opener?.isConnected)opener.focus()};
  },[]);
  return <dialog ref={ref} tabIndex={-1} onKeyDown={containDialogFocus} className="tenant-dialog history-detail-drawer" aria-labelledby={title} onCancel={event=>{event.preventDefault();onClose()}}>
    <header className="admin-drawer-header"><div><p className="admin-overline">{kind==='errors'?'Errors and processing':'Audit history'}</p><h2 id={title}>Occurrence details</h2></div><button type="button" className="subtle" onClick={onClose}>Close details</button></header>
    <div className="admin-drawer-body" aria-busy={state.loading}>
      {state.loading&&<AdminState kind="loading" title="Loading occurrence details"><p>The selected record is being checked against your current access.</p></AdminState>}
      {state.error&&<AdminState kind="error" title="Details unavailable" action={<button type="button" className="subtle" onClick={onRetry}>Retry details</button>}><p>{state.error}</p></AdminState>}
      {state.record&&!state.loading&&!state.error&&<><div className="admin-record-summary"><span className={`status-badge status-${outcomeTone(state.record.outcome)}`}>{outcomeLabel(state.record.outcome)}</span><h3>{state.record.operation}</h3><p><TenantTime value={state.record.occurred_at}/></p></div><HistoryFacts record={state.record} technical={technical} onOpenReport={onOpenReport}/></>}
    </div>
  </dialog>;
}

export function HistoryTable({items,kind,busy,onOpen}:{items:AuditEvent[];kind:'audit'|'errors';busy:boolean;onOpen:(id:string,opener:HTMLElement)=>void}){
  return <AdminTableRegion label={kind==='audit'?'Audit activity table':'Error occurrences table'}><table className="admin-data-table history-table">
    <caption className="sr-only">{kind==='audit'?'Audit activity':'Error occurrences'}, newest first. Dates follow tenant display settings and show their time zone. Open details for the complete record.</caption>
    <thead><tr><th scope="col" className="history-desktop-column history-time-column" aria-sort="descending">Date and time<span aria-hidden="true"> ↓</span></th><th scope="col">Activity</th><th scope="col" className="history-desktop-column">Module</th><th scope="col">Outcome</th><th scope="col" className="history-desktop-column">Actor reference</th><th scope="col"><span className="sr-only">Record actions</span></th></tr></thead>
    <tbody>{items.map(record=><tr key={record.id}><td className="history-desktop-column history-time-column"><TenantTime value={record.occurred_at}/></td><th scope="row" className="history-activity"><span className="history-operation">{record.operation}</span><span className="history-mobile-time"><TenantTime value={record.occurred_at}/></span><small>{record.target_type??'No target type recorded'}</small></th><td className="history-desktop-column">{record.module}</td><td><span className={`status-badge status-${outcomeTone(record.outcome)}`}>{outcomeLabel(record.outcome)}</span></td><td className="history-desktop-column history-reference"><span>{record.actor_id??'System / unavailable'}</span></td><td><button type="button" className="subtle history-open" disabled={busy} aria-label={`View occurrence ${record.id}`} onClick={event=>onOpen(record.id,event.currentTarget)}>Details<span aria-hidden="true"> ›</span></button></td></tr>)}</tbody>
  </table></AdminTableRegion>;
}

export function TenantObservability({kind,companyId,membershipId,onError,onOpenReport}:{kind:'audit'|'errors';companyId:string;membershipId:string;onError:(error:unknown)=>void;onOpenReport?:(id:string)=>void}){
  return <HistoryBrowser key={`${companyId}:${membershipId}:${kind}`} kind={kind} companyId={companyId} membershipId={membershipId} onError={onError} onOpenReport={onOpenReport}/>;
}
export function ReportErrorHistory({companyId,membershipId,caseId,visible,onError}:{companyId:string;membershipId:string;caseId:string;visible:boolean;onError:(error:unknown)=>void}){
  return visible?<ReportHistoryDisclosure key={`${companyId}:${membershipId}:${caseId}`} companyId={companyId} membershipId={membershipId} caseId={caseId} onError={onError}/>:null;
}
function ReportHistoryDisclosure({companyId,membershipId,caseId,onError}:{companyId:string;membershipId:string;caseId:string;onError:(error:unknown)=>void}){
  const [open,setOpen]=useState(false);
  return <div className="report-error-history"><button type="button" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{open?'Hide report error history':'Show report error history'}</button>{open&&<HistoryBrowser kind="errors" companyId={companyId} membershipId={membershipId} caseId={caseId} onError={onError}/>}</div>;
}

function HistoryBrowser({kind,companyId,membershipId,caseId,onError,onOpenReport}:{kind:'audit'|'errors';companyId:string;membershipId:string;caseId?:string;onError:(error:unknown)=>void;onOpenReport?:(id:string)=>void}){
  const [draft,setDraft]=useState<HistoryFilters>({}),[applied,setApplied]=useState<HistoryFilters>({}),[query,setQuery]=useState<HistoryFilters>({page:1,limit:10});
  const [page,setPage]=useState<HistoryPage<AuditEvent>|null>(null),[detail,setDetail]=useState<DetailState|null>(null);
  const [busy,setBusy]=useState(true),[message,setMessage]=useState(''),[denied,setDenied]=useState(false),[filtersOpen,setFiltersOpen]=useState(false);
  const epoch=useRef(0),detailEpoch=useRef(0),mounted=useRef(false),detailOpener=useRef<HTMLElement|null>(null),errorHandler=useRef(onError);
  errorHandler.current=onError;
  const filterId=useId(),dateHelp=useId();
  const [pageSize,setPageSize]=useState<PageSize>(10);
  const [dateValid,setDateValid]=useState({from:true,to:true}),[filterReset,setFilterReset]=useState(0);
  useLayoutEffect(()=>{mounted.current=true;return()=>{mounted.current=false;epoch.current++;detailEpoch.current++}},[]);
  const closeDetail=()=>{detailEpoch.current++;setDetail(null)};
  async function load(filters:HistoryFilters){
    filters={page:1,limit:pageSize,...filters};
    setQuery({...filters});
    const at=++epoch.current;
    closeDetail();setMessage('');setDenied(false);setBusy(true);
    try{
      const result=caseId?await observabilityApi.caseErrors(caseId,filters):kind==='audit'?await observabilityApi.audit(membershipId,filters):await observabilityApi.errors(membershipId,filters);
      if(!mounted.current||at!==epoch.current)return;
      if(result.company_id!==companyId||(caseId&&result.case_id!==caseId))throw new ApiError(409,'HISTORY_CONTEXT_CHANGED','Context changed');
      if(!Number.isSafeInteger(result.total)||result.total!<0||!Number.isSafeInteger(result.page)||result.page!<1||![10,25,50,100].includes(result.page_size??0)||typeof result.snapshot!=='string')throw new ApiError(422,'HISTORY_PAGE_INVALID','Numbered history unavailable');
      setPage(result);setQuery({...filters,page:result.page,snapshot:result.snapshot});
    }catch(error){if(mounted.current&&at===epoch.current){setPage(null);setDenied(accessChanged(error));setMessage(historyReadError(error));if(error instanceof ApiError&&error.status===401)errorHandler.current(error)}}
    finally{if(mounted.current&&at===epoch.current)setBusy(false)}
  }
  useEffect(()=>{void load({})},[]);
  async function fetchDetail(id:string){
    const at=++detailEpoch.current;
    setDetail({id,record:null,loading:true,error:''});
    try{
      const result=kind==='audit'?await observabilityApi.auditDetail(membershipId,id):await observabilityApi.errorDetail(membershipId,id);
      if(!mounted.current||at!==detailEpoch.current)return;
      if(result.id!==id)throw new ApiError(409,'HISTORY_CONTEXT_CHANGED','Context changed');
      setDetail({id,record:result,loading:false,error:''});
    }catch(error){if(mounted.current&&at===detailEpoch.current){if(accessChanged(error)){setPage(null);setDenied(true);setMessage(historyReadError(error))}setDetail({id,record:null,loading:false,error:historyReadError(error)});if(error instanceof ApiError&&error.status===401)errorHandler.current(error)}}
  }
  const openDetail=(id:string,opener:HTMLElement)=>{detailOpener.current=opener;if(caseId){const record=page?.items.find(item=>item.id===id);if(record)setDetail({id,record,loading:false,error:''})}else void fetchDetail(id)};
  const activeFilters=Object.entries(applied).filter(([key,value])=>!['cursor','page','limit','snapshot'].includes(key)&&Boolean(value));
  const signature=(filters:HistoryFilters)=>JSON.stringify(Object.entries(filters).filter(([key,value])=>!['cursor','page','limit','snapshot'].includes(key)&&Boolean(value)).sort(([left],[right])=>left.localeCompare(right)));
  const pendingFilters=signature(draft)!==signature(applied);
  const reset=()=>{setDraft({});setApplied({});setDateValid({from:true,to:true});setFilterReset(value=>value+1);void load({})};
  const title=caseId?'Report error history':kind==='audit'?'Audit':'Errors and processing';
  return <section className="tenant-history" aria-label={caseId?'Report error history':kind==='audit'?'Tenant audit history':'Tenant error history'}>
    <AdminPageHeader title={title} description={kind==='audit'?'Important company activity, newest first.':'Retained error occurrences, newest first. A support reference identifies an occurrence; it does not establish resolution.'} actions={<button type="button" className="subtle" disabled={busy} onClick={()=>void load({...applied,page:1,limit:pageSize})}>Refresh history</button>}/>
    <div className="admin-list-surface"><div className="admin-command-bar"><div className="admin-command-actions"><button type="button" className="subtle" aria-expanded={filtersOpen} aria-controls={filterId} onClick={()=>setFiltersOpen(value=>!value)}>Filters{activeFilters.length>0&&<span className="admin-count">{activeFilters.length}</span>}</button><button disabled={busy} type="button" className="subtle" onClick={reset}>Reset history search</button></div><span className="admin-list-order">Newest first · Tenant date settings</span></div>
      <form id={filterId} hidden={!filtersOpen} className="history-filter-panel" onSubmit={event=>{event.preventDefault();if(!dateValid.from||!dateValid.to)return;setApplied({...draft});void load(draft)}}>
        <fieldset disabled={busy}><legend className="sr-only">Filter {title.toLowerCase()}</legend><div className="history-filter-grid">
          <TenantDateFilter key={`${filterReset}:from`} label="From" value={draft.from} onChange={value=>setDraft(before=>({...before,from:value}))} onValidity={valid=>setDateValid(before=>before.from===valid?before:{...before,from:valid})}/>
          <TenantDateFilter key={`${filterReset}:to`} label="To" value={draft.to} onChange={value=>setDraft(before=>({...before,to:value}))} onValidity={valid=>setDateValid(before=>before.to===valid?before:{...before,to:valid})}/>
          <label>Module<select aria-label="Module" value={draft.module??''} onChange={event=>setDraft(value=>({...value,module:event.target.value}))}><option value="">All modules</option>{['Identity','Company','Reports','Settings','Documents','API','Other'].map(value=><option key={value}>{value}</option>)}</select></label>
          {!caseId&&<label>Actor reference<input maxLength={36} value={draft.actor_id??''} onChange={event=>setDraft(value=>({...value,actor_id:event.target.value}))}/></label>}
          <label>Operation<input maxLength={100} value={draft.operation??''} onChange={event=>setDraft(value=>({...value,operation:event.target.value}))}/></label>
          <label>Outcome<select aria-label="Outcome" value={draft.outcome??''} onChange={event=>setDraft(value=>({...value,outcome:event.target.value}))}><option value="">All outcomes</option>{['SUCCEEDED','FAILED','REJECTED','UNSPECIFIED'].map(value=><option key={value} value={value}>{outcomeLabel(value)}</option>)}</select></label>
          {kind==='errors'&&<label>Support reference<input maxLength={36} value={draft.support_reference??''} onChange={event=>setDraft(value=>({...value,support_reference:event.target.value}))}/></label>}
        </div><p id={dateHelp} className="admin-field-help">Filter times follow the tenant display zone and are converted to UTC for the query. Repeated daylight-saving times require an explicit offset choice.</p><div className="history-filter-actions"><button disabled={busy||!dateValid.from||!dateValid.to} type="submit">Search history</button>{pendingFilters&&<span className="admin-field-help">Apply your filter changes to update the results.</span>}</div></fieldset>
      </form>
      <div className="admin-results-summary" role="status">{busy?'Loading history…':page?`${page.total} matching occurrences. Page ${page.page} of ${page.pages}.`:message?'Results unavailable.':''}</div>
      <div aria-busy={busy}>
        {busy&&<AdminState kind="loading" title="Loading history"><p>Fetching the requested page for your current company.</p></AdminState>}
        {!busy&&message&&<AdminState kind={denied?'denied':'error'} title={denied?'History unavailable':'History could not be loaded'} action={<button type="button" className="subtle" onClick={()=>void load(query)}>Retry history</button>}><p>{message}</p></AdminState>}
        {!busy&&page&&page.items.length===0&&<AdminState kind="empty" title={activeFilters.length?'No matching occurrences':kind==='audit'?'No audit activity returned':'No error occurrences returned'} action={activeFilters.length?<button type="button" className="subtle" onClick={reset}>Clear filters</button>:undefined}><p>{activeFilters.length?'Try different filters or clear the search.':'There are no occurrences available for this company in the returned search period.'}</p></AdminState>}
        {!busy&&page&&page.items.length>0&&<HistoryTable kind={kind} items={page.items} busy={busy} onOpen={openDetail}/>}
      </div>
      {page&&<><Pagination label={title} total={page.total!} page={page.page!} pageSize={page.page_size! as PageSize} disabled={busy} onPage={number=>void load({...query,page:number})} onPageSize={size=>{setPageSize(size);void load({...applied,page:1,limit:size})}}/><p className="admin-field-help">Newest first. Counts use an append cutoff; refresh history to include new occurrences.</p></>}
    </div>
    {detail&&<DetailDrawer kind={kind} state={detail} opener={detailOpener.current} onClose={closeDetail} onRetry={()=>void fetchDetail(detail.id)} technical={!caseId} onOpenReport={onOpenReport?id=>{closeDetail();onOpenReport(id)}:undefined}/>}
  </section>;
}
