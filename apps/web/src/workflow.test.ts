import {describe, it, expect} from 'vitest';
import {draftReady, unavailableStages} from './workflow';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
describe('honest local requester draft', () => {
  const ids = request.clarifications.map(c => c.id);
  const answers = Object.fromEntries(request.clarifications.map(c => [c.id, c.golden_answer]));
  it('requires every clarification, including region vs RLS', () => {
    expect(draftReady(request.original_text, ids, answers)).toBe(true);
    for(const id of ids) expect(draftReady(request.original_text, ids, {...answers,[id]:' '})).toBe(false);
  });
  it('rejects empty and oversized requests', () => {
    expect(draftReady(' ',ids,answers)).toBe(false);
    expect(draftReady('x'.repeat(4001),ids,answers)).toBe(false);
  });
  it('never claims downstream execution from draft readiness', () => {
    draftReady(request.original_text,ids,answers);
    expect(unavailableStages()).toHaveLength(6);
    expect(unavailableStages().every(s => s.status === 'NOT_RUN')).toBe(true);
  });
});
