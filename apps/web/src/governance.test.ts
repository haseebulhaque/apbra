import {it,expect} from 'vitest';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import {createDesignPlan} from './designPlan';import {confirmRequirements} from './requirements';import {retrieveCuratedKnowledge} from './knowledge';import {generatePowerBI} from './powerbi';
import {createFailureCandidate,sha256} from './validation';import {createDemoGovernance,type DemoSession} from './governance';
const golden=()=>generatePowerBI(createDesignPlan(confirmRequirements({original_request:request.original_text,original_schema:schema,answers:Object.fromEntries(request.clarifications.map(c=>[c.id,c.golden_answer]))},true),retrieveCuratedKnowledge('sales-v1')));
it('business route needs independent eligible review and emits exact manifest',async()=>{
 const g=createDemoGovernance(),a=g.issueDemoSession('requester'),r=g.issueDemoSession('reviewer'),c=golden(),op=await g.submit(a,c);
 expect(op.status).toBe('PENDING_REVIEW');await expect(g.package(a,op.id,1)).rejects.toThrow('GOVERNANCE');
 g.review(r,op.id,1,op.validation.candidateSha256!,'APPROVE','Synthetic source reviewed');const output=await g.package(a,op.id,1);
 expect(output.manifest.governance).toBe('DEMO_BUSINESS_REVIEW');expect(output.manifest.identityEvidence).toBe('SIMULATED');
 for(const [path,text] of Object.entries(c.files)){expect(output.files[path]).toBe(text);expect(output.manifest.fileHashes[path]).toBe(await sha256(text));}
 expect(output.files['handover.txt']).toContain('NOT_RUN');expect(g.inspect(a,op.id).status).toBe('PACKAGED');
});
it('trusted route cannot bypass mandatory validation and ignores forged claims',async()=>{
 const g=createDemoGovernance(),t=g.issueDemoSession('trusted');const pass=await g.submit(t,golden());expect(pass.status).toBe('TRUSTED_ELIGIBLE');expect((await g.package(t,pass.id,1)).manifest.governance).toBe('DEMO_TRUSTED_POLICY');
 const fail=await g.submit(t,createFailureCandidate(golden()));expect(fail.status).toBe('VALIDATION_FAILED');await expect(g.package(t,fail.id,1)).rejects.toThrow();
 await expect(g.submit({mode:'SIMULATED_IDENTITY',trusted:true} as DemoSession,golden())).rejects.toThrow('CONTEXT_DENIED');
});
it('denies self/foreign review, missing reasons, stale approvals and revoked members',async()=>{
 const g=createDemoGovernance(),a=g.issueDemoSession('reviewer'),r=g.issueDemoSession('requester'),o=g.issueDemoSession('outsider');let op=await g.submit(a,golden());
 expect(()=>g.review(a,op.id,1,op.validation.candidateSha256!,'APPROVE','self')).toThrow('REVIEWER_DENIED');expect(()=>g.inspect(o,op.id)).toThrow('OPERATION_DENIED');
 op=await g.submit(r,golden());expect(()=>g.review(a,op.id,1,op.validation.candidateSha256!,'APPROVE',' ')).toThrow('REASON_REQUIRED');
 g.review(a,op.id,1,op.validation.candidateSha256!,'REQUEST_CHANGES','Review again');op=await g.resubmit(r,op.id,1,golden());expect(op.revision).toBe(2);expect(op.review).toBeNull();
 expect(()=>g.review(a,op.id,1,op.validation.candidateSha256!,'APPROVE','stale')).toThrow('STALE');g.review(a,op.id,2,op.validation.candidateSha256!,'APPROVE','reviewed');g.revokeDemoMember('reviewer');await expect(g.package(r,op.id,2)).rejects.toThrow('GOVERNANCE');
});
it('keeps snapshots immutable and rejects invalidation/revocation during packaging',async()=>{
 const g=createDemoGovernance(),t=g.issueDemoSession('trusted'),c=golden(),op=await g.submit(t,c);c.files['README.txt']='changed';op.validation.status='FAIL';
 expect(g.inspect(t,op.id).validation.status).toBe('PASS');const pending=g.package(t,op.id,1);g.invalidate(op.id);await expect(pending).rejects.toThrow();
 const newer=await g.submit(t,golden()),pending2=g.package(t,newer.id,1);g.revokeDemoMember('trusted');await expect(pending2).rejects.toThrow();expect(g.exportEvidence().audit.length).toBeGreaterThan(3);
});
