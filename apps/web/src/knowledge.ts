import standards from '../../../tests/bootstrap/fixtures/sales-v1/standards.json';

/** Local curated evidence only. No prompt, uploaded source, or tenant claim selects a pack. */
export function retrieveCuratedKnowledge(scenario: string) {
  if (scenario !== 'sales-v1') throw new Error('Unsupported curated scenario');
  return {
    kind: 'CURATED_FIXTURE_EVIDENCE' as const,
    scenario,
    packId: standards.pack_id,
    fixtureVersion: standards.fixture_version,
    customerId: standards.customer_id,
    synthetic: true as const,
    sourcePath: 'tests/bootstrap/fixtures/sales-v1/standards.json',
    authority: standards.authority,
    precedence: standards.precedence,
    authorization: 'NONE' as const,
    retrievalK: standards.rules.length,
    retrievedCount: standards.rules.length,
    orderedEvidenceIds: standards.rules.map(rule => rule.evidence_id),
    rules: standards.rules.map(rule => ({
      evidenceId: rule.evidence_id,
      sourceVersion: rule.source_version,
      section: rule.section,
      level: rule.level,
      text: rule.text,
      citation: rule.citation,
    })),
  };
}

export type CuratedKnowledge = ReturnType<typeof retrieveCuratedKnowledge>;

/** Canonical citation membership and mandatory coverage only; not consumed DesignPlan/version integrity. */
export function verifyCuratedCitations(scenario: string, citations: readonly string[]) {
  const evidence = retrieveCuratedKnowledge(scenario);
  const known = new Set(evidence.rules.map(rule => rule.citation));
  const supplied = new Set(citations);
  const unknown = [...supplied].filter(citation => !known.has(citation));
  const missing = evidence.rules.filter(rule => rule.level === 'mandatory' && !supplied.has(rule.citation))
    .map(rule => rule.citation);
  return {passed: unknown.length === 0 && missing.length === 0, missing, unknown};
}
