from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCOPE = runpy.run_path(ROOT / "scripts/check_foundry_v7_scope.py")
CHECKER = runpy.run_path(ROOT / "scripts/check_bootstrap.py")
CATALOG = json.loads((ROOT / "agents/catalog.json").read_text())


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="apbra-v7-governance-") as directory:
        root = Path(directory)
        paths = SCOPE["REGISTRATION_PATHS"] | {
            SCOPE["HISTORICAL_SOURCE"], "contracts/engineering/task-contract.schema.json",
        }
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        yield root


class FoundryV7RegistrationTests(unittest.TestCase):
    def validate(self, root):
        return SCOPE["validate"](
            root, CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"],
        )

    def test_exact_task_provenance_and_future_product_only_manifests(self):
        task, faults = self.validate(ROOT)
        self.assertEqual(faults, [])
        self.assertEqual(set(task["allowed_paths"]), SCOPE["REGISTRATION_PATHS"])
        scopes = SCOPE["FUTURE_SLICES"]
        self.assertEqual(sorted(len(paths) for paths in scopes.values()), [2, 7, 8])
        product = frozenset().union(*scopes.values())
        self.assertEqual(len(product), 17)
        self.assertTrue(all(name.startswith("apps/") for name in product))
        for name in sorted(product):
            with self.subTest(path=name):
                self.assertTrue(subprocess.check_output(
                    ["git", "show", SCOPE["BASE"] + ":" + name], cwd=ROOT,
                ))

    def test_rejects_missing_replaced_and_symlink_bound_files(self):
        with fixture() as root:
            for path in SCOPE["PINNED_FILES"]:
                with self.subTest(path=path):
                    target = root / path
                    original = target.read_bytes()
                    target.write_bytes(original + b"\n")
                    self.assertIsNone(self.validate(root)[0])
                    target.unlink()
                    self.assertIsNone(self.validate(root)[0])
                    target.symlink_to(ROOT / path)
                    self.assertIsNone(self.validate(root)[0])
                    target.unlink()
                    target.write_bytes(original)

    def test_original_source_register_matches_exact_base(self):
        name = SCOPE["HISTORICAL_SOURCE"]
        prior = subprocess.check_output(["git", "show", SCOPE["BASE"] + ":" + name], cwd=ROOT)
        self.assertEqual((ROOT / name).read_bytes(), prior)
        self.assertEqual(SCOPE["PINNED_FILES"][name], hashlib.sha256(prior).hexdigest())

    def test_registration_scope_denies_wrong_identity_missing_mixed_and_stale(self):
        phase = SCOPE["phase_errors"]
        globals_for_phase = phase.__globals__
        paths = SCOPE["REGISTRATION_PATHS"]
        branch = SCOPE["REGISTRATION_BRANCH"]
        identity = SCOPE["ISSUE"]
        task = self.validate(ROOT)[0]
        with patch.dict(globals_for_phase, registration_base=lambda root: True):
            self.assertEqual(phase(ROOT, task, identity, branch, paths), [])
            self.assertTrue(phase(ROOT, None, identity, branch, paths))
            self.assertTrue(phase(ROOT, task, "APBRA-85", branch, paths))
            self.assertTrue(phase(ROOT, task, identity, branch, paths - {SCOPE["TASK"]}))
            self.assertTrue(phase(ROOT, task, identity, branch, paths | {"apps/web/src/style.css"}))
            self.assertTrue(phase(ROOT, task, identity, "agent/APBRA-DEVOPS/APBRA-160-foreign", paths))
        with patch.dict(globals_for_phase, registration_base=lambda root: False):
            self.assertTrue(phase(ROOT, task, identity, branch, paths))

    def test_registration_does_not_issue_product_executions(self):
        task, faults = self.validate(ROOT)
        self.assertEqual(faults, [])
        for branch, paths in SCOPE["FUTURE_SLICES"].items():
            with self.subTest(branch=branch):
                self.assertIn("not been issued", SCOPE["phase_errors"](
                    ROOT, task, SCOPE["ISSUE"], branch, paths,
                )[0])
                bound, faults = SCOPE["bind"](
                    ROOT, CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"],
                    SCOPE["ISSUE"], branch, paths,
                )
                self.assertEqual(bound, ())
                self.assertTrue(faults)

    def test_git_prerequisite_requires_pinned_actual_base_tree_and_ancestry(self):
        gate = SCOPE["registration_base"]
        expected = {
            ("rev-parse", "origin/main"): SCOPE["BASE"],
            ("rev-parse", SCOPE["BASE"] + "^{tree}"): SCOPE["BASE_TREE"],
            ("merge-base", SCOPE["BASE"], "HEAD"): SCOPE["BASE"],
        }
        def lookup(root, *args):
            return expected[args].encode()
        with patch.dict(gate.__globals__, git=lookup):
            self.assertTrue(gate(ROOT))
            for key, good in tuple(expected.items()):
                with self.subTest(key=key):
                    expected[key] = "f" * 40
                    self.assertFalse(gate(ROOT))
                    expected[key] = good
        def unavailable(root, *args):
            raise subprocess.CalledProcessError(128, args)
        with patch.dict(gate.__globals__, git=unavailable):
            self.assertFalse(gate(ROOT))

    def test_v7_inverses_restore_entire_previous_files_before_historical_checks(self):
        recovered_file = "scripts/check_recovered_native_registration.py"
        native_file = "scripts/check_nv.py"
        checker_file = "scripts/check_bootstrap.py"
        recovered = runpy.run_path(ROOT / recovered_file)
        native = runpy.run_path(ROOT / native_file)
        restored = {
            checker_file: recovered["strip_v7_bootstrap"]((ROOT / checker_file).read_text()),
            native_file: recovered["strip_v7_nv"]((ROOT / native_file).read_text()),
        }
        for name, text in restored.items():
            with self.subTest(path=name):
                self.assertEqual(text.encode(), subprocess.check_output(
                    ["git", "show", SCOPE["BASE"] + ":" + name], cwd=ROOT,
                ))
        current = (ROOT / checker_file).read_text()
        prior = restored[checker_file]
        self.assertEqual(recovered["strip_bootstrap"](current), recovered["strip_bootstrap"](prior))
        self.assertEqual(native["strip_hooks"](current), native["strip_hooks"](prior))
        self.assertLessEqual(len(current.encode()), 262076)

    def test_v7_inverses_reject_duplicate_missing_and_modified_layers(self):
        recovered = runpy.run_path(ROOT / "scripts/check_recovered_native_registration.py")
        native = runpy.run_path(ROOT / "scripts/check_nv.py")
        checker_text = (ROOT / "scripts/check_bootstrap.py").read_text()
        native_text = (ROOT / "scripts/check_nv.py").read_text()
        hook = recovered["V7_BOOT_HOOK"]
        marker = recovered["V7_NV_MARKER"]
        for bad in (
            checker_text.replace(hook, "", 1), checker_text + hook,
            checker_text.replace(hook, hook + " ", 1), checker_text + "\n",
        ):
            with self.assertRaises(ValueError):
                recovered["strip_v7_bootstrap"](bad)
        for bad in (
            checker_text + hook,
            checker_text.replace(hook, hook.replace("active_branch==", "active_branch =="), 1),
        ):
            with self.assertRaises(ValueError):
                native["strip_hooks"](bad)
        # The older AST check must receive unrelated mutations intact. Only
        # the finite registration and released-source witnesses bind all bytes.
        weakened = checker_text.replace("return errors, manifest", "return [], manifest", 1)
        with self.assertRaises(ValueError):
            recovered["strip_v7_bootstrap"](weakened)
        self.assertEqual(
            native["strip_hooks"](weakened),
            native["strip_hooks"](checker_text).replace("return errors, manifest", "return [], manifest", 1),
        )
        self.assertNotEqual(native["strip_hooks"](weakened), native["strip_hooks"](checker_text))
        for bad in (
            native_text.replace(marker, "", 1), native_text + marker,
            native_text.replace(marker, marker + " ", 1), native_text + "\n",
        ):
            with self.assertRaises(ValueError):
                recovered["strip_v7_nv"](bad)

    def test_integrated_helper_fails_closed_on_tamper_and_extra_paths(self):
        recovered_file = "scripts/check_recovered_native_registration.py"
        recovered = runpy.run_path(ROOT / recovered_file)
        base = lambda root: True
        identity = SCOPE["ISSUE"]
        branch = SCOPE["REGISTRATION_BRANCH"]
        paths = SCOPE["REGISTRATION_PATHS"]
        runner = recovered["stage_authorities"]
        with fixture() as root:
            # This fixture models only the new stage. The full checkout separately
            # runs both historical helper chains and their original bootstrap tests.
            module = runpy.run_path(root / SCOPE["HELPER"])
            module["registration_base"].__globals__["registration_base"] = base
            arguments = (root, CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"], identity, branch)
            with patch.dict(
                runner.__globals__, _pre_v7_stage_authorities=lambda *args: ((), []),
                _v7_modules={str(root.resolve()): module},
            ):
                bound, errors = runner(*arguments, paths)
                self.assertEqual(errors, [])
                self.assertEqual(bound[0][1], paths)
                self.assertTrue(runner(*arguments, paths | {"apps/web/src/style.css"})[1])
                helper = root / SCOPE["HELPER"]
                helper.write_bytes(helper.read_bytes() + b"\n")
                self.assertTrue(runner(*arguments, paths)[1])

    def test_registration_readback_retains_frozen_native_source_and_original_pins(self):
        native = runpy.run_path(ROOT / "scripts/check_nv.py")
        recovered = runpy.run_path(ROOT / "scripts/check_recovered_native_registration.py")
        expected = (SCOPE["ISSUE"], SCOPE["REGISTRATION_BRANCH"], SCOPE["REGISTRATION_PATHS"])
        original = recovered["qualified_paths"]
        arguments = (ROOT, CHECKER, *expected)
        overlap = native["OVERLAP"]
        candidate = native["CANDIDATE"]
        if CHECKER["delivery_context"](ROOT) == expected and SCOPE["registration_base"](ROOT):
            self.assertEqual(original(*arguments, overlap, candidate), set(overlap))
        else:
            self.assertEqual(original(*arguments, overlap, candidate), set())
        altered = {**overlap, next(iter(overlap)): "f" * 64}
        self.assertEqual(original(*arguments, altered, candidate), set())
        self.assertEqual(original(*arguments, overlap, "f" * 40), set())
        self.assertEqual(original(ROOT, CHECKER, "APBRA-85", *expected[1:], overlap, candidate), set())
