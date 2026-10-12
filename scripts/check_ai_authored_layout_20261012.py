"""Additive outcome-bounded AI geometry authority; all prior authorities stay historical."""
from collections import OrderedDict
import functools
import hashlib
import json
import math

P = {'apps/api/src/apbra_api/config.py', 'apps/api/src/apbra_api/generation.py', 'apps/api/src/apbra_api/model_provider.py', 'apps/api/src/apbra_api/tenant_settings.py', 'apps/api/tests/test_api.py', 'apps/api/tests/test_config.py', 'apps/api/tests/test_generation.py', 'apps/api/tests/test_model_provider.py', 'apps/api/tests/test_tenant_settings.py', 'apps/web/e2e/protected-generation.spec.ts', 'apps/web/e2e/tenant-settings.spec.ts', 'apps/web/knowledge/report-design-format-contract-v2.md', 'apps/web/scripts/generation-bridge.ts', 'apps/web/src/App.test.tsx', 'apps/web/src/EnterpriseApp.tsx', 'apps/web/src/aiGeometry.test.ts', 'apps/web/src/aiGeometry.ts', 'apps/web/src/foundry.test.ts', 'apps/web/src/foundry.ts', 'apps/web/src/genericPowerBI.test.ts', 'apps/web/src/genericPowerBI.ts', 'apps/web/src/guardrail.test.ts', 'apps/web/src/guardrail.ts', 'apps/web/src/rag.test.ts', 'apps/web/src/rag.ts', 'apps/web/src/reportDesignNormalization.test.ts', 'apps/web/src/reportDesignNormalization.ts', 'apps/web/src/tenant.ts'}
G = {'scripts/check_ai_authored_layout_20261012.py', 'scripts/check_bootstrap.py', 'tasks/APBRA-160-ai-authored-layout-20261012.json', 'tests/bootstrap/test_ai_authored_layout_20261012_scope.py'}
B = 'agent/APBRA-DEVOPS/APBRA-160-ai-authored-layout'
R = 'agent/APBRA-DEVOPS/APBRA-160-ai-authored-layout-registration'
BASE = 'fbbd1b9c2cbde8b89bef8dfd55e29a0c6b1fedef'
ACTOR = 'Codex via haseebulhaque authenticated GitHub and Atlassian tools'
OWNER = 'Haseeb Ul Haque'
AUTHORITY = 'Haseeb directly renewed existing-MVP development at 2026-10-11T23:11:44Z and 2026-10-11T23:12:19Z until the bounded existing MVP correction is complete; this is outcome-bounded additive authority with no invented future expiry. Jira APBRA-160 comment10757 and current Confluence delivery records preserve all historical authorities and expired cutoffs as history.'
TASK_SHA = '3dc40d08e8e5e0e1fa1b7c35506059d1cd48f0af23433d938647dd577a303a10'
GATES = {'requirements': '235ae211e31af4c4b07ee0e3aeb3e3ff5a5074009b803a9e4484e924bdb65d3e', 'adrs': 'f4ad3f39f21bea167c79c0dd1ea0cfee35dba888c0cbc435b692b61f14701373', 'architecture_refs': '4759a3264b351d2c926eab083ac5b06d884acc61908350acb2fd647ffc5cb944', 'restricted_paths': '8efeef4ebffde9f48e8bf124c482f304063e3550acbbd2271354837fb1db0ae6', 'acceptance_criteria': '48b01d2c007f7b29ce9d1b786e5f3cb31800197f6d9e839b807cead9d42d70b0', 'verification_required': 'c848b06f981c0aabb577390a5b6754895c4a80059a436d1d0dd05bea08e096b3', 'out_of_scope': 'e29ea3da1aace255e4d9d8aa4ec2c89e9e8f4f3ced3c589c7eb5a30f81de6ef0', 'escalate_when': '4e826070a3ab7ee8da62a3bf2cee68715564570929d0e471e44b4596afafe67f', 'dependencies': '6ebf1c6c306793ac851999562e1a7be8d78b6e2bc121c2807e915b760527be2a', 'effective_release': '70d45f9f98d19e5d0efbe75768d5831e4963db9ca8b9f64d133198433fb4bec3', 'owner_acceptance': '6f105f5731b79c03247a9e657ec1eb6993e0a3c8b07f0527b5809daf82f2ae11', 'source_ids': 'cd1caf07ef536b903925f1bf8799dc59d6728464a6503e1570436a3e9a95c8b2', 'task_mode': '3e4f9b13887d4518542eac030c3e675f85a206e355823e8d1afbaf1b8b4c20c2', 'readiness': '3a67d3485c1c494d3642204d9a0236f717e45048cf8e8ce235474e7f826d6582'}
SOURCES = [('apbra-160-editable-first-draft-direction', '8519682', 28, 'cd53001720d227702d54bb89c5acdab7d18ba7b50f6c05b4ba166731bcc112af'), ('apbra-160-editable-first-draft-delivery', '9404417', 9, 'cddfc3bb32bf5e17687733281e2afb6288833c1c360ebc81a6c6c4a1ec7e91c9')]
SOURCES_SHA = '05882f360cdb4dbbe3a3492716b89af0a5e4b24e79a4e67fea00b394a46e7bcb'
SOURCE_FILE_SHA = '086e26d0f83e76347ab709d8859dd013513240a4e86ee9861af2086f38bb0f3e'
HISTORY = ('APBRA-108-candidate-source-safety.json', 'APBRA-129-capstone-shell.json', 'APBRA-130-requirements-snapshot.json', 'APBRA-131-curated-knowledge.json', 'APBRA-132-design-plan.json', 'APBRA-133-powerbi-project.json', 'APBRA-134-validation.json', 'APBRA-135-release.json', 'APBRA-136-orchestration.json', 'APBRA-137-final-capstone-ux.json', 'APBRA-138-measure-resolution.json', 'APBRA-139-report-design-normalization.json', 'APBRA-140-capstone-documentation.json', 'APBRA-141-measure-contract-pipeline.json', 'APBRA-142-layout-repair.json', 'APBRA-143-typed-confirmed-requirements.json', 'APBRA-144-ai-native-iterative-clarification.json', 'APBRA-145-generic-time-grain-support.json', 'APBRA-146-post-capstone-mvp-baseline-reconciliation.json', 'APBRA-147-confirmation-readiness-integrity.json', 'APBRA-148-post-capstone-product-reconciliation.json', 'APBRA-151-company-lifecycle.json', 'APBRA-159-data-model-documentation-reconciliation.json', 'APBRA-160-demo-ux.json', 'APBRA-160-foundry-host.json', 'APBRA-160-foundry-qualification-renewal-20261011.json', 'APBRA-160-foundry-qualification-renewal.json', 'APBRA-160-foundry-qualification.json', 'APBRA-160-foundry-structured-output.json', 'APBRA-160-local-rekey.json', 'APBRA-160-provider-retrieval.json', 'APBRA-160-renderer-geometry-20261011.json', 'APBRA-162-invited-private-case-foundation.json', 'APBRA-163-durable-conversation-evidence-acceptance.json', 'APBRA-164-protected-generation-output-history.json', 'APBRA-169-business-friendly-ux-application-shell.json', 'APBRA-170-professional-saas-experience-visual-system.json', 'APBRA-171-business-user-report-creation-intelligent-generation.json', 'APBRA-172-provider-neutral-sso.json', 'APBRA-173-private-content-storage.json', 'APBRA-173-production-web-release.json', 'APBRA-174-model-led-clarification-flexible-generation-delivery-guide.json', 'APBRA-175-deployment-portability-entitlement-docs.json', 'APBRA-176-owner-onboarding-identity-docs.json', 'APBRA-177-current-state-docs.json', 'APBRA-27-build.json', 'APBRA-76-deployment-guide.json', 'APBRA-85-bootstrap.json', 'APBRA-92-evaluation.json')
HISTORY_SHA = '7b11f1b578f38179aac5eb6f94dccba4ab34f9704d0754faa1d64f7b5f46cca7'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind(root, catalog, sources, validate):
    task, failures = validate(
        root, catalog, sources, filename='APBRA-160-ai-authored-layout-20261012.json',
        label='AI-authored outcome layout', branch=B, base=BASE, paths=P,
        task_sha=TASK_SHA, gates=GATES, source_bindings=SOURCES,
        sources_sha=SOURCES_SHA, count_label='28',
    )
    if task is not None:
        if (task['actual_authenticated_actor'], task['human_owner'], task['human_initiator']) != (ACTOR, OWNER, OWNER):
            failures.append('APBRA-160 AI layout actor/owner differs')
        if task['requirements'][0] != AUTHORITY:
            failures.append('APBRA-160 AI layout outcome authority differs')
        if not (root / 'scripts/check_ai_authored_layout_20261012.py').is_file():
            failures.append('APBRA-160 AI layout helper missing')
        source = root / 'docs/source-register.json'
        current = {name: hashlib.sha256((root / 'tasks' / name).read_bytes()).hexdigest()
                   for name in HISTORY if (root / 'tasks' / name).is_file()}
        if (digest(current) != HISTORY_SHA or not source.is_file() or
                hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_FILE_SHA):
            # Withdraw only additive authority; never rescue historical branches.
            return None, failures
    return (None if failures else task), failures


def stage(task_id, branch, paths):
    return task_id == 'APBRA-160' and branch == R and paths == G


def errors(task_id, branch, paths):
    if task_id == 'APBRA-160' and branch == R and paths != G:
        return ['APBRA-160 AI layout registration requires exactly four governance paths']
    if task_id == 'APBRA-160' and branch == B and (not paths or not paths <= P):
        return ['APBRA-160 AI layout product changes require only registered 28 literal paths']
    return []


class ContentMemo:
    def __init__(self, original, max_entries=128, max_key_bytes=131072, max_result_bytes=65536):
        self.original=original
        self.max_entries=max_entries
        self.max_key_bytes=max_key_bytes
        self.max_result_bytes=max_result_bytes
        self.cache=OrderedDict()
        self.hits=0;self.misses=0;self.fallbacks=0;self.evictions=0;self.original_calls=0
        functools.update_wrapper(self, original)
    def clear(self):self.cache.clear()
    def plain(self,value,ancestors=None):
        kind=type(value)
        if kind in (type(None),bool,int,str):return True
        if kind is float:return math.isfinite(value)
        if kind not in (dict,list):return False
        seen=set() if ancestors is None else ancestors
        marker=id(value)
        if marker in seen:return False
        seen.add(marker)
        try:
            if kind is dict:
                return all(type(k) is str and self.plain(v,seen) for k,v in value.items())
            return all(self.plain(v,seen) for v in value)
        finally:seen.remove(marker)
    def raw(self,schema,value,*args,**kwargs):
        self.original_calls+=1
        return self.original(schema,value,*args,**kwargs)
    def __call__(self,schema,value,*args,**kwargs):
        # Current closure accepts two args only; unsupported future/path kwargs
        # are passed untouched to original, never dropped or admitted by a cache.
        try:
            keyable = self.plain(schema) and self.plain(value)
        except (TypeError, ValueError, OverflowError, RecursionError):
            keyable = False
        if args or kwargs or not keyable:
            self.fallbacks+=1
            return self.raw(schema,value,*args,**kwargs)
        try:
            # Preserve dictionary order: exact error-message/tie ordering can
            # depend on representation. Key is complete content, not object ID,
            # file path, schema identity, authority state, digest or admission.
            key=json.dumps([schema,value],ensure_ascii=True,allow_nan=False,separators=(',',':'))
            if len(key.encode())>self.max_key_bytes:
                self.fallbacks+=1
                return self.raw(schema,value)
        except (TypeError,ValueError,OverflowError,RecursionError):
            self.fallbacks+=1
            return self.raw(schema,value)
        if key in self.cache:
            self.hits+=1
            cached=self.cache.pop(key);self.cache[key]=cached
            return list(cached)
        self.misses+=1
        errors=self.raw(schema,value)  # Exceptions are never cached.
        if type(errors) is not list or any(type(error) is not str for error in errors):
            return errors
        try:
            result_bytes = sum(len(error.encode()) for error in errors)
        except UnicodeEncodeError:
            return errors
        if result_bytes>self.max_result_bytes:
            return errors
        self.cache[key]=tuple(errors)
        if len(self.cache)>self.max_entries:
            self.cache.popitem(last=False);self.evictions+=1
        return list(errors)


def memo_schema_errors(original):
    """Memo only supplied JSON schema/value error content, never authority or I/O."""
    return ContentMemo(original)
