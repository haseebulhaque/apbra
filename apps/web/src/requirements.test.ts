import {it, expect} from 'vitest';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import expected from '../../../tests/bootstrap/fixtures/sales-v1/requirements.expected.json';
import {assessRequirements, confirmRequirements, type Submission} from './requirements';
const golden = (): Submission => ({original_request: request.original_text, original_schema: structuredClone(schema), answers: Object.fromEntries(request.clarifications.map(c => [c.id, c.golden_answer]))});
it('replays a confirmed snapshot with exact original inputs and fixture requirements', () => {
  const input = golden();
  const snapshot = confirmRequirements(input, true);
  const {artifact_kind, confirmation, ...requirements} = expected;
  expect(snapshot.requirements).toEqual(requirements);
  expect(snapshot.submission).toEqual(input);
  expect(confirmRequirements(JSON.parse(JSON.stringify(input)), true)).toEqual(snapshot);
  input.answers['sales-definition'] = 'changed';
  expect(snapshot.submission.answers['sales-definition']).toBe(request.clarifications[0].golden_answer);
});
it('requires explicit confirmation and every declared clarification', () => {
  expect(() => confirmRequirements(golden(), false)).toThrow();
  for (const c of request.clarifications) {
    const input = golden(); delete input.answers[c.id];
    expect(assessRequirements(input).status).toBe('AWAITING_CLARIFICATION');
    expect(() => confirmRequirements(input, true)).toThrow();
  }
});
it('fails closed on arbitrary prose, RLS requests, extra answers and incomplete coverage', () => {
  const cases = [golden(), golden(), golden(), golden()];
  cases[0].original_request += ' Include profits.';
  cases[1].answers['region-security'] = 'Require regional RLS';
  cases[2].answers.extra = 'yes';
  cases[3].original_schema.date_coverage.start = '2025-01-01';
  for (const input of cases) {
    expect(assessRequirements(input).status).toBe('UNSUPPORTED');
    expect(() => confirmRequirements(input, true)).toThrow();
  }
});
it('asks which date path to use when one otherwise unchanged schema adds a plausible fact-date relationship', () => {
  const input = golden();
  const fact = input.original_schema.tables.find(table => table.name === 'FactSales')!;
  fact.columns.push({name: 'DeliveryDate', type: 'date', nullable: false} as never);
  input.original_schema.relationships.push({...input.original_schema.relationships[0], from_column: 'DeliveryDate'} as never);

  const assessment = assessRequirements(input);
  expect(assessment.status).toBe('AWAITING_CLARIFICATION');
  expect(assessment.issues).toEqual([
    'Which FactSales date relationship should drive time intelligence: SaleDate or DeliveryDate?',
  ]);
  expect(() => confirmRequirements(input, true)).toThrow();
});
it('keeps unrelated schema changes unsupported even when an additional date relationship is present', () => {
  const input = golden();
  const fact = input.original_schema.tables.find(table => table.name === 'FactSales')!;
  fact.columns.push({name: 'DeliveryDate', type: 'date', nullable: false} as never);
  input.original_schema.relationships.push({...input.original_schema.relationships[0], from_column: 'DeliveryDate'} as never);
  input.original_schema.date_coverage.start = '2025-01-01';

  expect(assessRequirements(input).status).toBe('UNSUPPORTED');
});
