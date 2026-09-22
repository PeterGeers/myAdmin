"""
S5 Step 4 — Members **migration/backfill** helpers (SAM plane).

This package holds the *importable, storage-agnostic* pieces of the h-dcn member backfill
(task 4.1), kept out of the generic domain core so the pure transform can be unit-tested
without any live system (Google Sheet / DynamoDB) and without polluting the tenant-agnostic
engine with source-specific mapping:

    hdcn_backfill.py   the pure ``map_hdcn_row`` transform (h-dcn source row -> member record)
                       + read-only source adapters (CSV/JSON export; live-DynamoDB stub)
                       + the ``BackfillPlan`` / fidelity report the runner renders.

Discipline (design R5.2 + "generic core stays tenant-agnostic", Property 5):

- ``tenant_id = "h-dcn"`` is *data this backfill stamps* — the pilot tenant value being
  written. It legitimately appears here (a migration script is the right place for
  source-specific mapping) and MUST NOT leak into the generic module core as an
  ``if tenant == "h-dcn"`` branch.
- The backfill only ever *reads* the source (a Google-Sheet CSV/JSON export or the legacy
  ``Members`` table READ-ONLY) and writes *only* to the new ``sam-members`` table via the
  repository — never modifies the live source (non-destructive, R5.2).

The runner CLI that drives these pieces (dry-run-first, ``--apply`` to write) lives at
``scripts/aws/backfill-hdcn-members.py`` alongside the task-4.0 provisioner.
"""
