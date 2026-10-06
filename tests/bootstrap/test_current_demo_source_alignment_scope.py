"""Append-only APBRA-160 current-demo source provenance."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bootstrap_current_sources", ROOT / "scripts/check_bootstrap.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
HISTORICAL_COUNT = 74
HISTORICAL_SHA256 = "1f1ecb0729abfc6b76671b621208a6c60370a838f91a67050faa7e3c0b51fa4b"
CURRENT_ROWS = (
    ("apbra-160-current-six-stage-direction", "8519682", 26, "53cb026ea98269dd7bc7dd7b7da67e0c9003557c183c77467ece89a546a50350"),
    ("apbra-160-current-model-led-delivery", "9404417", 7, "59aead56e1a8d3541268dbd09533c7b5803b02a9e7ab7785035c48dec6c9ffb3"),
    ("apbra-160-historical-business-shell", "8388610", 2, "b44375446b2ce03e03c22136aa0cd74938253a88ab0c27cb7bbac89fc6ea4304"),
    ("apbra-160-conversational-ux-history", "3932422", 8, "c3eaabbceee9fa5f3f1f4cd18bfb4fe0f6a63a6b447731d920cac35bcbc6174a"),
    ("apbra-160-future-native-platform", "7864321", 2, "10502b3d6cf59134982ec231ed0081aaac7a6c8a1cd070bdd3f969d366494444"),
    ("apbra-160-use-cases-acceptance", "3932402", 5, "3faf1efa272470e3771f72f65d7a47e9d5026e12d31a689c19378f3ac9e644d5"),
    ("apbra-160-screen-interactions", "4063368", 5, "3cf12cb56cf804f3720e9215d15af34a57ec553469699cd635af072147296f3f"),
    ("apbra-160-reviewer-administration", "4063388", 6, "05749da8117cf5495cda152d1e2e1eb42a97494533ab5626f1881d583ddb05a1"),
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def provenance_errors(rows):
    errors = []
    if len(rows) != HISTORICAL_COUNT + len(CURRENT_ROWS):
        errors.append("unexpected source count")
    if digest(rows[:HISTORICAL_COUNT]) != HISTORICAL_SHA256:
        errors.append("historical source rows changed")
    if [row.get("id") for row in rows[HISTORICAL_COUNT:]] != [item[0] for item in CURRENT_ROWS]:
        errors.append("current source block is not exact and append-only")
    if len({row.get("id") for row in rows}) != len(rows):
        errors.append("source IDs are not unique")
    for source_id, content_id, version, expected_sha in CURRENT_ROWS:
        matches = [row for row in rows if row.get("id") == source_id]
        if len(matches) != 1:
            errors.append("missing or duplicate current source: " + source_id)
            continue
        row = matches[0]
        if (row.get("content_id"), row.get("version"), row.get("status")) != (
            content_id, version, "ACCEPTED",
        ):
            errors.append("wrong current source binding: " + source_id)
        if digest(row) != expected_sha:
            errors.append("current source row changed: " + source_id)
    return errors


class CurrentDemoSourceAlignmentScopeTests(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads((ROOT / "docs/source-register.json").read_text())["sources"]

    def test_exact_append_only_sources(self):
        self.assertEqual(provenance_errors(self.rows), [])
        self.assertIn("six-stage", self.rows[HISTORICAL_COUNT]["acceptance"])
        self.assertIn("no Foundry runtime edit", self.rows[HISTORICAL_COUNT]["acceptance"])
        self.assertIn("future capabilities", self.rows[HISTORICAL_COUNT + 4]["acceptance"])

    def test_mutations_fail_closed(self):
        variants = []
        removed = copy.deepcopy(self.rows)
        removed.pop(HISTORICAL_COUNT)
        variants.append(removed)
        extra = copy.deepcopy(self.rows)
        extra.append({"id": "unregistered-doc-source"})
        variants.append(extra)
        duplicate = copy.deepcopy(self.rows)
        duplicate[-1]["id"] = duplicate[-2]["id"]
        variants.append(duplicate)
        reordered = copy.deepcopy(self.rows)
        reordered[-1], reordered[-2] = reordered[-2], reordered[-1]
        variants.append(reordered)
        historical = copy.deepcopy(self.rows)
        historical[0]["version"] = 999
        variants.append(historical)
        for field, value in (("version", 25), ("status", "PROPOSED"), ("acceptance", "weakened")):
            changed = copy.deepcopy(self.rows)
            changed[HISTORICAL_COUNT][field] = value
            variants.append(changed)
        for rows in variants:
            with self.subTest(rows=rows[HISTORICAL_COUNT:HISTORICAL_COUNT + 1]):
                self.assertTrue(provenance_errors(rows))

    def test_exact_governance_only_branch_authority(self):
        expected = {
            "docs/source-register.json",
            "scripts/check_bootstrap.py",
            "tests/bootstrap/test_hosted_web_release_scope.py",
            "tests/bootstrap/test_current_demo_source_alignment_scope.py",
        }
        self.assertEqual(c.CURRENT_DEMO_SOURCE_BRANCH,
                         "agent/APBRA-DEVOPS/APBRA-160-current-source-alignment")
        self.assertEqual(c.CURRENT_DEMO_SOURCE_PATHS, expected)
        self.assertTrue(all("*" not in path for path in expected))

        def check(paths):
            return c.check(ROOT, active_task_id="APBRA-160",
                           active_branch=c.CURRENT_DEMO_SOURCE_BRANCH,
                           changed_paths=paths)[0]

        self.assertEqual(check(expected), [])
        for path in expected:
            with self.subTest(missing=path):
                self.assertIn("APBRA-160 current-source amendment must change exactly four governance files",
                              check(expected - {path}))
        for extra in ("apps/api/src/apbra_api/api.py", "tasks/APBRA-160-foundry-structured-output.json",
                      "docs/decisions/implementation-baseline.md", ".github/workflows/bootstrap.yml"):
            with self.subTest(extra=extra):
                self.assertIn("APBRA-160 current-source amendment must change exactly four governance files",
                              check(expected | {extra}))


if __name__ == "__main__":
    unittest.main()
