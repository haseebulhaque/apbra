import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {DurableGeneration} from './durableGeneration';
import type {DurableContract} from './api';

const contract:DurableContract={id:'contract-1',interpretation_id:'interpretation-1',schema_version:2,accepted_at:'2026-09-25T00:00:00Z',contract:{},current:true};

it('offers a clear private report build without overstating local validation',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={contract} csrfToken="csrf" onError={()=>{}}/>);
  expect(html).toContain('Build and find reports');
  expect(html).toContain('Expert review needed');
  expect(html).not.toContain('>Build report<');
  expect(html).not.toContain('Expert report plan JSON');
  expect(html).toContain('Candidate files stay private');
  expect(html).toContain('No current report yet');
  expect(html).toContain('Earlier builds and history');
  expect(html).toContain('Power BI Desktop, DAX, RLS, publication and deployment validation are not run');
});

it('limits raw reviewed-plan intake to the expert-facing detail',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={contract} csrfToken="csrf" actorRole="EXPERT" onError={()=>{}}/>);
  expect(html).toContain('Details for experts');
  expect(html).toContain('Checking expert case access');
  expect(html).not.toContain('Expert report plan JSON');
  expect(html).not.toContain('>Build report<');
});

it('requires a current confirmation while keeping historical output area visible',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={null} csrfToken="csrf" onError={()=>{}}/>);
  expect(html).toContain('Confirm your understanding to continue');
  expect(html).toContain('Earlier reports remain available below.');
  expect(html).not.toContain('>Build report<');
});
