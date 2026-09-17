import React, {useState, useEffect, useRef} from 'react';
import {runValidationAttempt, failureCase, type Validation, type ValidationAttempt} from './validation';
import {generatePowerBI, type Candidate} from './powerbi';
import {zipFiles} from './archive';
import {createDesignPlan, serializeDesignPlan, type DesignPlan} from './designPlan';
import {retrieveCuratedKnowledge} from './knowledge';
import {KnowledgePanel} from './KnowledgePanel';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import {unavailableStages, type Answers} from './workflow';

import {assessRequirements, confirmRequirements, type RequirementsSnapshot} from './requirements';

export function App() {
  const [prompt, setPrompt] = useState(request.original_text);
  const [answers, setAnswers] = useState<Answers>({});
  const [snapshot, setSnapshot] = useState<RequirementsSnapshot | null>(null);
  const [plan, setPlan] = useState<DesignPlan | null>(null);
  const [candidate,setCandidate]=useState<Candidate|null>(null);
  const [validation,setValidation]=useState<Validation|null>(null);
  const [history,setHistory]=useState<ValidationAttempt[]>([]);
  const [validating,setValidating]=useState(false),[validationError,setValidationError]=useState('');
  const epoch=useRef(0);
  async function runValidation(failure:boolean){
    if(!candidate)return;const current=epoch.current;
    setValidating(true);setValidationError('');
    const attempt=await runValidationAttempt(candidate,failure);
    setHistory(h=>[...h,attempt]);
    if(epoch.current===current){setValidation(attempt.result);setValidationError(attempt.error??'');setValidating(false);}
  }
  const [archiveUrl,setArchiveUrl]=useState<string|null>(null);
  useEffect(()=>{if(!candidate){setArchiveUrl(null);return;}const url=URL.createObjectURL(new Blob([zipFiles(candidate.files)],{type:'application/zip'}));setArchiveUrl(url);return()=>URL.revokeObjectURL(url);},[candidate]);
  function invalidate() { setSnapshot(null); setPlan(null); setCandidate(null); setValidation(null); setValidating(false); setValidationError(''); epoch.current++; }
  const submission = {original_request: prompt, original_schema: schema, answers};
  const assessment = assessRequirements(submission);
  const ready = assessment.status === 'READY_TO_CONFIRM';
  function editAnswer(id: string, value: string) { invalidate(); setAnswers({...answers, [id]:value}); }
  return <main>
    <header><span className="eyebrow">APBRA / ELVTR CAPSTONE</span><h1>Your report starts here.</h1><p>Explore the synthetic sales scenario and prepare your request.</p></header>
    <aside className="notice">Local requester shell · No backend connected. Your inputs stay in browser memory. Synthetic project generation runs locally. Power BI runtime evaluation and governed release are not available yet.</aside>
    <div className="layout"><section aria-labelledby="request-heading"><h2 id="request-heading">01 · Define the report</h2>
      <label htmlFor="scenario">Synthetic scenario</label><select id="scenario" value="sales-v1" onChange={() => {}}><option value="sales-v1">Sales performance · APBRA-90 v1.0.0</option></select>
      <details><summary>Inspect the synthetic schema</summary><pre>{JSON.stringify(schema, null, 2)}</pre></details>
      <label htmlFor="prompt">Report request</label><textarea id="prompt" rows={7} maxLength={4000} value={prompt} onChange={e => {setPrompt(e.target.value); invalidate();}}/>
      <h2>02 · Clarify the request</h2><p>These are predefined golden-scenario topics, not AI-generated questions.</p>
      {request.clarifications.map(c => <div className="question" key={c.id}><label htmlFor={c.id}>{c.topic}</label><textarea id={c.id} rows={3} maxLength={2000} value={answers[c.id] ?? ''} onChange={e => editAnswer(c.id, e.target.value)}/><button className="secondary" onClick={() => editAnswer(c.id,c.golden_answer)}>Use synthetic golden answer</button></div>)}
      <button disabled={!ready || !!snapshot} onClick={() => setSnapshot(confirmRequirements(submission, true))}>Confirm requirements and create snapshot</button>
      <p role="status">{snapshot ? 'RequirementsSnapshot confirmed in browser memory. Editing inputs invalidates it; refresh clears it.' : assessment.status}</p>
      {assessment.issues.length > 0 && <ul>{assessment.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
      {snapshot && <details open><summary>Inspect confirmed RequirementsSnapshot</summary><pre>{JSON.stringify(snapshot, null, 2)}</pre></details>}
      <h2>03 · Create the design</h2><p>Deterministic golden-scenario planning consumes confirmed requirements and current curated evidence. No AI interpretation is claimed.</p>
      <button disabled={!snapshot || !!plan} onClick={() => setPlan(createDesignPlan(snapshot!, retrieveCuratedKnowledge('sales-v1')))}>Create DesignPlan</button>
      {plan && <><p role="status">DesignPlan created and linked to requirements and all eight citations. Save the JSON to retain it after refresh.</p>
        <details><summary>Inspect DesignPlan and source bindings</summary><pre>{serializeDesignPlan(plan)}</pre></details>
        <a download="SalesPerformance.DesignPlan.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(serializeDesignPlan(plan))}>Save DesignPlan JSON</a></>}
      <h2>04 · Generate the project</h2><p>Render the validated DesignPlan into a synthetic Power BI candidate. This download is source inspection, not an approved release.</p>
      <button disabled={!plan||!!candidate} onClick={()=>setCandidate(generatePowerBI(plan))}>Generate Power BI candidate</button>
      {candidate&&<><p role="status">Candidate generated · {Object.keys(candidate.files).length} files · Desktop, DAX and RLS runtime NOT_RUN.</p>
        <details><summary>Inspect generated project files</summary>{Object.entries(candidate.files).map(([path,content])=><details key={path}><summary>{path}</summary><pre>{content}</pre></details>)}</details>
        {archiveUrl&&<a href={archiveUrl} download="SalesPerformance.candidate.zip">Save candidate ZIP · not a release</a>}</>}
      <h2>05 · Validate the candidate</h2><p>Checks the exact reviewed golden source profile and structural rules. This is not Desktop or DAX runtime validation.</p>
      <button disabled={!candidate||validating} onClick={()=>void runValidation(false)}>Validate golden candidate</button>
      <button className="secondary" disabled={!candidate||validating} onClick={()=>void runValidation(true)}>Run declared missing-relationship failure</button>
      {validating&&<p role="status">Validation running · no result yet</p>}{validationError&&<p role="alert">{validationError}</p>}
      {validation&&<><p role="status">Source validation {validation.status} · {validation.nextAction}</p><pre>{JSON.stringify(validation,null,2)}</pre></>}
      {history.length>0&&<><p>{history.length} validation attempts retained, including failures. Automatic repair is not implemented.</p><a download="SalesPerformance.validation-evidence.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify({failureCase,attempts:history},null,2))}>Save validation evidence JSON</a></>}
    </section><section aria-labelledby="progress-heading"><h2 id="progress-heading">Workflow progress</h2><p>Requirements and DesignPlan use deterministic golden-fixture processing. Generation renders source files; validation checks source files only; release has not run.</p>
      <ol className="stages">{unavailableStages().map(s => <li key={s.name}><span>{s.name}</span><strong>{s.name === 'RequirementsSnapshot' && snapshot ? 'CONFIRMED' : plan && s.name === 'Knowledge & citations' ? 'CONSUMED' : plan && s.name === 'DesignPlan' ? 'CREATED' : candidate && s.name === 'Power BI generation' ? 'GENERATED' : validation && s.name === 'Deterministic validation' ? validation.status : s.status}</strong></li>)}</ol>
      <h2>Release artefacts</h2><p>No approved release package exists.</p><button disabled>Download release package · unavailable</button>
      <p className="small">No production identity, tenant authorization, Power BI Desktop compatibility, DAX correctness or RLS runtime verification is claimed.</p>
    </section></div><KnowledgePanel/><footer>APBRA-134 · Local Capstone deterministic validation</footer>
  </main>;
}
