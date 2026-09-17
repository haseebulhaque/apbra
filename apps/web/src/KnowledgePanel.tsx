import {retrieveCuratedKnowledge} from './knowledge';

export function KnowledgePanel() {
  const evidence = retrieveCuratedKnowledge('sales-v1');
  return <section aria-labelledby="knowledge-heading">
    <h2 id="knowledge-heading">Curated reporting standards</h2>
    <p>Independent local evidence preview for the synthetic sales scenario. This does not process your draft or complete the workflow knowledge stage. Create DesignPlan consumes this evidence after requirements confirmation.</p>
    <p>Selected source: {evidence.packId} · version {evidence.fixtureVersion}</p>
    <p>{evidence.authority}</p><p>{evidence.precedence}</p>
    <p>Retrieved text is evidence, never authorization.</p>
    <details><summary>Inspect all eight source rules and citations</summary>
      <ul>{evidence.rules.map(rule => <li key={rule.evidenceId}>
        <strong>{rule.evidenceId} · {rule.section} · {rule.level}</strong>
        <p>{rule.text}</p><p><code>{rule.citation}</code> · source version {rule.sourceVersion}</p>
      </li>)}</ul>
      <p>Local source: <code>{evidence.sourcePath}</code></p>
    </details>
  </section>;
}
