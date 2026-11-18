"""Actual finite-stage controls; synthetic ref views never claim a release."""
import copy
import tarfile
import os
import io
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

ROOT=Path(__file__).resolve().parents[2]
H=runpy.run_path(ROOT/"scripts/native_invitation_scope.py")
C=runpy.run_path(ROOT/"scripts/check_bootstrap.py")
N=runpy.run_path(ROOT/"scripts/check_recovered_native_registration.py")
OLD=runpy.run_path(ROOT/"scripts/check_ci_browser_registration_v3.py")

def read(path):
    return json.loads(path.read_text())

@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        names=H["G"]|{H["MANIFEST"],"docs/source-register.json","agents/catalog.json",
            "contracts/engineering/task-contract.schema.json"}
        for name in names:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        locator=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","--absolute-git-dir"],text=True).strip()
        (root/".git").write_text("gitdir: "+locator+"\n")
        yield root

def validate(root):
    return H["validate"](root,read(root/"agents/catalog.json"),C["schema_errors"],C["task_errors"])


# Actual PR182 merge. A later product tree cannot supply registration fixtures.
REGISTRATION_COMMIT = "b29be2b7eb663c4d50fd8658cf06fa214be50a87"
REGISTRATION_TREE = "454ef242945ede7fde38ba4ba9af18bb46c1dfe7"


@contextmanager
def registration_source_view():
    """Replay the historical registration in a stand-alone test Git directory."""
    def git(root, *args):
        return subprocess.check_output(
            ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args],
            stderr=subprocess.DEVNULL, timeout=15,
        )

    git_local_variables = set(git(ROOT, "rev-parse", "--local-env-vars").decode().splitlines())
    environment = {name: value for name, value in os.environ.items() if name not in git_local_variables}
    environment.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1")
    # The historical checker launches its own Git subprocesses. Keep the
    # sanitized environment in effect for reads, fixture construction and use.
    with patch.dict(os.environ, environment, clear=True):
        original_refs = git(ROOT, "show-ref", "--head")
        index = Path(git(ROOT, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
        original_index = index.read_bytes()
        objects = git(ROOT, "rev-parse", "--path-format=absolute", "--git-path", "objects").decode().strip()
        if git(ROOT, "rev-parse", REGISTRATION_COMMIT + "^{tree}").decode().strip() != REGISTRATION_TREE:
            raise ValueError("Historical APBRA-184 registration tree differs")
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                data = git(ROOT, "archive", REGISTRATION_COMMIT)
                with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
                    if not all(member.isfile() or member.isdir() for member in bundle.getmembers()):
                        raise ValueError("Controlled source view cannot contain special entries")
                    bundle.extractall(root, filter="data")
                git(root, "init", "--template=", "--initial-branch=fixture")
                # This repo only reads the source objects. All refs and the index
                # are created by Git in this temporary directory.
                (root / ".git/objects/info/alternates").write_text(objects + "\n")
                git(root, "update-ref", "HEAD", REGISTRATION_COMMIT)
                git(root, "update-ref", "refs/remotes/origin/main", REGISTRATION_COMMIT)
                git(root, "read-tree", REGISTRATION_COMMIT)
                if git(root, "write-tree").decode().strip() != REGISTRATION_TREE:
                    raise ValueError("Historical APBRA-184 registration index differs")
                yield root
        finally:
            if git(ROOT, "show-ref", "--head") != original_refs or index.read_bytes() != original_index:
                raise AssertionError("Source-view fixture changed a real ref or index")

class FiniteStageScope(unittest.TestCase):
    def test_current_packet_exact_scope_schema_and_preserved_historical_sources(self):
        task,faults=validate(ROOT)
        self.assertEqual(faults,[])
        self.assertEqual(len(H["G"]),9)
        self.assertEqual(len(H["P"]),28)
        self.assertEqual(set(task["allowed_paths"]),H["P"])
        self.assertFalse(H["G"]&H["P"])
        for name in H["G"]|H["P"]:
            self.assertFalse(any(c in name for c in "*?["),name)
            self.assertNotIn("..",name.split("/"))
        self.assertEqual((ROOT/"docs/source-register.json").read_bytes(),
            subprocess.check_output(["git","show",H["BASE"]+":docs/source-register.json"],cwd=ROOT))
        self.assertEqual(len(read(ROOT/"docs/source-register.json")["sources"]),84)
        self.assertEqual(H["digest"](read(ROOT/"docs/source-register.json")),OLD["SOURCE_SHA"])
        self.assertTrue(H["native_released"](ROOT))

    def test_each_registration_omission_extra_path_mixed_product_and_wrong_branch_denied(self):
        task=read(ROOT/H["T"])
        self.assertEqual(H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["R"],H["G"]),[])
        for name in H["G"]:
            self.assertTrue(H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["R"],H["G"]-{name}),name)
        for paths in [set(),H["G"]|H["P"],H["G"]|{"compose.yaml"},H["G"]|{".github/workflows/bootstrap.yml"}]:
            self.assertTrue(H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["R"],paths))
        self.assertTrue(H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["B"]+"-foreign",H["P"]))

    def test_product_requires_real_registration_then_only_literal_paths(self):
        task=read(ROOT/H["T"])
        with patch.dict(H["phase_errors"].__globals__,registration_published=lambda root:False):
            for name in H["P"]:
                self.assertIn("not effective",H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["B"],{name})[0])
        with patch.dict(H["phase_errors"].__globals__,registration_published=lambda root:True):
            for name in H["P"]:
                self.assertEqual(H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["B"],{name}),[])
            for paths in [set(),H["P"]|H["G"],H["P"]|{"apps/web/package-foreign.json"}]:
                self.assertTrue(H["phase_errors"](ROOT,task,"APBRA-"+H["KEY"],H["B"],paths))
        self.assertTrue(H["phase_errors"](ROOT,None,"APBRA-"+H["KEY"],H["B"],H["P"]))

    def test_every_task_field_and_source_field_is_completely_bound(self):
        with fixture() as root:
            self.assertFalse(validate(root)[1])
            for name in [H["T"],H["S"]]:
                path=root/name;original=path.read_bytes();value=json.loads(original)
                for field in value:
                    changed=copy.deepcopy(value);changed[field]=None
                    path.write_text(json.dumps(changed))
                    self.assertTrue(validate(root)[1],(name,field))
                    path.write_bytes(original)
            task=read(root/H["T"])
            for field,value in [("allowed_paths",task["allowed_paths"]+["apps/web/src/Foreign.tsx"]),
                    ("owner_acceptance","PENDING"),("branch",H["B"]+"-foreign"),("base_commit","a"*40)]:
                changed=copy.deepcopy(task);changed[field]=value;(root/H["T"]).write_text(json.dumps(changed))
                with patch.dict(H["validate"].__globals__,TASK_SHA=H["digest"](changed)):
                    self.assertTrue(validate(root)[1],field)
            (root/H["T"]).write_text(json.dumps(task))
            previous=root/"docs/source-register.json";previous.write_bytes(previous.read_bytes()+b"\n")
            self.assertTrue(validate(root)[1],"Even registry whitespace must retain original bytes")

    def test_missing_symlink_mutated_helper_source_task_and_adr_fail_closed(self):
        with fixture() as root:
            for key,name,expected,*rest in N["FINITE_STAGES"]:
                if key==H["KEY"]:module=name
            for name in [module,H["T"],H["S"],H["A"]]:
                target=root/name;original=target.read_bytes()
                for mode in ["missing","symlink","mutated"]:
                    target.unlink()
                    if mode=="symlink":target.symlink_to(ROOT/name)
                    elif mode=="mutated":target.write_bytes(original+b"\nCHANGED")
                    modules,faults=N["finite_modules"](root)
                    if name==module or mode!="mutated":self.assertTrue(faults,(name,mode))
                    elif modules:
                        self.assertTrue(validate(root)[1],(name,mode))
                    if target.exists() or target.is_symlink():target.unlink()
                    target.write_bytes(original)

    def test_native_ancestry_tree_and_manifest_are_real_prerequisites(self):
        with patch.dict(H["native_released"].__globals__,ancestor=lambda *args:False):
            self.assertFalse(H["native_released"](ROOT))
            self.assertTrue(H["phase_errors"](ROOT,read(ROOT/H["T"]),"APBRA-"+H["KEY"],H["R"],H["G"]))
            self.assertTrue(H["phase_errors"](ROOT,read(ROOT/H["T"]),"APBRA-"+H["KEY"],H["B"],H["P"]))
        with patch.dict(H["native_released"].__globals__,git=lambda *args:b"wrong-tree\n"):
            self.assertFalse(H["native_released"](ROOT))
        with fixture() as root:
            p=root/H["MANIFEST"];p.write_bytes(p.read_bytes()+b"\n")
            self.assertFalse(H["native_released"](root))

    def test_real_main_registration_compares_every_nine_file_and_fails_on_blob_error(self):
        with fixture() as root:
            expected={name:(root/name).read_bytes() for name in H["G"]}
            def blob(_root,*args):
                self.assertEqual(args[0],"show");name=args[1].removeprefix("origin/main:")
                return expected[name]
            with patch.dict(H["registration_published"].__globals__,native_released=lambda root:True,git=blob):
                self.assertTrue(H["registration_published"](root))
                for name in H["G"]:
                    p=root/name;original=p.read_bytes();p.write_bytes(original+b"\n")
                    self.assertFalse(H["registration_published"](root),name);p.write_bytes(original)
            def fail(*args):raise subprocess.CalledProcessError(1,["git"])
            with patch.dict(H["registration_published"].__globals__,native_released=lambda root:True,git=fail):
                self.assertFalse(H["registration_published"](root))

    def test_exact_checker_and_nv_inverses_restore_all_previous_bytes_and_reject_corruption(self):
        for name,strip in [("scripts/check_bootstrap.py","finite_strip_bootstrap"),("scripts/check_nv.py","finite_strip_nv")]:
            current=(ROOT/name).read_text()
            baseline=subprocess.check_output(["git","show",H["BASE"]+":"+name],cwd=ROOT,text=True)
            self.assertEqual(N[strip](current),baseline)
            piece=N["FINITE_BOOT_HOOK"] if strip=="finite_strip_bootstrap" else N["FINITE_NV_APPEND"]
            for bad in [current.replace(piece,"",1),current+piece,current.replace(piece,piece+" ",1),current+"\n"]:
                with self.assertRaises(ValueError):N[strip](bad)
        self.assertLessEqual((ROOT/"scripts/check_bootstrap.py").stat().st_size,262076)
        for name,strip in [("scripts/check_bootstrap.py","strip_bootstrap"),("scripts/check_nv.py","strip_nv")]:
            self.assertEqual(N[strip]((ROOT/name).read_text()),
                subprocess.check_output(["git","show",OLD["BASE"]+":"+name],cwd=ROOT,text=True))
        self.assertEqual(runpy.run_path(ROOT/"scripts/check_nv.py")["PUBLIC_BOOT_EDITS"],N["BOOT_EDITS"])
        for name,key in [("scripts/check_bootstrap.py","BOOT_EDITS"),("scripts/check_nv.py","NV_EDITS")]:
            source=(ROOT/name).read_text()
            for before,after in N[key]:
                self.assertEqual(source.count(after),1,(name,key))

    def test_prospective_witness_requires_context_original_pins_and_complete_check(self):
        nv=runpy.run_path(ROOT/"scripts/check_nv.py")
        context=("APBRA-"+H["KEY"],H["R"],H["G"])
        # Replay the complete PR182 registration with its historical checker.
        # The actual checkout and its current checker are exercised below.
        with registration_source_view() as view:
            historical = runpy.run_path(view / "scripts/check_bootstrap.py")
            calls=[]
            def canonical(*args,**kwargs):
                calls.append(kwargs)
                return historical["check"](*args,**kwargs)
            model={**historical,"delivery_context":lambda root:context,"check":canonical}
            args=(view,model,*context,nv["OVERLAP"],nv["CANDIDATE"])
            self.assertEqual(H["qualified_paths"](*args),set(nv["OVERLAP"]))
            self.assertEqual(len(calls),1)
            failed=[]
            def fail(*a,**k):failed.append(k);return ["retained failure"],{}
            supplied={**model,"check":fail}
            self.assertEqual(H["qualified_paths"](view,supplied,*args[2:]),set())
            self.assertEqual(len(failed),1)
            supplied={**model,"delivery_context":lambda root:("APBRA-85",None,set())}
            self.assertEqual(H["qualified_paths"](view,supplied,*args[2:]),set())
            with patch.dict(H["qualified_paths"].__globals__,ancestor=lambda *args:False):
                self.assertEqual(H["qualified_paths"](*args),set())
            bad={**nv["OVERLAP"],next(iter(nv["OVERLAP"])):"0"*64}
            self.assertEqual(H["qualified_paths"](view,model,*context,bad,nv["CANDIDATE"]),set())
        # The actual current branch is also exercised. A foreign/main/product
        # invocation must deny this hypothetical registration context.
        actual=C["delivery_context"](ROOT)
        result=H["qualified_paths"](ROOT,C,*context,nv["OVERLAP"],nv["CANDIDATE"])
        self.assertEqual(result,set(nv["OVERLAP"]) if actual==context else set())

    def test_historical_fixture_ignores_inherited_git_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            with patch.dict(os.environ, {
                "GIT_DIR": str(outside / "git"),
                "GIT_COMMON_DIR": str(outside / "common"),
                "GIT_INDEX_FILE": str(outside / "index"),
                "GIT_OBJECT_DIRECTORY": str(outside / "objects"),
                "GIT_WORK_TREE": str(outside / "worktree"),
            }):
                with registration_source_view() as view:
                    self.assertEqual(
                        H["git"](view, "rev-parse", "HEAD", "origin/main").decode().splitlines(),
                        [REGISTRATION_COMMIT, REGISTRATION_COMMIT],
                    )
                    self.assertEqual(H["git"](view, "write-tree").decode().strip(), REGISTRATION_TREE)
            self.assertEqual(list(outside.iterdir()), [])

    def test_historical_canonical_registration_and_foreign_identity_do_not_accumulate_authority(self):
        with registration_source_view() as view:
            historical = runpy.run_path(view / "scripts/check_bootstrap.py")
            check = historical["check"]
            identity = "APBRA-" + H["KEY"]
            self.assertEqual(check(view, active_task_id=identity, active_branch=H["R"], changed_paths=H["G"])[0], [])
            self.assertTrue(check(view, active_task_id=identity, active_branch=H["R"], changed_paths=H["G"] | H["P"])[0])
            self.assertTrue(check(view, active_task_id=identity, active_branch=H["B"], changed_paths=H["G"])[0])
            self.assertTrue(check(view, active_task_id="APBRA-999", active_branch=H["R"], changed_paths=H["G"])[0])

if __name__=="__main__":
    unittest.main()
