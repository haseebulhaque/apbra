"""Narrow APBRA129 dispatch and source acceptance regression checks."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bootstrap_shell", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
class ShellScopeTests(unittest.TestCase):
    def setUp(self):
        self.task=json.loads((ROOT/"tasks/APBRA-129-capstone-shell.json").read_text())
        self.catalog=json.loads((ROOT/"agents/catalog.json").read_text())
        self.sources=json.loads((ROOT/"docs/source-register.json").read_text())
        self.card=next(v for v in self.catalog["cards"] if v["agent_id"]=="APBRA-DEVOPS")
    def test_exact_paths_only(self):
        self.assertEqual(set(self.task["allowed_paths"]), c.CAPSTONE_SHELL_PATHS)
        for path in ["apps/api/main.py","apps/web/src/other.ts","apps/web/.env","apps/web/../secret","packages/domain.py"]:
            self.assertFalse(c.path_allowed(path,self.task,self.card))
        self.assertTrue(c.path_allowed("apps/web/src/main.tsx",self.task,self.card))
    def test_accepted_bounded_source(self):
        self.assertEqual(c.task_errors(self.task,self.catalog,self.sources),[])
    def test_unknown_or_missing_status_never_authorizes_dispatch(self):
        for status in [None,"PROPOSED","REJECTED","TYPO",""]:
            sources=copy.deepcopy(self.sources)
            source=next(s for s in sources["sources"] if s["id"]=="capstone-web-shell")
            if status is None: source.pop("status")
            else: source["status"]=status
            self.assertTrue(c.task_errors(self.task,self.catalog,sources))

    def test_widened_task_and_symlink_are_rejected(self):
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for file in c.repo_files(ROOT):
                target=root/file.relative_to(ROOT)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(file,target)
            (root/"tasks/APBRA-129-capstone-shell.json").write_text(json.dumps(self.task))
            target=root/"apps/web/src/main.tsx"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)
            target.symlink_to(root/"README.md")
            errors,_=c.check(root)
            self.assertTrue(any("safe bootstrap scope" in e for e in errors))
            task=copy.deepcopy(self.task)
            task["allowed_paths"]=["apps/**"]
            (root/"tasks/APBRA-129-capstone-shell.json").write_text(json.dumps(task))
            errors,_=c.check(root)
            self.assertIn("Unexpected Capstone shell scope",errors)

    def test_downgraded_or_unrelated_contract_cannot_admit_shell(self):
        import tempfile
        import shutil
        mutations = [
            {"task_mode": "SPECIFICATION", "readiness": "READY_FOR_SPECIFICATION", "owner_acceptance": "BOOTSTRAP_ONLY"},
            {"task_mode": "REVIEW"},
            {"readiness": "NEEDS_REFINEMENT"},
            {"owner_acceptance": "PENDING"},
            {"source_ids": ["engineering-structure"]},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                for file in c.repo_files(ROOT):
                    target=root/file.relative_to(ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file,target)
                task=copy.deepcopy(self.task)
                task.update(mutation)
                (root/"tasks/APBRA-129-capstone-shell.json").write_text(json.dumps(task))
                errors,_=c.check(root)
                self.assertTrue(any("requires" in e for e in errors))
                self.assertTrue(any("safe bootstrap scope: apps/web/" in e for e in errors))
