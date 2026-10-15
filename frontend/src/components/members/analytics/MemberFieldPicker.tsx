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
  LocalizedLabel,
} from '../../../types/members';
import type {
  AggregateFunction,
  AggregateMeasure,
  FilterOperator,
  PivotConfig,
} from '../../../types/pivot';
import { saveAnalyticsSet, updateAnalyticsSet } from '../../../services/membersApiService';
import FieldChecklist from '../FieldChecklist';
import GroupedFieldSelect from '../GroupedFieldSelect';
import { operatorsForField, operatorTakesNoValue } from './analyticsConfig';
// The pure draft/label/filter transforms live in a sibling helpers module (clean cohesion seam).
import {
  AGGREGATE_FUNCTIONS,
  nextMeasureId,
  toDrafts,
  fromDrafts,
  nextFilterId,
  toFilterDrafts,
  fromFilterDrafts,
  pickableFields,
  seedListColumns,
  type MeasureDraft,
  type FilterDraft,
} from './memberFieldPicker.helpers';

/** The data source tag the client pivot adapter resolves member rows against. */
export const MEMBER_PIVOT_DATA_SOURCE = 'members';

/**
 * Local invalid-pattern guard for the inline `regex` / `notRegex` validity hint
 * (R7.3, R7.7). Mirrors the filter engine's own private `tryCompileRegex`
 * (`analyticsConfig.ts`, case-insensitive, swallows a bad pattern) so the row's
 * inline message agrees with the engine's never-match behaviour: an INVALID
 * pattern returns `false` here and matches NO row at execute, for BOTH `regex`
 * and `notRegex`. Kept local because the engine's helper is module-private; the
 * picker only needs the valid/invalid predicate, not the compiled RegExp.
 */
function isValidRegex(pattern: string): boolean {
  try {
    // eslint-disable-next-line no-new
    new RegExp(pattern, 'i');
    return true;
  } catch {
    return false;
  }
}

/**
 * A starting-point SEED for a NEW set (the Save-as flow): the config to
 * pre-populate the picker from, plus an optional default name. This is the
 * generic analytics-SET seed — a user saving a variant of the selected set —
 * NOT a predefined preset (the preset subsystem was removed).
 */
export interface PivotSeed {
  /** The config whose group columns / measures / list columns / filters seed the picker. */
  config: PivotConfig;
  /** Optional default name to pre-fill (e.g. the source set's name). */
  name?: string;
}

/** `members`-namespace i18n key prefix for every label this modal renders. */
const T = 'analytics.pivotViews.fieldPicker';

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
   * Optional seed to pre-populate the picker from — the Save-as flow (R4.6).
   * When provided, the group columns + measures + list columns + filters + a
   * default name are pre-populated from its config so the selected set is a
   * starting point the user can tweak and save as a NEW set. Ignored when
   * `existingModel` is supplied (an edit opens from the saved model).
   */
  seedPreset?: PivotSeed;
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
  // Key → resolved field, so a filter row can look up its field's type to drive
  // the type-adaptive operator list (operatorsForField) without re-scanning the
  // field array per render.
  const fieldByKey = useMemo(() => {
    const map = new Map<string, FieldConfigField>();
    for (const f of fields) map.set(f.key, f);
    return map;
  }, [fields]);
  // Both field lists (Group by + List columns) render THROUGH the shared
  // FieldChecklist (session-columns C1 / R4.1), which owns the functional-group
  // sectioning (catalog order, alphabetical within) so this picker and the
  // column chooser never drift into two near-identical checklists.

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
    setName(seedPreset?.name ?? '');
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
      // The DEFINITION filters are composed purely from the editable rows
      // (issue 3). There is no reserved-key carry — every filter key, including
      // the former year keys, is an ordinary editable row.
      filters: fromFilterDrafts(filterDrafts),
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
    // A new filter row defaults its operator to `eq` (R3.5); the operator UI is
    // wired in a later task, but the draft must carry a valid op so it composes.
    setFilterDrafts((prev) => [
      ...prev,
      { id: nextFilterId(), field: '', op: 'eq', value: '' },
    ]);
  };

  const removeFilter = (id: string) => {
    setFilterDrafts((prev) => prev.filter((f) => f.id !== id));
  };

  const updateFilter = (id: string, patch: Partial<Omit<FilterDraft, 'id'>>) => {
    setFilterDrafts((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  };

  /**
   * Change a filter row's field, resetting its operator to `eq` when the new
   * field's type no longer offers the row's current operator (R3.6). `eq` is in
   * every type's operator set, so it is always a valid fallback — e.g. switching
   * a row from a text field (`contains`) to a `number` field (which offers no
   * `contains`) snaps the operator back to `eq`. When the current operator is
   * still valid for the new field type it is preserved.
   */
  const changeFilterField = (id: string, field: string) => {
    setFilterDrafts((prev) =>
      prev.map((f) => {
        if (f.id !== id) return f;
        const allowed = operatorsForField(fieldByKey.get(field), fieldConfig ?? undefined);
        const op = allowed.includes(f.op) ? f.op : ('eq' as FilterOperator);
        return { ...f, field, op };
      }),
    );
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
                  preset: seedPreset.name ?? '',
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
                    <FieldChecklist
                      fields={fields}
                      selectedKeys={listColumns}
                      functionalGroups={fieldConfig?.functional_groups}
                      lang={lang}
                      onToggle={toggleListColumn}
                      testIdPrefix="field-picker-list"
                    />
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
                <FieldChecklist
                  fields={fields}
                  selectedKeys={groupColumns}
                  functionalGroups={fieldConfig?.functional_groups}
                  lang={lang}
                  onToggle={toggleGroupColumn}
                  testIdPrefix="field-picker-group"
                />
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
                    {/* Measure column — the grouped single-select (R2.2). Its
                        empty-value placeholder is the COUNT(*)-over-all-rows
                        sentinel (value ''), the only valid empty-column choice;
                        aggregate-measure semantics are unchanged (R11.1). */}
                    <GroupedFieldSelect
                      fields={fields}
                      value={m.column}
                      onChange={(key) => updateMeasure(m.id, { column: key })}
                      functionalGroups={fieldConfig?.functional_groups}
                      lang={lang}
                      ariaLabel={t(`${T}.measureColumn`)}
                      placeholder={t(`${T}.countAll`)}
                    />
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
                {filterDrafts.map((f) => {
                  // The operator list is type-adaptive (R3.1–R3.4): a text field
                  // offers contains/notContains/regex/notRegex, a number/date
                  // field offers the ordering ops, and every type always offers
                  // eq/ne/empty/notEmpty.
                  const operators = operatorsForField(
                    fieldByKey.get(f.field),
                    fieldConfig ?? undefined,
                  );
                  // The value Input is hidden for the presence checks (empty /
                  // notEmpty, R4.1) and shown for every value-taking op —
                  // including notContains / notRegex (R4.2).
                  const takesValue = !operatorTakesNoValue(f.op);
                  // Inline invalid-pattern hint on a regex OR notRegex row whose
                  // value will not compile (R7.3, R7.7). Non-empty value only —
                  // a blank value never narrows, so it is not "invalid" yet.
                  const regexInvalid =
                    (f.op === 'regex' || f.op === 'notRegex') &&
                    f.value.trim() !== '' &&
                    !isValidRegex(f.value);
                  return (
                    <VStack
                      key={f.id}
                      align="stretch"
                      spacing={1}
                      data-testid={`field-picker-filter-${f.id}`}
                    >
                      <HStack>
                        {/* Filter field — the grouped single-select (R2.1), so
                            the filter surface groups by functional group like the
                            checklist. Placeholder = the "Field" label (value ''). */}
                        <GroupedFieldSelect
                          fields={fields}
                          value={f.field}
                          onChange={(key) => changeFilterField(f.id, key)}
                          functionalGroups={fieldConfig?.functional_groups}
                          lang={lang}
                          ariaLabel={t(`${T}.filterField`)}
                          placeholder={t(`${T}.filterField`)}
                          testId={`field-picker-filter-field-${f.id}`}
                          maxW="40%"
                        />
                        {/* Operator — the type-adaptive list (R3.*). */}
                        <Select
                          aria-label={t(`${T}.filterOperator`)}
                          value={f.op}
                          onChange={(e) =>
                            updateFilter(f.id, { op: e.target.value as FilterOperator })
                          }
                          bg="gray.900"
                          maxW="30%"
                          data-testid={`field-picker-filter-op-${f.id}`}
                        >
                          {operators.map((op) => (
                            <option key={op} value={op}>
                              {t(`${T}.operators.${op}`)}
                            </option>
                          ))}
                        </Select>
                        {/* Value — hidden for empty/notEmpty (R4.1), shown for
                            every value-taking op incl. notContains/notRegex (R4.2). */}
                        {takesValue && (
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
                        )}
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
                      {/* Inline invalid-pattern message (R7.3, R7.7). The save is
                          never blocked on it — the row simply matches nothing at
                          execute, consistent with the engine guard (R7.4). */}
                      {regexInvalid && (
                        <Text
                          fontSize="xs"
                          color="red.300"
                          data-testid={`field-picker-filter-regex-invalid-${f.id}`}
                        >
                          {t(`${T}.filterRegexInvalid`)}
                        </Text>
                      )}
                    </VStack>
                  );
                })}
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

export default MemberFieldPicker;
