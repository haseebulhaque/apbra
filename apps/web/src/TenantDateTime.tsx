import React,{createContext,useContext,useEffect,useId,useMemo,useRef,useState} from 'react';
import {ApiError,dateDisplayApi,type DateDisplay,type DateDisplayHistory} from './api';
import {AdminState,AdminTableRegion,Pagination,usePagedItems} from './AdminUI';

export function validTimeZone(value:unknown):value is string{
  if(typeof value!=='string'||!value||value.length>255||value.trim()!==value||/^[+-]/.test(value))return false;
  try{new Intl.DateTimeFormat('en',{timeZone:value}).format(0);return true}catch{return false}
}
export function tenantTimeZoneOptions(at:Date=new Date()):Array<{zone:string;label:string}>{
  const supported=typeof Intl.supportedValuesOf==='function'?Intl.supportedValuesOf('timeZone'):[];
  const zones=[...new Set(['UTC',browserTimeZone(),...supported])].sort();
  return zones.map(zone=>{const offset=new Intl.DateTimeFormat('en',{timeZone:zone,timeZoneName:'longOffset'}).formatToParts(at).find(part=>part.type==='timeZoneName')?.value.replace('GMT','UTC')??'UTC';return{zone,label:`${offset==='UTC'?'UTC+00:00':offset} · ${zone.replaceAll('_',' ')}`}});
}

export function TimeZoneSelector({value,onChange,disabled=false}:{value:string;onChange:(zone:string)=>void;disabled?:boolean}){
  const id=useId(),[open,setOpen]=useState(false),[searching,setSearching]=useState(false),[active,setActive]=useState(-1),container=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null);
  const [referenceDate]=useState(()=>new Date()),options=useMemo(()=>tenantTimeZoneOptions(referenceDate),[referenceDate]);
  const query=value.trim().toLowerCase().replaceAll('_',' '),matches=options.filter(option=>!searching||`${option.zone.replaceAll('_',' ')} ${option.label}`.toLowerCase().includes(query));
  const selected=matches.findIndex(option=>option.zone===value);
  useEffect(()=>{setActive(selected)},[value,selected]);
  useEffect(()=>{if(open&&active>=0)document.getElementById(id+'-option-'+active)?.scrollIntoView?.({block:'nearest',behavior:'instant'})},[active,open,id]);
  useEffect(()=>{const outside=(event:PointerEvent)=>{if(!container.current?.contains(event.target as Node))setOpen(false)};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside)},[]);
  function choose(zone:string){onChange(zone);setSearching(false);input.current?.focus();setOpen(false)}
  return <div className="tenant-zone-picker" ref={container} onBlur={event=>{if(event.relatedTarget&&!event.currentTarget.contains(event.relatedTarget as Node))setOpen(false)}}>
    <label htmlFor={id}>Display time zone</label><div className="tenant-zone-input"><input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={id+'-list'} aria-activedescendant={open&&active>=0&&matches[active]?id+'-option-'+active:undefined} aria-describedby={id+'-help'} value={value} disabled={disabled} autoComplete="off" placeholder="Search a city, region or UTC offset" onFocus={()=>{setSearching(false);setOpen(true)}} onChange={event=>{onChange(event.target.value);setSearching(true);setOpen(true);setActive(-1)}} onKeyDown={event=>{if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();setOpen(true);setActive(before=>matches.length?Math.max(0,Math.min(matches.length-1,before+(event.key==='ArrowDown'?1:-1))):-1)}else if(event.key==='Enter'&&open&&active>=0&&matches[active]){event.preventDefault();choose(matches[active].zone)}else if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();setOpen(false)}}}/><button type="button" className="subtle tenant-zone-toggle" aria-label="Show time zones" aria-expanded={open} disabled={disabled} onClick={()=>{const next=!open;input.current?.focus();setOpen(next)}}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7 5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.7"/></svg></button>
    {open&&!disabled&&<div className="tenant-zone-popup"><div role="listbox" id={id+'-list'} aria-label="Time zones">{matches.map((option,index)=><div key={option.zone} id={id+'-option-'+index} role="option" aria-selected={index===active} onPointerDown={event=>event.preventDefault()} onClick={()=>choose(option.zone)}>{option.label}</div>)}</div>{matches.length===0&&<p role="status">No matching time zone. Try a city, region or UTC offset.</p>}<p className="tenant-zone-caption">{matches.length} matches · offsets on {referenceDate.toLocaleDateString()}. Dates use daylight saving for their own date.</p><button type="button" className="subtle" onClick={()=>choose('')}>Use each viewer’s local time</button></div>}</div>
    <p id={id+'-help'} className="admin-field-help">Search the IANA time-zone catalogue. Leave blank to follow each viewer’s local time ({browserTimeZone()} in this browser).</p>{!open&&value&&!validTimeZone(value)&&<p role="alert">Choose a valid time zone from the list.</p>}
  </div>;
}

export function canonicalTimeZone(value:string){if(!validTimeZone(value))throw new RangeError('Invalid IANA time zone');return new Intl.DateTimeFormat('en',{timeZone:value}).resolvedOptions().timeZone}
export function browserTimeZone(){
  const value=new Intl.DateTimeFormat().resolvedOptions().timeZone;
  return validTimeZone(value)?value:'UTC';
}
export function acceptDateDisplay(value:DateDisplay,companyId:string,minimumVersion=0){
  return value.company_id===companyId&&Number.isSafeInteger(value.version)&&value.version>=minimumVersion&&(value.time_zone===null||validTimeZone(value.time_zone))&&(value.version!==0||value.time_zone===null);
}
export function formatTenantTimestamp(value:string,zone:string,locale?:string){
  // Do not invent a zone for legacy naive values. Raw storage/downloads stay intact.
  if(!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value))return `${value} (time zone not recorded)`;
  const calendar=value.slice(0,10),[year,month,day]=calendar.split('-').map(Number);
  if(new Date(Date.UTC(year,month-1,day)).toISOString().slice(0,10)!==calendar)return 'Invalid recorded date';
  const date=new Date(value);
  if(!Number.isFinite(date.getTime()))return 'Invalid recorded date';
  if(!validTimeZone(zone))throw new RangeError('Invalid IANA time zone');
  return `${new Intl.DateTimeFormat(locale,{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZone:zone,timeZoneName:'longOffset'}).format(date)} · ${zone}`;
}
type DateContext={zone:string;status:'ready'|'loading'|'failed'};
const Context=createContext<DateContext>({zone:'UTC',status:'ready'});
const CHANGED='apbra-date-display-changed';
export function TenantDateTimeProvider({companyId,membershipId,children}:{companyId:string;membershipId:string;children:React.ReactNode}){
  // Parent keys this boundary by company + membership. No tenant preference is cached globally.
  return <ScopedDateProvider key={`${companyId}:${membershipId}`} companyId={companyId}>{children}</ScopedDateProvider>;
}
function ScopedDateProvider({companyId,children}:{companyId:string;children:React.ReactNode}){
  const [value,setValue]=useState<DateDisplay|null>(null),[status,setStatus]=useState<DateContext['status']>('loading');
  const epoch=useRef(0),latest=useRef(-1);
  useEffect(()=>{
    let mounted=true;
    const apply=(next:DateDisplay)=>{if(!mounted||!acceptDateDisplay(next,companyId,latest.current))return false;latest.current=next.version;setValue(next);setStatus('ready');return true};
    const load=()=>{const request=++epoch.current;void dateDisplayApi.current().then(next=>{if(request!==epoch.current||!mounted)return;if(!acceptDateDisplay(next,companyId))throw new Error('Date preference context changed');if(next.version>=latest.current)apply(next)}).catch(()=>{if(mounted&&request===epoch.current){setValue(null);setStatus('failed')}})};
    const changed=(event:Event)=>{const next=(event as CustomEvent<DateDisplay>).detail;if(next&&acceptDateDisplay(next,companyId,latest.current)){epoch.current++;apply(next)}};
    load();window.addEventListener('focus',load);window.addEventListener(CHANGED,changed);
    return()=>{mounted=false;epoch.current++;window.removeEventListener('focus',load);window.removeEventListener(CHANGED,changed)};
  },[companyId]);
  const zone=status==='ready'?(value?.time_zone??browserTimeZone()):'UTC';
  return <Context.Provider value={{zone,status}}>{status!=='ready'&&<p className="workspace-notice" role="status">{status==='loading'?'Loading tenant date settings. Dates temporarily show UTC.':'Tenant date settings could not be loaded. Dates show UTC; reload to retry.'}</p>}{children}</Context.Provider>;
}
export function useTenantDateTime(){return useContext(Context)}
export function TenantTime({value}:{value:string}){const {zone,status}=useTenantDateTime();return <time dateTime={value} title={value}>{formatTenantTimestamp(value,zone)}{status!=='ready'?' (temporary UTC display)':''}</time>}

/** Resolve a local filter input to all actual instants, including DST overlaps.
 * Empty candidates = gap/invalid; two candidates require an explicit user choice.
 */
export function localTimeCandidates(value:string,zone:string):string[]{
  if(!validTimeZone(zone)||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value))return [];
  const [y,m,d,h,min,sec=0]=value.split(/[-T:]/).map(Number),nominal=Date.UTC(y,m-1,d,h,min,sec);
  if(new Date(nominal).toISOString().slice(0,19)!==`${value.length===16?value+':00':value}`)return [];
  const fmt=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  const local=(stamp:number)=>{const p=Object.fromEntries(fmt.formatToParts(stamp).map(part=>[part.type,part.value]));return Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second)};
  const offsets=new Set<number>();for(let hour=-48;hour<=48;hour+=6){const stamp=nominal+hour*3600000;offsets.add(local(stamp)-stamp)}
  return [...offsets].map(offset=>nominal-offset).filter(stamp=>local(stamp)===nominal).sort((a,b)=>a-b).map(stamp=>new Date(stamp).toISOString());
}

export function localInputForInstant(value:string,zone:string){
  const stamp=Date.parse(value);if(!Number.isFinite(stamp))return '';
  const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(stamp).map(part=>[part.type,part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
}
export function TenantDateFilter({label,value,onChange,onValidity}:{label:string;value?:string;onChange:(value:string|undefined)=>void;onValidity:(valid:boolean)=>void}){
  const {zone}=useTenantDateTime(),help=useId();
  const [entry,setEntry]=useState(value?localInputForInstant(value,zone):''),[choice,setChoice]=useState(value??'');
  const sent=useRef(value),priorZone=useRef(zone);
  useEffect(()=>{if(value!==sent.current||zone!==priorZone.current){setEntry(value?localInputForInstant(value,zone):'');setChoice(value??'');onValidity(true)}sent.current=value;priorZone.current=zone},[value,zone]);
  const candidates=entry?localTimeCandidates(entry,zone):[];
  function change(next:string){setEntry(next);const matches=next?localTimeCandidates(next,zone):[];const resolved=matches.length===1?matches[0]:undefined;setChoice(resolved??'');sent.current=resolved;onChange(resolved);onValidity(!next||matches.length===1)}
  return <div className="tenant-date-filter"><label>{label} ({zone})<input type="datetime-local" step="1" value={entry} aria-describedby={help} onChange={event=>change(event.target.value)}/></label><p id={help} className="admin-field-help">{entry&&candidates.length===0?'This local time is invalid or does not occur because of daylight saving. Choose another time.':entry&&candidates.length>1?'This clock time occurs twice. Select the intended UTC offset.':'Dates use the displayed zone. Leave blank for no date boundary.'}</p>{entry&&candidates.length>1&&<label>{label} UTC offset<select value={choice} onChange={event=>{const next=event.target.value;const valid=candidates.includes(next);setChoice(valid?next:'');sent.current=valid?next:undefined;onChange(valid?next:undefined);onValidity(valid)}}><option value="">Choose the intended time</option>{candidates.map(instant=><option value={instant} key={instant}>{formatTenantTimestamp(instant,zone)}</option>)}</select></label>}</div>;
}

export function TenantDateSettings({companyId,membershipId,csrfToken,onAbandonmentChanged}:{companyId:string;membershipId:string;csrfToken:string;onAbandonmentChanged?:(required:boolean)=>void}){
  const [current,setCurrent]=useState<DateDisplay|null>(null),[draft,setDraft]=useState(''),[items,setItems]=useState<DateDisplayHistory[]>([]),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[failed,setFailed]=useState(false),[historyFailed,setHistoryFailed]=useState(false),[uncertain,setUncertain]=useState(false);
  const mounted=useRef(true),inFlight=useRef(false),loadEpoch=useRef(0),knownVersion=useRef(0);
  const page=usePagedItems(items,`${companyId}:${membershipId}`);
  const requiresReview=inFlight.current||uncertain||!!current&&draft!==(current.time_zone??'');
  useEffect(()=>{onAbandonmentChanged?.(requiresReview);return()=>onAbandonmentChanged?.(false)},[requiresReview,onAbandonmentChanged]);
  useEffect(()=>{if(!requiresReview)return;const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[requiresReview]);
  const load=async()=>{const epoch=++loadEpoch.current;setBusy(true);try{const value=await dateDisplayApi.admin(membershipId);if(!mounted.current||epoch!==loadEpoch.current)return;if(!acceptDateDisplay(value,companyId,knownVersion.current))throw new Error('Context changed');knownVersion.current=value.version;setCurrent(value);setDraft(value.time_zone??'');window.dispatchEvent(new CustomEvent(CHANGED,{detail:value}));setFailed(false);setUncertain(false);try{const history=await dateDisplayApi.history(membershipId);if(mounted.current&&epoch===loadEpoch.current){setItems(history);setHistoryFailed(false)}}catch{if(mounted.current&&epoch===loadEpoch.current)setHistoryFailed(true)}}catch{if(mounted.current&&epoch===loadEpoch.current){setCurrent(null);setItems([]);setFailed(true)}}finally{if(mounted.current&&epoch===loadEpoch.current)setBusy(false)}};
  useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;loadEpoch.current++}},[companyId,membershipId]);
  async function save(){if(inFlight.current||!current||uncertain||draft&&!validTimeZone(draft))return;inFlight.current=true;setBusy(true);setMessage('');let acknowledged=false;try{const value=await dateDisplayApi.update(draft?canonicalTimeZone(draft):null,current.version,membershipId,csrfToken);if(!mounted.current)return;if(!acceptDateDisplay(value,companyId,current.version+1)||value.version!==current.version+1||value.time_zone!==(draft?canonicalTimeZone(draft):null))throw new Error('Unconfirmed save');acknowledged=true;knownVersion.current=value.version;setCurrent(value);setDraft(value.time_zone??'');window.dispatchEvent(new CustomEvent(CHANGED,{detail:value}));setMessage('Date display saved for this tenant. Stored timestamps and report history are unchanged.');try{const history=await dateDisplayApi.history(membershipId);if(mounted.current){setItems(history);setHistoryFailed(false)}}catch{if(mounted.current)setHistoryFailed(true)}}catch(error){if(mounted.current&&!acknowledged){const rejected=error instanceof ApiError&&error.status>=400&&error.status<500&&error.status!==408;if(error instanceof ApiError&&[401,403].includes(error.status)){setCurrent(null);setItems([]);setFailed(true)}setUncertain(!rejected||error instanceof ApiError&&error.status===409);setMessage(rejected?'The server rejected this change. Check the time zone and reload current date settings if your access or version changed.':'The save could not be confirmed. Reload current date settings before trying again.')}}finally{inFlight.current=false;if(mounted.current)setBusy(false)}}
  return <section className="admin-settings-group" aria-label="Dates and time"><h3>Dates &amp; time</h3><p>Display dates consistently across this tenant. UTC storage and original report files stay unchanged. This preference is separate from AI report conventions.</p>{!current?<AdminState kind={failed?'error':'loading'} title={failed?'Date settings could not be loaded':'Loading date settings'} action={failed?<button onClick={()=>void load()}>Retry date settings</button>:undefined}/>:<><TimeZoneSelector value={draft} onChange={setDraft} disabled={busy||uncertain}/><p>Effective date settings version {current.version}. Preview: {formatTenantTimestamp(new Date().toISOString(),validTimeZone(draft)?draft:browserTimeZone())}</p><div className="command-bar"><button disabled={busy||uncertain||!!draft&&!validTimeZone(draft)||draft===(current.time_zone??'')} onClick={()=>void save()}>{busy?'Please wait…':'Save date display'}</button><button className="subtle" disabled={busy} onClick={()=>void load()}>Reload date settings</button></div></>}{message&&<p role={uncertain?'alert':'status'}>{message}</p>}<details className="admin-settings-history"><summary>Date settings history · {items.length} versions</summary>{historyFailed?<AdminState kind="error" title="Date settings history could not be loaded"/>:items.length===0?<p>No date preference has been saved.</p>:<AdminTableRegion label="Date settings history"><table className="admin-data-table"><thead><tr><th scope="col">Version</th><th scope="col">Display time zone</th><th scope="col">Recorded</th></tr></thead><tbody>{page.items.map(item=><tr key={item.version}><td>{item.version}</td><td>{item.time_zone??'Each viewer’s browser local time'}</td><td><TenantTime value={item.created_at}/></td></tr>)}</tbody></table></AdminTableRegion>}<Pagination label="Date settings history" total={page.total} page={page.page} pageSize={page.pageSize} onPage={page.onPage} onPageSize={page.onPageSize} disabled={busy}/></details></section>;
}
