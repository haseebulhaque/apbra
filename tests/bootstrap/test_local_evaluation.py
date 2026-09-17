"""Check actual stored observation accounting; these tests do not turn product failures green."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import hashlib
ROOT=Path(__file__).resolve().parents[2]
EVAL=ROOT/'tests/bootstrap/evaluation'
sys.path.insert(0,str(EVAL))
import harness
spec=importlib.util.spec_from_file_location('local_import',EVAL/'import-local.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
EVIDENCE=EVAL/'evidence/run-fcdff3d3'
class LocalEvaluationTests(unittest.TestCase):
    def test_frozen_observations_reconcile_without_waivers(self):
        raw=json.loads((EVIDENCE/'observations.json').read_text())
        run=module.import_observations(raw,'tests/bootstrap/evaluation/evidence/run-fcdff3d3/observations.json')
        saved=json.loads((EVIDENCE/'report.json').read_text())
        self.assertEqual(run['attempts'],saved['run']['attempts'])
        self.assertEqual(harness.summarize(run),saved['summary'])
        self.assertFalse(saved['summary']['mandatory_gate'])
        self.assertEqual(saved['summary']['unresolved_mandatory'],['repair','numeric-runtime','human-quality','held-out-relationship'])
        self.assertEqual(saved['summary']['executed'],21)
        self.assertEqual(saved['summary']['passed'],20)
        raw['observations'][0]['execution_id']='foreign'
        with self.assertRaises(ValueError):module.import_observations(raw,'tests/example.json')
    def test_source_and_manifest_binding(self):
        c=json.loads((EVIDENCE/'candidate.json').read_text())
        for name in ['business-manifest.json','trusted-manifest.json']:
            m=json.loads((EVIDENCE/name).read_text())
            self.assertEqual(m['identityEvidence'],'SIMULATED')
            self.assertEqual(set(m['fileHashes']),set(c['files']))
            for path,sha in m['fileHashes'].items():self.assertEqual(hashlib.sha256(c['files'][path].encode()).hexdigest(),sha)
        failure=json.loads((EVIDENCE/'failure.json').read_text())
        self.assertEqual(failure['result']['status'],'FAIL')
        self.assertEqual(failure['result']['nextAction'],'HUMAN_ESCALATION')
        self.assertNotEqual(failure['failedSha256'],failure['originalSha256'])
    def test_performance_all_samples_and_failures_retained(self):
        p=json.loads((EVIDENCE/'performance.json').read_text())
        self.assertEqual(len(p['samples']),20)
        self.assertEqual(sum(s['validation']['status']=='FAIL' for s in p['samples']),4)
        self.assertTrue(all(s['status']=='COMPLETE' for s in p['samples']))
        for stage,result in p['summary'].items():
            values=sorted(s['durations'][stage] for s in p['samples'])
            self.assertEqual(result['n'],20)
            self.assertEqual(result['p95'],values[18])
