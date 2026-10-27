/**
 * Functional-groups table — the drill-down ENTRY POINT (Phase 3, task 4.4; remediation R1.1–R1.4).
 *
 * The top of the group → field → attribute drill-down: a Table Filter Framework v2 table
 * (`useFilterableTable` + `FilterableHeader`, steering `37`/`32`) of the tenant's functional groups,
 * in DERIVED `(group.order, key)` order (no stored absolute position, `38` rule 2). It offers:
 *   - **Add group** → opens the group modal in `create` mode;
 *   - **row-click** → opens the group modal in `edit` mode (the row-click-opens-modal convention,
 *     `32`); the modal edits the group and can delete it (only when empty, R1.3) and drill into the
 *     group's fields (task 4.5 via `onOpenFields`).
 *
 * ## The two data roles (remediation R1.1 — DISPLAY vs WRITE)
 *
 * The table DISPLAYS the groups from the RESOLVED `FieldConfig` (`GET /members/field-config`) — the
 * tenant's full functional-group catalog, keyed by `functional_groups` and populated with every
 * resolved field (fixed ⊕ overlay ⊕ calculated) via `groupResolvedFields`. The WORKING
 * `field_overlay` object stays the WRITE model ONLY: the modal mutates it and bubbles the result up
 * through `onChange`; the editor (task 4.8) commits the one object once (Property 8). The delete
 * guard counts the RESOLVED fields in a group (R1.3), so a group holding only base/calculated
 * fields is correctly non-empty.
 *
 * WHERE the resolved config is unavailable (fetch failure / older module build) the table degrades
 * to displaying the groups authored in the working overlay, never blocking (R1.4). Group labels
 * resolve straight from the served per-language `label{}` via `resolveFieldConfigLabel`
 * (`label[lang] ?? label.en ?? label.nl ?? key`, R4.1/R4.2/R4.4) — no resource-key indirection.
 */
import React, { useMemo, useState } from 'react';
import {
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
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig } from '../../../types/members';
import { listGroups } from './overlayModel';
import { groupResolvedFields, resolveFieldConfigLabel } from '../../../services/membersConfigService';
import { FilterableHeader } from '../../filters/FilterableHeader';
import { useFilterableTable } from '../../../hooks/useFilterableTable';
import { MembersGroupModal, type GroupModalMode } from './MembersGroupModal';

export interface MembersGroupsTableProps {
  /**
   * The resolved `FieldConfig` the table DISPLAYS the group catalog + resolved field counts from
   * (R1.1). Null/absent → the table degrades to the working overlay's groups (R1.4), never blocks.
   */
  fieldConfig?: FieldConfig | null;
  /** The working field_overlay — the WRITE model the modal mutates (never the display source). */
  overlay: MembersConfigValue | undefined;
  /** Apply a mutated overlay (the table/modal never save — the editor commits once). */
  onChange: (next: MembersConfigValue) => void;
  /** Drill into a group's fields (opens the fields table, task 4.5). */
  onOpenFields?: (groupKey: string) => void;
  lang: 'nl' | 'en';
}

/** A flat row the Table Filter Framework operates on (its data is `Record<string, any>`). */
interface GroupRow extends Record<string, unknown> {
  label: string;
  key: string;
  order: number | '';
  /** The count of RESOLVED fields in the group (drives the modal's delete-when-empty guard, R1.3). */
  fieldCount: number;
}

export const MembersGroupsTable: React.FC<MembersGroupsTableProps> = ({
  fieldConfig,
  overlay,
  onChange,
  onOpenFields,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<GroupModalMode>('edit');
  const [selectedKey, setSelectedKey] = useState<string | undefined>(undefined);

  // DISPLAY from the RESOLVED config (R1.1): `groupResolvedFields` buckets the full resolved field
  // set into the DEFINED catalog groups in DERIVED `(group.order, key)` order, each carrying its
  // resolved field count (R1.3). When the resolved config is unavailable it yields no sections, so
  // we fall back to the groups authored in the working overlay — degrade, never block (R1.4).
  const rows: GroupRow[] = useMemo(() => {
    const sections = groupResolvedFields(fieldConfig).filter((s) => s.resolved);
    if (sections.length > 0) {
      return sections.map((s) => ({
        label: resolveFieldConfigLabel(s.group?.label, lang, s.key),
        key: s.key,
        order: typeof s.group?.order === 'number' ? s.group.order : '',
        fieldCount: s.fields.length,
      }));
    }
    // Fallback: the resolved config is unavailable — show the overlay's own groups (R1.4).
    return listGroups(overlay).map((g) => ({
      label: resolveFieldConfigLabel({ en: g.label_en, nl: g.label_nl }, lang, g.key),
      key: g.key,
      order: typeof g.order === 'number' ? g.order : '',
      fieldCount: 0,
    }));
  }, [fieldConfig, overlay, lang]);

  /** Resolved field count per group key — the modal's delete-when-empty guard reads this (R1.3). */
  const resolvedCountByKey = useMemo(() => {
    const m: Record<string, number> = {};
    rows.forEach((r) => {
      m[r.key] = r.fieldCount;
    });
    return m;
  }, [rows]);

  /**
   * Resolved group definition per key (`{key, label{nl,en}, order}`) from the server catalog — the
   * edit modal seeds its form from this when the working overlay has no entry (PLATFORM BASE groups
   * live only in the resolved config, not the tenant overlay). Without it, editing a base group
   * opened a BLANK form (bugfix — see root-cause-analysis.md).
   */
  const resolvedGroupByKey = useMemo(() => {
    const m: Record<string, { key: string; label?: Record<string, unknown> | string; order?: number }> = {};
    groupResolvedFields(fieldConfig)
      .filter((s) => s.resolved && s.group)
      .forEach((s) => {
        m[s.key] = {
          key: s.key,
          label: s.group?.label as Record<string, unknown> | string | undefined,
          order: typeof s.group?.order === 'number' ? s.group.order : undefined,
        };
      });
    return m;
  }, [fieldConfig]);

  const { filters, setFilter, sortField, sortDirection, handleSort, processedData } =
    useFilterableTable<GroupRow>(rows, { initialFilters: { label: '', key: '' } });

  const openCreate = () => {
    setModalMode('create');
    setSelectedKey(undefined);
    setModalOpen(true);
  };
  const openEdit = (key: string) => {
    setModalMode('edit');
    setSelectedKey(key);
    setModalOpen(true);
  };

  const col = {
    name: t('Groep', 'Group'),
    key: t('Sleutel', 'Key'),
    order: t('Volgorde', 'Order'),
  };

  return (
    <Box data-testid="members-groups-table">
      <HStack justify="space-between" mb={2}>
        <Text fontSize="sm" color="gray.400">
          {t('Functionele groepen', 'Functional groups')}
        </Text>
        <Button
          size="sm"
          colorScheme="orange"
          onClick={openCreate}
          data-testid="members-groups-add-btn"
        >
          {t('Groep toevoegen', 'Add group')}
        </Button>
      </HStack>

      {rows.length === 0 ? (
        <Text fontSize="sm" color="gray.500" data-testid="members-groups-empty">
          {t('Nog geen groepen. Voeg er een toe om te beginnen.', 'No groups yet. Add one to start.')}
        </Text>
      ) : (
        <TableContainer overflowX="auto">
          <Table
            variant="simple"
            size="sm"
            bg="gray.800"
            aria-label={t('Functionele groepen', 'Functional groups')}
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
                  placeholder={t('Filter groepen…', 'Filter groups…')}
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
                <FilterableHeader
                  label={col.order}
                  sortable
                  sortDirection={sortField === 'order' ? sortDirection : null}
                  onSort={() => handleSort('order')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map((row) => (
                <Tr
                  key={row.key}
                  data-testid={`members-groups-row-${row.key}`}
                  cursor="pointer"
                  _hover={{ bg: 'gray.700' }}
                  role="button"
                  aria-label={t(`Groep ${row.label} bewerken`, `Edit group ${row.label}`)}
                  tabIndex={0}
                  onClick={() => openEdit(row.key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      openEdit(row.key);
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
                    <Text fontSize="xs" color="gray.500">
                      {row.order === '' ? '—' : `#${row.order}`}
                    </Text>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </TableContainer>
      )}

      <MembersGroupModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        mode={modalMode}
        groupKey={selectedKey}
        overlay={overlay}
        onChange={onChange}
        onOpenFields={onOpenFields}
        resolvedFieldCount={selectedKey ? resolvedCountByKey[selectedKey] ?? 0 : 0}
        resolvedGroup={selectedKey ? resolvedGroupByKey[selectedKey] : undefined}
        lang={lang}
      />
    </Box>
  );
};

export default MembersGroupsTable;
