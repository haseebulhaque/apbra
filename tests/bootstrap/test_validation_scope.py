"""Exact APBRA134 admission fails closed on missing or invalid authority."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bootstrap_validation', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ValidationScopeTests(unittest.TestCase):
    def test_admission_and_negative_authority(self):
        task_path = 'tasks/APBRA-134-validation.json'
        task = json.loads((ROOT / task_path).read_text())
        mutations = [None, {'allowed_paths': ['apps/**']}, {'task_id': 'APBRA-999'},
                     {'assigned_agent': 'APBRA-RAG'}, {'source_ids': ['engineering-structure']},
                     {'task_mode': 'SPECIFICATION', 'readiness': 'READY_FOR_SPECIFICATION', 'owner_acceptance': 'BOOTSTRAP_ONLY'},
                     {'owner_acceptance': 'PENDING'}, {'readiness': 'NEEDS_REFINEMENT'}]
        for mutation in ['valid', *mutations, 'source-status', 'symlink']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                names = {p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)}
                names.update(c.CAPSTONE_VALIDATION_PATHS | {task_path})
                for name in names:
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, target)
                if mutation is None:
                    (root / task_path).unlink()
                elif isinstance(mutation, dict):
                    changed = copy.deepcopy(task)
                    changed.update(mutation)
                    (root / task_path).write_text(json.dumps(changed))
                elif mutation == 'source-status':
                    source_path = root / 'docs/source-register.json'
                    sources = json.loads(source_path.read_text())
                    next(s for s in sources['sources'] if s['id'] == 'capstone-validation')['status'] = 'PROPOSED'
                    source_path.write_text(json.dumps(sources))
                elif mutation == 'symlink':
                    target = root / 'apps/web/src/validation.ts'
                    target.unlink()
                    target.symlink_to(root / 'README.md')
                errors, _ = c.check(root)
                if mutation == 'valid':
                    self.assertEqual(errors, [])
                else:
                    self.assertTrue(any('safe bootstrap scope: apps/web/src/validation.ts' in e for e in errors), errors)
