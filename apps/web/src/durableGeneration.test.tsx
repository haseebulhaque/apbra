import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {DurableGeneration,automaticDesignPreflightMessage} from './durableGeneration';
import type {AutomaticDesignAttempt,DurableContract} from './api';

const contract:DurableContract={id:'contract-1',interpretation_id:'interpretation-1',schema_version:2,accepted_at:'2026-09-25T00:00:00Z',contract:{},current:true};

it('explains a saved zero-call input-limit failure without claiming a rejected model design',()=>{
  const attempt:AutomaticDesignAttempt={id:'attempt-1',confirmed_contract_id:'contract-1',status:'FAILED',failure:{code:'MODEL_INPUT_BUDGET_EXCEEDED',message:'Preflight failed'},usage:{call_count:0},provider_profile_id:null,model_or_deployment:null,prompt_version:null,configuration_id:null,capability_profile:{},validation:null,created_at:'2026-10-07T00:00:00Z',completed_at:null};
  expect(automaticDesignPreflightMessage(attempt)).toContain('input limit before a model call');
  expect(automaticDesignPreflightMessage(attempt)).toContain('confirmed requirements remain saved');
  expect(automaticDesignPreflightMessage({...attempt,usage:{call_count:1}})).toBeNull();
  expect(automaticDesignPreflightMessage({...attempt,usage:{}})).toBeNull();
  expect(automaticDesignPreflightMessage({...attempt,status:'RUNNING'})).toBeNull();
  expect(automaticDesignPreflightMessage({...attempt,failure:{code:'MODEL_PROVIDER_FAILED',message:'Failed'}})).toBeNull();
});

it('offers a clear private report build without overstating local validation',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={contract} csrfToken="csrf" onError={()=>{}}/>);
  expect(html).toContain('Build and find reports');
  expect(html).toContain('Create the report design');
  expect(html).not.toContain('>Build report<');
  expect(html).not.toContain('Expert report design JSON');
  expect(html).toContain('private candidate');
  expect(html).toContain('No current report yet');
  expect(html).toContain('Earlier builds and history');
  expect(html).toContain('Power BI Desktop, DAX, RLS, publication and deployment validation are not run');
});

it('limits raw reviewed-plan intake to the expert-facing detail',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={contract} csrfToken="csrf" actorRole="EXPERT" onError={()=>{}}/>);
  expect(html).toContain('Details for experts');
  expect(html).toContain('Checking expert report access');
  expect(html).not.toContain('Expert report design JSON');
  expect(html).not.toContain('>Build report<');
});

it('requires a current confirmation while keeping historical output area visible',()=>{
  const html=renderToStaticMarkup(<DurableGeneration caseId="case-1" contract={null} csrfToken="csrf" onError={()=>{}}/>);
  expect(html).toContain('Confirm your understanding to continue');
  expect(html).toContain('Earlier reports remain available below.');
  expect(html).not.toContain('>Build report<');
});
