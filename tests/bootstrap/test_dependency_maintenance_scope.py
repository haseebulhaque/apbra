"""Actual finite-stage controls; synthetic ref views never claim a release."""
import copy
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
H=runpy.run_path(ROOT/"scripts/dependency_maintenance_scope.py")
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

class FiniteStageScope(unittest.TestCase):
    def test_current_packet_exact_scope_schema_and_preserved_historical_sources(self):
        task,faults=validate(ROOT)
        self.assertEqual(faults,[])
        self.assertEqual(len(H["G"]),9)
        self.assertEqual(len(H["P"]),3)
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
        args=(ROOT,C,"APBRA-"+H["KEY"],H["R"],H["G"],nv["OVERLAP"],nv["CANDIDATE"])
        self.assertEqual(C["delivery_context"](ROOT),args[2:5])
        self.assertEqual(H["qualified_paths"](*args),set(nv["OVERLAP"]))
        calls=[]
        def fail(*a,**k):calls.append(k);return ["retained failure"],{}
        supplied={**C,"check":fail}
        self.assertEqual(H["qualified_paths"](ROOT,supplied,*args[2:]),set())
        self.assertEqual(len(calls),1)
        supplied={**C,"delivery_context":lambda root:("APBRA-85",None,set())}
        self.assertEqual(H["qualified_paths"](ROOT,supplied,*args[2:]),set())
        with patch.dict(H["qualified_paths"].__globals__,ancestor=lambda *args:False):
            self.assertEqual(H["qualified_paths"](*args),set())
        bad={**nv["OVERLAP"],next(iter(nv["OVERLAP"])):"0"*64}
        self.assertEqual(H["qualified_paths"](ROOT,C,*args[2:5],bad,nv["CANDIDATE"]),set())

    def test_current_canonical_registration_and_foreign_identity_do_not_accumulate_authority(self):
        self.assertEqual(C["check"](ROOT,active_task_id="APBRA-"+H["KEY"],active_branch=H["R"],changed_paths=H["G"])[0],[])
        self.assertTrue(C["check"](ROOT,active_task_id="APBRA-"+H["KEY"],active_branch=H["R"],changed_paths=H["G"]|H["P"])[0])
        self.assertTrue(C["check"](ROOT,active_task_id="APBRA-"+H["KEY"],active_branch=H["B"],changed_paths=H["G"])[0])
        self.assertTrue(C["check"](ROOT,active_task_id="APBRA-999",active_branch=H["R"],changed_paths=H["G"])[0])

if __name__=="__main__":
    unittest.main()
