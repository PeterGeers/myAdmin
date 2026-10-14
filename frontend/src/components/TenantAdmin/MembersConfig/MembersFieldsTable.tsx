/**
 * Fields table within a group (Members config drill-down — Phase 3, task 4.5; remediation R1.1/R1.2).
 *
 * The third tier of the group → field → attribute drill-down: reached from the group modal's
 * **Fields** affordance (task 4.4), it lists the fields assigned to one functional group as a Table
 * Filter Framework v2 table (`useFilterableTable` + `FilterableHeader`, steering `37`/`32`) in
 * DERIVED `(field.order, key)` order (`38` rule 2 — no stored absolute position). Columns show the
 * field's key attributes (resolved label, key, type, and compact attribute flags). It offers:
 *   - **Add field** → opens the field modal (task 4.6) in create mode for this group;
 *   - **row-click** → opens the field modal in edit mode (the row-click-opens-modal convention,
 *     `32`); the modal (task 4.6/4.7) edits attributes, moves the field, and — gated by the field's
 *     DERIVED provenance — deletes / resets it.
 *
 * ## DISPLAY from the resolved config (remediation R1.1/R1.2)
 *
 * The table DISPLAYS the group's fields from the RESOLVED `FieldConfig` (`GET /members/field-config`)
 * — the FULL field set assigned to the group: platform fixed, calculated, AND tenant-added, in the
 * derived `(field.order, key)` order (`groupResolvedFields` buckets + orders them, R1.2). This is
 * the fix for the I-3 defect family: the drill-down formerly listed only the raw `field_overlay`
 * deltas, hiding every fixed/calculated field. The working `field_overlay` is NO LONGER the display
 * source — it stays the WRITE model, mutated by the field modal and committed once by the editor.
 *
 * WHERE the resolved config is unavailable (fetch failure / older module build) the table degrades
 * to listing the fields authored in the working overlay, never blocking (R1.4). A field whose
 * `functional_group` is NOT catalog-resolvable is surfaced by passing `groupKey={null}` (the
 * "ungrouped" bucket), never silently dropped (R4.3). Labels resolve straight from the served
 * per-language `label{}` via `resolveFieldConfigLabel` (`label[lang] ?? label.en ?? label.nl ?? key`,
 * R4.1/R4.2/R4.4) — no resource-key indirection.
 */
import React, { useMemo } from 'react';
import {
  Badge,
  Box,
  Button,
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
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import {
  listFieldsInGroup,
  listUngroupedFields,
} from './overlayModel';
import { groupResolvedFields, resolveFieldConfigLabel } from '../../../services/membersConfigService';
import { FilterableHeader } from '../../filters/FilterableHeader';
import { useFilterableTable } from '../../../hooks/useFilterableTable';

export interface MembersFieldsTableProps {
  /**
   * The resolved `FieldConfig` the table DISPLAYS the group's full field set from (R1.1/R1.2).
   * Null/absent → the table degrades to the working overlay's fields (R1.4), never blocks.
   */
  fieldConfig?: FieldConfig | null;
  /** The working field_overlay — the WRITE model (display source only in the R1.4 fallback). */
  overlay: MembersConfigValue | undefined;
  /**
   * The group whose fields are listed. `null` lists the "ungrouped" bucket — fields whose
   * `functional_group` is absent / not catalog-resolvable (surfaced, never dropped — R4.3).
   */
  groupKey: string | null;
  /** Open the field modal in edit mode for this field (task 4.6). */
  onEditField?: (fieldKey: string) => void;
  /** Open the field modal in create mode for this group (task 4.6). */
  onAddField?: (groupKey: string | null) => void;
  lang: 'nl' | 'en';
}

/** A flat row the Table Filter Framework operates on (its data is `Record<string, any>`). */
interface FieldRow extends Record<string, unknown> {
  field: FieldConfigField;
  label: string;
  key: string;
  type: string;
}

/** Compact attribute flags shown on a field row (type / required / hidden / read-only / scope). */
const FieldFlags: React.FC<{ field: FieldConfigField; lang: 'nl' | 'en' }> = ({ field, lang }) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const flags: { label: string; colorScheme: string; id: string }[] = [];
  if (field.type) flags.push({ label: field.type, colorScheme: 'purple', id: 'type' });
  if (field.required) flags.push({ label: t('verplicht', 'required'), colorScheme: 'red', id: 'required' });
  if (field.visible === false) flags.push({ label: t('verborgen', 'hidden'), colorScheme: 'gray', id: 'hidden' });
  if (field.read_only) flags.push({ label: t('alleen-lezen', 'read-only'), colorScheme: 'blue', id: 'readonly' });
  // The resolved descriptor may carry a `scope` object (served after the SAM read-wire, task 3.1).
  const scope = (field as unknown as { scope?: MembersConfigValue }).scope;
  if (scope && typeof scope === 'object' && !Array.isArray(scope) && (scope as Record<string, unknown>).enabled === true) {
    flags.push({ label: t('scope-as', 'scope axis'), colorScheme: 'teal', id: 'scope' });
  }
  if (flags.length === 0) return null;
  return (
    <Wrap spacing={1}>
      {flags.map((f) => (
        <WrapItem key={f.id}>
          <Badge fontSize="0.6rem" colorScheme={f.colorScheme}>
            {f.label}
          </Badge>
        </WrapItem>
      ))}
    </Wrap>
  );
};

export const MembersFieldsTable: React.FC<MembersFieldsTableProps> = ({
  fieldConfig,
  overlay,
  groupKey,
  onEditField,
  onAddField,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // DISPLAY the group's FULL resolved field set in DERIVED `(field.order, key)` order (R1.1/R1.2).
  // `groupResolvedFields` buckets the resolved config into DEFINED catalog groups + a trailing
  // "ungrouped" bucket (`resolved: false`, R4.3); `groupKey === null` selects that bucket, a real
  // group key selects its section. When the resolved config is unavailable the sections are empty,
  // so we fall back to the working overlay's fields — degrade, never block (R1.4).
  const rows: FieldRow[] = useMemo(() => {
    const sections = groupResolvedFields(fieldConfig);
    const haveResolved = sections.length > 0;

    if (haveResolved) {
      const section =
        groupKey === null
          ? sections.find((s) => !s.resolved)
          : sections.find((s) => s.resolved && s.key === groupKey);
      const fields = section?.fields ?? [];
      return fields.map((f) => ({
        field: f,
        label: resolveFieldConfigLabel(f.label, lang, f.key),
        key: f.key,
        type: f.type ?? '',
      }));
    }

    // Fallback (R1.4): the resolved config is unavailable — list the working overlay's fields.
    const entries =
      groupKey === null ? listUngroupedFields(overlay) : listFieldsInGroup(overlay, groupKey);
    return entries.map((e) => ({
      field: {
        key: e.key,
        type: e.field.type,
        required: e.field.required,
        visible: e.field.visible,
        read_only: e.field.read_only,
        functional_group: e.field.functional_group,
        order: e.field.order,
        label: { en: e.field.label_en, nl: e.field.label_nl },
        scope: e.field.scope,
      } as FieldConfigField,
      label: resolveFieldConfigLabel({ en: e.field.label_en, nl: e.field.label_nl }, lang, e.key),
      key: e.key,
      type: e.field.type ?? '',
    }));
  }, [fieldConfig, overlay, groupKey, lang]);

  const { filters, setFilter, sortField, sortDirection, handleSort, processedData } =
    useFilterableTable<FieldRow>(rows, { initialFilters: { label: '', key: '' } });

  const col = {
    name: t('Veld', 'Field'),
    key: t('Sleutel', 'Key'),
    attrs: t('Attributen', 'Attributes'),
  };

  const testScope = groupKey ?? '__ungrouped__';

  return (
    <Box data-testid={`members-fields-table-${testScope}`}>
      <HStack justify="space-between" mb={2}>
        <Text fontSize="sm" color="gray.400">
          {groupKey === null
            ? t('Niet-gegroepeerde velden', 'Ungrouped fields')
            : t('Velden in groep', 'Fields in group')}
        </Text>
        {groupKey !== null && (
          <Button
            size="sm"
            colorScheme="orange"
            onClick={() => onAddField?.(groupKey)}
            data-testid="members-fields-add-btn"
          >
            {t('Veld toevoegen', 'Add field')}
          </Button>
        )}
      </HStack>

      {rows.length === 0 ? (
        <Text fontSize="sm" color="gray.500" data-testid={`members-fields-empty-${testScope}`}>
          {t('Geen velden in deze groep.', 'No fields in this group.')}
        </Text>
      ) : (
        <TableContainer overflowX="auto">
          <Table
            variant="simple"
            size="sm"
            bg="gray.800"
            aria-label={
              groupKey === null
                ? t('Niet-gegroepeerde velden', 'Ungrouped fields')
                : t('Velden in groep', 'Fields in group')
            }
          >
            <Thead>
              <Tr>
                <FilterableHeader
                  label={col.name}
                  filterValue={filters.label}
                  onFilterChange={(v) => setFilter('label', v)}
                  sortable
                  sortDirection={sortField === 'label' ? sortDirection : null}
                  onSort={() => handleSort('label')}
                  placeholder={t('Filter velden…', 'Filter fields…')}
                />
                <FilterableHeader
                  label={col.key}
                  filterValue={filters.key}
                  onFilterChange={(v) => setFilter('key', v)}
                  sortable
                  sortDirection={sortField === 'key' ? sortDirection : null}
                  onSort={() => handleSort('key')}
                  placeholder={t('Filter sleutels…', 'Filter keys…')}
                />
                <FilterableHeader label={col.attrs} />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map((row) => (
                <Tr
                  key={row.key}
                  data-testid={`members-fields-row-${row.key}`}
                  cursor="pointer"
                  _hover={{ bg: 'gray.700' }}
                  role="button"
                  aria-label={t(`Veld ${row.label} bewerken`, `Edit field ${row.label}`)}
                  tabIndex={0}
                  onClick={() => onEditField?.(row.key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onEditField?.(row.key);
                    }
                  }}
                >
                  <Td>
                    <Text fontSize="sm" color="gray.200">
                      {row.label}
                    </Text>
                  </Td>
                  <Td>
                    <Text fontSize="xs" color="gray.500">
                      {row.key}
                    </Text>
                  </Td>
                  <Td>
                    <FieldFlags field={row.field} lang={lang} />
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
};

export default MembersFieldsTable;
