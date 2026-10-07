# Design — Member Overview User Column Chooser (Session Columns)

- Spec: `./requirements.md` (R1–R7). Origin: `../design-options.md` Option 2.

## Overview

Let a user choose exactly which member fields show as columns on the overview —
adding any candidate field and removing ones they don't need — then filter and
sort on every one of them, with the chosen set **persisted per user** and
`member_number` always pinned first.

- Scope: **frontend + a per-user persistence record on the Members SAM plane**
  (DynamoDB), modeled directly on the analytics preferred-list. The column
  selection + filter/sort is a client concern (C1–C6); the persistence (C7/C8)
  adds one small DynamoDB entity + a GET/PUT route pair + two client wrappers,
  all mirroring existing code. No change to `GET /members` or the row scope.
- The hinge is the **flat-key rule** (verified this session): a column
  filters/sorts iff its key is a flat top-level property of the row. So the design
  makes each chosen field flat *just before* the filter engine sees it, reusing
  the exact accessor the cell render already uses (`valueFor`).
- All open questions are resolved (see Correctness Properties → Resolved
  decisions); the spec is Ready for implementation.

## Architecture

Three cooperating pieces, two of them shared:

```
FieldChecklist (shared)  ──►  ColumnChooser modal  ──►  chosen column keys
                                                              │
                       persist per user ◄── saveColumnPreferences (C7/C8)
                                                              │
MembersPage: columns = [member_number] ⊕ chosen ───────────────┤
                                                              ▼
                              on-the-fly flatten (valueFor) → enrichedRows
                                                              ▼
          useFilterableTable (dynamic key set) → FilterableHeader per column
```

Two planes:

- **Frontend** — the `FieldChecklist` + `ColumnChooser` UI, the unified column
  model on `MembersPage`, the on-the-fly flatten, and the dynamic filter key set.
- **Members SAM module (DynamoDB)** — a per-user `ColumnPreferences` record
  (`colprefs#<sub>`) with a `GET`/`PUT /members/column-preferences` route pair,
  built as a 1:1 mirror of the analytics preferred-list. No change to
  `GET /members` or row scope.

Data-flow walkthrough (end to end):

1. User opens `ColumnChooser` → checks `years_member` (a nested calculated field).
2. The user's chosen-column list gains `years_member`; it is persisted (C8 save)
   and the resolved column descriptor enters the column model.
3. `enrichedRows` memo adds `row.years_member = coerceByType(field,
   valueFor(row, 'membership', 'years_member'))` to every row.
4. `useFilterableTable` is handed the key set including `years_member` → its
   `FilterableHeader` renders a filter input and sort control.
5. Typing in it → `useColumnFilters` matches flat `row.years_member` → rows narrow.
   Sorting → `useTableSort` compares the numeric value → chronological order.
6. Stats strip + selection + export follow automatically (they read
   `processedData`), exactly as they do for the fixed columns today.

## Components and Interfaces

### C1 — `FieldChecklist` (shared component, extracted)

Extract the reusable checklist core out of
`frontend/src/components/members/analytics/MemberFieldPicker.tsx` into
`frontend/src/components/members/FieldChecklist.tsx`:

- **Input:** `fields: FieldConfigField[]`, `selectedKeys: string[]`,
  `disabledKeys?: string[]` (always-on, shown checked + locked),
  `functionalGroups`, `lang`, `onToggle(key)`.
- **Behaviour:** the existing `sectionFields()` grouping (functional-group
  sections in catalog order, alphabetical within), bilingual labels via the
  existing `resolveLabel`, per-field checkbox keyed by `f.key`, keyboard
  accessible — i.e. exactly today's `MemberFieldPicker` field list, lifted out.
- **`MemberFieldPicker` refactor:** it keeps composing a `PivotConfig` but renders
  its group-columns / list-columns lists *through* `FieldChecklist`. Behaviour and
  its existing `data-testid`s are preserved (its tests stay green — R5.1).
- **Rationale:** satisfies R4.1 — one widget, two thin wrappers differing only in
  output contract (`PivotConfig` vs `string[]`).

### C2 — `ColumnChooser` (new, thin)

`frontend/src/components/members/ColumnChooser.tsx` — a Chakra modal opened from a
toolbar button on `MembersPage`:

- Lists `fields.filter(isColumnCandidate)` via `FieldChecklist` — every candidate
  is selectable (R1.1 / OQ-3).
- `selectedKeys` = the currently-shown columns (checked); every other candidate is
  unchecked. Checking adds, unchecking removes — the user's selection fully
  determines the shown set (R1.3).
- `disabledKeys` = `['member_number']` only — the one always-on, non-toggleable
  column (R7.2). Everything else is freely checkable/uncheckable.
- Output: the ordered `string[]` of chosen keys. No `PivotConfig`. The page both
  applies it live AND persists it (C8).

### C3 — Unified column model on `MembersPage`

Replace the two divergent render paths with a single ordered column model:

```ts
type OverviewColumn = { field: FieldConfigField };
```

- **`chosenKeys`** — the user's own ordered list of column keys (from the persisted
  `ColumnPreferences`, C7/C8). This is the single source of which columns show.
- **First-time default (R6.4 / OQ-A → (a)):** when the user has NO saved columns,
  `chosenKeys` is seeded from the admin default/compact set — the hardcoded compact
  set (+ region + full-view overlay) when the context has empty `columns`, else the
  context's `columns`. A first-time user sees today's sensible default and can then
  customize; once they save a selection, THEIR list is authoritative.
- `chosenColumns` — `chosenKeys` resolved to `FieldConfigField` via the field
  config, filtered to candidates, de-duped, excluding `member_number` (added
  separately) and never promoting a flat alias twice (R3.4).
- **member_number is always first (R7):** the model prepends the `member_number`
  descriptor unconditionally and de-dupes it out of the rest, so it leads every
  render regardless of the chosen list and can never be removed.
- `columns = [member_number, ...chosenColumns]`, rendered by ONE
  `columns.map(header)` + ONE `columns.map(cell)`. Every column gets identical
  `FilterableHeader` wiring (`filterValue` + `onFilterChange` + `sortable` +
  `onSort`), gated by `isFilterable(key)`.
- **Context switch (OQ-1 resolved):** switching context does NOT rebuild
  `chosenKeys` for a user who has a saved list — their columns are retained; the
  context only continues to feed `default_sort` / `filterable_columns` /
  `page_size`.
- **Full unification (OQ-2 resolved):** the two legacy paths are collapsed into
  this one column model — chosen so the pattern is reusable in new SAM-backed
  tables, and because it makes the base overlay columns filterable as a side
  effect (debt paydown — see Correctness Properties). Because every column flows
  through the same wiring, **all candidate fields become first-class
  filterable/sortable columns** (R2.1 / OQ-3): no display-only column class remains.

### C4 — On-the-fly flatten

A memo on `MembersPage` promotes the chosen (and, by unification, any nested
candidate) field keys to flat top-level keys, reusing `valueFor`:

```ts
const enrichedRows = useMemo(
  () => memberRows.map(row => {
    const extra: Record<string, unknown> = {};
    for (const f of chosenColumns) {
      if (f.key in FLAT_ALIASES) continue;      // never clobber an alias (R3.4)
      extra[f.key] = coerceByType(f, valueFor(row, f.group, f.key));
    }
    return { ...row, ...extra };
  }),
  [memberRows, chosenColumns],
);
```

- `coerceByType(field, value)` — new small pure helper (co-located with
  `fieldValue.ts` or in a `columnValue.ts`): `number` → `Number(value)` (NaN →
  original/empty), `date` → a sortable form (ISO string / timestamp), else the
  `String`-safe value. This makes R2.3 (type-correct sort) hold, since the filter
  engine stringifies but the sort compares raw values.
- `enrichedRows` feeds `useFilterableTable`, composed with the Option-1 global
  search: **search first, then flatten the surviving rows** (both are pure row
  transforms; this order minimizes per-keystroke work).

### C5 — Dynamic filter key set

`useFilterableTable` is given `initialFilters` = the fixed keys **plus** each
chosen key (empty string). `useColumnFilters` already reconciles on the key-set
signature (findings F-007), preserving existing filter values when the set changes
and dropping removed keys — so adding/removing a column adds/removes its filter
input with no hook change (R4.3).

### C6 — `filterable_columns` exemption

When the active context defines `filterable_columns`, `isFilterable(key)` returns
false for keys outside it. A user-chosen key must be treated as filterable
regardless (the user explicitly asked to work with it):
`isFilterable = filterableSet ? (filterableSet.has(key) || chosenKeys.has(key)) : true`
(R2.1).

### C7 — `ColumnPreferences` persistence (mirror of the preferred-list, R6)

A new per-user, tenant-scoped DynamoDB record, built end-to-end as a parallel of
the analytics preferred-list — same shape, same `sub`-keyed privacy, same
reference-not-copy rule. Every piece has a 1:1 model in existing code. (The
entity shape is in Data Models below.)

- **Storage** — `sam/members/repository/table_design.py`: add
  `RECORD_TYPE_COLUMN_PREFS = "colprefs"`, `column_prefs_sk(sub)` →
  `colprefs#<sub>` (modeled on `pref_list_sk`), and `build_column_prefs_item`
  (modeled on `build_pref_list_item` — stamps the tenant PK + `colprefs#<sub>` SK,
  keeps `sub` addressable). Lives in the tenant partition; isolation is structural
  (PK pinned to tenant_id).
- **Repository** — `members_repository.py`:
  `get_column_preferences(tenant_id, sub)` / `save_column_preferences(tenant_id,
  entry)` — copies of `get_preferred_list` / `save_preferred_list` (tenant-match
  guard, full replace, validated before persist).
- **Routes** — `sam/members/handler/routes.py`, declared with the LITERAL path so
  no `{id}` placeholder shadows it, keyed by the verified `sub` at the edge (NOT a
  path param):
  - `GET /members/column-preferences` — `members:read` — returns
    `{ sub, columns, updated_at }` (empty `columns` when unset, R6.4).
  - `PUT /members/column-preferences` — `members:write` OR `members:export` —
    replaces the list; drops blank/dupe/non-candidate keys (R6.5).
- **Client** — `frontend/src/services/membersApiService.ts`:
  `getColumnPreferences()` / `saveColumnPreferences(columns: string[])`, modeled on
  `getPreferredList` / `savePreferredList` (unwrap `{ data }`, map `{ sub, columns,
  updated_at }`).

### C8 — Load / save wiring on `MembersPage`

- **Load:** on mount (after the field config resolves), call
  `getColumnPreferences()`; seed `chosenKeys` from the returned `columns`,
  resolving each key against the field config and skipping any that no longer
  resolves or is `member_number`. Empty response → the first-time default (C3).
- **Save:** when the user adds/removes a column in the chooser, persist the full
  ordered key list via `saveColumnPreferences(columns)` (full replace, R6.5).
  Optimistically update local state; a failed save shows a non-blocking toast and
  keeps the local change (never loses the user's working view). member_number is
  never written (implied, R7.3).
- The persisted list is **field keys only** — never member data — so this record
  is PII-free and scope-neutral (R6.6/R6.7).

## Data Models

### `ColumnPreferences` (SAM domain entity — new)

`sam/members/domain/column_preferences.py`, modeled 1:1 on `preferred_list.py`:

```python
@dataclass(frozen=True)
class ColumnPreferences:
    tenant_id: str                 # partition key; blank → cross-tenant hazard, refused
    sub: str                       # owning Cognito sub (SK id; user ≠ member, R11.1)
    columns: Sequence[str] = ()    # ordered field keys (refs into the field config)
    updated_at: str = ""           # ISO-8601 UTC, stamped on save
    # validate(): non-blank tenant_id; non-blank sub w/o key separator; columns is
    #   a list of non-blank strings (SHAPE only — a key that no longer resolves is
    #   skipped on READ, R6.6, never a validation error).
    # to_item() / from_item(): same pattern as PreferredList.
```

### DynamoDB item (new sort key in the tenant partition)

```
PK  = <tenant_id>
SK  = colprefs#<sub>                 (column_prefs_sk(sub); mirrors preflist#<sub>)
attrs = { sub, columns: [<field_key>, …], updated_at }
```

- One item per user; a full `PutItem` replace on save (exactly one preferences
  record per user). Isolation is structural (PK pinned to tenant_id); the `sub`
  is the authenticated principal, never client-supplied.

### API shapes

- `GET /members/column-preferences` → `{ data: { sub, columns: string[],
  updated_at } }`; `columns: []` when unset.
- `PUT /members/column-preferences` body `{ columns: string[] }` → same shape;
  blank / duplicate / non-candidate keys dropped server-side.

### Frontend types

- `MemberColumnPreferences` (mirrors `MemberPreferredList`): `{ sub, columns:
  string[], updated_at }`.
- `OverviewColumn` (C3): a resolved `FieldConfigField` in render order.

## Correctness Properties

### Property 1: One user-owned column set (OQ-1)
The user's persisted list IS the column set (plus always-on member_number). A
context switch retains it; the context only drives `default_sort` /
`filterable_columns` / `page_size`.
**Validates: Requirements 3.3**

### Property 2: Full unification (OQ-2)
One column model + one render loop; no append-only fallback. Reusable in new
SAM-backed tables; makes the base overlay columns filterable as a side effect
(debt paydown of the F-003/F-005 flat-key class, already fixed in analytics
stats/distributions via `valueFor`).
**Validates: Requirements 4.4**

### Property 3: Every candidate field is selectable + filterable + sortable (OQ-3, core)
With C3 + C4 no column class renders display-only.
**Validates: Requirements 1.1, 2.1**

### Property 4: First-time default = admin set (OQ-A → (a))
No saved columns → admin default/compact set + member_number.
**Validates: Requirements 6.4**

### Property 5: member_number pinned (R7)
Always first, never removable, implied in storage (rendered once even if the
stored list omits/includes it).
**Validates: Requirements 7.1, 7.3**

### Property 6: No flat-alias collision (R3.4)
Only non-alias keys are promoted; an existing flat alias is never overwritten.
**Validates: Requirements 3.4**

### Property 7: Scope-neutral + private (R6.6/R6.7)
The record stores field keys only (never member data), keyed by `sub` (private per
user); row scope stays server-enforced on `GET /members`.
**Validates: Requirements 6.6, 6.7**

### Property 8: Tenant + user isolation
PK pinned to tenant_id; `sub` resolved at the edge — no cross-tenant or cross-user
read/write.
**Validates: Requirements 6.3, 5.4**

## Error Handling

- **Save failure (network / 5xx):** keep the optimistic local change, show a
  non-blocking toast; never discard the user's working column set (C8).
- **Dangling stored key (field removed/hidden):** skipped on read, never an error
  (R6.6) — the column simply does not appear.
- **Non-candidate / blank / duplicate key in a PUT:** dropped server-side (R6.5);
  the write still succeeds with the cleaned list.
- **Empty / unset preferences:** GET returns `columns: []`; the page applies the
  first-time default (not an error — mirrors the preferred-list R11.2).
- **Malformed entry at the domain:** `ColumnPreferences.validate()` raises →
  422 at the edge (mirrors `PreferredList`); SHAPE-only, so a resolvable-later key
  is never rejected here.
- **Missing tenant / sub context:** refused (cross-tenant/cross-user hazard),
  mirroring the preferred-list guards.

## Testing Strategy

- **`FieldChecklist`** — functional-group sections in catalog order, alphabetical
  within; `disabledKeys` rendered checked + locked; `onToggle` fires; bilingual.
- **`ColumnChooser`** — lists every candidate; currently-shown ones checked;
  member_number always-on/locked; check adds + uncheck removes; emits the ordered
  key set.
- **`MembersPage`** — surface a nested field → filter narrows (nested value);
  sort is type-correct (number/date); AND-compose with a column filter and with
  the Option-1 global search; no flat-alias collision; member_number always first
  + not removable; chosen columns retained across a context switch (CP-1); the
  persistence round-trip (mock `getColumnPreferences` seeds columns on load; a
  chooser change calls `saveColumnPreferences` with the full list); first-time
  default (CP-4) + dangling-key-skip; save-failure keeps the local change.
- **SAM persistence (mirror the preferred-list suites):** `ColumnPreferences`
  entity validation + `to_item`/`from_item`; `column_prefs_sk` /
  `build_column_prefs_item`; repository get/save (tenant match, full replace);
  route gating (members:read GET, members:write|export PUT) + `sub`-from-edge
  (never a client sub); empty-when-unset; cross-tenant / cross-user isolation.
- **Client wrappers** — `getColumnPreferences` / `saveColumnPreferences` service
  tests (envelope unwrap, `columns` mapping, empty default).
- **Regression (keep green):** existing MembersPage / useFilterableTable /
  useColumnFilters / FilterableHeader / fieldValue / MemberFieldPicker +
  preferred-list SAM suites.
