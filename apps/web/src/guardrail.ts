import policy from './guardrailPolicy.json';

export type GuardrailDecision = {
  status: 'ALLOW' | 'HUMAN_REVIEW_REQUIRED' | 'OUT_OF_SCOPE';
  terminal: boolean;
  code: string;
  reason: string;
  generation: 'AVAILABLE_AFTER_REQUIREMENTS' | 'BLOCKED_NOT_RUN';
  evidence: Array<{evidenceId: string; citation: string; sourcePath: string}>;
};

const allowed = (): GuardrailDecision => ({
  status: 'ALLOW', terminal: false, code: 'BOUNDED_POWER_BI_REQUEST',
  reason: 'Request remains within the bounded Sales Performance demonstration.',
  generation: 'AVAILABLE_AFTER_REQUIREMENTS', evidence: [],
});

/** Deterministic Capstone policy boundary. It demonstrates where an AI-facing
 * workflow stops; it is not a general-purpose content classifier or reviewer workflow. */
export function assessRequestGuardrail(prompt: string): GuardrailDecision {
  const excessiveVisuals = policy.rules[0];
  const visualCount = [...prompt.matchAll(/\b(\d{1,4})\s+(?:report\s+)?visuals?\b/gi)]
    .map(match => Number(match[1])).find(count => count > excessiveVisuals.max_visuals_per_page!);
  if (visualCount !== undefined) {
    return {
      status: 'HUMAN_REVIEW_REQUIRED', terminal: true, code: 'EXCESSIVE_SINGLE_PAGE_VISUALS',
      reason: `The request asks for ${visualCount} visuals on one page, beyond the bounded, readable report-design pattern supported by this demo.`,
      generation: 'BLOCKED_NOT_RUN',
      evidence: [{evidenceId: excessiveVisuals.id, citation: excessiveVisuals.citation, sourcePath: 'apps/web/src/guardrailPolicy.json'}],
    };
  }
  if (/\b(marketing campaign|email campaign|social media campaign|advertising copy)\b/i.test(prompt)
      && !/\b(power\s*bi|report|dashboard|analytics|business intelligence)\b/i.test(prompt)) {
    const scopeRule=policy.rules[1];
    return {
      status: 'OUT_OF_SCOPE', terminal: true, code: 'NOT_A_POWER_BI_REQUEST',
      reason: 'This request is outside the bounded Power BI report-generation scope.',
      generation: 'BLOCKED_NOT_RUN',
      evidence: [{evidenceId:scopeRule.id,citation:scopeRule.citation,sourcePath:'apps/web/src/guardrailPolicy.json'}],
    };
  }
  return allowed();
}
