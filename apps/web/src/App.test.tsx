import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {App} from './App';
import {ReviewPanel,deploymentGuideEligible} from './EnterpriseApp';
import type {GuardrailDecision} from './guardrail';
import type {ReportDesign} from './foundry';
import type {CandidateValidation} from './genericPowerBI';

it('renders distinct business and administration navigation',()=>{
  const html=renderToStaticMarkup(<App/>);
  for(const label of ['Create Report','My Runs','Tenant Settings','AI &amp; Models','Governed Knowledge','Branding &amp; Report Standards','Guardrails &amp; Generation'])expect(html).toContain(label);
  expect(html).toContain('Create Power BI Report');expect(html).toContain('Upload Excel');expect(html).toContain('Upload CSV');expect(html).toContain('Analyse Requirement');
});
it('renders a structured complexity policy outcome as human review with generation not started',()=>{
  const decision:GuardrailDecision={outcome:'HUMAN_REVIEW_REQUIRED',generation:'NOT_STARTED',evaluations:[{ruleId:'COMPLEXITY-001',category:'complexity',severity:'error',result:'HUMAN_REVIEW_REQUIRED',reason:'The structured design exceeds tenant visual limits.',recommendedAction:'Reduce scope or obtain verification.'}]};const html=renderToStaticMarkup(<ReviewPanel decision={decision}/>);expect(html).toContain('Human Review Required');expect(html).toContain('Generation status:');expect(html).toContain('Not started');expect(html).toContain('COMPLEXITY-001');
});
it('renders a typed out-of-scope outcome without starting generation',()=>{
  const decision:GuardrailDecision={outcome:'OUT_OF_SCOPE',generation:'NOT_STARTED',evaluations:[{ruleId:'SCOPE-001',category:'scope',severity:'error',result:'OUT_OF_SCOPE',reason:'The structured interpretation is outside Power BI reporting.',recommendedAction:'Return to the requester.'}]};const html=renderToStaticMarkup(<ReviewPanel decision={decision}/>);expect(html).toContain('Outside report-generation scope');expect(html).toContain('Not started');expect(html).toContain('SCOPE-001');
});
it('keeps course fixtures and built-in demo controls out of the business UX',()=>{
  const html=renderToStaticMarkup(<App/>);for(const term of ['APBRA-90','ELVTR','golden answer','Try a sample','Scenario','NOT_RUN'])expect(html).not.toContain(term);
});
it('offers the deployment guide only for a validated generated candidate',()=>{const candidate={kind:'PowerBICandidate',generatorVersion:'bounded-generic-pbip-1',projectName:'Report',files:{},runtime:{desktop:'NOT_RUN',dax:'NOT_RUN'},release:'NOT_ELIGIBLE'} as const;const design={artifact_kind:'ReportDesign'} as ReportDesign;const pass:CandidateValidation={status:'PASS',checks:[]};const fail:CandidateValidation={status:'FAIL',checks:[]};const available={outcome:'PASS',generation:'AVAILABLE',evaluations:[]} as GuardrailDecision;for(const decision of [{outcome:'BLOCKED',generation:'NOT_STARTED'},{outcome:'OUT_OF_SCOPE',generation:'NOT_STARTED'},{outcome:'HUMAN_REVIEW_REQUIRED',generation:'NOT_STARTED'}] as GuardrailDecision[])expect(deploymentGuideEligible(candidate,design,pass,decision)).toBe(false);expect(deploymentGuideEligible(candidate,design,fail,available)).toBe(false);expect(deploymentGuideEligible(null,design,pass,available)).toBe(false);expect(deploymentGuideEligible(candidate,design,pass,available)).toBe(true);});
