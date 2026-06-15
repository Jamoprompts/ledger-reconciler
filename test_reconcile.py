#!/usr/bin/env python3
"""Tests for the reconciler — stdlib unittest, zero dependencies.

Run:  python3 -m unittest -v
Each test pins one classification path plus the netting math, so a regression
in the categorization logic fails loudly instead of silently mis-reporting.
"""

import unittest

from reconcile import reconcile


def by_id(results):
    return {r["id"]: r for r in results}


class ReconcileTest(unittest.TestCase):
    def test_match_when_all_fields_agree(self):
        row = {"id": "1", "counterparty": "Acme", "amount": "100.00",
               "status": "approved", "as_of": "2026-05-31"}
        results = by_id(reconcile({"1": row}, {"1": dict(row)}))
        self.assertEqual(results["1"]["category"], "MATCH")
        self.assertEqual(results["1"]["impact"], 0.0)

    def test_field_mismatch_carries_signed_amount_delta(self):
        a = {"id": "1", "counterparty": "Acme", "amount": "100.00",
             "status": "pending", "as_of": "2026-05-31"}
        b = {**a, "amount": "90.00", "status": "approved"}
        r = by_id(reconcile({"1": a}, {"1": b}))["1"]
        self.assertEqual(r["category"], "FIELD_MISMATCH")
        self.assertAlmostEqual(r["impact"], 10.0)   # record minus downstream
        self.assertIn("status", r["detail"])

    def test_missing_in_downstream(self):
        a = {"id": "1", "counterparty": "Acme", "amount": "100.00",
             "status": "approved", "as_of": "2026-05-31"}
        r = by_id(reconcile({"1": a}, {}))["1"]
        self.assertEqual(r["category"], "MISSING_IN_DOWNSTREAM")
        self.assertAlmostEqual(r["impact"], 100.0)

    def test_orphan_in_downstream(self):
        b = {"id": "1", "counterparty": "Acme", "amount": "100.00",
             "status": "approved", "as_of": "2026-05-31"}
        r = by_id(reconcile({}, {"1": b}))["1"]
        self.assertEqual(r["category"], "ORPHAN_IN_DOWNSTREAM")
        self.assertAlmostEqual(r["impact"], 100.0)

    def test_amount_within_tolerance_is_treated_as_match(self):
        a = {"id": "1", "counterparty": "Acme", "amount": "100.00",
             "status": "approved", "as_of": "2026-05-31"}
        b = {**a, "amount": "100.01"}                       # one-cent drift
        flagged = by_id(reconcile({"1": a}, {"1": b}))["1"]
        self.assertEqual(flagged["category"], "FIELD_MISMATCH")   # default surfaces it
        tolerated = by_id(reconcile({"1": a}, {"1": b}, tolerance=0.01))["1"]
        self.assertEqual(tolerated["category"], "MATCH")          # opt-in swallows it

    def test_tolerance_does_not_mask_other_field_diffs(self):
        a = {"id": "1", "counterparty": "Acme", "amount": "100.00",
             "status": "pending", "as_of": "2026-05-31"}
        b = {**a, "amount": "100.01", "status": "approved"}
        r = by_id(reconcile({"1": a}, {"1": b}, tolerance=0.01))["1"]
        self.assertEqual(r["category"], "FIELD_MISMATCH")
        self.assertIn("status", r["detail"])
        self.assertNotIn("amount", r["detail"])             # amount tolerated, status still flagged

    def test_net_variance_sums_across_categories(self):
        a = {
            "match": {"id": "match", "counterparty": "A", "amount": "50.00",
                      "status": "approved", "as_of": "2026-05-31"},
            "diff": {"id": "diff", "counterparty": "B", "amount": "100.00",
                     "status": "approved", "as_of": "2026-05-31"},
            "gone": {"id": "gone", "counterparty": "C", "amount": "21000.00",
                     "status": "approved", "as_of": "2026-05-31"},
        }
        b = {
            "match": dict(a["match"]),
            "diff": {**a["diff"], "amount": "90.00"},   # +10 delta
            "orphan": {"id": "orphan", "counterparty": "D", "amount": "5.00",
                       "status": "approved", "as_of": "2026-05-31"},
        }
        results = reconcile(a, b)
        net = sum(r["impact"] for r in results)
        # +10 (diff) + 21000 (gone, missing downstream) + 5 (orphan) == 21015
        self.assertAlmostEqual(net, 21015.0)


if __name__ == "__main__":
    unittest.main()
