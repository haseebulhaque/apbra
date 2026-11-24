"""Check exact issuance scope, historical inverse and verified merge fixtures."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CHECKER = runpy.run_path(ROOT / "scripts/check_bootstrap.py")
RECOVERED = runpy.run_path(ROOT / "scripts/check_recovered_native_registration.py")
OLD = runpy.run_path(ROOT / "scripts/check_foundry_v7_scope.py")
ISSUE_SCOPE = runpy.run_path(ROOT / "scripts/check_foundry_v7_metadata_issuance.py")
CATALOG = json.loads((ROOT / "agents/catalog.json").read_text())


def run_git(root, *args, github_fixture=False):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Synthetic fixture", "GIT_AUTHOR_EMAIL": "test@example.org",
           "GIT_COMMITTER_NAME": "GitHub" if github_fixture else "Synthetic fixture",
           "GIT_COMMITTER_EMAIL": "noreply@github.com" if github_fixture else "test@example.org"}
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
         "-C", str(root), *args], stderr=subprocess.PIPE, env=env,
    )


class MetadataIssuanceTests(unittest.TestCase):
    def check(self, root, branch, paths, issue="APBRA-160"):
        errors, _ = CHECKER["check"](root, active_task_id=issue, active_branch=branch, changed_paths=paths)
        return errors

    def binding(self, root, branch, paths, issue="APBRA-160"):
        return ISSUE_SCOPE["bind"](
            root, OLD, CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"], issue, branch, paths,
        )

    def test_original_dormant_registration_and_unchanged_implementation_inventory(self):
        contract = ISSUE_SCOPE["exact_task"](ROOT, OLD, CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"])
        self.assertEqual(set(contract["allowed_paths"]), ISSUE_SCOPE["PRODUCT_PATHS"])
        self.assertEqual(len(ISSUE_SCOPE["ISSUANCE_PATHS"]), 5)
        self.assertEqual(len(ISSUE_SCOPE["PRODUCT_PATHS"]), 2)
        for branch, paths in OLD["FUTURE_SLICES"].items():
            self.assertIn(ISSUE_SCOPE["UNISSUED"], OLD["phase_errors"](ROOT, None, "APBRA-160", branch, paths))

    def test_governance_only_exact_scope_and_wrong_authority(self):
        paths = ISSUE_SCOPE["ISSUANCE_PATHS"]
        branch = ISSUE_SCOPE["ISSUANCE_BRANCH"]
        globals_ = ISSUE_SCOPE["bind"].__globals__
        with patch.dict(globals_, approved_base=lambda root: True, ref=lambda root, ref: ISSUE_SCOPE["BASE"],
                        candidate_head=lambda *args: True):
            selected, errors = self.binding(ROOT, branch, paths)
            self.assertEqual(errors, [])
            self.assertEqual(selected[0][1], paths)
            self.assertEqual(selected[0][0]["task_mode"], "SPECIFICATION")
            for wrong in (set(), paths - {ISSUE_SCOPE["TASK"]}, paths | ISSUE_SCOPE["PRODUCT_PATHS"]):
                self.assertFalse(self.binding(ROOT, branch, wrong)[0])
            self.assertFalse(self.binding(ROOT, branch, paths, "APBRA-85")[0])
            self.assertFalse(self.binding(ROOT, branch + "-other", paths)[0])
        with patch.dict(globals_, approved_base=lambda root: True, ref=lambda root, ref: "c" * 40):
            self.assertFalse(self.binding(ROOT, branch, paths)[0])

    def test_exact_inverses_restore_actual_pr186_bytes_and_keep_mutations_visible(self):
        bootstrap = "scripts/check_bootstrap.py"
        recovered = "scripts/check_recovered_native_registration.py"
        for file, strip in ((bootstrap, "strip_metadata_bootstrap"), (recovered, "strip_metadata_recovered")):
            source = (ROOT / file).read_bytes()
            self.assertEqual(RECOVERED[strip](source), run_git(ROOT, "show", ISSUE_SCOPE["BASE"] + ":" + file))
        current = (ROOT / bootstrap).read_text()
        hook = RECOVERED["METADATA_BOOT_HOOK"]
        strict = RECOVERED["strip_metadata_bootstrap"]
        for bad in (current + hook, current.replace(hook, "", 1), current.replace("issued_v7_branch", "issued_v7_branch "), current+"\n"):
            with self.subTest():
                with self.assertRaises(ValueError):
                    strict(bad.encode())
        native = runpy.run_path(ROOT / "scripts/check_nv.py")
        historic = native["strip_hooks"](current)
        modified = current.replace("return errors, manifest", "return [], manifest", 1)
        self.assertNotEqual(native["strip_hooks"](modified), historic)
        self.assertLessEqual(len(current.encode()), 262076)

    def test_task_tamper_is_rejected_even_if_schema_remains_valid(self):
        bind = ISSUE_SCOPE["exact_task"]
        raw = OLD["raw"]
        for broken in (b"{}", raw(ROOT, ISSUE_SCOPE["TASK"]) + b"\n"):
            new = {**OLD, "raw": lambda root, name: broken if name == ISSUE_SCOPE["TASK"] else raw(root, name)}
            with self.assertRaises(ValueError):
                bind(ROOT, new, CATALOG, CHECKER["schema_errors"], CHECKER["task_errors"])

    def test_actual_current_issuance_context_preserves_prior_app_witness(self):
        context = ("APBRA-160", ISSUE_SCOPE["ISSUANCE_BRANCH"], ISSUE_SCOPE["ISSUANCE_PATHS"])
        if CHECKER["delivery_context"](ROOT) != context or not ISSUE_SCOPE["approved_base"](ROOT):
            # Other released consumers also test the exact inverse and synthetic merge below.
            return
        self.assertEqual(self.check(ROOT, context[1], context[2]), [])
        native = runpy.run_path(ROOT / "scripts/check_nv.py")
        overlap, candidate = native["OVERLAP"], native["CANDIDATE"]
        qualified = RECOVERED["qualified_paths"]
        self.assertEqual(qualified(ROOT, CHECKER, *context, overlap, candidate), set(overlap))
        self.assertEqual(qualified(ROOT, CHECKER, *context, overlap, "c" * 40), set())
        self.assertIn(ISSUE_SCOPE["UNISSUED"], self.check(ROOT, ISSUE_SCOPE["PRODUCT_BRANCH"], ISSUE_SCOPE["PRODUCT_PATHS"]))

    @patch.dict(os.environ, PR_HEAD_SHA="")
    def test_issued_metadata_preserves_exact_finite_invitation_candidate_witness(self):
        scope = ISSUE_SCOPE
        with tempfile.TemporaryDirectory(prefix="apbra-metadata-invitation-") as folder:
            path = Path(folder)
            run_git(path, "init", "-q", "-b", "main")
            run_git(path, "fetch", "--no-tags", str(ROOT), scope["BASE"] + ":" + scope["MAIN"])
            run_git(path, "reset", "--hard", "origin/main")
            run_git(path, "switch", "-c", "synthetic-issuance")
            for name in scope["ISSUANCE_PATHS"]:
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            run_git(path, "add", "--", *sorted(scope["ISSUANCE_PATHS"]))
            run_git(path, "commit", "-m", "Synthetic exact issuance")
            issued = scope["ref"](path, "HEAD")
            run_git(path, "switch", "main")
            run_git(path, "merge", "--no-ff", issued, "-m",
                    "Merge pull request #9876 from haseebulhaque/" + scope["ISSUANCE_BRANCH"],
                    github_fixture=True)
            release = scope["ref"](path, "HEAD")
            run_git(path, "update-ref", scope["MAIN"], release)
            self.assertEqual(scope["released_issuance"](path, OLD["raw"]), release)

            prior = runpy.run_path(path / "scripts/native_invitation_scope.py")
            recovered = runpy.run_path(path / "scripts/check_recovered_native_registration.py")
            checker = runpy.run_path(path / "scripts/check_bootstrap.py")
            native = runpy.run_path(path / "scripts/check_nv.py")
            branch, paths = prior["B"], prior["P"]
            self.assertEqual(len(paths), 28)
            run_git(path, "switch", "-c", branch)
            for name in sorted(paths):
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                previous = target.read_bytes() if target.exists() else b""
                comment = b"#" if target.suffix == ".py" else b"//"
                target.write_bytes(previous + b"\n" + comment + b" Synthetic scope fixture.\n")
            run_git(path, "add", "--", *sorted(paths))
            run_git(path, "commit", "-m", "Synthetic exact invitation fixture")
            invitation_head = scope["ref"](path, "HEAD")
            overlap, candidate = native["OVERLAP"], native["CANDIDATE"]
            witness = recovered["qualified_paths"]
            with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF="main"):
                self.assertEqual(checker["delivery_context"](path), ("APBRA-184", branch, paths))
                self.assertEqual(witness(path, checker, "APBRA-184", branch, paths, overlap, candidate), set(overlap))
                self.assertEqual(witness(path, checker, "APBRA-184", branch, paths | {"README.md"},
                                         overlap, candidate), set())
                dirty = path / sorted(paths)[0]
                clean = dirty.read_bytes()
                dirty.write_bytes(clean + b"\n")
                self.assertEqual(witness(path, checker, "APBRA-184", branch, paths, overlap, candidate), set())
                dirty.write_bytes(clean)
            wrong = branch + "-foreign"
            with patch.dict(os.environ, GITHUB_HEAD_REF=wrong, GITHUB_BASE_REF="main"):
                self.assertEqual(witness(path, checker, "APBRA-184", wrong, paths, overlap, candidate), set())

            renamed = "apps/web/e2e/native-invitations.spec.ts"
            self.assertIn(renamed, paths)
            run_git(path, "mv", "-f", "README.md", renamed)
            run_git(path, "commit", "-m", "Synthetic extra rename")
            self.assertIn("README.md", scope["changed"](path, scope["MAIN"], "HEAD"))
            with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF="main"):
                self.assertEqual(witness(path, checker, "APBRA-184", branch, paths, overlap, candidate), set())
            run_git(path, "reset", "--hard", invitation_head)

            run_git(path, "switch", "main")
            protected = "apps/api/src/apbra_api/model_provider.py"
            self.assertNotIn(protected, paths)
            target = path / protected
            target.write_bytes(target.read_bytes() + b"\n# Synthetic predecessor drift.\n")
            run_git(path, "add", "--", protected)
            run_git(path, "commit", "-m", "Synthetic unrelated trusted-main drift")
            run_git(path, "update-ref", scope["MAIN"], "HEAD")
            run_git(path, "switch", branch)
            run_git(path, "merge", "--no-ff", "main", "-m", "Compose on synthetic drift")
            self.assertEqual(scope["changed"](path, scope["MAIN"], "HEAD"), paths)
            with patch.dict(os.environ, GITHUB_HEAD_REF=branch, GITHUB_BASE_REF="main"):
                self.assertEqual(checker["delivery_context"](path), ("APBRA-184", branch, paths))
                self.assertEqual(witness(path, checker, "APBRA-184", branch, paths, overlap, candidate), set())

    @patch.dict(os.environ, PR_HEAD_SHA="")
    def test_mutual_release_lifecycle_on_disposable_git_refs(self):
        scope = ISSUE_SCOPE
        with tempfile.TemporaryDirectory(prefix="apbra-metadata-git-") as folder:
            path = Path(folder)
            run_git(path, "init", "-q", "-b", "main")
            run_git(path, "fetch", "--no-tags", str(ROOT), scope["BASE"] + ":refs/remotes/origin/main")
            run_git(path, "reset", "--hard", "origin/main")
            run_git(path, "switch", "-c", "synthetic-issuance")
            for name in scope["ISSUANCE_PATHS"]:
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            run_git(path, "add", "--", *sorted(scope["ISSUANCE_PATHS"]))
            run_git(path, "commit", "-m", "Synthetic scope source")
            head = scope["ref"](path, "HEAD")
            # A local branch, even with the exact five source files, issues nothing.
            self.assertIsNone(scope["released_issuance"](path, OLD["raw"]))
            run_git(path, "switch", "main")
            msg = "Merge pull request #9876 from haseebulhaque/" + scope["ISSUANCE_BRANCH"]
            run_git(path, "merge", "--no-ff", head, "-m", msg, github_fixture=True)
            issue_merge = scope["ref"](path, "HEAD")
            self.assertIsNone(scope["released_issuance"](path, OLD["raw"]))
            run_git(path, "update-ref", "refs/remotes/origin/main", issue_merge)
            self.assertEqual(scope["released_issuance"](path, OLD["raw"]), issue_merge)
            run_git(path, "switch", "-c", "synthetic-product")
            for name in scope["PRODUCT_PATHS"]:
                target = path / name
                target.write_bytes(target.read_bytes() + b"\n# Synthetic metadata change.\n")
            paths = scope["PRODUCT_PATHS"]
            product_branch = scope["PRODUCT_BRANCH"]
            context = ("APBRA-160", product_branch, paths)
            alternate_contexts = [
                ("APBRA-85", product_branch, paths),
                ("APBRA-160", product_branch, paths | {"apps/web/src/style.css"}),
                ("APBRA-160", product_branch, paths - {next(iter(paths))}),
            ]
            self.assertFalse(self.binding(path, product_branch, paths)[0])
            for issue, branch, changed in alternate_contexts:
                self.assertFalse(self.binding(path, branch, changed, issue)[0])
            run_git(path, "add", "--", *sorted(paths))
            run_git(path, "commit", "-m", "Synthetic successor")
            prod_head = scope["ref"](path, "HEAD")
            self.assertTrue(self.binding(path, product_branch, paths)[0])
            run_git(path, "commit", "--allow-empty", "-m", "Synthetic second commit")
            self.assertFalse(self.binding(path, product_branch, paths)[0])
            run_git(path, "reset", "--hard", prod_head)
            run_git(path, "config", "status.showUntrackedFiles", "no")
            stray = path / "unexpected-untracked.txt"
            stray.write_text("Synthetic untracked file.")
            self.assertFalse(self.binding(path, product_branch, paths)[0])
            stray.unlink()
            run_git(path, "switch", "main")
            run_git(path, "merge", "--no-ff", prod_head, "-m", "Synthetic GitHub checkout")
            checkout = scope["ref"](path, "HEAD")
            for actual_pr_head in ("", checkout, issue_merge):
                with patch.dict(os.environ, PR_HEAD_SHA=actual_pr_head):
                    self.assertFalse(self.binding(path, product_branch, paths)[0])
            with patch.dict(os.environ, PR_HEAD_SHA=prod_head):
                self.assertTrue(self.binding(path, product_branch, paths)[0])
            run_git(path, "reset", "--hard", issue_merge)
            run_git(path, "switch", "synthetic-product")
            run_git(path, "tag", "origin/main", scope["BASE"])
            self.assertEqual(scope["ref"](path, scope["MAIN"]), issue_merge)
            self.assertTrue(self.binding(path, product_branch, paths)[0])
            run_git(path, "tag", "-d", "origin/main")
            synthetic_checker = runpy.run_path(path / "scripts/check_bootstrap.py")
            synthetic_recovered = runpy.run_path(path / "scripts/check_recovered_native_registration.py")
            native = runpy.run_path(path / "scripts/check_nv.py")
            witness = synthetic_recovered["qualified_paths"]
            protected = native["OVERLAP"]
            with patch.dict(os.environ, GITHUB_HEAD_REF=product_branch, GITHUB_BASE_REF="main"):
                self.assertEqual(synthetic_checker["delivery_context"](path), context)
                faults, _ = synthetic_checker["check"](
                    path, active_task_id="APBRA-160", active_branch=product_branch, changed_paths=paths,
                )
                self.assertEqual(faults, [])
                self.assertEqual(
                    witness(path, synthetic_checker, *context, protected, native["CANDIDATE"]),
                    set(protected) | paths,
                )
                for branch in OLD["FUTURE_SLICES"]:
                    if branch == product_branch:
                        continue
                    faults, _ = synthetic_checker["check"](
                        path, active_task_id="APBRA-160", active_branch=branch,
                        changed_paths=OLD["FUTURE_SLICES"][branch],
                    )
                    self.assertIn(scope["UNISSUED"], faults)
            run_git(path, "switch", "main")
            run_git(path, "merge", "--no-ff", prod_head, "-m",
                    "Merge pull request #9877 from haseebulhaque/" + product_branch, github_fixture=True)
            release = scope["ref"](path, "HEAD")
            clean = (None, None, set())
            clean_checker = {"delivery_context": lambda root: clean}
            self.assertEqual(scope["metadata_successor"](path, clean_checker, clean, OLD), set())
            run_git(path, "update-ref", "refs/remotes/origin/main", release)
            self.assertEqual(scope["metadata_successor"](path, clean_checker, clean, OLD), paths)
            with patch.dict(os.environ, GITHUB_HEAD_REF="main", GITHUB_BASE_REF="main"):
                downstream = (None, "main", set())
                self.assertEqual(synthetic_checker["delivery_context"](path), downstream)
                self.assertEqual(
                    witness(path, synthetic_checker, *downstream, protected, native["CANDIDATE"]),
                    set(protected) | paths,
                )
            self.assertFalse(self.binding(path, product_branch, paths)[0])
            target = path / next(iter(paths))
            target.write_bytes(target.read_bytes() + b"\n")
            self.assertEqual(scope["metadata_successor"](path, clean_checker, clean, OLD), set())
