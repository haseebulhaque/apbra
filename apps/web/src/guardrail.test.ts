import {expect, it} from 'vitest';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import {assessRequestGuardrail} from './guardrail';
import {assessRequirements, confirmRequirements} from './requirements';

const answers=Object.fromEntries(request.clarifications.map(item=>[item.id,item.golden_answer]));

it('allows the bounded Sales Performance request to continue through requirements',()=>{
  expect(assessRequestGuardrail(request.original_text).status).toBe('ALLOW');
  const submission={original_request:request.original_text,original_schema:schema,answers};
  expect(assessRequirements(submission).status).toBe('READY_TO_CONFIRM');
  expect(confirmRequirements(submission,true).artifact_kind).toBe('RequirementsSnapshot');
});

it('terminates a 250-visual request with structured human-review evidence and no generation',()=>{
  const prompt='Create an executive sales report with 250 visuals on a single report page.';
  const decision=assessRequestGuardrail(prompt);
  expect(decision).toMatchObject({status:'HUMAN_REVIEW_REQUIRED',terminal:true,code:'EXCESSIVE_SINGLE_PAGE_VISUALS',generation:'BLOCKED_NOT_RUN'});
  expect(decision.reason).toContain('250 visuals');
  expect(decision.evidence[0].citation).toBe('local-policy:capstone-power-bi-demo-boundaries/GUARD-001');
  expect(()=>confirmRequirements({original_request:prompt,original_schema:schema,answers},true)).toThrow();
});

it('blocks an unrelated marketing request outside Power BI scope',()=>{
  const decision=assessRequestGuardrail('Write a marketing campaign for our new product.');
  expect(decision).toMatchObject({status:'OUT_OF_SCOPE',terminal:true,code:'NOT_A_POWER_BI_REQUEST',generation:'BLOCKED_NOT_RUN'});
});
