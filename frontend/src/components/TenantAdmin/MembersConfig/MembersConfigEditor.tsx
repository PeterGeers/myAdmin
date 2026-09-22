/**
 * Members typed authoring UI — parent (s5c tasks 2.5/2.6, C-EDITOR).
 *
 * A structured, bilingual, no-raw-JSON editor for the three `members.*` params, reachable
 * from the Tenant-Admin area for a Members-enabled tenant. It hosts four sub-editors:
 *
 *   1. Functional-group catalog  — field_overlay.functional_groups (list<object>)
 *   2. Field overlay             — field_overlay.fields (map<field_def>) + fixed_overrides
 *   3. Scope dimensions          — scope_dimensions (list<object>)
 *   4. View contexts             — view_contexts (list<object>)
 *
 * Sub-editors 1 + 2 both edit the single `field_overlay` param object; each still commits
 * the WHOLE object in one PUT (save-once, Property 8). Pickers offer only defined
 * functional groups / resolvable field keys (Property 7 authoring-time help); the backend
 * validates on Save.
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
  getMembersParameterDefinitions,
  getMembersParameters,
} from '../../../services/membersConfigService';
import type { Parameter } from '../../../types/parameterTypes';
import type {
  MembersParamDefinition,
  MembersConfigValue,
} from '../../../types/membersConfig';
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
 *  - scope-dimension keys
 * plus any injected platform base keys. Mirrors how the backend 2.4 validation widens the
 * resolvable set by the sibling field_overlay + scope_dimensions.
 */
function deriveResolvableKeys(
  overlay: MembersConfigValue | undefined,
  scope: MembersConfigValue | undefined,
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
  if (Array.isArray(scope)) {
    scope.forEach((d) => {
      if (d && typeof d === 'object' && !Array.isArray(d)) {
        const k = String((d as Record<string, MembersConfigValue>).key ?? '');
        if (k) keys.add(k);
      }
    });
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

  // Live working copies of the two params that feed the pickers, so a newly-added
  // functional group / field key becomes pickable immediately (before Save).
  const [overlayValue, setOverlayValue] = useState<MembersConfigValue>({});
  const [scopeValue, setScopeValue] = useState<MembersConfigValue>([]);

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
      setScopeValue((values.scope_dimensions?.value as MembersConfigValue) ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    () => deriveResolvableKeys(overlayValue, scopeValue, fixedBaseKeys),
    [overlayValue, scopeValue, fixedBaseKeys],
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
  const scopeDef = defByKey.scope_dimensions;
  const viewDef = defByKey.view_contexts;

  return (
    <Box data-testid="members-config-editor">
      <Tabs colorScheme="orange" variant="enclosed" isLazy>
        <TabList>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {lang === 'nl' ? 'Functionele groepen' : 'Functional Groups'}
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {lang === 'nl' ? 'Veldoverlay' : 'Field Overlay'}
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {lang === 'nl' ? 'Scope-dimensies' : 'Scope Dimensions'}
          </Tab>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {lang === 'nl' ? 'Weergavecontexten' : 'View Contexts'}
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

          {/* 2. Field overlay — fields + fixed_overrides (still the same param object) */}
          <TabPanel>
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

          {/* 3. Scope dimensions */}
          <TabPanel>
            {scopeDef && (
              <MembersParamSubEditor
                paramKey="scope_dimensions"
                def={scopeDef}
                existing={rows.scope_dimensions}
                ctx={ctx}
                onValueChange={setScopeValue}
                onSaved={load}
              />
            )}
          </TabPanel>

          {/* 4. View contexts */}
          <TabPanel>
            {viewDef && (
              <MembersParamSubEditor
                paramKey="view_contexts"
                def={viewDef}
                existing={rows.view_contexts}
                ctx={ctx}
                onSaved={load}
              />
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default MembersConfigEditor;
