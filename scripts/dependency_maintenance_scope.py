"""Finite accepted stage; registration and product release are separate."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

KEY = '185'
BASE = '2d7fd0f2121c4bc6a6be6aa70ece317428168c28'
NATIVE = "edeb26101fb1ad0e9d35871520392e6aa2148047"
TREE = "3ae7c67ddaf91c53ff060babf14c617732117440"
B = 'agent/APBRA-DEVOPS/APBRA-185-development-dependency-maintenance'
R = 'agent/APBRA-DEVOPS/APBRA-185-dependency-registration'
T = 'tasks/APBRA-185-development-dependency-maintenance.json'
S = 'docs/source-register-apbra185.json'
A = 'docs/decisions/development-dependency-maintenance.md'
G = set(['docs/decisions/development-dependency-maintenance.md', 'docs/source-register-apbra185.json', 'scripts/check_bootstrap.py', 'scripts/check_nv.py', 'scripts/check_recovered_native_registration.py', 'scripts/dependency_maintenance_scope.py', 'tasks/APBRA-185-development-dependency-maintenance.json', 'tests/bootstrap/test_dependency_maintenance_scope.py', 'tests/bootstrap/test_recovered_native_registration_scope.py'])
P = set(['apps/web/package-lock.json', 'apps/web/package.json', 'docs/engineering/development-dependency-security.md'])
TASK_SHA = 'f87425e8848cd96f8297d7f50c4d0ee4a2282dcc7df83880ed3bfad9a51974de'
SOURCE_SHA = '736fbf05bb61602b9a2811cc680937b9943259a4ed28167b002f77675ee5fe5d'
DOC_SHA = '7d9419302dadc0a9a95bb4f3eb2fc2bd0e7db08755a201fe1d5a27b3f2ead8d9'
OLD_SOURCE_SHA = "086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e"
OLD_SOURCE_OBJECT = "05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb"
MANIFEST = "docs/engineering/recovered-native-frozen-manifests-v3.json"
MANIFEST_SHA = "d88d66f5012f932812366e8b77a0efae844af75db568716a46ecd0b3d9b1d162"

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def safe(root,name):
    p=root/name
    return p.is_file() and not p.is_symlink() and not any(
        part.is_symlink() for part in p.parents if part==root or root in part.parents)

def raw(root,name):
    if not safe(root,name):raise ValueError("Missing or unsafe finite stage file: "+name)
    return (root/name).read_bytes()

def git(root,*args):
    return subprocess.check_output(["git","-C",str(root),*args],stderr=subprocess.DEVNULL,timeout=10)

def ancestor(root,sha,ref):
    return subprocess.run(["git","-C",str(root),"merge-base","--is-ancestor",sha,ref],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode==0

def native_released(root):
    """Immutable actual merged native tree, not a local observed-source claim."""
    try:
        return (all(ancestor(root,BASE,ref) for ref in ("HEAD","origin/main"))
            and ancestor(root,NATIVE,BASE)
            and git(root,"rev-parse",BASE+"^{tree}").decode().strip()==TREE
            and git(root,"rev-parse",NATIVE+"^{tree}").decode().strip()==TREE
            and hashlib.sha256(raw(root,MANIFEST)).hexdigest()==MANIFEST_SHA)
    except (OSError,ValueError,subprocess.SubprocessError):
        return False

def registration_published(root):
    """Every governance path must be the actual main version before product edits."""
    try:
        return native_released(root) and all(
            git(root,"show","origin/main:"+name)==raw(root,name) for name in G)
    except (OSError,ValueError,subprocess.SubprocessError):
        return False

def validate(root,catalog,schema_errors,task_errors):
    try:
        task=json.loads(raw(root,T))
        extension=json.loads(raw(root,S))
        previous=json.loads(raw(root,"docs/source-register.json"))
        faults=schema_errors(json.loads(raw(root,"contracts/engineering/task-contract.schema.json")),task)
        if digest(task)!=TASK_SHA:faults.append(KEY+" complete task binding differs")
        if digest(extension)!=SOURCE_SHA:faults.append(KEY+" complete accepted-source binding differs")
        if hashlib.sha256(raw(root,A)).hexdigest()!=DOC_SHA:faults.append(KEY+" accepted ADR bytes differ")
        if (hashlib.sha256(raw(root,"docs/source-register.json")).hexdigest()!=OLD_SOURCE_SHA
                or digest(previous)!=OLD_SOURCE_OBJECT):
            faults.append(KEY+" original historical source registry differs")
        rows=extension["sources"]
        oldids=[r["id"] for r in previous["sources"]]
        newids=[r["id"] for r in rows]
        if (len(set(newids))!=len(newids) or set(oldids)&set(newids)
                or any(row.get("status")!="ACCEPTED" for row in rows)):
            faults.append(KEY+" new source IDs shadow, duplicate or lack acceptance")
        if not faults:faults+=task_errors(task,catalog,{**previous,"sources":previous["sources"]+rows})
        if (task.get("task_id"),task.get("assigned_agent"),task.get("agent_card_version"),
                task.get("base_commit"),task.get("branch"),task.get("task_mode"),
                task.get("readiness"),task.get("owner_acceptance"))!=(
                "APBRA-"+KEY,"APBRA-DEVOPS","0.1",BASE,B,"IMPLEMENTATION",
                "READY_FOR_IMPLEMENTATION","RECORDED"):
            faults.append(KEY+" accepted task/card/base/branch/state differs")
        if task.get("allowed_paths") is None or set(task["allowed_paths"])!=P or len(task["allowed_paths"])!=len(P):
            faults.append(KEY+" literal product paths differ")
        if any(not isinstance(p,str) or re.search(r"[*?\[]",p) or ".." in p.split("/") for p in P|G):
            faults.append(KEY+" unsafe or wildcard literal path")
        return (None if faults else task),faults
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
        return None,[KEY+" finite stage authority unreadable or unsafe"]

def phase_errors(root,task,identity,branch,paths):
    if identity!="APBRA-"+KEY:
        return []
    if not native_released(root):return [KEY+" actual merged native prerequisite missing"]
    if branch==R:
        if task is None or paths!=G:return [KEY+" registration requires exact nine governance paths"]
        return []
    if branch!=B:return [KEY+" unregistered branch"]
    if task is None or not paths or not paths<=P:return [KEY+" product requires literal finite scope"]
    if not registration_published(root):return [KEY+" registration is not effective on actual main"]
    return []

def bind(root,catalog,schema_errors,task_errors,identity,branch,paths):
    task,faults=validate(root,catalog,schema_errors,task_errors)
    faults+=phase_errors(root,task,identity,branch,paths)
    if task is None:return (),faults
    if identity=="APBRA-"+KEY and branch==R:
        registration=copy.deepcopy(task)
        registration.update(branch=R,allowed_paths=sorted(G),
            objective="Registration only: "+task["objective"])
        return ((registration,G),),faults
    return ((task,P),),faults

def qualified_paths(root,checker,identity,branch,paths,overlap,candidate):
    """A prospective readback is finite authority plus full canonical checks, not release."""
    try:
        if identity!="APBRA-"+KEY or branch not in (R,B):
            return set()
        if (identity,branch,paths)!=checker["delivery_context"](root):return set()
        task,faults=validate(root,json.loads(raw(root,"agents/catalog.json")),
            checker["schema_errors"],checker["task_errors"])
        faults+=phase_errors(root,task,identity,branch,paths)
        if faults:return set()
        if not all(ancestor(root,candidate,ref) for ref in ("HEAD","origin/main")):return set()
        for name,expected in overlap.items():
            if hashlib.sha256(git(root,"show",candidate+":"+name)).hexdigest()!=expected:return set()
            if branch==R or name not in P:
                if raw(root,name)!=git(root,"show","origin/main:"+name):return set()
        faults,_=checker["check"](root,active_task_id=identity,active_branch=branch,changed_paths=paths)
        return set() if faults else set(overlap)
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError,RecursionError):
        return set()
