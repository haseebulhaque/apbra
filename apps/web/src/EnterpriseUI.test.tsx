import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {Callout,DisclosurePanel,FileDownloadRow,NavItem,ProcessingState,StatusBadge,WorkflowStepper} from './EnterpriseUI';
import {AgentCostControls} from './EnterpriseApp';

it('keeps unknown agent limits blank and distinguishes built-in tools from MCP',()=>{
  const html=renderToStaticMarkup(<AgentCostControls limits={null} onChange={()=>{}}/>);
  expect((html.match(/value=""/g)??[]).length).toBe(4);
  expect(html).toContain('built-in tool limits do not bound MCP');
  expect(html).toContain('Saving a value does not qualify remote enforcement');
});

it('shows only explicit configured agent limits and respects the busy state',()=>{
  const html=renderToStaticMarkup(<AgentCostControls disabled limits={{max_builtin_tool_calls:null,max_mcp_calls:1,max_provider_requests:2,max_retrieval_output_tokens:null}} onChange={()=>{}}/>);
  expect(html).toContain('value="1"');
  expect(html).toContain('value="2"');
  expect((html.match(/value=""/g)??[]).length).toBe(2);
  expect(html).toContain('disabled=""');
});

it('renders keyboard-accessible navigation with an active page',()=>{
  const html=renderToStaticMarkup(<NavItem active label="Create Report" icon="+" onClick={()=>{}}/>);
  expect(html).toContain('aria-current="page"');
  expect(html).toContain('Create Report');
});

it('renders workflow stages with text and current-step semantics',()=>{
  const html=renderToStaticMarkup(<WorkflowStepper stages={[
    {label:'Requirement',state:'completed'},
    {label:'Data',state:'current'},
    {label:'Generate',state:'attention'},
  ]}/>);
  expect(html).toContain('aria-label="Report creation progress"');
  expect(html).toContain('aria-current="step"');
  for(const text of ['Completed','Current','Needs attention'])expect(html).toContain(text);
});

it('renders disclosure, status, and live processing primitives',()=>{
  const html=renderToStaticMarkup(<><StatusBadge tone="success">Connected</StatusBadge><DisclosurePanel summary="Technical run evidence"><p>Run details</p></DisclosurePanel><ProcessingState title="Preparing the report design…"/></>);
  expect(html).toContain('Connected');
  expect(html).toContain('<summary>Technical run evidence</summary>');
  expect(html).toContain('role="status"');
});

it('renders file downloads with meaningful accessible names',()=>{
  const html=renderToStaticMarkup(<FileDownloadRow title="Power BI project" description="Generated project" href="blob:test" filename="Report.zip" label="Download Power BI project" primary/>);
  expect(html).toContain('download="Report.zip"');
  expect(html).toContain('Download Power BI project');
});

it('renders attention and error messages without colour-only meaning',()=>{
  const html=renderToStaticMarkup(<><Callout tone="warning" title="Human review required"><p>Generation has not started.</p></Callout><Callout tone="danger" title="Cannot generate automatically"><p>Review the request.</p></Callout></>);
  expect(html).toContain('Human review required');
  expect(html).toContain('Cannot generate automatically');
  expect(html).toContain('Generation has not started');
});
