/**
 * Members typed authoring UI — parent (s5c tasks 2.5/2.6, C-EDITOR).
 *
 * A structured, bilingual, no-raw-JSON editor for the `members.*` params, reachable
 * from the Tenant-Admin area for a Members-enabled tenant. It hosts three sub-editors:
 *
 *   1. Functional-group catalog  — field_overlay.functional_groups (list<object>)
 *   2. Field overlay             — field_overlay.fields (map<field_def>) + fixed_overrides,
 *                                  presented above a UNIFIED field list + provenance badge.
 *                                  Scope-binding is authored HERE as a per-field `scope`
 *                                  attribute (Phase 3 step 9) — see below.
 *
 * (The view-contexts sub-editor was removed in Phase 2 step b — view contexts are retired. The
 *  standalone analytics sub-editor TAB, and the whole analytics role / jubilee / address-mapping
 *  config layer, were removed — superseded by the generic Dynamic Pivot Views mechanism.)
 *
 * Members config redesign Phase 3 step 9 (R2): the standalone `scope_dimensions` sub-editor TAB
 * is RETIRED. Scope-binding is now authored as a FIELD ATTRIBUTE — a field (an added variable
 * field under `fields`, or a fixed-field re-presentation under `fixed_overrides`) carries a
 * `scope` sub-object `{enabled, values, label?, required_for?}` declaring that it IS a scope axis
 * bound to itself. The Flask builder DERIVES `config#scope` from these field attributes (falling
 * back to the standalone `members.scope_dimensions` param when the overlay declares no axis), so
 * the resolver (`handler/app.py`) and the `scopegrant#` grants stay untouched (R2.3/R2.4) and the
 * projected `ScopeConfig` is semantically equivalent (Property 2). Authoring stays the SINGLE
 * `field_overlay` object (one save → one re-projection, R2.1) — the scope attribute rides on the
 * same whole-object commit as the field it annotates.
 *
 * (The analytics field-ROLE alias authoring — and the whole analytics role / jubilee-rule /
 * address-mapping config layer — has been removed: it duplicated the generic Dynamic Pivot Views
 * mechanism. There is no analytics tab and no per-field analytics `alias` attribute; the
 * configurator authors only functional groups + the field overlay.)
 *
 * Members config redesign Phase 3 step 11 (R4): the Field Overlay tab leads with the group →
 * field → attribute authoring HIERARCHY (`MembersGroupFieldHierarchy`) on the Phase 1 attribute
 * catalog — functional groups (`key`/`label`/`order`) are the sections, fields are nested within
 * their group, and each field shows its per-field attributes, in DERIVED `(group.order,
 * field.order, key)` order (R4.1/R4.2, no stored position field). A field whose `functional_group`
 * is not catalog-resolvable is surfaced in a trailing "ungrouped" section rather than dropped
 * (R4.3 — the picker-resolvability guard made visible). It is a PRESENTATION view; authoring stays
 * the single `field_overlay` object (one save → one re-projection, R4.7). i18n resource-key wiring
 * and building-block composition (Table Filter Framework v2, LazySelect) are task 4.2.
 *
 * Members config redesign Phase 3 step 8 (R1): the former two-section fixed/overlay split on the
 * Field Overlay tab is re-presented as ONE ordered field list (`MembersFieldProvenanceList`),
 * ordered `(group.order, field.order, key)` (R1.3 — no new position field), each field showing a
 * provenance badge (base / tenant_added / base_overridden, R1.2). That list is a PRESENTATION view
 * over the module's resolved field-config; authoring stays the single `field_overlay` object (one
 * save → one re-projection, R1.4) via the sub-editor below it.
 *
 * Both sub-editors edit the single `field_overlay` param object; each still commits the WHOLE
 * object in one PUT (save-once, Property 8). Pickers offer only defined functional groups /
 * resolvable field keys (Property 7 authoring-time help); the backend validates on Save (R2.1
 * validation for the per-field scope axis).
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Spinner,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  VStack,
} from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import {
  getMembersFieldConfig,
  getMembersParameterDefinitions,
  getMembersParameters,
  orderResolvedFields,
} from '../../../services/membersConfigService';
import { MembersConfigStatus } from './MembersConfigStatus';
import { MembersFieldProvenanceList } from './MembersFieldProvenanceList';
import { MembersGroupFieldHierarchy } from './MembersGroupFieldHierarchy';
import type { Parameter } from '../../../types/parameterTypes';
import type {
  MembersParamDefinition,
  MembersConfigValue,
} from '../../../types/membersConfig';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import { MembersParamSubEditor } from './MembersParamSubEditor';

interface Props {
  tenant: string;
  /**
   * Optional platform fixed/calculated base keys (dotted, e.g. `personal.first_name`).
   * When supplied they are merged into the field-key pickers alongside the tenant's own
   * authored keys. The backend remains authoritative on Save.
   */
  fixedBaseKeys?: string[];
  /** Known role names for enum-option `roles` + permission_roles multi-selects. */
  availableRoles?: string[];
}

/** Pull the functional-group keys out of a field_overlay value object. */
function extractFunctionalGroupKeys(overlay: MembersConfigValue | undefined): string[] {
  if (!overlay || typeof overlay !== 'object' || Array.isArray(overlay)) return [];
  const groups = (overlay as Record<string, MembersConfigValue>).functional_groups;
  if (!Array.isArray(groups)) return [];
  return groups
    .map((g) =>
      g && typeof g === 'object' && !Array.isArray(g)
        ? String((g as Record<string, MembersConfigValue>).key ?? '')
        : '',
    )
    .filter(Boolean);
}

/**
 * Derive the resolvable field-key set from the tenant's own authored config:
 *  - overlay field keys (map keys of field_overlay.fields)
 *  - fixed_override keys (dotted keys the tenant relabels/reassigns)
 * plus any injected platform base keys.
 *
 * Phase 3 step 9 (R2) reconciliation: scope-binding is no longer a standalone
 * `scope_dimensions` param whose dimension keys had to be folded in here — it is now a per-field
 * `scope` ATTRIBUTE that rides on a `fields` / `fixed_overrides` entry. A field authored as a
 * scope axis is therefore ALREADY one of the overlay keys above, so the derived set stays correct
 * without a separate scope source. (The standalone `members.scope_dimensions` param survives only
 * as the backend's fallback projection source — the SPA no longer authors it, so it no longer
 * widens the picker set.)
 */
function deriveResolvableKeys(
  overlay: MembersConfigValue | undefined,
  baseKeys: string[],
): string[] {
  const keys = new Set<string>(baseKeys);
  if (overlay && typeof overlay === 'object' && !Array.isArray(overlay)) {
    const o = overlay as Record<string, MembersConfigValue>;
    const fields = o.fields;
    if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
      Object.keys(fields).forEach((k) => keys.add(k));
    }
    const overrides = o.fixed_overrides;
    if (overrides && typeof overrides === 'object' && !Array.isArray(overrides)) {
      Object.keys(overrides).forEach((k) => keys.add(k));
    }
  }
  return Array.from(keys).sort();
}

export const MembersConfigEditor: React.FC<Props> = ({
  tenant,
  fixedBaseKeys = [],
  availableRoles = [],
}) => {
  const { i18n } = useTranslation();
  const lang = i18n.language?.startsWith('nl') ? 'nl' : 'en';

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [defs, setDefs] = useState<MembersParamDefinition[]>([]);
  const [rows, setRows] = useState<Record<string, Parameter>>({});
  // The module's projected delivered/loaded status (Phase 0 step 3). Empty = unavailable
  // (older module build / fetch glitch) → the status banner simply hides. A status fetch
  // never blocks authoring, so a failure degrades to "unavailable", not an error.
  const [configStatus, setConfigStatus] = useState<Record<string, string | number | null>>({});
  // The module's RESOLVED field list, ordered `(group.order, field.order, key)` (Phase 3 step 8,
  // R1.3). Drives the unified field list + provenance badge that replaced the two-section split.
  // Empty = unavailable (older build / fetch glitch) → the list shows a "no resolved fields" note;
  // the field-config fetch never blocks authoring.
  const [resolvedFields, setResolvedFields] = useState<FieldConfigField[]>([]);
  // The RAW resolved field-config (fields + functional_groups) the group → field → attribute
  // authoring hierarchy (Phase 3 step 11, R4.1) is derived from. Null = unavailable (older build /
  // fetch glitch) → the hierarchy shows an "unavailable" note; the fetch never blocks authoring.
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);

  // Live working copy of the field_overlay param that feeds the pickers, so a newly-added
  // functional group / field key becomes pickable immediately (before Save). Scope-binding now
  // rides on this same object (per-field `scope` attribute, Phase 3 step 9), so there is no longer
  // a separate scope_dimensions working copy to track.
  const [overlayValue, setOverlayValue] = useState<MembersConfigValue>({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [definitions, values] = await Promise.all([
        getMembersParameterDefinitions(),
        getMembersParameters(),
      ]);
      setDefs(definitions);
      setRows(values);
      setOverlayValue((values.field_overlay?.value as MembersConfigValue) ?? {});
      // The resolved field-config feeds BOTH the delivered/loaded status banner (Phase 0 step 3)
      // and the unified field list + provenance badge (Phase 3 step 8, R1). Both are best-effort
      // and non-blocking: a failure resolves to null inside getMembersFieldConfig (the banner then
      // hides, the list shows a "no resolved fields" note), so the editor loads regardless of the
      // module endpoint's availability. The field list is ordered `(group.order, field.order, key)`
      // (R1.3) with NO new position field — the order is derived on read.
      const resolvedConfig = await getMembersFieldConfig();
      setConfigStatus(resolvedConfig?.config_status ?? {});
      setResolvedFields(orderResolvedFields(resolvedConfig));
      // The RAW config feeds the group → field → attribute hierarchy (Phase 3 step 11, R4.1):
      // its `functional_groups` are the sections, its `fields` the nested per-group fields.
      setFieldConfig(resolvedConfig);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();

  }, [tenant]);

  const defByKey = useMemo(() => {
    const m: Record<string, MembersParamDefinition> = {};
    defs.forEach((d) => {
      m[d.key] = d;
    });
    return m;
  }, [defs]);

  const functionalGroupKeys = useMemo(
    () => extractFunctionalGroupKeys(overlayValue),
    [overlayValue],
  );
  const resolvableFieldKeys = useMemo(
    () => deriveResolvableKeys(overlayValue, fixedBaseKeys),
    [overlayValue, fixedBaseKeys],
  );

  const ctx = useMemo(
    () => ({
      functionalGroupKeys,
      resolvableFieldKeys,
      availableRoles,
      lang: lang as 'nl' | 'en',
    }),
    [functionalGroupKeys, resolvableFieldKeys, availableRoles, lang],
  );

  if (loading) {
    return (
      <Box p={4}>
        <Spinner color="orange.400" />
        <Text color="gray.400" display="inline" ml={2}>
          {lang === 'nl' ? 'Configuratie laden…' : 'Loading configuration…'}
        </Text>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={4}>
        <Text color="red.300">{error}</Text>
      </Box>
    );
  }

  const overlayDef = defByKey.field_overlay;

  return (
    <Box data-testid="members-config-editor">
      <MembersConfigStatus status={configStatus} lang={lang as 'nl' | 'en'} />
      <Tabs colorScheme="orange" variant="enclosed" isLazy>
        <TabList>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {lang === 'nl' ? 'Functionele groepen' : 'Functional Groups'}
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {lang === 'nl' ? 'Veldoverlay' : 'Field Overlay'}
          </Tab>
        </TabList>

        <TabPanels>
          {/* 1. Functional-group catalog — a slice of field_overlay */}
          <TabPanel>
            {overlayDef && (
              <MembersParamSubEditor
                paramKey="field_overlay"
                def={overlayDef}
                existing={rows.field_overlay}
                ctx={ctx}
                onValueChange={setOverlayValue}
                onSaved={load}
                sliceKey="functional_groups"
              />
            )}
          </TabPanel>

          {/* 2. Field overlay — fields + fixed_overrides (still the same param object).
              Phase 3 step 8 (R1): the former two-section fixed/overlay split is RE-PRESENTED as
              ONE ordered field list + provenance badge (base / tenant_added / base_overridden),
              ordered `(group.order, field.order, key)` with no new position field (R1.3). The list
              is a presentation view over the module's resolved field-config; authoring stays the
              SINGLE `field_overlay` object (one save → one re-projection, R1.4) via the sub-editor
              below it.
              Phase 3 step 9 (R2): scope-binding is authored HERE too — each `fields` /
              `fixed_overrides` entry carries a `scope` attribute `{enabled, values, label?,
              required_for?}` declaring that the field is a scope axis. The standalone
              `scope_dimensions` tab is retired; the scope attribute rides on this same whole-object
              commit (save-once, Property 8), and the Flask builder derives `config#scope` from it.
              */}
          <TabPanel>
            {/* Phase 3 step 11 (R4.1/R4.2/R4.3): the group → field → attribute authoring
                hierarchy on the Phase 1 catalog — functional groups (key/label/order) as sections,
                fields nested within their group, per-field attributes on each field row, in DERIVED
                `(group.order, field.order, key)` order (no stored position field). A field whose
                group is not catalog-resolvable is surfaced in a trailing "ungrouped" section
                (R4.3). Presentation only; authoring stays the SINGLE `field_overlay` object below. */}
            <MembersGroupFieldHierarchy config={fieldConfig} lang={lang as 'nl' | 'en'} />
            <MembersFieldProvenanceList fields={resolvedFields} lang={lang as 'nl' | 'en'} />
            {overlayDef && (
              <MembersParamSubEditor
                paramKey="field_overlay"
                def={overlayDef}
                existing={rows.field_overlay}
                ctx={ctx}
                onValueChange={setOverlayValue}
                onSaved={load}
                sliceKeys={['fields', 'fixed_overrides']}
              />
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default MembersConfigEditor;
