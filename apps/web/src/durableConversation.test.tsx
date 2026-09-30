import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {DurableConversation} from './durableConversation';
import type {CaseRecord} from './api';

const record:CaseRecord={id:'case-1',company_id:'company-1',creator_membership_id:'member-1',current_request_version_id:'request-1',version:1,semantic_context_version:3,created_at:'2026-09-24T00:00:00Z',updated_at:'2026-09-24T00:00:00Z',current_request:{id:'request-1',sequence:1,request_text:'Compare capacity by facility.',created_at:'2026-09-24T00:00:00Z'}};

it('labels durable messages and qualified evidence without claiming generated output',()=>{
  const html=renderToStaticMarkup(<DurableConversation record={record} csrfToken="csrf" onContextChanged={()=>{}} onError={()=>{}}/>);
  expect(html).toContain('Your report journey');
  expect(html).toContain('Shape your report');
  expect(html).toContain('Add a business message');
  expect(html).toContain('Add CSV or XLSX evidence');
  expect(html).toContain('confirmation is not available without supported evidence');
  expect(html).toContain('Review the understanding');
  for(const step of ['Goal','Information','Understanding','Confirm','Build','Report'])expect(html).toContain(`<strong>${step}</strong>`);
  expect(html).toContain('aria-current="step"');
  expect(html).not.toMatch(/candidate ready|report generated/i);
});
