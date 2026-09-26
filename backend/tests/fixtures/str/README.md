# STR test fixtures — Airbnb export samples

Committed, version-controlled sample exports used by the Airbnb ingest tests. These
must live under `backend/tests/` (NOT the git-ignored repo-root `.agent-output/`), so
CI's checkout has them — otherwise the parser raises `ValueError: All files failed to
parse: airbnb_pending.csv` and header detection returns `None`
(spec `.kiro/specs/code-quality-maintenance/full-test-suite-fixes-2026-09-26`, tasks C2/H2).

## Files

| File | Shape | Read by |
|------|-------|---------|
| `airbnb_pending.csv` | **Pending** export (no `Uitbetaald`/`Verwacht op` columns) — BOM-prefixed, US-notation `Bruto-inkomsten`, quoted European `Servicekosten` (`"42,59"`) | `tests/unit/test_str_airbnb_parser.py`, `tests/unit/test_str_processor_airbnb_scan.py` |
| `airbnb_08_2026-09_2026.csv` | **Realised** export (has `Uitbetaald` + `Verwacht op` markers) | `tests/unit/test_str_processor_airbnb_scan.py` |

Each reservation appears on TWO rows sharing one `Bevestigingscode` — a `Boeking` row
and a `Doorloop totaal` row — which the parser groups and SUMS. See
`.kiro/specs/STR/airbnb-export-format-update/design.md` for the format spec.

## Anchored expectations (do not drift without updating the tests)

These exact values are asserted by `test_str_airbnb_parser.py::TestAnchoredExamples`:

| Bevestigingscode | Boeking Bruto | Doorloop Bruto | **Gross (sum)** | Fee (sum) |
|------------------|--------------:|---------------:|----------------:|----------:|
| `HMXDT8WAFF`     | 274.80        | 76.67          | **351.47**      | **42.59** |
| `HMTFCHFWTP`     | 85.50         | 23.86          | **109.36**      | **13.25** |

## PII / anonymization

The `Gast` (guest-name) column is **anonymized** to `Guest NN` placeholders — no real
personal names in version control. Everything else is preserved byte-for-byte: BOM,
column order, spacing/padding, amounts, dates, reservation codes, and the quoted
European Servicekosten cells. No emails/phones are present. Do **not** commit a raw
export with real guest names; re-run the anonymization when refreshing (below).

## Refreshing when the Airbnb export format changes

Airbnb occasionally changes the export layout (extra preamble rows, BOM, renamed/added
columns). When that happens the fixture is refreshed DELIBERATELY, together with the
tests — never leave the tests asserting the old shape (Change-With-Tests Contract,
steering `30-backend-api-flask-mysql.md`).

1. Capture a fresh real export (pending + realised).
2. Anonymize the `Gast` column ONLY, preserving every other byte (BOM, spacing, quoting).
   A byte-preserving substitution — NOT a `csv` round-trip, which corrupts the quoted
   `"42,59"` cells and shifts columns.
3. Replace the files here and update the anchored expectations table above AND the
   assertions in `test_str_airbnb_parser.py` / `test_str_processor_airbnb_scan.py` to
   the new values, in the same change.
4. Verify: `cd backend && source .venv/bin/activate && pytest tests/unit/test_str_airbnb_parser.py tests/unit/test_str_processor_airbnb_scan.py -q` → all pass.
