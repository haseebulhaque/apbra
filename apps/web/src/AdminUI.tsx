import React,{useEffect,useId,useRef,useState} from 'react';

export const PAGE_SIZES=[10,25,50,100] as const;
export type PageSize=typeof PAGE_SIZES[number];
export function paginationModel(total:number,page:number,pageSize:PageSize){
  if(!Number.isSafeInteger(total)||total<0||!Number.isSafeInteger(page)||page<1||!PAGE_SIZES.includes(pageSize))throw new RangeError('Invalid pagination');
  const pages=Math.max(1,Math.ceil(total/pageSize)),current=Math.min(page,pages),offset=(current-1)*pageSize;
  const numbers=[...new Set([1,current-1,current,current+1,pages])].filter(value=>value>=1&&value<=pages).sort((a,b)=>a-b);
  return {total,page:current,pageSize,pages,offset,start:total?offset+1:0,end:Math.min(offset+pageSize,total),numbers};
}

/** A complete, authorized array only. Never use this to conceal a truncated API page. */
export function usePagedItems<T>(items:readonly T[],scope=''){
  const [state,setState]=useState<{scope:string;page:number;pageSize:PageSize}>({scope,page:1,pageSize:10});
  const active=state.scope===scope?state:{scope,page:1,pageSize:10 as PageSize};
  const model=paginationModel(items.length,active.page,active.pageSize);
  useEffect(()=>{setState(current=>current.scope!==scope?{scope,page:1,pageSize:10}:current.page>model.pages?{...current,page:model.pages}:current)},[scope,model.pages]);
  const onPage=(page:number)=>{if(Number.isSafeInteger(page)&&page>=1)setState({...active,page:Math.min(page,model.pages)})};
  const onPageSize=(pageSize:PageSize)=>{if(PAGE_SIZES.includes(pageSize))setState({scope,page:1,pageSize})};
  return {...model,items:items.slice(model.offset,model.end),onPage,onPageSize};
}

export function Pagination({label,total,page,pageSize,onPage,onPageSize,disabled=false}:{label:string;total:number;page:number;pageSize:PageSize;onPage:(page:number)=>void;onPageSize:(size:PageSize)=>void;disabled?:boolean}){
  const model=paginationModel(total,page,pageSize);
  return <nav className="record-pagination" aria-label={`${label} pagination`}>
    <div className="pagination-summary"><label>Rows per page<select aria-label={`${label} rows per page`} value={pageSize} disabled={disabled} onChange={event=>{const size=Number(event.target.value);if(PAGE_SIZES.includes(size as PageSize))onPageSize(size as PageSize)}}>{PAGE_SIZES.map(size=><option key={size} value={size}>{size}</option>)}</select></label><span role="status">{model.start}–{model.end} of {total}</span></div>
    <div className="pagination-pages"><button type="button" className="subtle" aria-label={`Previous ${label.toLowerCase()} page`} disabled={disabled||model.page===1} onClick={()=>onPage(model.page-1)}>Previous</button>
      {model.numbers.map((number,index)=><React.Fragment key={number}>{index>0&&number-model.numbers[index-1]>1&&<span className="pagination-gap" aria-hidden="true">…</span>}<button type="button" className="subtle pagination-number" aria-label={`${label} page ${number}`} aria-current={total>0&&number===model.page?'page':undefined} disabled={disabled||total===0} onClick={()=>onPage(number)}>{number}</button></React.Fragment>)}
      <span className="pagination-page-count">Page {model.page} of {model.pages}</span><button type="button" className="subtle" aria-label={`Next ${label.toLowerCase()} page`} disabled={disabled||model.page===model.pages} onClick={()=>onPage(model.page+1)}>Next</button></div>
  </nav>;
}

export function AdminPageHeader({title,description,meta,actions}:{title:string;description?:string;meta?:React.ReactNode;actions?:React.ReactNode}){
  return <header className="admin-page-header"><div><h2>{title}</h2>{description&&<p>{description}</p>}{meta&&<div className="admin-page-meta">{meta}</div>}</div>{actions&&<div className="admin-page-actions">{actions}</div>}</header>;
}

export function AdminState({kind,title,children,action}:{kind:'loading'|'empty'|'error'|'denied';title:string;children?:React.ReactNode;action?:React.ReactNode}){
  return <div className={`admin-state admin-state-${kind}`} role={kind==='loading'?'status':kind==='error'||kind==='denied'?'alert':undefined}>
    <span className="admin-state-symbol" aria-hidden="true">{kind==='loading'?<span className="admin-spinner"/>:kind==='error'||kind==='denied'?'!':'—'}</span>
    <div><h3>{title}</h3>{children&&<div className="admin-state-copy">{children}</div>}{action&&<div className="admin-state-actions">{action}</div>}</div>
  </div>;
}

export function AdminTableRegion({label,children}:{label:string;children:React.ReactNode}){
  return <div className="admin-table-region" role="region" aria-label={label} tabIndex={0}>{children}</div>;
}

/** Native modal: browser-managed focus containment, Escape and return to the opener. */
export function AdminDialog({title,busy=false,onClose,children}:{title:string;busy?:boolean;onClose:()=>void;children:React.ReactNode}){
  const ref=useRef<HTMLDialogElement>(null),id=useId();
  useEffect(()=>{const dialog=ref.current!,opener=document.activeElement as HTMLElement|null;dialog.showModal();dialog.querySelector<HTMLButtonElement>('button')?.focus();return()=>{dialog.close();if(opener?.isConnected)opener.focus()}},[]);
  useEffect(()=>{if(busy)ref.current?.focus()},[busy]);
  return <dialog ref={ref} tabIndex={-1} className="tenant-dialog admin-confirm-dialog" aria-labelledby={id} aria-busy={busy} onKeyDown={containDialogFocus} onCancel={event=>{event.preventDefault();if(!busy)onClose()}}><header className="admin-drawer-header"><h2 id={id}>{title}</h2><button type="button" className="subtle" disabled={busy} onClick={onClose}>Close</button></header><div className="admin-dialog-body">{children}</div></dialog>;
}

export function containDialogFocus(event:React.KeyboardEvent<HTMLDialogElement>){
  if(event.key!=='Tab')return;
  const controls=Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button,input,select,textarea,summary,a[href],[tabindex]')).filter(element=>element.tabIndex>=0&&!element.matches(':disabled')&&element.getClientRects().length>0);
  const index=controls.indexOf(document.activeElement as HTMLElement);
  if(controls.length===0){event.preventDefault();event.currentTarget.focus();return}
  if(index<0||event.shiftKey&&index===0||!event.shiftKey&&index===controls.length-1){event.preventDefault();controls[event.shiftKey?controls.length-1:0].focus()}
}

export function providerCursorState(cursors:Array<string|undefined>,page:number,next:string|null,more:boolean){
  if(!Number.isSafeInteger(page)||page<0||page>=cursors.length)throw new Error('Invalid page selection.');
  if(more&&(!next||cursors.slice(0,page+1).includes(next)))throw new Error('The service returned a repeated or missing page marker. The listing is incomplete.');
  return more&&cursors[page+1]===next?cursors:cursors.slice(0,page+1);
}

/** Cursor pages are not a complete array; never invent a total or invoke access. */
export function ProviderReadPanel({title,scope,expectedVersion,kind,load}:{title:string;scope:string;expectedVersion:number;kind:'agents'|'files';load:(limit:number,after?:string)=>Promise<import('./api').ProviderReadPage>}){
  const [state,setState]=useState<{scope:string;page:number;size:PageSize;cursors:Array<string|undefined>;busy:boolean;result:import('./api').ProviderReadPage|null;error:string}>({scope,page:0,size:10,cursors:[undefined],busy:false,result:null,error:''});
  const epoch=useRef(0),alive=useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;epoch.current++}},[]);
  useEffect(()=>{epoch.current++;setState({scope,page:0,size:10,cursors:[undefined],busy:false,result:null,error:''})},[scope]);
  const active=state.scope===scope?state:{scope,page:0,size:10 as PageSize,cursors:[undefined],busy:false,result:null,error:''};
  const read=async(page=active.page,size=active.size,cursors=active.cursors)=>{
    const stamp=++epoch.current;setState({scope,page,size,cursors,busy:true,result:null,error:''});
    try{const result=await load(size,cursors[page]);if(!alive.current||stamp!==epoch.current)return;
      if(result.settings_version!==expectedVersion)throw new Error('The effective settings changed. Reload settings before reading again.');
      const retained=providerCursorState(cursors,page,result.next_cursor,result.has_more);
      setState({scope,page,size,cursors:retained,busy:false,result,error:''});
    }catch(error){if(alive.current&&stamp===epoch.current)setState({scope,page,size,cursors,busy:false,result:null,error:error instanceof Error?error.message:'The metadata read failed. Try again after checking access.'})}
  };
  const result=active.result;
  return <section className="admin-list-surface provider-read-panel" aria-label={title} aria-busy={active.busy}><h3>{title}</h3>
    <p>{kind==='agents'?'Read agent metadata available to the signed-in account in the configured project. This does not verify report-generation permission or change the selected reporting agent.':'Read current processing metadata for this attached knowledge store. This is not file content or a complete revision, deletion or audit history.'}</p>
    <div className="admin-command-actions"><button type="button" className="subtle" disabled={active.busy} onClick={()=>void read()}>{active.busy?'Reading…':result?'Refresh metadata':'Read metadata'}</button><label><span>Rows per page</span><select aria-label={`${title} rows per page`} value={active.size} disabled={active.busy} onChange={e=>{const size=Number(e.target.value) as PageSize;if(!PAGE_SIZES.includes(size))return;if(result)void read(0,size,[undefined]);else setState({...active,size,page:0,cursors:[undefined]})}}>{PAGE_SIZES.map(size=><option key={size} value={size}>{size}</option>)}</select></label></div>
    {active.busy&&<AdminState kind="loading" title="Reading provider metadata"/>}
    {active.error&&<AdminState kind="error" title="Metadata could not be read"><p>{active.error}</p></AdminState>}
    {!active.busy&&result?.status==='DENIED'&&<AdminState kind="denied" title="This account cannot read this resource"><p>No permissions were changed. Ask the workspace operator to check the existing delegated access.</p></AdminState>}
    {!active.busy&&result?.status==='UNAVAILABLE'&&<AdminState kind="empty" title="Provider metadata is unavailable"><p>{result.reason==='READ_ACCESS_UNCONFIGURED'||result.reason==='CALLER_RESOURCE_ACCESS_REQUIRED'?'Read access has not been set up for this account and resource. This does not mean the source contains no records.':result.reason==='STORE_NOT_REFERENCED_BY_CONFIGURED_AGENT_VERSION'?'This store is not referenced by the configured agent version. Its files were not read.':'The configured connection could not provide this metadata. Check the saved agent version and existing access.'}</p></AdminState>}
    {!active.busy&&result?.status==='OBSERVED'&&<><p role="status">Page {active.page+1} · {result.items.length} records on this page. The service does not provide a total count.</p>{result.items.length===0?<AdminState kind="empty" title="No records returned for this page"/>:<AdminTableRegion label={`${title} records`}><table><caption>{title} · read-only snapshot</caption><thead><tr><th scope="col">{kind==='agents'?'Agent':'File ID'}</th><th scope="col">{kind==='agents'?'State':'Processing status'}</th><th scope="col">Access information</th></tr></thead><tbody>{result.items.map(item=><tr key={item.id}><th scope="row">{item.name??item.id}{item.configured?' · configured':''}</th><td>{(kind==='agents'?item.state??'unknown':item.status??'unknown').replaceAll('_',' ').replace(/^./,letter=>letter.toUpperCase())}</td><td>{kind==='agents'?'Metadata observed; invocation not verified':'Current metadata only; original file unchanged'}</td></tr>)}</tbody></table></AdminTableRegion>}<nav className="pagination-pages" aria-label={`${title} pagination`}><button type="button" className="subtle" disabled={active.page===0} onClick={()=>void read(active.page-1)}>Previous</button>{active.cursors.map((_,index)=><button type="button" key={index} className="subtle" aria-label={`${title} page ${index+1}`} aria-current={index===active.page?'page':undefined} onClick={()=>void read(index)}>{index+1}</button>)}<button type="button" className="subtle" disabled={!result.has_more||!result.next_cursor} onClick={()=>{if(result.next_cursor)void read(active.page+1,active.size,[...active.cursors.slice(0,active.page+1),result.next_cursor])}}>Next</button></nav></>}
  </section>;
}
