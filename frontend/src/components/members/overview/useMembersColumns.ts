/**
 * Members Overview — unified column model + row-derivation hook. Extracted from
 * `pages/MembersPage.tsx` during the file-length split (code-quality-fixes
 * 2026-10-15, task 6) with ZERO behaviour change: every memo/callback below is
 * moved verbatim — same order, same dependency arrays, same comments — so the
 * resolved columns, labels, cells, searched/enriched rows and the dynamic filter
 * key-set are byte-for-byte what the page produced inline.
 *
 * Owns the derivation chain the table + stats + filter toolkit consume:
 *   members → memberRows → searchedRows → enrichedRows (→ useFilterableTable),
 *   plus the ordered `columns` model, the header `columnLabel`, the `renderCell`
 *   accessor, and the `dynamicInitialFilters` key set.
 */

import React, { useMemo, useCallback } from 'react';
import {
  COMPACT_FIELD_KEYS, MEMBER_NUMBER_KEY, FIXED_COLUMN_LABEL_KEYS,
  INITIAL_FILTERS, resolveLabel, type OverviewColumn,
} from './membersOverviewModel';
import {
  renderFieldValue, isColumnCandidate, valueFor,
  buildEnumLabelMap, enumValueToFilterText,
} from '../fieldValue';
import { coerceByType, shouldFlatten } from '../columnValue';
import type {
  Member, MemberRow, FieldConfig, FieldConfigField, ScopeDimension,
} from '../../../types/members';

export interface UseMembersColumnsParams {
  members: Member[];
  fieldConfig: FieldConfig | null;
  chosenKeys: string[];
  globalSearch: string;
  lang: string;
  t: (key: string) => string;
}

export interface UseMembersColumnsReturn {
  memberRows: MemberRow[];
  columns: OverviewColumn[];
  chosenColumns: OverviewColumn[];
  effectiveChosenKeys: string[];
  columnLabel: (field: FieldConfigField) => string;
  renderCell: (field: FieldConfigField, row: MemberRow) => React.ReactNode;
  isFilterable: (key: string) => boolean;
  enrichedRows: MemberRow[];
  dynamicInitialFilters: Record<string, string>;
  defaultSort: { field: string; direction: 'asc' };
}

export function useMembersColumns({
  members,
  fieldConfig,
  chosenKeys,
  globalSearch,
  lang,
  t,
}: UseMembersColumnsParams): UseMembersColumnsReturn {
  // ── Scope / region dimension resolution (task 4.2, design C-SCOPE; R5.3) ──────
  // Resolve the scope dimension (region preferred). Row scope itself is ALWAYS
  // enforced SERVER-SIDE; the region text filter is a client-side narrowing of
  // the already-scoped rows and NEVER invents scope.
  // (Kept to preserve the original memo ordering + dependencies.)
  useMemo<ScopeDimension | undefined>(() => {
    const dims = fieldConfig?.dimensions ?? [];
    return (
      dims.find(d => d.key === 'region')
      ?? dims.find(d => d.enabled !== false)
    );
  }, [fieldConfig]);

  // Every shown header carries a FilterableHeader filter input. The former
  // per-view-context `filterable_columns` allow-list is gone (Phase 2 step b —
  // view contexts retired); the Members table now renders over the resolved
  // `FieldConfig` visible fields directly, so every column is filterable.
  const isFilterable = useCallback((_key: string): boolean => true, []);

  // Build flat rows; promote the region display value for the region column + stats.
  const memberRows: MemberRow[] = useMemo(
    () => members.map(m => ({
      ...m,
      region_display: (m.region as string) || '',
    })),
    [members],
  );

  // ── Unified column model (session-columns task 4.2, design C3) ────────────────
  // Fast lookup of every resolved field descriptor by key.
  const fieldByKey = useMemo(
    () => new Map<string, FieldConfigField>(
      (fieldConfig?.fields ?? []).map(f => [f.key, f]),
    ),
    [fieldConfig],
  );

  // The admin default/compact column KEYS a FIRST-TIME user (empty `chosenKeys`)
  // sees (R6.4). The compact set carries member_number first; it is prepended
  // separately by the model below, so drop it here. `region` is a
  // dimension-backed column surfaced after the compact fixed fields.
  const defaultColumnKeys: string[] = useMemo(() => {
    const compact = COMPACT_FIELD_KEYS.filter(k => k !== MEMBER_NUMBER_KEY);
    return [...compact, 'region'];
  }, []);

  // THEIR saved list when non-empty, else the first-time admin default.
  const effectiveChosenKeys: string[] = useMemo(
    () => (chosenKeys.length > 0 ? chosenKeys : defaultColumnKeys),
    [chosenKeys, defaultColumnKeys],
  );

  // Resolve the member_number descriptor (R7.1). Prefer the field-config
  // descriptor; fall back to a synthesized one so the leading column always
  // renders even when the config omits member_number.
  const memberNumberColumn: OverviewColumn = useMemo(
    () => ({ field: fieldByKey.get(MEMBER_NUMBER_KEY) ?? { key: MEMBER_NUMBER_KEY } }),
    [fieldByKey],
  );

  // `chosenColumns` — `effectiveChosenKeys` resolved to column descriptors,
  // de-duped, with member_number excluded (prepended separately, R7.3). A field
  // explicitly not a candidate is skipped (R5.1); a key with no descriptor
  // (e.g. `region`) is kept with a synthesized descriptor so it renders.
  const chosenColumns: OverviewColumn[] = useMemo(() => {
    const seen = new Set<string>([MEMBER_NUMBER_KEY]);
    const resolved: OverviewColumn[] = [];
    for (const key of effectiveChosenKeys) {
      if (!key || seen.has(key)) continue;
      const field = fieldByKey.get(key);
      if (field && !isColumnCandidate(field)) continue;
      seen.add(key);
      resolved.push({ field: field ?? { key } });
    }
    return resolved;
  }, [effectiveChosenKeys, fieldByKey]);

  // The final ordered column model: member_number ALWAYS first (R7.1), then the
  // chosen columns. ONE source of truth for both the header map + the cell map.
  const columns: OverviewColumn[] = useMemo(
    () => [memberNumberColumn, ...chosenColumns],
    [memberNumberColumn, chosenColumns],
  );

  // Resolve a column's header label (session-columns C3). member_number +
  // the other fixed compact keys keep their legacy i18n label; every other
  // column uses its field-config `resolveLabel`.
  const columnLabel = useCallback(
    (field: FieldConfigField): string => {
      if (field.key === MEMBER_NUMBER_KEY) {
        return t(FIXED_COLUMN_LABEL_KEYS[MEMBER_NUMBER_KEY]);
      }
      const legacyKey = FIXED_COLUMN_LABEL_KEYS[field.key];
      if (legacyKey) return t(legacyKey);
      return resolveLabel(field.label, lang, field.key);
    },
    [t, lang],
  );

  // Resolve a column's cell value for a row. member_number + region keep their
  // legacy accessors; every other column renders through valueFor +
  // renderFieldValue.
  const renderCell = useCallback(
    (field: FieldConfigField, row: MemberRow): React.ReactNode => {
      if (field.key === MEMBER_NUMBER_KEY) return (row.member_number as string) || '-';
      if (field.key === 'region') return row.region_display || '-';
      return renderFieldValue(field, valueFor(row, field.group, field.key), lang);
    },
    [lang],
  );

  // ── Per-column enum value→label map (BU-9, R5.2/R5.3/R5.4) ───────────────────
  // Filter/search must match the LABEL the user sees in their language (nl
  // `Overleden`, gb `Passed Away`) OR the hidden stored key (`died`) — BOTH, so
  // either way of typing finds the same row (label matching is ADDED on top of
  // key matching, the key is never dropped). Build the value→label map ONCE per
  // enum column here — keyed on the field config + lang — so a keystroke in the
  // search box or a column filter resolves a cell's label+key by a cheap Map
  // lookup, NOT by re-resolving `options` per row per keystroke. A field with no
  // rich `{value,label}` options maps to `null` (its value is its own label). The
  // stored key is never rewritten (R5.4). Keyed by value, so two options sharing a
  // label keep both keys and a filter on that label matches both.
  const enumLabelMaps = useMemo(
    () => new Map<string, Map<string, string> | null>(
      (fieldConfig?.fields ?? []).map(f => [f.key, buildEnumLabelMap(f, lang)]),
    ),
    [fieldConfig, lang],
  );

  // Every candidate field (visible !== false) the global search scans.
  const searchableFields: FieldConfigField[] = useMemo(
    () => (fieldConfig?.fields ?? []).filter(isColumnCandidate),
    [fieldConfig],
  );

  // Narrow the rows by the global search BEFORE the per-column filter/sort
  // toolkit. A row matches when ANY candidate field's resolved value contains
  // the query (case-insensitive substring). For an enum/reference field the
  // match is against the ACTIVE-LANGUAGE LABEL **OR** the stored KEY (via the
  // one-per-column `enumLabelMaps` lookup, R5.2/R5.4) — both, so `Overleden`,
  // `Passed Away`, and the raw `died` key all match the same row. Scope is never
  // widened.
  const searchedRows: MemberRow[] = useMemo(() => {
    const q = globalSearch.trim().toLowerCase();
    if (q === '') return memberRows;
    return memberRows.filter(row =>
      searchableFields.some(f => {
        const value = valueFor(row, f.group, f.key);
        if (value === null || value === undefined) return false;
        const labelMap = enumLabelMaps.get(f.key) ?? null;
        const text = labelMap
          ? enumValueToFilterText(labelMap, value)
          : String(value);
        return text.toLowerCase().includes(q);
      }),
    );
  }, [memberRows, searchableFields, globalSearch, enumLabelMaps]);

  // ── On-the-fly flatten (session-columns task 4.3, design C4) ──────────────────
  // Promote each chosen column's resolved value to a flat top-level property on
  // the row so the per-column filter (`useColumnFilters`, which reads `row[key]`)
  // and the sort compare a real, display-faithful value.
  //
  //   • ENUM/reference columns (BU-9, R5.2/R5.3/R5.4): promote the ACTIVE-LANGUAGE
  //     LABEL together with the stored KEY (via the one-per-column
  //     `enumLabelMaps`), so the column filter matches the `Overleden`/`Passed
  //     Away` text the user sees OR the raw `died` key — both. This applies even
  //     to a flat-alias key (`status`, `membership_type`) — the alias carries the
  //     stored key, which is exactly the findings.md #2 bug (the status filter
  //     keyed off the value); overlaying the label (while keeping the key
  //     matchable) here is the fix. The stored record key is untouched (R5.4).
  //   • NON-enum, NON-alias columns: coerced by the field `type` so a number/date
  //     sorts correctly (design C4). Flat aliases are left to `flattenMember`.
  const enrichedRows: MemberRow[] = useMemo(() => {
    const fields = chosenColumns.map(c => c.field);
    const promotable = fields.filter(
      f => shouldFlatten(f.key) || (enumLabelMaps.get(f.key) ?? null) !== null,
    );
    if (promotable.length === 0) return searchedRows;
    return searchedRows.map(row => {
      const extra: Record<string, unknown> = {};
      for (const f of promotable) {
        const labelMap = enumLabelMaps.get(f.key) ?? null;
        const raw = valueFor(row, f.group, f.key);
        extra[f.key] = labelMap
          ? enumValueToFilterText(labelMap, raw)
          : coerceByType(f, raw);
      }
      return { ...row, ...extra };
    });
  }, [searchedRows, chosenColumns, enumLabelMaps]);

  // The Members table sorts by name ascending by default.
  const defaultSort = useMemo(
    () => ({ field: 'name', direction: 'asc' as const }),
    [],
  );

  // ── Dynamic filter key set (session-columns task 4.4, design C5) ──────────────
  // `initialFilters` = the fixed keys PLUS each chosen column key, so every shown
  // column has a filter slot. Keyed on the chosen column KEY LIST so a changed
  // set rebuilds the object (and shifts the key-set signature the hook watches).
  const dynamicInitialFilters = useMemo(() => {
    const next: Record<string, string> = { ...INITIAL_FILTERS };
    for (const { field } of chosenColumns) {
      if (!(field.key in next)) next[field.key] = '';
    }
    return next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosenColumns.map(c => c.field.key).join('\u241F')]);

  return {
    memberRows,
    columns,
    chosenColumns,
    effectiveChosenKeys,
    columnLabel,
    renderCell,
    isFilterable,
    enrichedRows,
    dynamicInitialFilters,
    defaultSort,
  };
}
