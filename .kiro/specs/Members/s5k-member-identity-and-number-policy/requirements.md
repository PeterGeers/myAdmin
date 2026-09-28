# S5k — Member identity & Lidnummer cleanup

## Summary
A SMALL cleanup of member identity + the Lidnummer (`member_number`), driven by the real need to
store non-person entities (sponsors, clubs) and by findings during s5j review. Scope deliberately
kept minimal:

1. **`member_id` (UUID) is internal-only** — never shown as administration.
2. **`member_number` (Lidnummer) is a plain OPTIONAL string** — manually entered or imported; any
   format (`M00012`, `ABCDEFG`, or empty). An OPTIONAL per-tenant format regex validates it.
3. **Delete the `membernum#` uniqueness-guard mechanism** — overhead solving a non-problem.
4. **Auto-numbering is REJECTED** (too complex for a simple administration) — see "Considered &
   rejected". A cheap opt-in "suggest next number" UX is noted as a possible FUTURE parameter, not
   built here.

Governs the SAM Members module (`sam/members`) + a small frontend audit. Follows steering
`36-config-and-parameters.md` and `35-sam-module-architecture-sam.md`.

## Background (verified 2026-09-24 — prod `sam-members` + code)
- `member_number` is a FIXED string field (`membership.member_number`, `MEMBER_NUMBER_FIELD_KEY`
  in `fixed_fields.py`; stores under the `membership` bucket — NOT an overlay field). Its optional
  tenant FORMAT is a `MemberNumberFormat` attached via a `fixed_overrides` entry in the
  `members.field_overlay` param (h-dcn `^M\d{5}$`), which VALIDATES a value — it does not generate.
- **h-dcn partition of `sam-members` = 2311 items, by record type:** `member#` = **1152** (the
  actual members — matches the app), `membernum#` = **1152** (the uniqueness guards, 1:1 with
  members), `membershiptype#` = **7** (the Lidmaatschap Beheer catalog config). Members are
  numbered `M#####` (imported); `member_id`/sk is the UUID (`member#<uuid>`), an internal key.
  (The larger tenant config — `config#fields`/`config#scope`/`config#views` — lives in the SEPARATE
  `governance_projection` table, not here.) The guard cleanup below touches ONLY the 1152
  `membernum#` rows — never `member#` or `membershiptype#`.
- The write path today writes a member record PLUS a `membernum#<number>` uniqueness guard in one
  `TransactWriteItems` (guard holds `member_number` + `member_id`, so it doubles as a reverse
  lookup). The guard is FULLY deployed — **1152 guards for 1152 members (1:1)** — so it IS
  consistently maintained today. It is nonetheless removed here (see below): the value it provides
  is negligible for a low-concurrency club admin app, and — with auto-numbering rejected — there is
  no auto-generation path that even needs it.
- A stale generation hook `hdcn_derive_member_number` (`tenants/hdcn/hooks.py`) hardcodes `L-`/6
  and IGNORES the format param — effectively dead (imported members keep their `M#####`; the hook
  never renumbers) and, if ever hit, would wrongly emit `L-000042`.

## User stories

### US1 — member_id is internal-only
As a tenant admin/user, I want the human-facing **Lidnummer** everywhere I read/manage members and
never the internal **`member_id`** (UUID), so the administration is not confusing.

### US2 — Lidnummer is a plain optional string
As a tenant admin, I want to enter/import the Lidnummer as a free string (or leave it empty), so
any tenant's numbering scheme — numeric `M00012`, alphanumeric `ABCDEFG`, or none — is supported
without special code.

### US3 — sponsors / clubs (the driver)
As a tenant admin, I want to RE-IMPORT the gsheet JSON with sponsor / other-club rows and have them
stored in the members module (typically with no Lidnummer), so numberless / non-person entities are
supported WITHOUT new entity-kind code — using the optional Lidnummer (this cleanup) + an existing
`membership_type` catalog entry (e.g. `sponsor`, `club`) + overlay/`show_when` field tuning.

## Requirements

### R1 — member_id internal-only
- **R1.1** `member_id` (UUID / row key) MUST NOT appear as a user-facing administrative field:
  not a table column, modal row/label, editable field, or export field. (s5j removed the modal
  UUID row as a point fix.)
- **R1.2** The human-facing identifier in all UI is the Lidnummer (`member_number`).
- **R1.3** Audit the frontend for any remaining `member_id` UI leak and remove it. `member_id`
  stays the internal row / React key only.

### R2 — Lidnummer is a plain optional string (no generation)
- **R2.1** `member_number` stays a FIXED string, now OPTIONAL: empty/absent is a valid member. No
  auto-generation of any kind.
- **R2.2** KEEP the optional per-tenant `member_number_format` validation (already built): when a
  tenant authors a format (regex or prefix+width, e.g. `^M\d{5}$` or `^[A-Z]{7}$`), a PRESENT value
  must match; an absent format imposes only "non-blank when present." Empty is always allowed.
- **R2.3** DELETE the stale `hdcn_derive_member_number` hook + its registration (keep
  `hdcn_validate_member` — the motorcycle rule is genuinely bespoke). No tenant-name branch remains
  in the number path.

### R3 — delete the uniqueness-guard mechanism
- **R3.1** Remove the `membernum#<member_number>` guard: `save_member` becomes a single `PutItem`
  (no `TransactWriteItems`, no `attribute_not_exists`, no `MemberNumberConflictError`). Retire the
  `membernum#` sort-key token from `table_design.py`.
- **R3.2** Delete the 1152 existing `membernum#` guard rows in prod as part of rollout.
- **R3.3** A duplicate Lidnummer is treated as a DATA-QUALITY concern, not a correctness failure.
  An OPTIONAL soft-check (query-and-warn on save) MAY be added but never blocks a write. (Decide
  during implementation; may defer to a data-quality report.)

### R4 — verify before done
- **R4.1** SAM tests: member saves with empty number; with a present number; with an arbitrary
  string (`ABCDEFG`); format validation accepts/rejects per the tenant regex; `save_member` is a
  single `PutItem`; the stale `L-`/6 hook is gone.
- **R4.2** Frontend: no `member_id` shown as administration (R1 audit).
- **R4.3** Suites green; verified in prod (a new member saves with a typed `M#####`; a sponsor
  saves numberless; no residual guard writes).

## Considered & REJECTED — auto member-number generation
An earlier draft designed a generic, config-selected numbering ENGINE (strategies
`counter`/`max_plus_one`/`manual`/`none`, a `NumberStrategyRegistry`, a `members.number_policy`
param + projection, a per-type `allocates_number` flag, cross-plane vocabulary guards).
**REJECTED (user, 2026-09-24): too complex for a simple administration.** A club admin types or
imports the Lidnummer; auto-generation + the uniqueness guard solve a problem that does not exist
here. Recorded so the decision is not silently re-litigated.

## FUTURE (optional, NOT built here) — "suggest next number" as a tenant parameter
If a tenant later wants the create-member form to PRE-FILL a suggested next number, it can be a
cheap, purely parameter-driven UX nicety — NOT a backend engine:
- a plain per-tenant toggle (e.g. `members.suggest_next_number: true/false`, default off) + reuse
  the existing `member_number_format` to shape the suggestion;
- the FRONTEND computes `max(existing) + 1` (a read, from the loaded list or a cheap endpoint),
  formats it, and pre-fills the field; the user can overtype it; on save it is a plain string.
- No persisted counter, no guard, no transaction — the suggestion is advisory. A rare duplicate is
  the same data-quality tradeoff as R3.3.
This is the "config selects behaviour" pattern (steering 36) at its trivial end (a toggle, not a
strategy engine). Add only if/when actually wanted.

## Out of scope
- Auto-numbering engine / `number_policy` / strategy registry (rejected above).
- The scope/access filter (unchanged).
- **Sponsors/clubs need NO new entity-kind model.** Once this cleanup makes the Lidnummer optional,
  re-importing the gsheet JSON with sponsor/club rows works using EXISTING mechanisms: optional
  Lidnummer + a `membership_type` catalog entry (`sponsor`, `club`) to distinguish them + the
  overlay/`show_when`/required-override to tune which fields apply per type. The ONLY thing to
  VERIFY (not necessarily build): that person-specific REQUIRED fixed fields (e.g. `birth_date`)
  do not block a non-person row — if they do, relax them per type via the existing overlay
  required-override, NOT a new "kind" model. So "full entity-kind modelling" is NOT needed and is
  removed as a scope item; a check that org rows import cleanly is a small follow-up if desired.
