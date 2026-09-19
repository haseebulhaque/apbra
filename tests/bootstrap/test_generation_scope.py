"""Exact APBRA133 admission fails closed on missing or invalid authority."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bootstrap_generation', ROOT / 'scripts/check_bootstrap.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class GenerationScopeTests(unittest.TestCase):
    def test_admission_and_negative_authority(self):
        task_path = 'tasks/APBRA-133-powerbi-project.json'
        task = json.loads((ROOT / task_path).read_text())
        mutations = [
            (None, None),
            ({'allowed_paths': ['apps/**']}, 'Unexpected Capstone generation scope'),
            ({'task_id': 'APBRA-999'}, 'Unexpected Capstone generation identity'),
            ({'assigned_agent': 'APBRA-RAG'}, 'Unexpected Capstone generation identity'),
            ({'source_ids': ['engineering-structure']}, 'Capstone generation requires its specific accepted source'),
            ({'task_mode': 'SPECIFICATION', 'readiness': 'READY_FOR_SPECIFICATION', 'owner_acceptance': 'BOOTSTRAP_ONLY'}, 'Capstone generation requires issued implementation acceptance'),
            ({'owner_acceptance': 'PENDING'}, 'Implementation acceptance is not recorded'),
            ({'readiness': 'NEEDS_REFINEMENT'}, 'Implementation mode/readiness mismatch'),
        ]
        for mutation, expected_error in [('valid', None), *mutations, ('source-status', 'Proposed sources cannot authorize implementation'), ('symlink', 'File outside safe bootstrap scope: apps/web/src/powerbi.ts')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                names = {p.relative_to(ROOT).as_posix() for p in c.repo_files(ROOT)}
                names.update(c.CAPSTONE_GENERATION_PATHS | {task_path})
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
                    next(s for s in sources['sources'] if s['id'] == 'capstone-powerbi-project')['status'] = 'PROPOSED'
                    source_path.write_text(json.dumps(sources))
                elif mutation == 'symlink':
                    target = root / 'apps/web/src/powerbi.ts'
                    target.unlink()
                    target.symlink_to(root / 'README.md')
                errors, _ = c.check(root)
                if mutation in ('valid', None):
                    self.assertEqual(errors, [])
                else:
                    self.assertTrue(any(expected_error in error for error in errors), errors)
