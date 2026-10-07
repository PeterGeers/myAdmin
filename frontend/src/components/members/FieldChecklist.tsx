/**
 * FieldChecklist — the shared, reusable checklist core (session-columns C1,
 * task 1.1; R4.1).
 *
 * The checklist widget lifted verbatim out of
 * `analytics/MemberFieldPicker.tsx`: it renders a resolved field set as a list
 * of per-field checkboxes, bucketed into SECTIONS by functional group
 * (catalog order, alphabetical WITHIN each group by resolved label), with
 * bilingual labels. It is the single checklist both the pivot picker
 * (`PivotConfig` output) and the column chooser (`string[]` output) compose, so
 * the two never drift into near-identical widgets (R4.1).
 *
 * This component is PRESENTATION + selection only — it owns no selection state.
 * The parent passes the current `selectedKeys` (checked) and an optional
 * `disabledKeys` (always-on: rendered checked AND locked, e.g. `member_number`
 * on the column chooser, R7.2) and receives a single `onToggle(key)` per click;
 * the parent decides what a toggle means for its own output contract.
 *
 * Behaviour preserved from the MemberFieldPicker checklist core:
 *   - `sectionFields()` grouping — functional-group sections in the tenant's
 *     `functional_groups` catalog `order`, alphabetical within each section by
 *     the resolved (active-language) label; a field with no group — or one not
 *     in the catalog — falls into a single "ungrouped" section appended last;
 *     empty sections are dropped.
 *   - bilingual labels via `resolveLabel` (active language → `nl` → `en` → key).
 *   - a Chakra `Checkbox` per field keyed by `f.key`, keyboard accessible.
 *
 * @module components/members/FieldChecklist
 * @see .kiro/specs/Members/member-field-search/session-columns (design C1; R4.1)
 */

import React, { useMemo } from 'react';
import { Text, VStack, Checkbox } from '@chakra-ui/react';
import type {
  FieldConfigField,
  FunctionalGroup,
  LocalizedLabel,
} from '../../types/members';

/**
 * Resolve a localized (`{nl,en}`) or plain-string label to the active language
 * (prefer the active language, then `nl`, then `en`, then the fallback). Lifted
 * from `MemberFieldPicker` so both the pivot picker and the column chooser
 * resolve labels through the ONE checklist (R4.1).
 */
export function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/** The fallback section key for fields with no (or a dangling) functional group. */
export const DEFAULT_FG_SECTION_KEY = '__ungrouped__';

/** A resolved, display-ready section: a functional-group heading + its fields. */
export interface FieldChecklistSection {
  /** The functional-group key, or {@link DEFAULT_FG_SECTION_KEY} for the fallback. */
  key: string;
  /** The section heading (localized), or `undefined` for the ungrouped fallback. */
  label?: LocalizedLabel;
  /** The section's fields, sorted alphabetically by their resolved label. */
  fields: FieldConfigField[];
}

/**
 * Bucket the fields into ordered SECTIONS by functional group, then sort
 * alphabetically WITHIN each section by the resolved (active-language) label.
 * Section order follows the tenant's `functional_groups` catalog `order`; a
 * field with no group — or one not in the catalog — falls into a single
 * "ungrouped" section appended last (never a crash). Empty sections are dropped.
 *
 * Lifted verbatim from the MemberFieldPicker checklist core so the pivot picker
 * and the column chooser share one sectioning rule (R4.1).
 */
export function sectionFields(
  fields: FieldConfigField[],
  catalog: FunctionalGroup[] | undefined,
  lang: string,
): FieldChecklistSection[] {
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

  const sections: FieldChecklistSection[] = [];
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

export interface FieldChecklistProps {
  /** The fields to list — already filtered to the caller's candidate set. */
  fields: FieldConfigField[];
  /** The currently-selected (checked) field keys. */
  selectedKeys: string[];
  /**
   * Always-on keys: rendered checked AND locked (disabled), so the user cannot
   * toggle them (e.g. `member_number` on the column chooser, R7.2). Optional.
   */
  disabledKeys?: string[];
  /** The tenant's functional-group catalog (drives section order + headings). */
  functionalGroups: FunctionalGroup[] | undefined;
  /** Active language for bilingual label resolution. */
  lang: string;
  /** Fired with the field key when the user toggles a (non-disabled) checkbox. */
  onToggle: (key: string) => void;
  /**
   * The `data-testid` prefix for the rendered sections/checkboxes, so a wrapper
   * can PRESERVE its own existing per-field testids (e.g. MemberFieldPicker's
   * `field-picker-group` / `field-picker-list`). A section renders
   * `${testIdPrefix}-section-<sectionKey>` and each field renders
   * `${testIdPrefix}-<fieldKey>`. Defaults to `field-checklist`.
   */
  testIdPrefix?: string;
}

/**
 * The shared checklist: sections of per-field checkboxes with bilingual labels,
 * selection driven by the parent (`selectedKeys` / `disabledKeys`) and reported
 * back via `onToggle(key)`.
 */
export const FieldChecklist: React.FC<FieldChecklistProps> = ({
  fields,
  selectedKeys,
  disabledKeys,
  functionalGroups,
  lang,
  onToggle,
  testIdPrefix = 'field-checklist',
}) => {
  const sections = useMemo(
    () => sectionFields(fields, functionalGroups, lang),
    [fields, functionalGroups, lang],
  );

  const selected = useMemo(() => new Set(selectedKeys), [selectedKeys]);
  const locked = useMemo(() => new Set(disabledKeys ?? []), [disabledKeys]);

  return (
    <VStack align="stretch" spacing={3} data-testid={`${testIdPrefix}-fields`}>
      {sections.map((section) => (
        <VStack
          key={section.key}
          align="stretch"
          spacing={1}
          data-testid={`${testIdPrefix}-section-${section.key}`}
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
          {section.fields.map((f) => {
            const isLocked = locked.has(f.key);
            return (
              <Checkbox
                key={f.key}
                // A locked (always-on) field shows checked regardless of the
                // selection set; otherwise it reflects `selectedKeys`.
                isChecked={isLocked || selected.has(f.key)}
                isDisabled={isLocked}
                onChange={() => onToggle(f.key)}
                colorScheme="orange"
                data-testid={`${testIdPrefix}-${f.key}`}
              >
                {resolveLabel(f.label, lang, f.key)}
              </Checkbox>
            );
          })}
        </VStack>
      ))}
    </VStack>
  );
};

export default FieldChecklist;
