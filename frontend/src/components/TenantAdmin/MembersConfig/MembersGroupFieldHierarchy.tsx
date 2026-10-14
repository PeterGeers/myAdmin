/**
 * Members group → field → attribute authoring hierarchy (Members config redesign Phase 3
 * step 11 — task 4.1 structure, task 4.2 i18n + composition; R4.1/R4.2/R4.3/R4.4/R4.5/R4.6).
 *
 * Step 11 rebuilds the Members authoring surface as the catalog's OWN group → field → attribute
 * shape (`38-sam-module-field-config.md` rules 1/2), on the Phase 1 attribute catalog
 * (`sam/members/domain/attribute_catalog.py`). This component is the PRESENTATION of that
 * hierarchy over the module's resolved field-config:
 *
 *   - **functional groups** (`key` / `label` / `order`) are the top-level sections — every DEFINED
 *     catalog group is a section (even an empty one, so a tenant can author fields into it);
 *   - **fields** are nested WITHIN their group as the rows of a per-group TABLE — a field belongs
 *     to the group its `functional_group` attribute references;
 *   - **per-field attributes** (type / required / visible / order / provenance / scope axis)
 *     are shown on each field row, read straight off the resolved descriptor.
 *
 * Display order is DERIVED `(group.order, field.order, key)` (rule 2) by `groupResolvedFields` —
 * there is NO stored absolute position field. Groups sort by `(group.order, key)`; fields within a
 * group by `(field.order, key)`.
 *
 * ## i18n Option (b) — task 4.2 (R4.4, `38` rule 6)
 *
 * Shipped field / group / enum-option labels resolve via RESOURCE KEYS under the `admin` namespace
 * (`admin:membersConfig.field.<key>` / `.group.<key>` / `.enum.<fieldKey>.<optionValue>` — the
 * `LABEL_KEY_SCHEME` the Phase-1 catalog pins), with an inline per-language TENANT OVERRIDE that
 * takes precedence: `tenant_inline[locale] ?? resource(key)[locale] ?? fallback`. The resolution is
 * the pure `resolveShippedLabel` in `membersConfigService` — this component only injects the real
 * `admin`-namespace translator (`useTranslation('admin')`). An enum option's `value` is
 * LANGUAGE-NEUTRAL (it is the key segment, never translated); only its `label` is per-language.
 *
 * ## Composition — task 4.2 (R4.5, `37`)
 *
 * The per-group field list is composed from the registered **Table Filter Framework v2** building
 * block (`useFilterableTable` + `FilterableHeader`, steering `37`/`32`) rather than a bespoke
 * Chakra layout: each group section renders a sortable/filterable `Table` whose header cells are
 * `FilterableHeader`s (text filter + `aria-sort` + keyboard-activated sort) and whose rows are the
 * group's fields. Enum options use the shared value/label split. No new shared block is extracted
 * (rule of three) — the existing blocks are reached for.
 *
 * Catalog-resolvability (R4.3): the sections come ONLY from the catalog's defined groups; a field
 * whose `functional_group` is NOT catalog-resolvable is surfaced in a trailing "ungrouped" section
 * (`resolved: false`) rather than silently dropped — the picker-resolvability guard made visible.
 *
 * This is a PRESENTATION view (like `MembersFieldProvenanceList`): it enforces nothing and writes
 * nothing. Authoring stays the SINGLE `field_overlay` object committed through the sub-editor (one
 * save → one re-projection, R4.7) — this hierarchy is how the author SEES the group → field →
 * attribute structure their one save authors.
 */
import React, { useMemo } from 'react';
import {
  Badge,
  Box,
  HStack,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Thead,
  Tr,
  VStack,
  Wrap,
  WrapItem,
} from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import type {
  EnumOptionConfig,
  FieldConfigField,
  FieldProvenance,
  FunctionalGroup,
  LocalizedLabel,
} from '../../../types/members';
import type { MembersConfigValue } from '../../../types/membersConfig';
import {
  groupResolvedFields,
  LABEL_KEY_SCHEME,
  resolveShippedLabel,
  type FieldHierarchyGroup,
  type LabelTranslator,
} from '../../../services/membersConfigService';
import type { FieldConfig } from '../../../types/members';
import { FilterableHeader } from '../../filters/FilterableHeader';
import { useFilterableTable } from '../../../hooks/useFilterableTable';

export interface MembersGroupFieldHierarchyProps {
  /**
   * The resolved field-config the hierarchy is derived from (`GET /members/field-config`).
   * Null/absent → an "unavailable" note (an unconfigured tenant or an older module build), never
   * an error — the hierarchy, like the provenance list, never gates authoring.
   */
  config: FieldConfig | null | undefined;
  /** UI language for the inline labels (matches the editor's `lang` convention, steering 32). */
  lang: 'nl' | 'en';
}

/** The three provenance badges (shared vocabulary with `MembersFieldProvenanceList`, R1.2). */
const PROVENANCE_BADGE: Record<
  FieldProvenance,
  { colorScheme: string; nl: string; en: string }
> = {
  base: { colorScheme: 'gray', nl: 'Basis', en: 'Base' },
  tenant_added: { colorScheme: 'green', nl: 'Toegevoegd', en: 'Tenant-added' },
  base_overridden: { colorScheme: 'orange', nl: 'Basis (overschreven)', en: 'Base (overridden)' },
};

/** The unqualified field-key segment used as the resource-key / enum segment (R4.4, `38` rule 6). */
function unqualifiedKey(key: string): string {
  const i = key.lastIndexOf('.');
  return i >= 0 ? key.slice(i + 1) : key;
}

/** True when `v` is a plain object (not array/null) — used to read the `scope` attribute. */
function isObject(v: MembersConfigValue | undefined): v is { [k: string]: MembersConfigValue } {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

/** Normalize the resolved descriptor's `options` into rich `{value,label?}` entries (R4.4). */
function toEnumOptions(
  options: FieldConfigField['options'] | undefined,
): EnumOptionConfig[] {
  if (!Array.isArray(options)) return [];
  return options.map((o) => (typeof o === 'string' ? { value: o } : o));
}

/**
 * The per-field attribute chips (R4.2 — "per-field attributes"): the field's type, requiredness,
 * visibility, order, and scope-axis binding (step 9), read straight off the resolved descriptor.
 * Presentation only.
 */
const FieldAttributeChips: React.FC<{ field: FieldConfigField; lang: 'nl' | 'en' }> = ({
  field,
  lang,
}) => {
  const chips: { label: string; colorScheme: string; testId: string }[] = [];

  if (field.type) {
    chips.push({ label: field.type, colorScheme: 'purple', testId: 'attr-type' });
  }
  if (field.required) {
    chips.push({
      label: lang === 'nl' ? 'verplicht' : 'required',
      colorScheme: 'red',
      testId: 'attr-required',
    });
  }
  if (field.visible === false) {
    chips.push({
      label: lang === 'nl' ? 'verborgen' : 'hidden',
      colorScheme: 'gray',
      testId: 'attr-hidden',
    });
  }
  if (field.read_only) {
    chips.push({
      label: lang === 'nl' ? 'alleen-lezen' : 'read-only',
      colorScheme: 'blue',
      testId: 'attr-readonly',
    });
  }
  // Scope-axis attribute (Phase 3 step 9): the resolved descriptor may carry a `scope` object.
  const scope = (field as unknown as { scope?: MembersConfigValue }).scope;
  if (isObject(scope) && scope.enabled === true) {
    chips.push({
      label: lang === 'nl' ? 'scope-as' : 'scope axis',
      colorScheme: 'teal',
      testId: 'attr-scope',
    });
  }
  // (members-analytics-role-removal) the analytics-alias role chip was removed — the per-field
  // analytics role config layer no longer exists.

  if (chips.length === 0) return null;
  return (
    <Wrap spacing={1} data-testid={`members-hierarchy-attrs-${field.key}`}>
      {chips.map((c) => (
        <WrapItem key={c.testId}>
          <Badge
            fontSize="0.6rem"
            colorScheme={c.colorScheme}
            data-testid={`members-hierarchy-${c.testId}-${field.key}`}
          >
            {c.label}
          </Badge>
        </WrapItem>
      ))}
    </Wrap>
  );
};

/**
 * The resolved enum options for a field, rendered as value→label chips (R4.4): the `value` is the
 * LANGUAGE-NEUTRAL key (shown verbatim), the `label` resolves via the enum resource key with the
 * inline per-language override. Rendered only when the field actually ships/declares options.
 */
const FieldEnumOptions: React.FC<{
  field: FieldConfigField;
  lang: 'nl' | 'en';
  resolveEnumLabel: (fieldKey: string, opt: EnumOptionConfig) => string;
}> = ({ field, lang, resolveEnumLabel }) => {
  const options = toEnumOptions(field.options);
  if (options.length === 0) return null;
  const fieldSeg = unqualifiedKey(field.key);
  return (
    <Wrap spacing={1} mt={1} data-testid={`members-hierarchy-enum-${field.key}`}>
      {options.map((opt) => (
        <WrapItem key={opt.value}>
          <Badge
            variant="outline"
            fontSize="0.6rem"
            colorScheme="purple"
            data-testid={`members-hierarchy-enum-${field.key}-${opt.value}`}
          >
            {/* value (neutral) → resolved per-language label */}
            <Text as="span" color="gray.500">
              {opt.value}
            </Text>
            {' · '}
            {resolveEnumLabel(fieldSeg, opt)}
          </Badge>
        </WrapItem>
      ))}
    </Wrap>
  );
};

/** A flat row shape the Table Filter Framework v2 operates on (its data is `Record<string,any>`). */
interface FieldTableRow extends Record<string, unknown> {
  field: FieldConfigField;
  /** The resolved (resource-key + inline override) display label — the filter/sort key. */
  label: string;
  key: string;
  type: string;
  provenance: FieldProvenance;
}

/**
 * One functional-group section: the group heading + its fields rendered as a Table Filter
 * Framework v2 table (R4.5 composition). The table header cells are `FilterableHeader`s (text
 * filter + sortable `aria-sort` + keyboard sort), and `useFilterableTable` drives the
 * filter-then-sort pipeline over the group's rows.
 */
const GroupSection: React.FC<{
  section: FieldHierarchyGroup;
  lang: 'nl' | 'en';
  resolveFieldLabel: (field: FieldConfigField) => string;
  resolveGroupHeading: (section: FieldHierarchyGroup) => string;
  resolveEnumLabel: (fieldKey: string, opt: EnumOptionConfig) => string;
}> = ({ section, lang, resolveFieldLabel, resolveGroupHeading, resolveEnumLabel }) => {
  const heading = resolveGroupHeading(section);
  const emptyNote = lang === 'nl' ? 'Geen velden in deze groep.' : 'No fields in this group.';

  // Build the flat rows the Table Filter Framework operates on. Order is already the derived
  // `(field.order, key)` from `groupResolvedFields`; the sort hook starts in that order (no
  // default sort) and only re-orders when the author clicks a sortable header.
  const rows: FieldTableRow[] = useMemo(
    () =>
      section.fields.map((f) => ({
        field: f,
        label: resolveFieldLabel(f),
        key: f.key,
        type: f.type ?? '',
        provenance: f.provenance ?? 'base',
      })),
    [section.fields, resolveFieldLabel],
  );

  const {
    filters,
    setFilter,
    sortField,
    sortDirection,
    handleSort,
    processedData,
  } = useFilterableTable<FieldTableRow>(rows, {
    initialFilters: { label: '', key: '' },
  });

  const colLabel = {
    name: lang === 'nl' ? 'Veld' : 'Field',
    key: lang === 'nl' ? 'Sleutel' : 'Key',
    attrs: lang === 'nl' ? 'Attributen' : 'Attributes',
    provenance: lang === 'nl' ? 'Herkomst' : 'Provenance',
  };

  return (
    <Box
      data-testid={`members-hierarchy-group-${section.resolved ? section.key : '__ungrouped__'}`}
      borderWidth="1px"
      borderColor={section.resolved ? 'gray.700' : 'orange.700'}
      borderRadius="md"
      p={3}
      bg="gray.850"
    >
      <HStack justify="space-between" mb={2}>
        <HStack spacing={2}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.200">
            {heading}
          </Text>
          {section.resolved ? (
            <Text fontSize="xs" color="gray.500">
              {section.key}
            </Text>
          ) : (
            <Badge colorScheme="orange" fontSize="0.6rem" data-testid="members-hierarchy-unresolved-badge">
              {lang === 'nl' ? 'niet-oplosbaar' : 'unresolvable'}
            </Badge>
          )}
        </HStack>
        {section.resolved && typeof section.group?.order === 'number' && (
          <Text fontSize="xs" color="gray.600">
            #{section.group.order}
          </Text>
        )}
      </HStack>

      {section.fields.length === 0 ? (
        <Text
          fontSize="xs"
          color="gray.600"
          data-testid={`members-hierarchy-group-empty-${section.key}`}
        >
          {emptyNote}
        </Text>
      ) : (
        <TableContainer overflowX="auto">
          <Table
            variant="simple"
            size="sm"
            bg="gray.800"
            aria-label={
              lang === 'nl'
                ? `Velden in groep ${heading}`
                : `Fields in group ${heading}`
            }
          >
            <Thead>
              <Tr>
                <FilterableHeader
                  label={colLabel.name}
                  filterValue={filters.label}
                  onFilterChange={(v) => setFilter('label', v)}
                  sortable
                  sortDirection={sortField === 'label' ? sortDirection : null}
                  onSort={() => handleSort('label')}
                  placeholder={lang === 'nl' ? 'Filter velden…' : 'Filter fields…'}
                />
                <FilterableHeader
                  label={colLabel.key}
                  filterValue={filters.key}
                  onFilterChange={(v) => setFilter('key', v)}
                  sortable
                  sortDirection={sortField === 'key' ? sortDirection : null}
                  onSort={() => handleSort('key')}
                  placeholder={lang === 'nl' ? 'Filter sleutels…' : 'Filter keys…'}
                />
                <FilterableHeader label={colLabel.attrs} />
                <FilterableHeader
                  label={colLabel.provenance}
                  sortable
                  sortDirection={sortField === 'provenance' ? sortDirection : null}
                  onSort={() => handleSort('provenance')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map((row) => {
                const f = row.field;
                const badge = PROVENANCE_BADGE[row.provenance] ?? PROVENANCE_BADGE.base;
                return (
                  <Tr
                    key={f.key}
                    data-testid={`members-hierarchy-field-${f.key}`}
                    _hover={{ bg: 'gray.700' }}
                  >
                    <Td>
                      <Text fontSize="sm" color="gray.200">
                        {row.label}
                      </Text>
                      <FieldEnumOptions field={f} lang={lang} resolveEnumLabel={resolveEnumLabel} />
                    </Td>
                    <Td>
                      <Text fontSize="xs" color="gray.500">
                        {f.key}
                      </Text>
                    </Td>
                    <Td>
                      <FieldAttributeChips field={f} lang={lang} />
                    </Td>
                    <Td>
                      <Badge
                        colorScheme={badge.colorScheme}
                        data-testid={`members-hierarchy-provenance-${f.key}`}
                      >
                        {badge[lang]}
                      </Badge>
                    </Td>
                  </Tr>
                );
              })}
            </Tbody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
};

export const MembersGroupFieldHierarchy: React.FC<MembersGroupFieldHierarchyProps> = ({
  config,
  lang,
}) => {
  // The `admin`-namespace translator the Option-(b) resolver uses for shipped labels (R4.4).
  const { t, i18n } = useTranslation('admin');

  // Wrap i18next into the resolver's minimal `LabelTranslator` shape. `exists`/`t` are called with
  // the fully-qualified `admin:membersConfig.*` key, so the namespace prefix resolves regardless of
  // the hook's bound namespace.
  const translator: LabelTranslator = useMemo(
    () => ({
      t: (key, options) => t(key, { ...options, defaultValue: key }) as unknown as string,
      exists: (key, options) =>
        typeof i18n?.exists === 'function' ? i18n.exists(key, options) : false,
    }),
    [t, i18n],
  );

  // Shipped FIELD label: inline override (`field.label`) ?? resource key ?? the stable key.
  const resolveFieldLabel = useMemo(
    () =>
      (field: FieldConfigField): string =>
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.fieldKey(unqualifiedKey(field.key)),
          inline: field.label,
          lang,
          translator,
          fallback: field.key,
        }),
    [lang, translator],
  );

  // Shipped GROUP heading: inline override (`group.label`) ?? resource key ?? the group key. The
  // trailing "ungrouped" bucket has no catalog group → a plain bilingual literal.
  const resolveGroupHeading = useMemo(
    () =>
      (section: FieldHierarchyGroup): string => {
        if (!section.resolved) return lang === 'nl' ? 'Niet-gegroepeerd' : 'Ungrouped';
        return resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.groupKey(section.key),
          inline: section.group?.label as FunctionalGroup['label'],
          lang,
          translator,
          fallback: section.key,
        });
      },
    [lang, translator],
  );

  // Shipped ENUM-OPTION label: the option `value` is LANGUAGE-NEUTRAL (never translated); only the
  // `label` resolves — inline override ?? the enum resource key ?? the value itself as fallback.
  const resolveEnumLabel = useMemo(
    () =>
      (fieldSeg: string, opt: EnumOptionConfig): string =>
        resolveShippedLabel({
          resourceKey: LABEL_KEY_SCHEME.enumKey(fieldSeg, opt.value),
          inline: opt.label as LocalizedLabel | undefined,
          lang,
          translator,
          fallback: opt.value,
        }),
    [lang, translator],
  );

  const sections = groupResolvedFields(config);
  const title = lang === 'nl' ? 'Groep → veld → attribuut' : 'Group → field → attribute';
  const empty =
    lang === 'nl' ? 'Geen opgeloste velden beschikbaar.' : 'No resolved fields available.';

  return (
    <Box
      data-testid="members-group-field-hierarchy"
      mb={4}
      p={3}
      borderWidth="1px"
      borderColor="gray.700"
      borderRadius="md"
      bg="gray.900"
    >
      <Text fontSize="sm" color="gray.400" mb={2}>
        {title}
      </Text>
      {sections.length === 0 ? (
        <Text fontSize="sm" color="gray.500" data-testid="members-group-field-hierarchy-empty">
          {empty}
        </Text>
      ) : (
        <VStack align="stretch" spacing={3}>
          {sections.map((section) => (
            <GroupSection
              key={section.resolved ? section.key : '__ungrouped__'}
              section={section}
              lang={lang}
              resolveFieldLabel={resolveFieldLabel}
              resolveGroupHeading={resolveGroupHeading}
              resolveEnumLabel={resolveEnumLabel}
            />
          ))}
        </VStack>
      )}
    </Box>
  );
};

export default MembersGroupFieldHierarchy;
