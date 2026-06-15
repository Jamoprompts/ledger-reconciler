# Ledger Reconciler — proof of concept

A small, working tool for the everyday reconciliation problem: the same records
live in two systems (a book of record and a downstream report), and they drift.
This keys on a shared ID, compares every field, classifies each row, and reports
exactly what disagrees and the dollar impact — instead of eyeballing two
spreadsheets side by side.

Built to demonstrate the data-analysis-and-reconciliation half of an
AI-enabled analyst workflow. The data is fictional so nothing is confidential.

## What it does

1. **Match.** Joins two sources on a shared key and confirms the rows that fully agree.
2. **Classify.** Buckets every disagreement: `FIELD_MISMATCH` (with the exact fields and the signed amount delta), `MISSING_IN_DOWNSTREAM` (in the record, not the copy), and `ORPHAN_IN_DOWNSTREAM` (in the copy, not the record).
3. **Quantify.** Reports the net amount variance and the largest single item, so the reviewer knows what to chase first.
4. **Narrate (optional).** `--summary` writes a short reviewer-facing narrative — using Claude if an API key is set, otherwise a deterministic offline summary. The prompt is instructed to use only the computed facts and invent no figures.
5. **Export (optional).** `--csv` writes the exceptions to a file for follow-up.

## Run it

```bash
python3 reconcile.py                      # the reconciliation report
python3 reconcile.py --summary            # add an AI/offline narrative
python3 reconcile.py --csv exceptions.csv # also export the exceptions
```

Sample data lives in `system_of_record.csv` and `downstream_report.csv`. They
disagree on purpose: an amount-and-status mismatch, a date drift, one record
missing downstream, and one orphan that only exists downstream.

## Design choices worth defending in an interview

- **Every disagreement is categorized, not just flagged.** "These two numbers differ" is noise; "this row is missing downstream vs that row's amount is off by 180" is something a reviewer can act on.
- **The dollar impact is signed and netted.** A reconciliation that doesn't tell you the size of the gap hasn't finished the job.
- **The AI writes the summary, never the numbers.** Totals and deltas are computed in code; the model only narrates the facts it's handed. That keeps the figures trustworthy.
- **Zero dependencies.** Standard-library Python and CSV, so it runs anywhere and is easy to read.

## Honest scope

An afternoon prototype: single-key join, four sample fields, CLI only. A
production version would handle composite keys, tolerance thresholds (e.g. ignore
sub-cent rounding), fuzzy counterparty matching, and a persisted exceptions queue.
The point is to show the reconciliation logic and the judgment behind it.

## How it maps to the JD

| JD line | Where it shows up here |
|---|---|
| Work with structured data from internal dashboards and enterprise systems | the two source files standing in for two systems |
| Reconcile inconsistencies and support routine reporting | the whole tool, plus `--csv` export |
| Use generative AI for drafting; craft prompts | `--summary` narrative with a no-fabrication prompt |
| Identify inefficiencies; propose practical solutions | categorized exceptions + net impact to triage by |
| Contribute to SOPs and documentation | this README and the inline docstring |
