/**
 * MemberFieldPicker — compose + save a member pivot/list set (C4, task 7.4).
 *
 * A keyboard-accessible Chakra modal that lets a user build a {@link PivotConfig}
 * for the Members data source from the resolved field config, then save it as a
 * tenant-scoped analytics set via `membersApiService.saveAnalyticsSet` — the
 * Members module's OWN DynamoDB store, NOT the Flask `pivotService`/`pivot_models`
 * MySQL store (F-012: a SAM module owns its data on its own plane; design C4;
 * R4.4, R4.5, R4.6, R6.1).
 *
 * The picker serves the whole save lifecycle (task 7.5):
 *   - **save new / save-as** — with no `existingModel`, it composes a fresh
 *     config and persists it via `saveAnalyticsSet` (always a NEW tenant set);
 *   - **update** — with an `existingModel` ({@link ExistingPivotModel}), it opens
 *     pre-populated from that set's own `PivotConfig` and persists the edited
 *     config back onto the SAME id via `updateAnalyticsSet` (R4.4b — explicit,
 *     never implicit).
 *
 * In both paths the composed `PivotConfig.filters` are the set's own DEFINITION
 * filters and travel with the saved set (R4.4); the Analytics page's live
 * row/scope filter is never handed to this picker, so it is never baked into a
 * saved set (R4.4a). Persisting is always an explicit Save/Update click here —
 * no run-time filter tweak writes to a saved set (R4.4b).
 *
 * What it does:
 *
 *   - **Lists the groupable/aggregatable fields** from `fieldConfig.fields` — the
 *     fixed ⊕ overlay ⊕ calculated union the module resolves — with BILINGUAL
 *     labels via a local `resolveLabel` (mirroring the Members table's
 *     `fieldForm.resolveLabel`) and the `analytics.pivotViews.fieldPicker.*` i18n
 *     keys (task 0.3). No hardcoded English, no hardcoded field list (R4.5 / R6.1).
 *
 *   - **Composes a `PivotConfig`:** the user chooses **group columns** (zero or
 *     more — an empty set is a valid *filtered-list* set, R4.8) and zero or more
 *     **aggregate measures** (COUNT/SUM/AVG/MIN/MAX over a chosen field, or
 *     COUNT(*) over all rows). The data source is fixed to
 *     {@link MEMBER_PIVOT_DATA_SOURCE} (`'members'`), satisfying R4.4/R4.5 so the
 *     saved model is a member set the Pivot Views area filters to
 *     (`data_source === 'members'`).
 *
 *   - **Can be SEEDED from a preset** (R4.6): when a `seedPreset` is supplied the
 *     picker opens pre-populated from that preset's `config` (its group columns +
 *     measures + a default name), so a predefined set is a *starting point* the
 *     user tweaks and saves as their own variant.
 *
 *   - **Saves** the composed config via `membersApiService.saveAnalyticsSet(name,
 *     config, kind)`. It serializes the config to the module's snake_case
 *     `definition` through `toBackendConfig`, so the member set persists on the
 *     Members module's own `/members/analytics-sets` DynamoDB CRUD (tenant-scoped
 *     by the Lambda — F-012). On success the modal toasts and calls
 *     `onSaved(config, name, id)` so the Pivot Views area can refresh its
 *     saved-set list and run the set.
 *
 * Accessibility: the Chakra `Modal` traps focus, closes on Escape, and restores
 * focus on close; every control carries a resolved bilingual label; the save is
 * blocked (with an inline reason) until a name is entered and at least one group
 * column or measure is chosen, rather than silently no-opping.
 *
 * Read-only w.r.t. member data: this composes a saved *view definition*; it never
 * mutates a member.
 *
 * @module components/members/analytics/MemberFieldPicker
 * @see .kiro/specs/Members/member-analytics (design C4; requirements R4.4, R4.5, R4.6, R6.1)
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Button,
  Text,
  VStack,
  HStack,
  Checkbox,
  FormControl,
  FormLabel,
  Input,
  Select,
  IconButton,
  Divider,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type {
  FieldConfig,
  FieldConfigField,
  FunctionalGroup,
  LocalizedLabel,
} from '../../../types/members';
import type {
  AggregateFunction,
  AggregateMeasure,
  PivotConfig,
} from '../../../types/pivot';
import { saveAnalyticsSet, updateAnalyticsSet } from '../../../services/membersApiService';
import { MEMBER_PIVOT_DATA_SOURCE, type MemberPivotPreset } from './memberPivotPresets';

/** The aggregate functions the framework supports (mirrors `AggregateFunction`). */
const AGGREGATE_FUNCTIONS: readonly AggregateFunction[] = [
  'COUNT',
  'SUM',
  'AVG',
  'MIN',
  'MAX',
];

/** The COUNT(*) sentinel — count all rows in a group, not a specific column. */
const COUNT_STAR = '*';

/** `members`-namespace i18n key prefix for every label this modal renders. */
const T = 'analytics.pivotViews.fieldPicker';

/**
 * Resolve a localized (`{nl,en}`) or plain-string label to the active language,
 * mirroring the Members table's `fieldForm.resolveLabel` (prefer active language,
 * then `nl`, then `en`, then the fallback). Kept local so the analytics surface
 * has no cross-module import of a form helper (R4.5 / R6.1).
 */
function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/** A single composable aggregate-measure row in local state (stable id for React keys). */
interface MeasureDraft {
  id: string;
  function: AggregateFunction;
  /** Field key, or `''` meaning COUNT(*) (all rows). */
  column: string;
}

let measureIdSeq = 0;
function nextMeasureId(): string {
  measureIdSeq += 1;
  return `measure-${measureIdSeq}`;
}

/** Turn a config's `aggregateMeasures` into editable `MeasureDraft`s. */
function toDrafts(measures: AggregateMeasure[] | undefined): MeasureDraft[] {
  return (measures ?? []).map((m) => ({
    id: nextMeasureId(),
    function: m.function,
    column: m.column === COUNT_STAR ? '' : m.column,
  }));
}

/** Turn editable `MeasureDraft`s back into framework `AggregateMeasure`s. */
function fromDrafts(drafts: MeasureDraft[]): AggregateMeasure[] {
  return drafts.map((d) => ({
    function: d.function,
    column: d.function === 'COUNT' && d.column === '' ? COUNT_STAR : d.column,
  }));
}

/**
 * The reserved definition-filter keys the jubilee / new-members selectors own
 * (mirrors `analyticsConfig`'s `JUBILEE_YEAR_FILTER_KEY` /
 * `JOINED_AFTER_FILTER_KEY`). The picker's generic Filters section never shows
 * or clobbers these — they are year-aware filters driven by the Pivot Views
 * selector UI, so they are carried through untouched on the composed config.
 * Hardcoded here (rather than imported) to keep the picker's definition filters
 * independent of the selector plumbing.
 */
const RESERVED_FILTER_KEYS: readonly string[] = ['years_member', 'joined_after_year'];

/** A single composable definition-filter row in local state (stable id for React keys). */
interface FilterDraft {
  id: string;
  /** Field key the filter matches on, or `''` (unset row). */
  field: string;
  /** The value the field must equal (string equality, applied at execute time). */
  value: string;
}

let filterIdSeq = 0;
function nextFilterId(): string {
  filterIdSeq += 1;
  return `filter-${filterIdSeq}`;
}

/**
 * Seed the editable filter rows from a config's `filters` map, SKIPPING the
 * reserved year keys (they are not generic equality filters). Each remaining
 * entry becomes an editable row so a saved set's definition filters round-trip
 * through the editor (R4.4). A value is stringified for the text input.
 */
function toFilterDrafts(
  filters: Record<string, unknown> | undefined,
): FilterDraft[] {
  if (!filters) return [];
  const drafts: FilterDraft[] = [];
  for (const [field, raw] of Object.entries(filters)) {
    if (RESERVED_FILTER_KEYS.includes(field)) {
      continue;
    }
    if (raw === null || raw === undefined) {
      continue;
    }
    drafts.push({ id: nextFilterId(), field, value: String(raw) });
  }
  return drafts;
}

/**
 * Compose the editable filter rows back into a `{ [fieldKey]: value }` map,
 * MERGED onto the set's existing reserved filters (so a jubilee/joined-after
 * year is preserved). Blank rows (no field, or no value) are dropped; the last
 * row wins on a duplicate field key.
 */
function fromFilterDrafts(
  drafts: FilterDraft[],
  base: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  // Carry the reserved year filters from the base config untouched.
  if (base) {
    for (const key of RESERVED_FILTER_KEYS) {
      if (key in base && base[key] !== undefined && base[key] !== null) {
        result[key] = base[key];
      }
    }
  }
  for (const d of drafts) {
    const field = d.field.trim();
    const value = d.value.trim();
    if (field === '' || value === '') {
      continue; // blank row → not a filter
    }
    result[field] = value;
  }
  return result;
}

/**
 * An existing saved member set the picker edits (task 7.5 — update path). When
 * supplied, the modal opens pre-populated from this set's own definition and
 * persists edits back onto the SAME `id` via `updateAnalyticsSet`, rather than
 * creating a new set. The `config.filters` are the set's own definition
 * filters (R4.4) — they round-trip through the editor; the page's live filter is
 * never part of this (R4.4a).
 */
export interface ExistingPivotModel {
  /** The saved set's tenant-scoped id (the backend `set_id` string — never a cross-tenant id, R5.2). */
  id: string;
  /** The saved model's current name (pre-fills the name field). */
  name: string;
  /** The saved model's current definition (pre-fills group columns + measures + filters). */
  config: PivotConfig;
}

export interface MemberFieldPickerProps {
  /** Whether the modal is open. */
  isOpen: boolean;
  /** Close handler (overlay / Escape / Cancel). */
  onClose: () => void;
  /** The resolved field config whose fields the picker lists (R4.5). */
  fieldConfig: FieldConfig | null;
  /** Active language for bilingual label resolution. */
  language: string;
  /**
   * Optional preset to SEED the picker from (R4.6). When provided, the group
   * columns + measures + default name are pre-populated from its config so the
   * predefined set is a starting point the user can tweak and save. Ignored when
   * `existingModel` is supplied (an edit opens from the saved model, not a preset).
   */
  seedPreset?: MemberPivotPreset;
  /**
   * Optional existing saved set to EDIT (task 7.5 — update path). When
   * supplied, the picker opens pre-populated from this set's own definition and
   * a successful Save calls `updateAnalyticsSet(existingModel.id, …)` instead
   * of creating a new set. When absent, Save creates a NEW set (save /
   * save-as).
   */
  existingModel?: ExistingPivotModel;
  /**
   * Called after a successful save/update with the composed `PivotConfig`, the
   * set name, and the persisted set id (the new id for a save, or
   * `existingModel.id` for an update) — so the Pivot Views area can refresh its
   * saved-set list and (re)select the set. The id is `undefined` only when the
   * backend omits it from a save response.
   */
  onSaved?: (config: PivotConfig, name: string, modelId?: string) => void;
}

/**
 * Build the composable field list from the resolved field config: every field
 * present (fixed ⊕ overlay ⊕ calculated), skipping entries explicitly hidden
 * (`visible === false`) and any without a key. Order follows the config's own
 * order (already sorted by the module), so the picker reflects the tenant's
 * configured field set verbatim (R4.5 / R6.1).
 */
function pickableFields(fieldConfig: FieldConfig | null): FieldConfigField[] {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return [];
  return fields.filter(
    (f): f is FieldConfigField =>
      !!f && typeof f.key === 'string' && f.key !== '' && f.visible !== false,
  );
}

/** The fallback section key for fields with no (or a dangling) functional group. */
const DEFAULT_FG_SECTION_KEY = '__ungrouped__';

/** A resolved, display-ready section: a functional-group heading + its fields. */
interface FieldPickerSection {
  /** The functional-group key, or {@link DEFAULT_FG_SECTION_KEY} for the fallback. */
  key: string;
  /** The section heading (localized), or `undefined` for the ungrouped fallback. */
  label?: LocalizedLabel;
  /** The section's fields, sorted alphabetically by their resolved label. */
  fields: FieldConfigField[];
}

/**
 * Bucket the pickable fields into ordered SECTIONS by functional group, then
 * sort alphabetically WITHIN each section by the resolved (active-language)
 * label. Section order follows the tenant's `functional_groups` catalog `order`
 * (R4.9); a field with no group — or one not in the catalog — falls into a
 * single "ungrouped" section appended last (never a crash). Empty sections are
 * dropped. Mirrors the Members modals' `groupFieldsBySection`, kept local so the
 * analytics surface has no cross-module form import (R4.5 / R6.1).
 */
function sectionFields(
  fields: FieldConfigField[],
  catalog: FunctionalGroup[] | undefined,
  lang: string,
): FieldPickerSection[] {
  const catalogByKey = new Map<string, FunctionalGroup>();
  (catalog ?? []).forEach((g) => catalogByKey.set(g.key, g));

  const buckets = new Map<string, FieldConfigField[]>();
  for (const f of fields) {
    const g = f.functional_group;
    const key = g && catalogByKey.has(g) ? g : DEFAULT_FG_SECTION_KEY;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(f);
  }

  const byLabel = (a: FieldConfigField, b: FieldConfigField) =>
    resolveLabel(a.label, lang, a.key).localeCompare(
      resolveLabel(b.label, lang, b.key),
      lang,
      { sensitivity: 'base' },
    );

  const orderedCatalog = (catalog ?? [])
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  const sections: FieldPickerSection[] = [];
  for (const g of orderedCatalog) {
    const bucket = buckets.get(g.key);
    if (bucket && bucket.length > 0) {
      sections.push({ key: g.key, label: g.label, fields: bucket.slice().sort(byLabel) });
    }
  }
  const fallback = buckets.get(DEFAULT_FG_SECTION_KEY);
  if (fallback && fallback.length > 0) {
    sections.push({ key: DEFAULT_FG_SECTION_KEY, fields: fallback.slice().sort(byLabel) });
  }
  return sections;
}

export const MemberFieldPicker: React.FC<MemberFieldPickerProps> = ({
  isOpen,
  onClose,
  fieldConfig,
  language,
  seedPreset,
  existingModel,
  onSaved,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  const lang = (language || 'nl').slice(0, 2);
  const fields = useMemo(() => pickableFields(fieldConfig), [fieldConfig]);
  // Both field lists (Group by + List columns) render grouped by functional
  // group (catalog order) and alphabetical WITHIN each group, so a long field
  // set is scannable rather than a flat wall of checkboxes.
  const sections = useMemo(
    () => sectionFields(fields, fieldConfig?.functional_groups, lang),
    [fields, fieldConfig, lang],
  );

  const [name, setName] = useState('');
  const [groupColumns, setGroupColumns] = useState<string[]>([]);
  const [measures, setMeasures] = useState<MeasureDraft[]>([]);
  // The curated LIST columns a filtered-list set projects (findings F-009 / the
  // "missing columns" fix). Only meaningful for a list set (no group columns);
  // persisted as `config.listColumns` so the saved list set reruns with exactly
  // these columns instead of falling back to a thin default. Defaults to every
  // pickable field so a freshly-composed list set is never near-empty.
  const [listColumns, setListColumns] = useState<string[]>([]);
  // The set's DEFINITION filters (issue 3): editable (field, value) rows that
  // compose into `config.filters` and persist with the set, e.g.
  // {clubblad:'Papier'}. Seeded from the opened set's own filters (round-trip);
  // the reserved jubilee/joined-after year filters are never shown here.
  const [filterDrafts, setFilterDrafts] = useState<FilterDraft[]>([]);
  const [saving, setSaving] = useState(false);

  // Seed the modal each time it opens. Precedence (task 7.5):
  //   1. `existingModel` → EDIT: pre-fill from the saved model's own definition
  //      (its group columns + measures + name), so the update round-trips the
  //      set's definition filters (R4.4) through the editor.
  //   2. `seedPreset` → NEW from a preset (R4.6): the preset's config is a
  //      starting point the user tweaks and saves as their own set.
  //   3. neither → NEW blank set.
  // The effect intentionally keys only on open/model/preset identity: `t` is
  // captured but NOT a dependency (it is a fresh reference each render under some
  // i18n configs, which would otherwise re-seed — and clobber the user's edits —
  // on every render).
  useEffect(() => {
    if (!isOpen) return;
    if (existingModel) {
      setGroupColumns([...existingModel.config.groupColumns]);
      setMeasures(toDrafts(existingModel.config.aggregateMeasures));
      // Seed the list columns from the saved set; if it carries none (a legacy
      // list set saved before this picker captured columns), default to every
      // pickable field so editing never silently drops the whole column set.
      setListColumns(seedListColumns(existingModel.config, fieldConfig));
      setFilterDrafts(toFilterDrafts(existingModel.config.filters));
      setName(existingModel.name);
      setSaving(false);
      return;
    }
    const cfg = seedPreset?.config;
    setGroupColumns(cfg ? [...cfg.groupColumns] : []);
    setMeasures(toDrafts(cfg?.aggregateMeasures));
    setListColumns(seedListColumns(cfg, fieldConfig));
    setFilterDrafts(toFilterDrafts(cfg?.filters));
    setName(seedPreset ? t(`analytics.pivotViews.presetNames.${presetLeaf(seedPreset)}`) : '');
    setSaving(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, existingModel, seedPreset]);

  const isEditing = !!existingModel;

  const trimmedName = name.trim();
  // A valid composition is EITHER an aggregate set (≥1 group column or measure)
  // OR a filtered-list set that names ≥1 list column — so a list set can never
  // save with no columns (the "missing columns" fix). (`isListSet` is derived
  // below from groupColumns; a list set with measures is still an aggregate.)
  const hasAggregateSelection = groupColumns.length > 0 || measures.length > 0;
  const hasListSelection = groupColumns.length === 0 && listColumns.length > 0;
  const hasSelection = hasAggregateSelection || hasListSelection;
  const canSave = trimmedName !== '' && hasSelection && !saving;

  /**
   * The composed config this modal would save (data source fixed to members).
   * The group columns + measures come from the live editor state; the DEFINITION
   * filters (and the other definition-level fields) are carried from the source
   * the picker opened from — the edited model when updating, else the seed preset
   * — so a set's own filters travel with it (R4.4). The Analytics page's live
   * filter is never a source here (R4.4a).
   */
  const composedConfig = useMemo<PivotConfig>(() => {
    const base = existingModel?.config ?? seedPreset?.config;
    // A list set (no group columns) carries its curated `listColumns` so it
    // reruns with exactly those columns (the "missing columns" fix); an
    // aggregate set (group columns present) never carries listColumns — its
    // columns are the group + measure columns. Omitted when empty.
    const isListSet = groupColumns.length === 0;
    const curatedList = isListSet
      ? listColumns.filter((k) => k !== '')
      : [];
    return {
      dataSource: MEMBER_PIVOT_DATA_SOURCE,
      groupColumns: [...groupColumns],
      aggregateMeasures: fromDrafts(measures),
      // The DEFINITION filters are composed from the editable rows (issue 3),
      // merged onto the base config's RESERVED year filters so a jubilee/joined
      // selector choice is preserved and never clobbered.
      filters: fromFilterDrafts(filterDrafts, base?.filters),
      columnPivot: base?.columnPivot ?? null,
      columnNestLevels: base?.columnNestLevels ?? [],
      displayMode: base?.displayMode ?? 'flat',
      ...(curatedList.length > 0 ? { listColumns: curatedList } : {}),
    };
  }, [groupColumns, measures, listColumns, filterDrafts, existingModel, seedPreset]);

  const toggleGroupColumn = (key: string) => {
    setGroupColumns((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const toggleListColumn = (key: string) => {
    setListColumns((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  // A list set (no group columns) must name at least one list column so the
  // result is not near-empty; an aggregate set does not use list columns.
  const isListSet = groupColumns.length === 0;

  const addMeasure = () => {
    setMeasures((prev) => [...prev, { id: nextMeasureId(), function: 'COUNT', column: '' }]);
  };

  const removeMeasure = (id: string) => {
    setMeasures((prev) => prev.filter((m) => m.id !== id));
  };

  const updateMeasure = (id: string, patch: Partial<Omit<MeasureDraft, 'id'>>) => {
    setMeasures((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  };

  const addFilter = () => {
    setFilterDrafts((prev) => [...prev, { id: nextFilterId(), field: '', value: '' }]);
  };

  const removeFilter = (id: string) => {
    setFilterDrafts((prev) => prev.filter((f) => f.id !== id));
  };

  const updateFilter = (id: string, patch: Partial<Omit<FilterDraft, 'id'>>) => {
    setFilterDrafts((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  };

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      // A set with no group columns is a filtered-LIST set; one with group
      // columns is an aggregate (count) set (R4.8). The module store accepts an
      // empty group/measures list as first-class (F-011/F-012), so a list set
      // saves without the Flask aggregate-only gate that previously rejected it.
      const kind: 'count' | 'list' = groupColumns.length === 0 ? 'list' : 'count';
      if (existingModel) {
        // UPDATE path (task 7.5 / R4.4b): persist the edited definition back onto
        // the same tenant-scoped id — explicit, never implicit. The id came from
        // the saved-set list (tenant-scoped by the Members Lambda), so no
        // cross-tenant id is sent (R5.2). Persisted on the Members module's own
        // DynamoDB plane via the Members API, NOT the Flask pivot store (F-012).
        await updateAnalyticsSet(existingModel.id, trimmedName, composedConfig, kind);
        toast({ title: t(`${T}.toast.updated`), status: 'success' });
        onSaved?.(composedConfig, trimmedName, existingModel.id);
      } else {
        // SAVE / SAVE-AS path: always create a NEW tenant set on the Members
        // module's DynamoDB plane (Members API, not the Flask pivot store — F-012).
        const res = await saveAnalyticsSet(trimmedName, composedConfig, kind);
        toast({ title: t(`${T}.toast.saved`), status: 'success' });
        onSaved?.(composedConfig, trimmedName, res?.id);
      }
      onClose();
    } catch {
      toast({
        title: t(existingModel ? `${T}.toast.updateError` : `${T}.toast.saveError`),
        status: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="member-field-picker">
        <ModalHeader>{t(isEditing ? `${T}.updateTitle` : `${T}.title`)}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack align="stretch" spacing={4}>
            {/* Seeded-from-preset hint (R4.6). */}
            {seedPreset && (
              <Text fontSize="sm" color="orange.300" data-testid="field-picker-seeded">
                {t(`${T}.seededFrom`, {
                  preset: t(`analytics.pivotViews.presetNames.${presetLeaf(seedPreset)}`),
                })}
              </Text>
            )}

            {/* Set name (required to save). */}
            <FormControl isRequired>
              <FormLabel htmlFor="field-picker-name">{t(`${T}.name`)}</FormLabel>
              <Input
                id="field-picker-name"
                data-testid="field-picker-name"
                placeholder={t(`${T}.namePlaceholder`)}
                value={name}
                onChange={(e) => setName(e.target.value)}
                bg="gray.900"
                color="white"
                _placeholder={{ color: 'gray.400' }}
              />
            </FormControl>

            <Divider borderColor="gray.600" />

            {/* List columns — shown ONLY for a filtered-list set (no group
                columns, R4.8), and FIRST so the primary filtered-list choice
                leads. These are the member fields the list projects as columns;
                without them a list set rendered near-empty (the "missing
                columns" bug). Persisted as `config.listColumns`. */}
            {isListSet && (
              <>
                <FormControl>
                  <FormLabel>{t(`${T}.listColumns`)}</FormLabel>
                  <Text fontSize="xs" color="gray.400" mb={2}>
                    {t(`${T}.listColumnsHint`)}
                  </Text>
                  {fields.length === 0 ? (
                    <Text fontSize="sm" color="gray.500" data-testid="field-picker-no-list-fields">
                      {t(`${T}.noFields`)}
                    </Text>
                  ) : (
                    <VStack align="stretch" spacing={3} data-testid="field-picker-list-fields">
                      {sections.map((section) => (
                        <VStack
                          key={section.key}
                          align="stretch"
                          spacing={1}
                          data-testid={`field-picker-list-section-${section.key}`}
                        >
                          {section.label && (
                            <Text
                              fontSize="xs"
                              fontWeight="semibold"
                              textTransform="uppercase"
                              color="orange.300"
                            >
                              {resolveLabel(section.label, lang, section.key)}
                            </Text>
                          )}
                          {section.fields.map((f) => (
                            <Checkbox
                              key={f.key}
                              isChecked={listColumns.includes(f.key)}
                              onChange={() => toggleListColumn(f.key)}
                              colorScheme="orange"
                              data-testid={`field-picker-list-${f.key}`}
                            >
                              {resolveLabel(f.label, lang, f.key)}
                            </Checkbox>
                          ))}
                        </VStack>
                      ))}
                    </VStack>
                  )}
                </FormControl>

                <Divider borderColor="gray.600" />
              </>
            )}

            {/* Group columns — the groupable fields (R4.5). Empty = filtered list (R4.8). */}
            <FormControl>
              <FormLabel>{t(`${T}.groupColumns`)}</FormLabel>
              <Text fontSize="xs" color="gray.400" mb={2}>
                {t(`${T}.groupColumnsHint`)}
              </Text>
              {fields.length === 0 ? (
                <Text fontSize="sm" color="gray.500" data-testid="field-picker-no-fields">
                  {t(`${T}.noFields`)}
                </Text>
              ) : (
                <VStack align="stretch" spacing={3} data-testid="field-picker-group-fields">
                  {sections.map((section) => (
                    <VStack
                      key={section.key}
                      align="stretch"
                      spacing={1}
                      data-testid={`field-picker-group-section-${section.key}`}
                    >
                      {section.label && (
                        <Text
                          fontSize="xs"
                          fontWeight="semibold"
                          textTransform="uppercase"
                          color="orange.300"
                        >
                          {resolveLabel(section.label, lang, section.key)}
                        </Text>
                      )}
                      {section.fields.map((f) => (
                        <Checkbox
                          key={f.key}
                          isChecked={groupColumns.includes(f.key)}
                          onChange={() => toggleGroupColumn(f.key)}
                          colorScheme="orange"
                          data-testid={`field-picker-group-${f.key}`}
                        >
                          {resolveLabel(f.label, lang, f.key)}
                        </Checkbox>
                      ))}
                    </VStack>
                  ))}
                </VStack>
              )}
            </FormControl>

            <Divider borderColor="gray.600" />

            {/* Aggregate measures (R4.7) — composable function + column rows. */}
            <FormControl>
              <FormLabel>{t(`${T}.measures`)}</FormLabel>
              <Text fontSize="xs" color="gray.400" mb={2}>
                {t(`${T}.measuresHint`)}
              </Text>
              <VStack align="stretch" spacing={2} data-testid="field-picker-measures">
                {measures.map((m) => (
                  <HStack key={m.id} data-testid={`field-picker-measure-${m.id}`}>
                    <Select
                      aria-label={t(`${T}.measureFunction`)}
                      value={m.function}
                      onChange={(e) =>
                        updateMeasure(m.id, { function: e.target.value as AggregateFunction })
                      }
                      bg="gray.900"
                      maxW="40%"
                    >
                      {AGGREGATE_FUNCTIONS.map((fn) => (
                        <option key={fn} value={fn}>
                          {t(`${T}.functions.${fn}`)}
                        </option>
                      ))}
                    </Select>
                    <Select
                      aria-label={t(`${T}.measureColumn`)}
                      value={m.column}
                      onChange={(e) => updateMeasure(m.id, { column: e.target.value })}
                      bg="gray.900"
                    >
                      {/* COUNT(*) over all rows — the only valid empty-column choice. */}
                      <option value="">{t(`${T}.countAll`)}</option>
                      {fields.map((f) => (
                        <option key={f.key} value={f.key}>
                          {resolveLabel(f.label, lang, f.key)}
                        </option>
                      ))}
                    </Select>
                    <IconButton
                      aria-label={t(`${T}.removeMeasure`)}
                      data-testid={`field-picker-remove-measure-${m.id}`}
                      size="sm"
                      variant="ghost"
                      colorScheme="red"
                      icon={<Text aria-hidden>✕</Text>}
                      onClick={() => removeMeasure(m.id)}
                    />
                  </HStack>
                ))}
                <Button
                  size="sm"
                  variant="outline"
                  alignSelf="flex-start"
                  data-testid="field-picker-add-measure"
                  onClick={addMeasure}
                >
                  {t(`${T}.addMeasure`)}
                </Button>
              </VStack>
            </FormControl>

            <Divider borderColor="gray.600" />

            {/* Definition filters (issue 3) — composable (field == value) rows
                that narrow the set at execute time, e.g. clubblad == "Papier".
                They compose into `config.filters` and persist with the set
                (R4.4). The reserved jubilee/joined-after year filters are driven
                by the Pivot Views selectors and are not shown here. */}
            <FormControl>
              <FormLabel>{t(`${T}.filters`)}</FormLabel>
              <Text fontSize="xs" color="gray.400" mb={2}>
                {t(`${T}.filtersHint`)}
              </Text>
              <VStack align="stretch" spacing={2} data-testid="field-picker-filters">
                {filterDrafts.map((f) => (
                  <HStack key={f.id} data-testid={`field-picker-filter-${f.id}`}>
                    <Select
                      aria-label={t(`${T}.filterField`)}
                      value={f.field}
                      onChange={(e) => updateFilter(f.id, { field: e.target.value })}
                      bg="gray.900"
                      maxW="50%"
                      data-testid={`field-picker-filter-field-${f.id}`}
                    >
                      <option value="">{t(`${T}.filterField`)}</option>
                      {fields.map((field) => (
                        <option key={field.key} value={field.key}>
                          {resolveLabel(field.label, lang, field.key)}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label={t(`${T}.filterValue`)}
                      placeholder={t(`${T}.filterValue`)}
                      value={f.value}
                      onChange={(e) => updateFilter(f.id, { value: e.target.value })}
                      bg="gray.900"
                      color="white"
                      _placeholder={{ color: 'gray.400' }}
                      data-testid={`field-picker-filter-value-${f.id}`}
                    />
                    <IconButton
                      aria-label={t(`${T}.removeFilter`)}
                      data-testid={`field-picker-remove-filter-${f.id}`}
                      size="sm"
                      variant="ghost"
                      colorScheme="red"
                      icon={<Text aria-hidden>✕</Text>}
                      onClick={() => removeFilter(f.id)}
                    />
                  </HStack>
                ))}
                <Button
                  size="sm"
                  variant="outline"
                  alignSelf="flex-start"
                  data-testid="field-picker-add-filter"
                  onClick={addFilter}
                >
                  {t(`${T}.addFilter`)}
                </Button>
              </VStack>
            </FormControl>

            {/* Inline reason the Save is blocked (never a silent no-op). */}
            {!hasSelection && (
              <Text fontSize="sm" color="yellow.300" data-testid="field-picker-selection-required">
                {t(`${T}.selectionRequired`)}
              </Text>
            )}
            {hasSelection && trimmedName === '' && (
              <Text fontSize="sm" color="yellow.300" data-testid="field-picker-name-required">
                {t(`${T}.nameRequired`)}
              </Text>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose} data-testid="field-picker-cancel">
            {t(`${T}.cancel`)}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isDisabled={!canSave}
            isLoading={saving}
            data-testid="field-picker-save"
          >
            {t(isEditing ? `${T}.update` : `${T}.save`)}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

/**
 * The preset's i18n leaf key under `analytics.pivotViews.presetNames.*`. A
 * preset's `labelKey` is the full path `analytics.pivotViews.presetNames.<leaf>`;
 * this returns `<leaf>` so the modal resolves the bilingual name the same way the
 * Pivot Views dropdown does (no hardcoded English).
 */
function presetLeaf(preset: MemberPivotPreset): string {
  const parts = preset.labelKey.split('.');
  return parts[parts.length - 1] || preset.key;
}

/**
 * Seed the list-column selection when the picker opens on a (list) set.
 *
 * Precedence:
 *   1. the config's own `listColumns` (a preset / previously-saved list set that
 *      already named its columns) — used verbatim so editing preserves them;
 *   2. otherwise, a legacy saved/preset LIST set (no group columns) that never
 *      named its columns DEFAULTS to every pickable field — so an old set still
 *      renders its full column set rather than near-empty (the "missing columns"
 *      fix). An aggregate set (group columns present) seeds no list columns.
 *   3. a brand-new blank compose (`config === undefined`) seeds NOTHING — the
 *      user picks the list columns they want rather than starting with every
 *      field pre-checked. The save validation still requires ≥1 list column for
 *      a list set, so a new set can never save near-empty.
 *
 * The `fieldConfig` arg is retained for the legacy-set fallback.
 */
function seedListColumns(
  config: PivotConfig | undefined,
  fieldConfig: FieldConfig | null,
): string[] {
  const existing = config?.listColumns;
  if (Array.isArray(existing) && existing.length > 0) {
    return existing.filter((k): k is string => typeof k === 'string' && k !== '');
  }
  // Brand-new blank compose: nothing pre-selected (user's explicit choice).
  if (!config) {
    return [];
  }
  const isAggregate = (config.groupColumns?.length ?? 0) > 0;
  if (isAggregate) {
    return [];
  }
  // Legacy saved/preset list set with no named columns → full set fallback.
  return pickableFields(fieldConfig).map((f) => f.key);
}

export default MemberFieldPicker;
