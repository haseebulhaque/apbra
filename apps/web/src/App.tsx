import React, {useState, useEffect, useRef, useCallback} from 'react';
import {createExecutionTrace} from './execution';
import {GovernancePanel} from './GovernancePanel';
import {runValidationAttempt, failureCase, type Validation, type ValidationAttempt} from './validation';
import {generatePowerBI, type Candidate} from './powerbi';
import {zipFiles} from './archive';
import {createDesignPlan, serializeDesignPlan, type DesignPlan} from './designPlan';
import {retrieveCuratedKnowledge, type CuratedKnowledge} from './knowledge';
import {assessRequestGuardrail} from './guardrail';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import {unavailableStages, type Answers} from './workflow';

import {assessRequirements, confirmRequirements, type RequirementsSnapshot} from './requirements';

export function App({initialPrompt=request.original_text}:{initialPrompt?:string}={}) {
  const [trace]=useState(createExecutionTrace);
  const [,setTraceRevision]=useState(0);
  const notify=useCallback(()=>setTraceRevision(n=>n+1),[]);
  function observed<T,>(stage:string,work:()=>T){try{return trace.sync(stage,work);}finally{notify();}}
  const [prompt, setPrompt] = useState(initialPrompt);
  const [answers, setAnswers] = useState<Answers>({});
  const [snapshot, setSnapshot] = useState<RequirementsSnapshot | null>(null);
  const [knowledge,setKnowledge]=useState<CuratedKnowledge|null>(null);
  const [plan, setPlan] = useState<DesignPlan | null>(null);
  const [candidate,setCandidate]=useState<Candidate|null>(null);
  const [,setGovernanceState]=useState('NOT_RUN');
  const [validation,setValidation]=useState<Validation|null>(null);
  const [history,setHistory]=useState<ValidationAttempt[]>([]);
  const [validating,setValidating]=useState(false),[validationError,setValidationError]=useState('');
  const epoch=useRef(0);
  async function runValidation(failure:boolean){
    if(!candidate)return;const current=epoch.current;
    const token=trace.start(failure?'DECLARED_FAILURE_VALIDATION':'SOURCE_VALIDATION');notify();
    setValidating(true);setValidationError('');
    const attempt=await runValidationAttempt(candidate,failure);
    trace.finish(token,attempt,attempt.outcome==='INCOMPLETE'?'VALIDATION_INCOMPLETE':undefined);notify();
    setHistory(h=>[...h,attempt]);
    if(epoch.current===current){setValidation(attempt.result);setValidationError(attempt.error??'');setValidating(false);}
  }
  const [archiveUrl,setArchiveUrl]=useState<string|null>(null);
  useEffect(()=>{if(!candidate){setArchiveUrl(null);return;}const url=URL.createObjectURL(new Blob([zipFiles(candidate.files)],{type:'application/zip'}));setArchiveUrl(url);return()=>URL.revokeObjectURL(url);},[candidate]);
  function invalidate() { if(snapshot||knowledge||plan||candidate){trace.invalidate('Requirements input changed');notify();} setSnapshot(null); setKnowledge(null); setPlan(null); setCandidate(null); setValidation(null); setValidating(false); setValidationError(''); epoch.current++; }
  const submission = {original_request: prompt, original_schema: schema, answers};
  const guardrail = assessRequestGuardrail(prompt);
  const assessment = guardrail.status === 'ALLOW' ? assessRequirements(submission) : {status:'UNSUPPORTED' as const,issues:[guardrail.reason]};
  const ready = guardrail.status === 'ALLOW' && assessment.status === 'READY_TO_CONFIRM';
  const requestStatus = guardrail.status === 'ALLOW' ? (snapshot ? 'CONFIRMED' : assessment.status) : guardrail.status.replaceAll('_',' ');
  const stageStatus=(name:string)=>name==='Requirement'
    ? (guardrail.status==='ALLOW'?'CAPTURED':requestStatus)
    : name==='Clarification' ? (guardrail.status!=='ALLOW'?'NOT_RUN':snapshot?'CONFIRMED':assessment.status==='AWAITING_CLARIFICATION'?'REQUIRED':'READY')
    : name==='Governed Knowledge' ? (knowledge?'GROUNDED':'NOT_RUN')
    : name==='DesignPlan' ? (plan?'CREATED':'NOT_RUN')
    : name==='Generation' ? (candidate?'READY':'NOT_RUN')
    : name==='Validation' ? (validation?.status??'NOT_RUN')
    : 'NOT_RUN';
  function editAnswer(id: string, value: string) { invalidate(); setAnswers({...answers, [id]:value}); }
  return <main>
    <header><span className="eyebrow">APBRA / ELVTR CAPSTONE</span><h1>Sales Performance report architect</h1><p>Turn a report requirement into a governed, structured Power BI design and validated candidate.</p></header>
    <details><summary>Prototype limitations</summary><p>This is a local deterministic AI architecture demonstration with no backend or live model provider. It supports one bounded Sales Performance scenario and two explicit guardrail examples. The sample PBIP has separate human Desktop evidence; this browser session does not rerun Power BI.</p></details>
    <div className="layout"><section aria-labelledby="request-heading"><h2 id="request-heading">01 · Define the report</h2>
      <label htmlFor="scenario">Synthetic scenario</label><select id="scenario" value="sales-v1" onChange={() => {}}><option value="sales-v1">Sales performance · APBRA-90 v1.0.0</option></select>
      <details><summary>Inspect the synthetic schema</summary><pre>{JSON.stringify(schema, null, 2)}</pre></details>
      <label htmlFor="prompt">Report request</label><textarea id="prompt" rows={7} maxLength={4000} value={prompt} onChange={e => {setPrompt(e.target.value); invalidate();}}/>
      {guardrail.status !== 'ALLOW' && <aside className="notice" role="alert"><strong>{requestStatus}</strong><p>{guardrail.reason}</p><p><strong>No Power BI report has been generated.</strong> This is a terminal demo state.</p><details><summary>View technical evidence</summary><pre>{JSON.stringify(guardrail,null,2)}</pre><p>No reviewer workflow or notification is implemented.</p></details><a download="SalesPerformance.guardrail-evidence.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(guardrail,null,2))}>Save guardrail evidence JSON</a></aside>}
      <h2>02 · Clarify the requirement</h2><p>Resolve the material sales, comparison and security decisions before creating the design.</p>
      {request.clarifications.map(c => <div className="question" key={c.id}><label htmlFor={c.id}>{c.topic}</label><textarea id={c.id} rows={3} maxLength={2000} value={answers[c.id] ?? ''} onChange={e => editAnswer(c.id, e.target.value)}/><button className="secondary" onClick={() => editAnswer(c.id,c.golden_answer)}>Use synthetic golden answer</button></div>)}
      <button disabled={!ready || !!snapshot} onClick={() => setSnapshot(observed('REQUIREMENTS_CONFIRMED',()=>confirmRequirements(submission, true)))}>Confirm requirements and create snapshot</button>
      <p role="status">{snapshot ? 'RequirementsSnapshot confirmed. Editing inputs invalidates it.' : requestStatus}</p>
      {guardrail.status === 'ALLOW' && assessment.issues.length > 0 && <ul>{assessment.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
      {snapshot && <details><summary>View technical evidence · RequirementsSnapshot</summary><pre>{JSON.stringify(snapshot, null, 2)}</pre></details>}
      <h2>03 · Ground and structure the design</h2><p>Use the controlled local standards pack to create the structured DesignPlan.</p>
      <button disabled={!snapshot || !!plan} onClick={() => {const evidence=observed('CURATED_EVIDENCE',()=>retrieveCuratedKnowledge('sales-v1'));setKnowledge(evidence);setPlan(observed('DESIGN_PLAN',()=>createDesignPlan(snapshot!,evidence)));}}>Retrieve governed standards and create DesignPlan</button>
      {knowledge&&<><aside className="notice"><strong>Grounded using {knowledge.retrievedCount} governed corporate standards</strong><p>{knowledge.rules.slice(0,3).map(rule=>rule.citation).join(' · ')}</p></aside><details><summary>View full governed knowledge evidence</summary><p>Pack <code>{knowledge.packId}</code> · version {knowledge.fixtureVersion} · local source <code>{knowledge.sourcePath}</code></p><ul>{knowledge.rules.map(rule=><li key={rule.evidenceId}><strong>{rule.evidenceId}</strong> · {rule.text}<br/><code>{rule.citation}</code></li>)}</ul></details></>}
      {plan && <><p role="status">DesignPlan created and linked to requirements and all {plan.provenance.citations.length} controlled-source citations. Save the JSON to retain it after refresh.</p>
        <details><summary>View technical evidence · DesignPlan</summary><pre>{serializeDesignPlan(plan)}</pre></details>
        <a download="SalesPerformance.DesignPlan.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(serializeDesignPlan(plan))}>Save DesignPlan JSON</a></>}
      <h2>04 · Generate the project</h2><p>Render the validated DesignPlan into a synthetic Power BI candidate. This download is source inspection, not an approved release.</p>
      <button disabled={!plan||!!candidate} onClick={()=>setCandidate(observed('POWER_BI_GENERATION',()=>generatePowerBI(plan)))}>Generate Power BI candidate</button>
      {candidate&&<><aside className="notice" role="status"><strong>POWER BI CANDIDATE READY</strong><p>{Object.keys(candidate.files).length} generated files are ready to download and validate.</p></aside>
        <details><summary>View technical evidence · generated project files</summary>{Object.entries(candidate.files).map(([path,content])=><details key={path}><summary>{path}</summary><pre>{content}</pre></details>)}</details>
        {archiveUrl&&<a href={archiveUrl} download="SalesPerformance.candidate.zip">Save candidate ZIP · not a release</a>}</>}
      <h2>05 · Validate the candidate</h2><p>Checks the exact reviewed golden source profile and structural rules. This is not Desktop or DAX runtime validation.</p>
      <button disabled={!candidate||validating} onClick={()=>void runValidation(false)}>Validate golden candidate</button>
      <button className="secondary" disabled={!candidate||validating} onClick={()=>void runValidation(true)}>Run declared missing-relationship failure</button>
      {validating&&<p role="status">Validation running · no result yet</p>}{validationError&&<p role="alert">{validationError}</p>}
      {validation&&<><p role="status">Source validation {validation.status} · {validation.nextAction}</p><details><summary>View technical evidence · validation result</summary><pre>{JSON.stringify(validation,null,2)}</pre></details></>}
      {history.length>0&&<><p>{history.length} validation attempts retained, including failures. Automatic repair is not implemented.</p><a download="SalesPerformance.validation-evidence.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify({failureCase,attempts:history},null,2))}>Save validation evidence JSON</a></>}
    </section><section aria-labelledby="progress-heading"><h2 id="progress-heading">Workflow</h2><p>Requirement → Clarification → Governed Knowledge → DesignPlan → Generation → Validation</p>
      <ol className="stages">{unavailableStages().map(s => <li key={s.name}><span>{s.name}</span><strong>{stageStatus(s.name)}</strong></li>)}</ol>
      <h2>Sample output</h2><p>The current SalesPerformance PBIP has separate successful human validation in Windows Power BI Desktop.</p><button disabled>Production release · unavailable</button>
      <p className="small">No production identity, tenant authorization, Power BI Desktop compatibility, DAX correctness or RLS runtime verification is claimed.</p>
    </section></div><GovernancePanel trace={trace} notify={notify} candidate={validation?.status==='PASS'?candidate:null} onState={setGovernanceState}/><section aria-labelledby="execution-heading"><h2 id="execution-heading">07 · Retain execution evidence</h2><p>Execution {trace.id}. Save the complete record before refreshing. Timings measure local processing only; identities are simulated and external runtime remains untested by this browser session.</p>{trace.export().steps.length>0&&<a download="SalesPerformance.execution-evidence.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(trace.export(),null,2))}>Save complete execution evidence JSON</a>}</section><section aria-labelledby="boundaries-heading"><h2 id="boundaries-heading">Capability boundaries</h2><p><strong>Implemented locally:</strong> bounded clarification, controlled local retrieval with citations, structured requirements and DesignPlan, guardrail decisions, source validation, and Power BI package generation. The current sample PBIP has separate successful human Desktop evidence.</p><p><strong>Prototype:</strong> fictional customer knowledge and the deliberately limited Power BI feature set.</p><p><strong>Not implemented:</strong> production Azure deployment, tenant publishing, enterprise SSO or multi-tenancy, reviewer workflow, notifications, automated production deployment, and dynamic handover-document generation.</p></section><footer>APBRA Capstone · Local AI architecture demonstration</footer>
  </main>;
}
