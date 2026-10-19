import React,{useEffect,useRef,useState} from 'react';
import {ApiError,nativeFilesApi,requestOutputsApi,type NativeGeneratedFile,type RequestOutput} from './api';

export function RequestOutputs({caseId,contextVersion,csrfToken,receiptId,unsavedGoal=false,onError}:{caseId:string;contextVersion:number;csrfToken:string;receiptId?:string;unsavedGoal?:boolean;onError:(error:unknown)=>void}){
 const [file,setFile]=useState<File|null>(null),[outputs,setOutputs]=useState<RequestOutput[]>([]),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[more,setMore]=useState<string|null>(null);
 const [nativeFiles,setNativeFiles]=useState<NativeGeneratedFile[]|null>(null),[retrieval,setRetrieval]=useState(false);
 const binding=JSON.stringify([caseId,contextVersion,csrfToken,receiptId,unsavedGoal]),current=useRef(binding);current.current=binding;
 const epoch=useRef(0),input=useRef<HTMLInputElement>(null),commands=useRef<Record<string,string|undefined>>({});
 useEffect(()=>{epoch.current++;commands.current={};setFile(null);if(input.current)input.current.value='';setOutputs([]);setBusy(false);setMessage('');setMore(null);setNativeFiles(null);setRetrieval(false);return()=>{epoch.current++}},[binding]);
 async function act(kind:'list'|'more'|'files'|'file'|'native'|'attachment',index?:number){
  if(busy||(kind!=='list'&&kind!=='more'&&kind!=='files'&&unsavedGoal))return;
  const at=++epoch.current,key=current.current;setBusy(true);setMessage('');
  try{
   if(kind==='files'){
    if(!receiptId)return;const result=await nativeFilesApi.list(caseId,receiptId);
    if(at!==epoch.current||key!==current.current)return;setNativeFiles(result.items);setRetrieval(result.retrieval_configured);setMessage(result.items.length?'Generated file references loaded. Fetching a file makes a read-only request through the configured project.':'No supported generated file references were found. The original answer is retained; you can import an actual generated file.');
   }else if(kind==='list'||kind==='more'){
    const result=await requestOutputsApi.list(caseId,kind==='more'?more??undefined:undefined);
    if(at!==epoch.current||key!==current.current)return;
    setOutputs(previous=>kind==='more'?[...previous,...result.items.filter(row=>!previous.some(old=>old.id===row.id))]:result.items);setMore(result.next_cursor??null);setMessage(result.items.length?'Saved output history loaded.':'No saved model outputs.');
   }else{
    if(kind==='file'&&!file||(kind==='native'||kind==='attachment')&&!receiptId||kind==='attachment'&&(index===undefined||!retrieval||!nativeFiles?.some(f=>f.index===index&&f.savable)))return;
    const commandSlot=kind==='attachment'?'attachment:'+index:kind;const command=commands.current[commandSlot]??crypto.randomUUID();commands.current[commandSlot]=command;
    const result=kind==='attachment'?await nativeFilesApi.save(caseId,receiptId!,index!,contextVersion,command,csrfToken):kind==='file'?await requestOutputsApi.upload(caseId,file!,contextVersion,command,csrfToken):await requestOutputsApi.saveNative(caseId,receiptId!,contextVersion,command,csrfToken);
    if(at!==epoch.current||key!==current.current)return;
    setOutputs(previous=>[result.output,...previous.filter(row=>row.id!==result.output.id)]);
    setMessage('Output saved. Download it below. Content verification has not been run.');
   }
  }catch(error){if(at===epoch.current&&key===current.current){setMessage(error instanceof ApiError&&error.status>=400&&error.status<500?error.message:'Output could not be loaded or saving could not be confirmed. You can explicitly retry the same save.');if(error instanceof ApiError&&[401,403,404].includes(error.status))onError(error)}}
  finally{if(at===epoch.current&&key===current.current)setBusy(false)}
 }
 return <section aria-label="Model output files" aria-busy={busy}><h3>Model output files</h3><p>Save a generated file against this saved request and download it unchanged. ZIP files remain unopened. APBRA has not verified report completeness, correctness or Power BI compatibility.</p>{unsavedGoal&&<p>Save your edited goal before attaching an output.</p>}<label>Generated output file <input ref={input} type="file" disabled={busy||unsavedGoal} onChange={event=>{setFile(event.target.files?.[0]??null);commands.current.file=undefined;setMessage('')}}/></label><button type="button" disabled={busy||unsavedGoal||!file} onClick={()=>void act('file')}>Save generated file</button>{receiptId&&<><p>Save the selected answer as a file. A supplied file tree is packaged as a ZIP; a single assistant text is retained unchanged. Multiple text parts use a JSON array that preserves their boundaries.</p><button type="button" disabled={busy||unsavedGoal} onClick={()=>void act('native')}>Save selected answer output</button><button type="button" disabled={busy} onClick={()=>void act('files')}>Show generated files</button>{nativeFiles&&<><p>{retrieval?'Fetch and save keeps original file bytes. It does not run analysis, design or report checks.':'The current server has no connected project file retrieval capability.'}</p><ul>{nativeFiles.map(file=><li key={file.index}>{file.filename}<button type="button" disabled={busy||unsavedGoal||!retrieval||!file.savable} onClick={()=>void act('attachment',file.index)}>Fetch and save {file.filename}</button>{!file.savable&&<p>The supplied filename cannot be safely used for downloading. The original response is retained.</p>}</li>)}</ul></>}</>}<button type="button" disabled={busy} onClick={()=>void act('list')}>Show saved output files</button>{message&&<p role="status">{message}</p>}{more&&<button type="button" disabled={busy} onClick={()=>void act('more')}>Show older output files</button>}<ul>{outputs.map(output=><li key={output.id}><a href={requestOutputsApi.download(caseId,output.id)} download>{output.filename}</a><p>{output.bytes} bytes · request context {output.context_version} · content verification not run</p><details><summary>File integrity</summary><p>SHA-256 {output.sha256}</p></details></li>)}</ul></section>;
}
