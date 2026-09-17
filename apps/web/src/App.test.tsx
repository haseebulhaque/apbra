import {it, expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {App} from './App';
it('renders labelled input and honest unavailable release state', () => {
  const html=renderToStaticMarkup(<App/>);
  expect(html).toContain('for="prompt"');
  for(const id of ['sales-definition','yoy-coverage','region-security']) expect(html).toContain(`for="${id}"`);
  expect(html.match(/NOT_RUN/g)).toHaveLength(6);
  expect(html).toContain('Use the isolated demo governance panel for eligibility and package downloads.');
  expect(html).toContain('disabled="">Production release');
  expect(html).toContain('controlled local retrieval with citations');
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
});
