# Design — Member Overview User Column Chooser (Session Columns)

- Spec: `./requirements.md` (R1–R5). Origin: `../design-options.md` Option 2.
- Scope: **frontend + a per-user persistence record on the Members SAM plane**
  (DynamoDB), modeled directly on the analytics preferred-list. The column
  selection + filter/sort is a client concern (C1–C6); the persistence (C7/C8)
  adds one small DynamoDB entity + a GET/PUT route pair + two client wrappers,
  all mirroring existing code. No change to `GET /members` or the row scope.

## Design overview

Three cooperating pieces, two of them shared:

```
FieldChecklist (shared)  ──►  ColumnChooser modal  ──►  session column keys
                                                              │
MembersPage: columns = default/context ⊕ session ──────────────┤
                                                              ▼
                              on-the-fly flatten (valueFor) → enrichedRows
                                                              ▼
          useFilterableTable (dynamic key set) → FilterableHeader per column
```

The hinge is the **flat-key rule** (proven this session): a column filters/sorts
iff its key is a flat top-level property of the row. So the design makes each
surfaced field flat *just before* the filter engine sees it, reusing the exact
accessor the cell render already uses (`valueFor`).

---

## C1 — `FieldChecklist` (shared component, extracted)

Extract the reusable checklist core out of
`frontend/src/components/members/analytics/MemberFieldPicker.tsx` into
`frontend/src/components/members/FieldChecklist.tsx`:

- **Input:** `fields: FieldConfigField[]`, `selectedKeys: string[]`,
  `disabledKeys?: string[]` (already-present columns, shown checked + locked),
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

## C2 — `ColumnChooser` (new, thin)

`frontend/src/components/members/ColumnChooser.tsx` — a Chakra modal opened from a
toolbar button on `MembersPage`:

- Lists `fields.filter(isColumnCandidate)` via `FieldChecklist`.
- `disabledKeys` = the keys already shown by the active default/context column set
  (checked + locked — R1.3/R1.4).
- `selectedKeys` = the current session columns; toggling calls back to the page.
- Output: the ordered `string[]` of surfaced keys. No `PivotConfig`, no save — pure
  session selection (R3.1).

## C3 — Column model on `MembersPage` (unify the two render paths)

Replace the two divergent render paths with a single ordered column model:

```ts
type OverviewColumn = { field: FieldConfigField; source: 'base' | 'context' | 'session' };
```

- `baseOrContextColumns` — the existing logic: the hardcoded compact set (+ region
  + full-view overlay) when the context has empty `columns`, else `contextColumns`.
  Unchanged in meaning; just produced as a list rather than hand-written JSX.
- `sessionColumns` — the surfaced keys resolved to `FieldConfigField` via the field
  config, filtered to candidates, excluding any key already in the base/context set
  (R1.4, no duplicates) and any flat alias (R3.4).
- **member_number is always first (R7):** the column model prepends the
  `member_number` field descriptor unconditionally and de-dupes it out of the rest,
  so it leads every render regardless of context or user columns and can never be
  removed. The chooser presents it as always-on, not a toggleable candidate.
- `columns = [member_number, ...baseOrContext (minus member_number), ...session]`,
  rendered by ONE `columns.map(header)` + ONE `columns.map(cell)`. Every column —
  fixed, base, context, session — gets identical `FilterableHeader` wiring
  (`filterValue` + `onFilterChange` + `sortable` + `onSort`), gated by
  `isFilterable(key)`.
- **R4.4 fallback:** if unifying the paths proves too large to land safely in one
  step, session columns are appended to whichever path is active and wired the same
  way; the trade-off (two code paths persist) is documented in `findings.md`. The
  unified model is preferred because it also makes the base overlay columns
  filterable as a side effect (debt paydown — see Strategic note).

## C4 — On-the-fly flatten (the real work)

A memo on `MembersPage` promotes the surfaced (and, if C3-unified, any nested
candidate) field keys to flat top-level keys, reusing `valueFor`:

```ts
const flatKeys = sessionColumns.map(f => f.key)
  .filter(k => !(k in FLAT_ALIASES));          // never clobber an alias (R3.4)

const enrichedRows = useMemo(
  () => memberRows.map(row => {
    const extra: Record<string, unknown> = {};
    for (const f of sessionColumns) {
      if (f.key in FLAT_ALIASES) continue;
      extra[f.key] = coerceByType(f, valueFor(row, f.group, f.key));
    }
    return { ...row, ...extra };
  }),
  [memberRows, sessionColumns],
);
```

- `coerceByType(field, value)` — new small pure helper (co-located with
  `fieldValue.ts` or in a `columnValue.ts`): `number` → `Number(value)` (NaN →
  original/empty), `date` → a sortable form (ISO string / timestamp), else the
  `String`-safe value. This is what makes R2.3 (type-correct sort) hold, since the
  filter engine stringifies but the sort compares raw values.
- `enrichedRows` feeds `useFilterableTable` (replacing the current `searchedRows`
  from Option 1 — the two compose: search narrows, flatten enriches; order is
  flatten over the searched rows, or search over enriched rows — either works since
  both are pure row transforms. Design choice: **search first, then flatten the
  surviving rows** to minimize per-keystroke work).

## C5 — Dynamic filter key set

`useFilterableTable` is given `initialFilters` = the fixed six **plus** each
surfaced key (empty string). `useColumnFilters` already reconciles on the key-set
signature (findings F-007), preserving existing filter values when the set changes
and dropping removed keys — so adding/removing a session column adds/removes its
filter input with no hook change (R4.3).

## C6 — `filterable_columns` exemption

When the active context defines `filterable_columns`, `isFilterable(key)` returns
false for keys outside it. A user-surfaced key must be treated as filterable
regardless (the user explicitly asked to work with it): `isFilterable` becomes
`filterableSet ? (filterableSet.has(key) || sessionKeys.has(key)) : true` (R2.1).

## C7 — `ColumnPreferences` persistence (mirror of the preferred-list, R6)

A new per-user, tenant-scoped DynamoDB record, built end-to-end as a parallel of
the analytics preferred-list — same shape, same `sub`-keyed privacy, same
reference-not-copy rule. Every piece below has a 1:1 model in existing code.

**Entity** — `sam/members/domain/column_preferences.py`, modeled on
`preferred_list.py`:

```python
@dataclass(frozen=True)
class ColumnPreferences:
    tenant_id: str
    sub: str                       # owning Cognito sub (user ≠ member, R11.1)
    columns: Sequence[str] = ()    # ordered field keys (refs into the field config)
    updated_at: str = ""
    # validate(): non-blank tenant_id; non-blank sub w/o key separator;
    #   columns is a list of non-blank strings (SHAPE only — a key that no
    #   longer resolves is skipped on READ, R6.6, never a validation error).
    # to_item() / from_item(): same pattern as PreferredList.
```

**Storage** — `sam/members/repository/table_design.py`: add
`RECORD_TYPE_COLUMN_PREFS = "colprefs"`, `column_prefs_sk(sub)` →
`colprefs#<sub>` (modeled on `pref_list_sk`), and `build_column_prefs_item`
(modeled on `build_pref_list_item` — stamps the tenant PK + `colprefs#<sub>` SK,
keeps `sub` addressable). Lives in the tenant partition like every other entity;
isolation is structural (PK pinned to tenant_id).

**Repository** — `members_repository.py`: `get_column_preferences(tenant_id, sub)`
and `save_column_preferences(tenant_id, entry)` — copies of
`get_preferred_list` / `save_preferred_list` (tenant-match guard, full replace,
validated before persist).

**Routes** — `sam/members/handler/routes.py`, in `RouteGroup` (reuse the analytics
group or a small new one), declared with the LITERAL path so no `{id}` placeholder
shadows it, keyed by the verified `sub` at the edge (NOT a path param):
- `GET /members/column-preferences` — `members:read` — returns
  `{ sub, columns, updated_at }` (empty `columns` when unset, R6.4).
- `PUT /members/column-preferences` — `members:write` OR `members:export` —
  replaces the list; drops blank/dupe/non-candidate keys (R6.5).

**Client** — `frontend/src/services/membersApiService.ts`:
`getColumnPreferences()` / `saveColumnPreferences(columns: string[])`, modeled on
`getPreferredList` / `savePreferredList` (unwrap `{ data }`, map `{ sub, columns,
updated_at }`). A `MemberColumnPreferences` type mirrors `MemberPreferredList`.

## C8 — Load / save wiring on `MembersPage`

- **Load:** on mount (after the field config resolves), call
  `getColumnPreferences()`; seed `sessionColumns` from the returned `columns`,
  resolving each key against the field config and skipping any that no longer
  resolves or is `member_number` (always-on, R7.3). Empty on a first-time user.
- **Save:** when the user adds/removes a column in the chooser, persist the full
  ordered key list via `saveColumnPreferences(columns)` (full replace, R6.5).
  Optimistically update local state; a failed save shows a non-blocking toast and
  keeps the local change (never loses the user's working view). member_number is
  never written (implied, R7.3).
- The persisted list is **field keys only** — never member data — so this record
  is PII-free and scope-neutral (R6.6/R6.7).

---

## Data flow (end to end)

1. User opens `ColumnChooser` → checks `years_member` (a nested calculated field).
2. `sessionColumns` gains the `years_member` descriptor.
3. `enrichedRows` memo adds `row.years_member = coerceByType(field,
   valueFor(row, 'membership', 'years_member'))` to every row.
4. `useFilterableTable` is handed the key set including `years_member` → its
   `FilterableHeader` renders a filter input and sort control.
5. Typing in it → `useColumnFilters` matches flat `row.years_member` → rows narrow.
   Sorting → `useTableSort` compares the numeric value → chronological order.
6. Stats strip + selection + export follow automatically (they read
   `processedData`), exactly as they do for the fixed columns today.

## Testing strategy (maps R5)

- **`FieldChecklist`** — extract test from `MemberFieldPicker` behaviour; grouping
  + alpha order + disabled/already-present rendering.
- **`ColumnChooser`** — lists candidates, excludes already-present, emits key set.
- **`MembersPage`** — surface a nested field → filter narrows (nested value);
  sort is type-correct (number/date); AND-compose with a column filter and with
  the Option-1 global search; no flat-alias collision; member_number always first
  + not removable; context-switch rule (OQ-1); the persistence round-trip (mock
  `getColumnPreferences` → seeds columns on load; a chooser change calls
  `saveColumnPreferences` with the full list); empty-default + dangling-key-skip.
- **SAM persistence (mirror the preferred-list suites):**
  `column_preferences` entity validation + `to_item`/`from_item`;
  `column_prefs_sk` / `build_column_prefs_item`; repository get/save (tenant match,
  full replace); route gating (members:read GET, members:write|export PUT) +
  `sub`-from-edge (never a client sub); empty-when-unset; cross-tenant / cross-user
  isolation.
- **Client wrappers** — `getColumnPreferences` / `saveColumnPreferences` service
  tests (envelope unwrap, `columns` mapping, empty default).
- Keep green: existing MembersPage / useFilterableTable / useColumnFilters /
  FilterableHeader / fieldValue / MemberFieldPicker + preferred-list SAM suites.

## Open questions

- **OQ-1 — context switch behaviour.** When the user switches view context, do
  surfaced session columns persist or clear? Proposal: **retain** them (they are
  the user's working set, independent of the admin context), excluding any that
  the newly-selected context already shows. Confirm before implementing R3.3.
- **OQ-2 — render-path unification scope.** Do C3 as a full unification (preferred,
  larger diff on the busiest member screen) or the append-only fallback (smaller,
  leaves two paths)? Decide at design sign-off; affects task sizing.
- **OQ-3 — generalize to all overlay columns?** Out of scope here, but C4 makes it
  trivial later (flatten every candidate, not only surfaced). Flag if wanted.

## Strategic note

C4 is the same "flat `row[key]` misses a nested value" fix already shipped in the
analytics stats/distributions (findings F-003/F-005, via `valueFor`). Doing it for
session columns — and, if C3 is unified, for the base overlay columns too — pays
down that latent defect on the overview rather than adding more of it. Option 1
(global search) stays independent and already shipped; this spec is additive to it.
