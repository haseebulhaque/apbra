"""APBRA-90 fixture integrity; no application or Power BI runtime claims."""
import csv
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

PACK = Path(__file__).parent / "fixtures" / "sales-v1"


def load(name):
    return json.loads((PACK / name).read_text())


def rows():
    result = {}
    for table in load("schema.json")["tables"]:
        with (PACK / table["file"]).open(encoding="utf-8", newline="") as stream:
            result[table["name"]] = list(csv.DictReader(stream))
    return result


def validate_data(data):
    """Validate fixture invariants without executing any supplied SQL or expressions."""
    schema = load("schema.json")
    for table in schema["tables"]:
        records = data[table["name"]]
        columns = {c["name"] for c in table["columns"]}
        identifiers = set()
        for record in records:
            if set(record) != columns or any(v == "" for v in record.values()):
                raise ValueError("Columns/nulls")
            key = record[table["primary_key"]]
            if key in identifiers:
                raise ValueError("Duplicate primary key")
            identifiers.add(key)
            for col in table["columns"]:
                value = record[col["name"]]
                if col["type"] == "integer":
                    if str(int(value)) != value:
                        raise ValueError("Integer")
                elif col["type"] == "date":
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("Date")
                elif col["type"] == "decimal":
                    d = Decimal(value)
                    if not d.is_finite() or d < 0 or format(d, ".2f") != value:
                        raise ValueError("Money")
    for rel in schema["relationships"]:
        keys = {r[rel["to_column"]] for r in data[rel["to_table"]]}
        if any(r[rel["from_column"]] not in keys for r in data[rel["from_table"]]):
            raise ValueError("Foreign key")
    for row in data["FactSales"]:
        if int(row["Quantity"]) <= 0:
            raise ValueError("Quantity")
        if Decimal(row["SalesAmount"]) != (
                int(row["Quantity"]) * Decimal(row["UnitPrice"]) -
                Decimal(row["DiscountAmount"])):
            raise ValueError("Net sales")
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    expected = [(start + timedelta(days=i)).isoformat()
                for i in range((end - start).days + 1)]
    if [r["Date"] for r in data["DimDate"]] != expected:
        raise ValueError("Calendar")


class SalesFixtureTests(unittest.TestCase):
    def test_frozen_manifest_exact_inventory_and_hashes(self):
        manifest = load("manifest.json")
        self.assertEqual(manifest["fixture_version"], "1.0.0")
        self.assertTrue(manifest["synthetic"])
        self.assertEqual(set(manifest["files"]),
                         {p.name for p in PACK.iterdir() if p.name != "manifest.json"})
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((PACK / name).read_bytes()).hexdigest(), digest, name)

    def test_csv_types_keys_relations_and_money(self):
        validate_data(rows())

    def test_ddl_matches_metadata_and_accepts_fixture(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("PRAGMA foreign_keys=ON")
            # Trusted version-controlled fixture DDL only.
            db.executescript((PACK / "schema.sql").read_text())
            data = rows()
            for table in load("schema.json")["tables"]:
                name = table["name"]
                actual = db.execute(f"PRAGMA table_info({name})").fetchall()
                self.assertEqual([r[1] for r in actual],
                                 [c["name"] for c in table["columns"]])
                self.assertEqual([r[1] for r in actual if r[5]], [table["primary_key"]])
                placeholders = ",".join("?" for _ in actual)
                db.executemany(f"INSERT INTO {name} VALUES ({placeholders})",
                               [list(r.values()) for r in data[name]])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE FactSales SET ProductId='missing' WHERE SaleId='S001'")

    def test_calendar_attributes_and_leap_day(self):
        months = "January February March April May June July August September October November December".split()
        data = rows()["DimDate"]
        self.assertEqual(len(data), 731)
        self.assertIn("2024-02-29", [r["Date"] for r in data])
        for r in data:
            d = date.fromisoformat(r["Date"])
            self.assertEqual((int(r["Year"]), int(r["Quarter"]), int(r["MonthNumber"]),
                              r["MonthName"], r["YearMonth"]),
                             (d.year, (d.month - 1) // 3 + 1, d.month, months[d.month - 1],
                              d.strftime("%Y-%m")))

    def test_hand_calculated_totals_distinct_orders_and_yoy(self):
        sales = rows()["FactSales"]
        for context in load("numeric.expectations.json")["contexts"]:
            def select(year):
                return [r for r in sales if r["SaleDate"].startswith(str(year)) and
                        ("region" not in context or r["RegionId"] == context["region"])]
            selected = select(context["year"])
            total = sum(Decimal(r["SalesAmount"]) for r in selected)
            orders = len({r["OrderId"] for r in selected})
            self.assertEqual(total, Decimal(context["sales"]))
            self.assertEqual(orders, context["orders"])
            self.assertEqual(sum(int(r["Quantity"]) for r in selected), context["quantity"])
            self.assertEqual(sum(Decimal(r["CostAmount"]) for r in selected),
                             Decimal(context["cost"]))
            n, d = map(Decimal, context["aov_fraction"])
            self.assertEqual(total / orders, n / d)
            previous = select(context["year"] - 1)
            if context["prior_sales"] is None:
                self.assertFalse(previous)
                self.assertIsNone(context["yoy_fraction"])
            else:
                prior = sum(Decimal(r["SalesAmount"]) for r in previous)
                self.assertEqual(prior, Decimal(context["prior_sales"]))
                n, d = map(Decimal, context["yoy_fraction"])
                self.assertEqual((total - prior) / prior, n / d)
        self.assertGreater(len(sales), len({r["OrderId"] for r in sales}))

    def test_clarification_and_requirement_consistency(self):
        request, expected = load("request.json"), load("requirements.expected.json")
        ids = [c["id"] for c in request["clarifications"]]
        self.assertEqual(ids, ["sales-definition", "yoy-coverage", "region-security"])
        self.assertEqual(expected["confirmed_clarification_ids"], ids)
        self.assertTrue(request["confirmation_required"])
        self.assertEqual(request["initial_state"], "AWAITING_CLARIFICATION")
        self.assertEqual(request["request_id"], expected["request_id"])
        self.assertEqual(expected["artifact_kind"], "EXPECTED_NOT_EXECUTED")
        self.assertFalse(expected["rls_required"])
        self.assertEqual(expected["comparison"],
                         {"current_year": 2025, "prior_year": 2024, "missing_or_zero_prior": "blank"})

    def test_design_bindings_and_citations(self):
        design, schema = load("design.expected.json"), load("schema.json")
        requirement, standards = load("requirements.expected.json"), load("standards.json")
        fields = {t["name"] + "." + c["name"] for t in schema["tables"] for c in t["columns"]}
        self.assertEqual(set(design["required_tables"]), {t["name"] for t in schema["tables"]})
        self.assertEqual(design["relationships"], schema["relationships"])
        self.assertEqual(design["page_filters"], requirement["filters"])
        self.assertTrue(set(design["page_filters"]) <= fields)
        self.assertEqual([p["name"] for p in design["pages"]], requirement["pages"])
        measures = {m["id"] for m in design["measures"]}
        self.assertEqual(measures, set(requirement["required_measure_ids"]))
        for page in design["pages"]:
            for visual in page["visual_intents"]:
                if "axis" in visual:
                    self.assertIn(visual["axis"], fields)
                self.assertTrue(set(visual.get("measures", [visual["measure"]] if "measure" in visual else [])) <= measures)
        rules = standards["rules"]
        self.assertEqual(len({r["evidence_id"] for r in rules}), len(rules))
        self.assertEqual(set(design["required_evidence_ids"]),
                         {r["evidence_id"] for r in rules if r["level"] == "mandatory"})
        for rule in rules:
            self.assertEqual(rule["citation"], "fixture:" + standards["pack_id"] + "/" + rule["evidence_id"])
            self.assertEqual(rule["source_version"], standards["fixture_version"])
        self.assertFalse(design["rls"]["required"])
        self.assertEqual(design["rls"]["roles"], [])

    def test_cases_are_inputs_not_fabricated_execution(self):
        cases = load("cases.json")
        self.assertEqual(cases["execution_status"], "NOT_RUN")
        self.assertEqual(cases["candidate_baseline"]["status"], "NOT_AVAILABLE")
        ids = {c["id"] for c in cases["cases"]}
        self.assertEqual(len(ids), len(cases["cases"]))
        clarifications = {c["id"] for c in load("request.json")["clarifications"]}
        for case in cases["cases"]:
            if "base" in case:
                self.assertIn(case["base"], ids)
            if "withhold_answer" in case:
                self.assertIn(case["withhold_answer"], clarifications)
        missing = next(c for c in cases["cases"] if c["id"] == "missing-prior-year")
        self.assertEqual(missing["coverage_override"]["start"], "2025-01-01")

    def test_corrupt_primary_key_is_rejected(self):
        data = rows()
        data["FactSales"][1]["SaleId"] = data["FactSales"][0]["SaleId"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_data(data)

    def test_corrupt_foreign_key_is_rejected(self):
        data = rows()
        data["FactSales"][0]["ProductId"] = "NOT_A_PRODUCT"
        with self.assertRaisesRegex(ValueError, "Foreign key"):
            validate_data(data)

    def test_wrong_net_sales_is_rejected(self):
        data = rows()
        data["FactSales"][0]["SalesAmount"] = "200.00"
        with self.assertRaisesRegex(ValueError, "Net sales"):
            validate_data(data)

    def test_missing_calendar_day_is_rejected(self):
        data = rows()
        data["DimDate"] = [r for r in data["DimDate"] if r["Date"] != "2024-02-29"]
        with self.assertRaisesRegex(ValueError, "Calendar"):
            validate_data(data)

    def test_invalid_money_and_null_are_rejected(self):
        for bad in ("NaN", "-1.00", "1.001", ""):
            with self.subTest(bad=bad):
                data = rows()
                data["FactSales"][0]["SalesAmount"] = bad
                with self.assertRaises(ValueError):
                    validate_data(data)


if __name__ == "__main__":
    unittest.main()
