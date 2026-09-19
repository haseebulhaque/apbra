import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {App} from './App';
import {DataStructurePanel,GeneratedFiles,PolicyPanel,ReportDesignPanel,ReviewPanel,Summary,deploymentGuideEligible} from './EnterpriseApp';
import type {GuardrailDecision} from './guardrail';
import type {ReportDesign,RequirementInterpretation} from './foundry';
import type {CandidateValidation} from './genericPowerBI';

it('renders the enterprise shell, grouped navigation and six-stage workflow',()=>{
  const html=renderToStaticMarkup(<App/>);
  for(const label of ['Workspace','Create Report','My Runs','Administration','Tenant Settings','AI &amp; Models','Governed Knowledge','Branding &amp; Report Standards','Guardrails &amp; Generation'])expect(html).toContain(label);
  for(const stage of ['Requirement','Data','Clarify','Design','Validate','Generate'])expect(html).toContain(stage);
  expect(html).toContain('Create Power BI Report');expect(html).toContain('Upload your data structure');expect(html).toContain('Analyse requirement');
});

it('presents uploaded schema as a collapsed business-readable structure',()=>{
  const html=renderToStaticMarkup(<DataStructurePanel data={{kind:'REQUEST_DATA_STRUCTURE',fileName:'Operations.xlsx',format:'XLSX',parsedAt:'2026-09-19',relationships:[],tables:[{name:'Cases',sourceName:'Cases',rowCount:12,rows:[],columns:[{name:'CaseId',sourceName:'Case ID',type:'text',nullable:false,sampleValues:['C-1']}]}]}}/>);
  expect(html).toContain('View detected structure');expect(html).toContain('Data structure detected');expect(html).toContain('12 rows');expect(html).toContain('Case ID');expect(html).not.toContain('<pre>');
});

it('renders dynamic requirements and report design in business sections',()=>{
  const interpretation:RequirementInterpretation={request_kind:'POWER_BI_REPORT',objective:'Monitor service quality',businessQuestions:['Where are delays increasing?'],kpis:['Resolution time'],dimensions:['Team'],filters:['Priority'],audience:'Operations leaders',pages:['Overview'],assumptions:['Use local time'],ambiguities:[],clarifications:[]};
  const summary=renderToStaticMarkup(<Summary interpretation={interpretation} answers={{scope:'Include open cases'}}/>);
  for(const label of ['Requirements Summary','Objective','Audience','KPIs','Business questions','Filters','Pages and views','Assumptions','Confirmed decisions'])expect(summary).toContain(label);
  const design={artifact_kind:'ReportDesign',schema_version:1,projectName:'OperationsQuality',overview:'Monitor service performance.',audience:'Operations leaders',dataModel:{factTables:['Cases'],dimensionTables:['Teams'],relationships:[]},measures:[{id:'m1',name:'Case count',businessDefinition:'Count of cases',aggregation:'COUNT',field:'Cases.CaseId',numeratorMeasureId:'',denominatorMeasureId:'',format:'integer'}],pages:[{id:'p1',name:'Overview',purpose:'Summarise service performance',visuals:[{id:'v1',type:'card',title:'Cases',categoryField:'',measureIds:['m1'],fields:[],altText:'Case count'}]}],filters:['Cases.Priority'],branding:{themeName:'Corporate',primary:'#000',accent:'#fff'},accessibility:['Descriptive titles'],standardsApplied:[{citation:'STD-1',decision:'Use accessible titles'}],assumptions:[],warnings:[],generationRequirements:[]} satisfies ReportDesign;
  const report=renderToStaticMarkup(<ReportDesignPanel design={design}/>);
  for(const label of ['Report Design','Data model','Measures and KPIs','Pages and visuals','Branding and accessibility','Standards applied'])expect(report).toContain(label);
});

it('shows business-facing generation checks while retaining technical evidence',()=>{
  const decision:GuardrailDecision={outcome:'PASS',generation:'AVAILABLE',evaluations:[{ruleId:'SCHEMA-001',category:'schema-quality',severity:'info',result:'PASS',reason:'Referenced fields exist.',recommendedAction:'None.'}]};
  const html=renderToStaticMarkup(<PolicyPanel decision={decision}/>);
  expect(html).toContain('Generation checks');expect(html).toContain('Ready to generate');expect(html).toContain('Technical policy evidence');expect(html).toContain('SCHEMA-001');
});

it('renders professional project and fixed deployment-guide downloads',()=>{
  const html=renderToStaticMarkup(<GeneratedFiles projectName="OperationsQuality" projectUrl="blob:project" guideDownload={{url:'blob:guide',filename:'Report-Deployment-Guide.pdf'}}/>);
  expect(html).toContain('Your files');expect(html).toContain('Download Power BI project');expect(html).toContain('Download deployment guide');expect(html).toContain('Report-Deployment-Guide.pdf');
});

it('renders human review and out-of-scope outcomes without presenting a crash',()=>{
  const review:GuardrailDecision={outcome:'HUMAN_REVIEW_REQUIRED',generation:'NOT_STARTED',evaluations:[{ruleId:'COMPLEXITY-001',category:'complexity',severity:'error',result:'HUMAN_REVIEW_REQUIRED',reason:'The design exceeds tenant visual limits.',recommendedAction:'Reduce scope or obtain verification.'}]};
  const outside:GuardrailDecision={outcome:'OUT_OF_SCOPE',generation:'NOT_STARTED',evaluations:[{ruleId:'SCOPE-001',category:'scope',severity:'error',result:'OUT_OF_SCOPE',reason:'The request is outside Power BI reporting.',recommendedAction:'Revise the request.'}]};
  const reviewHtml=renderToStaticMarkup(<ReviewPanel decision={review}/>);expect(reviewHtml).toContain('Human review required');expect(reviewHtml).toContain('Power BI generation has not started');expect(reviewHtml).toContain('Recommended next step');
  const outsideHtml=renderToStaticMarkup(<ReviewPanel decision={outside}/>);expect(outsideHtml).toContain('This request cannot be generated automatically');expect(outsideHtml).toContain('Power BI generation has not started');
});

it('keeps course fixtures and developer terminology out of the business UX',()=>{
  const html=renderToStaticMarkup(<App/>);for(const term of ['APBRA-90','ELVTR','golden answer','Try a sample','Scenario','NOT_RUN','RequirementsSnapshot','DesignPlan','bootstrap'])expect(html).not.toContain(term);
});

it('offers the deployment guide only for a validated generated candidate',()=>{const candidate={kind:'PowerBICandidate',generatorVersion:'bounded-generic-pbip-1',projectName:'Report',files:{},runtime:{desktop:'NOT_RUN',dax:'NOT_RUN'},release:'NOT_ELIGIBLE'} as const;const design={artifact_kind:'ReportDesign'} as ReportDesign;const pass:CandidateValidation={status:'PASS',checks:[]};const fail:CandidateValidation={status:'FAIL',checks:[]};const available={outcome:'PASS',generation:'AVAILABLE',evaluations:[]} as GuardrailDecision;for(const decision of [{outcome:'BLOCKED',generation:'NOT_STARTED'},{outcome:'OUT_OF_SCOPE',generation:'NOT_STARTED'},{outcome:'HUMAN_REVIEW_REQUIRED',generation:'NOT_STARTED'}] as GuardrailDecision[])expect(deploymentGuideEligible(candidate,design,pass,decision)).toBe(false);expect(deploymentGuideEligible(candidate,design,fail,available)).toBe(false);expect(deploymentGuideEligible(null,design,pass,available)).toBe(false);expect(deploymentGuideEligible(candidate,design,pass,available)).toBe(true);});
