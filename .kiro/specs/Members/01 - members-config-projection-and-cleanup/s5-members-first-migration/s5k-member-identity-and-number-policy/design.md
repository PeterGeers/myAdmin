# S5k — Design (member identity & Lidnummer cleanup)

## Overview
A small, contained cleanup — NOT a numbering engine. Three changes:
1. `member_number` becomes an OPTIONAL plain string (keep the optional format validator).
2. Delete the `membernum#` uniqueness-guard mechanism (single `PutItem`).
3. `member_id` (UUID) confined to internal use.
Follows steering 36 / 35. No new config param, no projection change, no cross-plane machinery.

## D1 — `member_number`: optional fixed string, optional validation
- `member_number` stays a FIXED string (`membership.member_number`) but is now OPTIONAL — empty is
  a valid member. Remove any "required non-empty member_number" precondition in the write path.
- KEEP the existing optional `MemberNumberFormat` validation (`fixed_fields.validate_member_number_
  format`): when a tenant authored a format (regex or prefix+width), a PRESENT value must match;
  empty always passes. This already supports non-numeric regexes (free `regex` field), so
  `ABCDEFG` (`^[A-Z]{7}$`) is covered with no model change.
- **DELETE `hdcn_derive_member_number`** and its registration in `register_hdcn_hooks`
  (`tenants/hdcn/hooks.py`); keep `hdcn_validate_member`. The `DERIVE_MEMBER_NUMBER` HookName is
  retired (or left unused — decide in implementation). No generation code remains.

## D2 — Delete the uniqueness guard (single-PutItem write)
`sam/members/repository/members_repository.py` `save_member` today writes the member item PLUS a
`membernum#<number>` guard in one `TransactWriteItems` (guard = `attribute_not_exists`, and stores
`member_number`+`member_id` as a reverse lookup). Change:
- `save_member` becomes a single `PutItem` of the member record. Remove the transaction, the guard
  item, the `attribute_not_exists` condition, and the `MemberNumberConflictError` path.
- Retire the `membernum#` sort-key token from `repository/table_design.py`.
- Rollout: delete the 1152 existing `membernum#` guard rows in prod (a one-off cleanup script,
  gated/[H]).
Rationale: the guard IS fully deployed (1152 guards for 1152 members, 1:1) — so this is NOT a
"fix a broken mechanism" change; it is a deliberate SIMPLIFICATION. The guard only caught
byte-exact duplicates (no canonicalization), doubles the write path, and — with auto-numbering
rejected (no generation path needs it) — its value is negligible for a low-concurrency club admin
app. A duplicate Lidnummer is a data-quality issue, not a concurrency-correctness failure.

**Reverse-lookup note:** the guard also served as a `member_number → member_id` lookup. If any read
path relied on `membernum#<n>` to find a member by number, replace it with a query/scan or (only if
a real access pattern needs it) a GSI — CHECK during implementation. Likely nothing depends on it
(reads are by `member_id` / list).

## D3 — Optional soft duplicate-check (detect, not prevent) — OPTIONAL
On save, MAY query whether another member already has the same non-empty number and log/return a
WARNING — never blocks the write. Ship now or defer to a periodic data-quality report; decide in
implementation. Not required for the cleanup.

## D4 — member_id containment (R1)
Frontend audit: grep the members UI for `member_id` used as a displayed/administrative value
(columns, modal rows, exports, labels) and remove/replace with `member_number`. Keep `member_id`
as the internal row / React `key` only. (s5j already did the modal row.)

## Correctness properties
- **P1** A member saves with an empty `member_number` (single `PutItem`, no error).
- **P2** A present `member_number` that violates the tenant format is rejected (422); empty passes.
- **P3** No code AUTO-GENERATES a member number (no `next_counter`/derive call remains in the
  write path — the value is only ever user-entered or import-supplied); AND no tenant-name literal
  (`hdcn`/`h-dcn`) appears in the `member_number` write/validate code. The tenant's FORMAT (h-dcn
  `M`/5) still exists but as CONFIG DATA in `member_number_format`, never a code literal.
  Verifiable by grep: no generation call, no tenant literal in the number path.
- **P4** `member_id` never appears as user-facing administration.
- **P5** No `membernum#` guard is written or read; a duplicate number does not corrupt state.

## Testing strategy
- SAM: empty-number save; present-number save; arbitrary string (`ABCDEFG`); format
  accept/reject per tenant regex; `save_member` issues a single `PutItem` (no transaction); the
  `L-`/6 hook is gone; no `membernum#` item written.
- Frontend: no `member_id` shown as administration (R1 audit; add a guard test if practical).
- Rollout: the guard-row deletion script is idempotent + tenant-scoped.

## Non-goals
- Auto-numbering engine / `number_policy` / strategy registry (rejected — see requirements).
- The "suggest next number" toggle (future, optional — requirements FUTURE section).
- Scope/access filter unchanged. Full sponsors/clubs entity modelling may be a follow-up.
