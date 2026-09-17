import {it,expect} from 'vitest';
import {createExecutionTrace} from './execution';
it('retains exact snapshots, measured processing duration and explicit evidence boundaries',()=>{
 let time=10,n=0;const t=createExecutionTrace(()=>time,()=> '2026-09-17T00:00:00Z',()=>`id-${++n}`);
 const input={value:1};const token=t.start('requirements');time=18;t.finish(token,input);input.value=9;
 const e=t.export();expect(e.steps[0]).toMatchObject({durationMs:8,status:'COMPLETE',output:{value:1}});
 expect(e.usage.providerCost).toBeNull();expect(e.evidenceBoundary.desktop).toBe('NOT_RUN');
 e.steps[0].output='tampered';expect(t.export().steps[0].output).toEqual({value:1});
});
it('retains failures and pending work and prevents stale completion becoming active after invalidation',()=>{
 const t=createExecutionTrace();t.sync('requirements',()=>({v:1}));const stale=t.start('validation');
 t.invalidate('input changed');t.finish(stale,{status:'PASS'});
 expect(t.export().active).toEqual({});expect(t.export().steps[1].parents).toHaveLength(1);
 expect(()=>t.sync('generation',()=>{throw new Error('private implementation detail')})).toThrow();
 expect(t.export().steps.at(-1)).toMatchObject({status:'ERROR',error:'STEP_FAILED'});
 t.start('pending');expect(t.export().steps.at(-1)).toMatchObject({status:'RUNNING',durationMs:null});
 expect(()=>t.finish(stale,{})).toThrow('INVALID_TRACE_TOKEN');
});
