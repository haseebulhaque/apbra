import {it, expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {App,sampleGeneratorEligible} from './App';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
it('renders labelled input and honest unavailable release state', () => {
  const html=renderToStaticMarkup(<App/>);
  expect(html).toContain('for="prompt"');
  expect(html).toContain('Interpret requirement with GPT-4.1');
  expect(html).toContain('Questions below are generated at runtime');
  for(const id of ['sales-definition','yoy-coverage','region-security']) expect(html).not.toContain(`for="${id}"`);
  expect(html).toContain('Prototype limitations');
  expect(html).toContain('Requirement → Clarification → Governed Knowledge → DesignPlan → Generation → Validation');
  for(const stage of ['Requirement','Clarification','Governed Knowledge','DesignPlan','Generation','Validation']) expect(html).toContain(stage);
  expect(html).toContain('disabled="">Production release');
  expect(html).toContain('controlled local retrieval with real embeddings and citations');
  expect(html).toContain('reviewer workflow');
  expect(html).not.toContain('href=');
});
it('renders the excessive-visual request as a terminal human-review state',()=>{
  const html=renderToStaticMarkup(<App initialPrompt="Create an executive sales report with 250 visuals on a single report page."/>);
  expect(html).toContain('HUMAN REVIEW REQUIRED');
  expect(html).toContain('No Power BI report has been generated');
  expect(html).toContain('EXCESSIVE_SINGLE_PAGE_VISUALS');
  expect(html).toContain('local-policy:capstone-power-bi-demo-boundaries/GUARD-001');
  expect(html).toContain('download="SalesPerformance.guardrail-evidence.json"');
  expect(html).not.toContain('UNSUPPORTED');
});
it('renders the unrelated request as a terminal out-of-scope state',()=>{
  const html=renderToStaticMarkup(<App initialPrompt="Write a marketing campaign for our new product."/>);
  expect(html).toContain('OUT OF SCOPE');
  expect(html).toContain('No Power BI report has been generated');
  expect(html).not.toContain('UNSUPPORTED');
});
it('enables the preserved sample compiler only for explicit APBRA-90 demo decisions',()=>{
  expect(sampleGeneratorEligible(request.original_text,{},true)).toBe(true);
  expect(sampleGeneratorEligible('another supported Power BI request',{},true)).toBe(false);
  expect(sampleGeneratorEligible(request.original_text,Object.fromEntries(request.clarifications.map(c=>[c.id,c.golden_answer])),false)).toBe(true);
  expect(sampleGeneratorEligible(request.original_text,{one:'partial'},false)).toBe(false);
});
