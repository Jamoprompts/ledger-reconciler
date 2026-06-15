#!/usr/bin/env python3
"""
Ledger Reconciler - proof of concept
------------------------------------
Reconciles the same set of records as they appear in two systems: a system of
record (the book of record) and a downstream report (a manually maintained or
exported copy). It keys on a shared ID, compares every field, and classifies
each row so a reviewer sees exactly what disagrees and the dollar impact, instead
of eyeballing two spreadsheets side by side.

This is the everyday reconciliation loop: structured data from two sources,
inconsistencies surfaced and categorized, a clean exceptions report, and an
optional AI-written narrative. The data here is fictional so nothing is confidential.

Usage:
    python3 reconcile.py
    python3 reconcile.py --summary             # add an AI narrative (Claude if a key is set, else offline)
    python3 reconcile.py --csv exceptions.csv  # also write the exceptions to a file
    python3 reconcile.py --tolerance 0.01      # ignore amount drift <= 1 cent (off by default)
"""

import csv
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE_A = HERE / "system_of_record.csv"      # the book of record
SOURCE_B = HERE / "downstream_report.csv"     # the downstream copy
KEY = "id"
COMPARE_FIELDS = ["counterparty", "amount", "status", "as_of"]
AMOUNT_FIELD = "amount"


def load(path):
    with open(path, newline="") as f:
        return {row[KEY]: row for row in csv.DictReader(f)}


def money(row):
    try:
        return float(row[AMOUNT_FIELD])
    except (KeyError, ValueError):
        return 0.0


def reconcile(a, b, tolerance=0.0):
    """Return a list of result dicts, one per key in the union of both sources.

    `tolerance` suppresses amount differences at or below the given absolute
    value (e.g. 0.01 to ignore penny rounding). It defaults to 0.0 so the tool
    surfaces every disagreement unless an operator opts in to swallow known
    noise — reconciliation should hide nothing by default.
    """
    results = []
    for key in sorted(set(a) | set(b)):
        ra, rb = a.get(key), b.get(key)
        if ra and not rb:
            results.append({"id": key, "category": "MISSING_IN_DOWNSTREAM",
                            "impact": money(ra), "detail": f"{ra['counterparty']} present in record, absent downstream"})
        elif rb and not ra:
            results.append({"id": key, "category": "ORPHAN_IN_DOWNSTREAM",
                            "impact": money(rb), "detail": f"{rb['counterparty']} present downstream, absent in record"})
        else:
            diffs = []
            amt_delta = 0.0
            for field in COMPARE_FIELDS:
                if ra.get(field) != rb.get(field):
                    if field == AMOUNT_FIELD:
                        delta = money(ra) - money(rb)
                        # epsilon absorbs float representation error (100.01 - 100.00
                        # is not exactly 0.01) so the threshold compares cleanly
                        if abs(delta) <= tolerance + 1e-9:
                            continue  # within tolerance — treat as agreement
                        amt_delta = delta
                        diffs.append(f"amount {ra[field]} vs {rb[field]} (delta {amt_delta:+.2f})")
                    else:
                        diffs.append(f"{field} '{ra.get(field)}' vs '{rb.get(field)}'")
            if not diffs:
                results.append({"id": key, "category": "MATCH", "impact": 0.0, "detail": "all fields agree"})
            else:
                results.append({"id": key, "category": "FIELD_MISMATCH", "impact": amt_delta,
                                "detail": "; ".join(diffs)})
    return results


def report(results):
    order = ["MATCH", "FIELD_MISMATCH", "MISSING_IN_DOWNSTREAM", "ORPHAN_IN_DOWNSTREAM"]
    by_cat = {c: [r for r in results if r["category"] == c] for c in order}
    print("=" * 72)
    print("LEDGER RECONCILIATION  —  system of record  vs  downstream report")
    print("=" * 72)
    for cat in order:
        rows = by_cat[cat]
        print(f"\n{cat}  ({len(rows)})")
        for r in rows:
            tag = f"  [{r['impact']:+.2f}]" if r["impact"] else ""
            print(f"  - {r['id']}: {r['detail']}{tag}")
    exceptions = [r for r in results if r["category"] != "MATCH"]
    net = sum(r["impact"] for r in results)
    print("\n" + "-" * 72)
    print(f"{len(results)} records compared · {len(by_cat['MATCH'])} clean · "
          f"{len(exceptions)} exception(s) · net amount variance {net:+.2f}")
    print("-" * 72)
    return exceptions, net


def write_csv(results, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "category", "impact", "detail"])
        w.writeheader()
        for r in results:
            if r["category"] != "MATCH":
                w.writerow(r)
    print(f"\nWrote {path}")


def narrative(exceptions, net):
    """AI summary if a key is present; otherwise a deterministic offline summary."""
    facts = "\n".join(f"{r['id']} | {r['category']} | impact {r['impact']:+.2f} | {r['detail']}"
                      for r in exceptions)
    prompt = ("You are a reconciliation analyst. Summarize these exceptions for a reviewer in 3-4 "
              "sentences: what disagrees, the net dollar variance, and what to chase first. "
              "Use ONLY the facts given; do not invent figures.\n\n"
              f"NET VARIANCE: {net:+.2f}\nEXCEPTIONS:\n{facts}\n\nSUMMARY:")
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model="claude-sonnet-4-6", max_tokens=300,
                messages=[{"role": "user", "content": prompt}])
            return "[Claude] " + msg.content[0].text
        except Exception as e:  # noqa: BLE001
            return f"(Claude unavailable: {e})"
    # offline deterministic summary
    cats = {}
    for r in exceptions:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    parts = ", ".join(f"{n} {c.lower().replace('_', ' ')}" for c, n in cats.items())
    biggest = max(exceptions, key=lambda r: abs(r["impact"]), default=None)
    lead = f" Largest single item: {biggest['id']} ({biggest['impact']:+.2f})." if biggest and biggest["impact"] else ""
    return (f"[offline] {len(exceptions)} exception(s): {parts}. Net amount variance {net:+.2f}.{lead} "
            "Chase the field mismatches and any record missing downstream before sign-off.")


def arg_value(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


if __name__ == "__main__":
    tolerance = float(arg_value("--tolerance", 0.0))
    a, b = load(SOURCE_A), load(SOURCE_B)
    results = reconcile(a, b, tolerance=tolerance)
    exceptions, net = report(results)
    if "--summary" in sys.argv:
        print("\nNARRATIVE:")
        print("  " + narrative(exceptions, net).replace("\n", "\n  "))
    if "--csv" in sys.argv:
        i = sys.argv.index("--csv")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "exceptions.csv"
        write_csv(results, out)
