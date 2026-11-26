# Years-Member Update (Rejoin Support)

## Context

The `years_member` calculated field in `sam/members/domain/calculated_fields.py` currently computes tenure from `joined_date` only:

```python
def _derive_years_member(record, *, today=None):
    joined = _parse_iso_date(_membership(record).get("joined_date"))
    if joined is None:
        return None
    ref = today or _dt.date.today()
    years = ref.year - joined.year
    return years if years >= 0 else None
```

When a member leaves (`status = "left"`) and rejoins years later with a new `joined_date`, the old tenure is lost: `2026 - 2026 = 0` instead of `previous_years + 0`.

## Problem

**Requirement:** `years_member` must include years from prior membership periods when a member ends membership and rejoins.

**Key insight:** Prior-period tenure cannot be derived once `joined_date` is overwritten on rejoin — the old period leaves no trace. So at least ONE minimal value MUST be persisted.

## Constraint (AVG/GDPR)

We must not retain user-related data longer than needed. Full historical membership tracking (a history table, event log, etc.) is therefore **out of scope** — it would permanently store per-member tenure epochs. A single accumulated-years integer is the minimum-necessary alternative.

The Members repository (`sam/members/repository/members_repository.py`) uses a **single-table DynamoDB design** (`sam/members/repository/table_design.py`):

```
PK  tenant_id
SK  record_type#id

SK values (all in the same tenant partition):
  member#<member_id>                              -- the bare member record
  member#<member_id>#membership#<membership_id>   -- one membership of that member
  member#<member_id>#delegates                    -- delegate set (single item)
  member#<member_id>#payment#<payment_id>         -- member-scoped payment
```

**Important correction:** There are already **separate child items** for memberships (`membership_sk(member_id, membership_id)`, `delete_membership(...)`). The statement "one record per member" in the earlier draft was **incorrect** — the design natively supports multiple membership items per member under the same `member#<id>` prefix. A member can have unlimited membership periods, each a distinct DynamoDB item.

## Solution Architecture (recommended)

### Variant A — Admin-entered previous years (chosen, simplified)   [NEW PREFERRED]

Instead of a system-accumulated integer, let the **member administration** supply the prior-years figure at rejoin time as their own judgement.

```python
years_member = previous_years + (ref.year - joined.year)
```

- **No historic data needed.** No accumulation machinery, no status-change write path to maintain, no per-period retention. The admin sets `previous_years` directly at rejoin.
- **AVG:** minimal storage (one minimal integer + current `joined_date`); no per-period history retained. The retained value is the admin's judgement — a single necessary integer, within minimum necessity.
- **Simplification:** rejoin becomes: set `previous_years`, set new `joined_date`, set status `active`. Done. The whole "add elapsed years on leave / keep accumulator" write path collapses into a single admin input.

### Variant C — UUID archive (per user's design)

1. On `status -> left` / `lapsed`: purge all personal/identifying fields (name, address, email, phone, documents) from the member record, but retain minimal membership metadata: `uuid`, `member_number`, `joined_date`, `leaving_date`, plus the accumulated `previous_years_member`.
2. On rejoin: the new application resolves to the **same UUID record**. Set new `joined_date`, set status `active`. Old membership metadata (incl. accumulated prior years) remains.

Mapping: identity-based (`member[UUID].previous_years_member`), not value-based.

AVG assessment of Variant C: still personal data (art. 4(1)) → pseudonym, not anonymous; needs legal basis, retention clock, purpose limitation, erasure.

### Variant D — Multiple membership child items (already supported by the table design)

Native multiple `member#<id>#membership#<mid>` items. Pros: per-period retention. Cons: read path must `Query` the `member#<id>#membership#` prefix.

### Variant B — Full membership-history tracking (not chosen)

History table / event log; violates AVG minimisation (per-period retention).

## AVG Compliance Checklist (applies to Variants A, C, D)
1. **Legal basis (art. 6):** legitimate interest / membership agreement; financial subset under bewaarplicht (e.g., 7 years).
2. **Storage limitation (art. 5(1)(e)):** defined retention period for dormant membership records; purge/anonymise afterwards.
3. **Purpose limitation (art. 5(1)(b)):** retain only needed fields (number, dates, statuses).
4. **Right to erasure (art. 17):** delete dormant membership metadata on request unless legal obligation or legal-claim defence applies.
5. **Minimisation:** Variant A (one admin-entered integer) retains less / similar; choose based on whether exact history/reporting is needed.

## Comparison
| Variant | Stored data | AVG notes | Verdict |
|---|---|---|---|
| A | 1 admin-entered integer on bare member item | minimal; no historic data | **chosen (simplified)** |
| C | period metadata on UUID (purged contacts) | needs retention clock | use if history/reporting needed |
| D | separate `membership#` child items (already exist) | per-period retention | use if history/reporting needed |
| B | separate history table | highest risk | not chosen |

## Files involved
| File | Role |
|---|---|
| `sam/members/domain/calculated_fields.py` | `_derive_years_member()` accepts optional `previous_total`; registry entry `years_member` under `FieldGroup.MEMBERSHIP`, `inputs=("membership.joined_date")`. |
| `sam/members/domain/_membership_reads.py` | `_enrich_calculated()` merges calculated fields into record buckets (`personal` / `membership`). Add `membership.previous_years_member` injection here. |
| `sam/members/domain/fixed_fields.py` | Defines `joined_date` (fixed DATE, required) and `status` (open ENUM: `application, pending, active, suspended, lapsed, left`). Status is the trigger for updating the accumulator. |
| Frontend `fieldValue.ts` / `valueFor()` | Resolves calculated fields nested-bucket-first; `previous_years_member` resolves automatically under `membership`. |
| `sam/members/repository/table_design.py` | Key schema: `member_sk` + `membership_sk`; shows the child-item pattern already exists. |
| `sam/members/repository/_members_repository_lifecycle.py` | `delete_membership` method confirms child-item CRUD. |

## Implementation sketch
1. **Extend `_derive_years_member`** to accept `previous_years: int = 0` (the admin-entered value) and return `previous_years + elapsed_years`.
2. **Write path:** on rejoin, admin sets `previous_years`, system writes new `joined_date`, sets status `active`. (No leave-time accumulation needed.)
3. **`_enrich_calculated`** merges the calculated `years_member` (which now reads `previous_years` + current-period elapsed).

## Acceptance criteria
- [ ] `years_member` for a rejoined member equals admin-judged prior years + current tenure years.
- [ ] No historic period data retained (no accumulation history, no separate history table).
- [ ] Existing `years_member` tests still pass (`frontend/src/components/members/fieldValue.test.ts`, SAM `tests/test_field_resolver.py`).
