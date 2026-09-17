import {it,expect} from 'vitest';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import {createDesignPlan} from './designPlan';import {confirmRequirements} from './requirements';import {retrieveCuratedKnowledge} from './knowledge';import {generatePowerBI} from './powerbi';
import {validateCandidate,candidateDigest,createFailureCandidate,failureCase} from './validation';
const golden=()=>generatePowerBI(createDesignPlan(confirmRequirements({original_request:request.original_text,original_schema:schema,answers:Object.fromEntries(request.clarifications.map(c=>[c.id,c.golden_answer]))},true),retrieveCuratedKnowledge('sales-v1')));
it('passes only declared source checks and binds a SHA256 without runtime/release claims',async()=>{const c=golden(),v=await validateCandidate(c);expect(v.status).toBe('PASS');expect(v.candidateSha256).toBe(await candidateDigest(c));expect(v.nextAction).toBe('GOVERNANCE_REQUIRED');expect(v.runtime).toEqual({desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'});});
it('executes predeclared failure with independent findings, distinct digest and original retained',async()=>{const c=golden(),before=JSON.stringify(c),f=createFailureCandidate(c),v=await validateCandidate(f);expect(v.status).toBe('FAIL');expect(v.findings.some(x=>x.code===failureCase.expectedCode)).toBe(true);expect(v.nextAction).toBe('HUMAN_ESCALATION');expect(v.candidateSha256).not.toBe(await candidateDigest(c));expect(JSON.stringify(c)).toBe(before);});
it('rejects changed bytes in every file, even whitespace, and malformed/extra/missing files',async()=>{
 const original=golden();for(const path of Object.keys(original.files)){const c=structuredClone(original);c.files[path]+=' ';expect((await validateCandidate(c)).status,path).toBe('FAIL');}
 for(const mutate of [(c:any)=>delete c.files['DesignPlan.json'],(c:any)=>c.files['extra.json']='{}',(c:any)=>c.files['SalesPerformance.pbip']='{',(c:any)=>c.files['../escape']='x',(c:any)=>c.files['DesignPlan.json']=null]){const c=golden();mutate(c);expect((await validateCandidate(c)).status).toBe('FAIL');}
});
it('rejects forged envelope and snapshots input before asynchronous hashing',async()=>{
 for(const value of [null,[],{},'PASS',{...golden(),release:'APPROVED'},{...golden(),runtime:{desktop:'PASS'}},{...golden(),status:'PASS'}])expect((await validateCandidate(value)).status).toBe('FAIL');
 const c=golden(),pending=validateCandidate(c);c.files['README.txt']='changed';const v=await pending;expect(v.status).toBe('PASS');expect(v.candidateSha256).not.toBe(await candidateDigest(c));expect((await validateCandidate(c)).status).toBe('FAIL');
});
