import React, {useState} from 'react';
import {KnowledgePanel} from './KnowledgePanel';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import {draftReady, unavailableStages, type Answers} from './workflow';

export function App() {
  const [prompt, setPrompt] = useState(request.original_text);
  const [answers, setAnswers] = useState<Answers>({});
  const [saved, setSaved] = useState(false);
  const ready = draftReady(prompt, request.clarifications.map(c => c.id), answers);
  function editAnswer(id: string, value: string) { setSaved(false); setAnswers({...answers, [id]:value}); }
  return <main>
    <header><span className="eyebrow">APBRA / ELVTR CAPSTONE</span><h1>Your report starts here.</h1><p>Explore the synthetic sales scenario and prepare your request.</p></header>
    <aside className="notice">Local requester shell · No backend connected. Your inputs stay in browser memory. Generated Power BI packages and evaluation results are not available yet.</aside>
    <div className="layout"><section aria-labelledby="request-heading"><h2 id="request-heading">01 · Define the report</h2>
      <label htmlFor="scenario">Synthetic scenario</label><select id="scenario" value="sales-v1" onChange={() => {}}><option value="sales-v1">Sales performance · APBRA-90 v1.0.0</option></select>
      <details><summary>Inspect the synthetic schema</summary><pre>{JSON.stringify(schema, null, 2)}</pre></details>
      <label htmlFor="prompt">Report request</label><textarea id="prompt" rows={7} maxLength={4000} value={prompt} onChange={e => {setPrompt(e.target.value); setSaved(false);}}/>
      <h2>02 · Clarify the request</h2><p>These are predefined golden-scenario topics, not AI-generated questions.</p>
      {request.clarifications.map(c => <div className="question" key={c.id}><label htmlFor={c.id}>{c.topic}</label><textarea id={c.id} rows={3} maxLength={2000} value={answers[c.id] ?? ''} onChange={e => editAnswer(c.id, e.target.value)}/><button className="secondary" onClick={() => editAnswer(c.id,c.golden_answer)}>Use synthetic golden answer</button></div>)}
      <button disabled={!ready} onClick={() => setSaved(true)}>Save draft in this browser</button>
      <p role="status">{saved ? 'Draft prepared in memory. Requirements processing is NOT_RUN; refresh clears this draft.' : 'Complete the request and all three answers to prepare your draft.'}</p>
    </section><section aria-labelledby="progress-heading"><h2 id="progress-heading">Workflow progress</h2><p>Every stage remains not run until its implementation is connected and executes.</p>
      <ol className="stages">{unavailableStages().map(s => <li key={s.name}><span>{s.name}</span><strong>{s.status}</strong></li>)}</ol>
      <h2>Release artefacts</h2><p>No generated candidate or release package exists.</p><button disabled>Download release package · unavailable</button>
      <p className="small">No production identity, tenant authorization, Power BI Desktop compatibility, DAX correctness or RLS runtime verification is claimed.</p>
    </section></div><KnowledgePanel/><footer>APBRA-129 · Local Capstone requester shell</footer>
  </main>;
}
