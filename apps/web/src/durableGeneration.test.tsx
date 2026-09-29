import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {DurableGeneration} from './durableGeneration';
import type {DurableContract} from './api';

const contract:DurableContract={id:'contract-1',interpretation_id:'interpretation-1',schema_version:2,accepted_at:'2026-09-25T00:00:00Z',contract:{},current:true};

it('offers a clear private report build without overstating local validation',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={contract} csrfToken="csrf" onError={()=>{}}/>);
  expect(html).toContain('Generated reports');
  expect(html).toContain('Build report');
  expect(html).toContain('Validated ZIP outputs remain private');
  expect(html).toContain('Supplied and reviewed ReportDesign JSON');
  expect(html).toContain('LOCAL_DETERMINISTIC_NO_MODEL_CALL');
  expect(html).toContain('Power BI Desktop, DAX, RLS and deployment validation are not run');
});

it('requires a current confirmation while keeping historical output area visible',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={null} csrfToken="csrf" onError={()=>{}}/>);
  expect(html).toContain('Confirm the current understanding before building a report');
  expect(html).toContain('Historical outputs remain available below');
  expect(html).not.toContain('>Build report<');
});
