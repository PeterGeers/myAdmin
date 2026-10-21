/**
 * Members typed authoring UI — the group → field → attribute DRILL-DOWN (Members config redesign
 * Phase 3, step 11; task 4.8 wires it together).
 *
 * A structured, bilingual, no-raw-JSON editor for the `members.*` field overlay, reachable from the
 * Tenant-Admin area for a Members-enabled tenant. It replaces the former two-tab slice-editor with a
 * drill-down: **functional-groups table → group modal → fields table → field modal**. The tenant
 * admin designs the system from a functional view — every concept is an attribute of a field, every
 * field belongs to a group:
 *
 *   - `MembersGroupsTable` — the entry point: create / edit / delete-when-empty a functional group
 *     (R4.1/R4.2); a group's modal drills into its fields.
 *   - `MembersFieldsTable` — the fields of the opened group; row-click opens the field modal.
 *   - `MembersFieldModal` — every editable field option AS AN ATTRIBUTE, including the step-9 scope
 *     attribute and the step-10 analytics alias; its `actionsSlot` carries `MembersFieldActions`.
 *   - `MembersFieldActions` — provenance-driven delete / reset / hide + move-to-group (R1.3/R4.3);
 *     provenance is DERIVED (never a badge) and only GOVERNS the actions offered.
 *
 * ## The single save path (R1.4/R4.8, `38` rule 5 / Property 8)
 *
 * The editor holds ONE working `field_overlay` object in state. Every modal mutation is a pure
 * `overlayModel` transform applied to that object (never a network call). The ONE **Save** button
 * commits the whole object in a SINGLE request via `saveMembersParameter` (PUT the tenant row, or
 * POST to create it), then reloads. There is no per-field save, no second authoring door — group
 * create/edit/delete, field edits, attribute add/edit/delete, move-to-group, scope-as-attribute
 * (step 9) and the analytics alias (step 10) all author the one object through this one path.
 *
 * The resolved field-config (`GET /members/field-config`) is loaded best-effort for the projection
 * STATUS banner and the DERIVED provenance that governs the field modal's actions; a failure
 * degrades to "unavailable" and NEVER blocks authoring.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  HStack,
  Spinner,
  Text,
  useToast,
  VStack,
} from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import {
  getMembersFieldConfig,
  resolveFieldConfigLabel,
  saveMembersParameter,
} from '../../../services/membersConfigService';
import { MembersConfigStatus } from './MembersConfigStatus';
import { MembersGroupsTable } from './MembersGroupsTable';
import { MembersFieldsTable } from './MembersFieldsTable';
import { MembersFieldModal, type FieldModalMode } from './MembersFieldModal';
import { MembersFieldActions } from './MembersFieldActions';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldProvenance } from '../../../types/members';

interface Props {
  tenant: string;
  /** Known role names for enum-option `roles` multi-selects in the field modal. */
  availableRoles?: string[];
}

/** Build a `fieldKey → provenance` map from the resolved field-config (DERIVED, read-only). */
function provenanceByKey(cfg: FieldConfig | null): Record<string, FieldProvenance> {
  const m: Record<string, FieldProvenance> = {};
  (cfg?.fields ?? []).forEach((f) => {
    if (f.key && f.provenance) m[f.key] = f.provenance;
  });
  return m;
}

export const MembersConfigEditor: React.FC<Props> = ({ tenant, availableRoles = [] }) => {
  const { i18n } = useTranslation();
  const lang = (i18n.language?.startsWith('nl') ? 'nl' : 'en') as 'nl' | 'en';
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configStatus, setConfigStatus] = useState<Record<string, string | number | null>>({});
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);

  // The ONE working field_overlay object the whole drill-down authors; committed in one save.
  const [overlay, setOverlay] = useState<MembersConfigValue>({});
  // Baseline to detect unsaved edits (one Save → one request).
  const [baseline, setBaseline] = useState<string>('{}');

  // Drill-down navigation: which group is open (null = groups table), and the field modal state.
  const [openGroupKey, setOpenGroupKey] = useState<string | null>(null);
  const [fieldModalOpen, setFieldModalOpen] = useState(false);
  const [fieldModalMode, setFieldModalMode] = useState<FieldModalMode>('edit');
  const [fieldModalKey, setFieldModalKey] = useState<string | undefined>(undefined);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      // Load the resolved field config FIRST — it carries the RAW stored `config#fields` overlay
      // (`field_overlay`) this editor seeds + writes back (spec 11 bugfix). GET and PUT are the
      // SAME SAM row, so a save is loss-free. The retired Flask `members.field_overlay` param is
      // no longer read here — SAM `config#fields` is the single source of truth. Best-effort: a
      // failure resolves to null (banner hides, provenance = base) and NEVER blocks authoring.
      const resolvedConfig = await getMembersFieldConfig();
      setConfigStatus(resolvedConfig?.config_status ?? {});
      setFieldConfig(resolvedConfig);
      // Seed the ONE working overlay from the authoritative SAM row. The reader serves the
      // overlay in the AUTHORING WIRE shape already (`fields` / `fixed_overrides` /
      // `functional_groups`, the one-key contract) so read + write are symmetric — no client-side
      // key translation.
      const overlayValue = (resolvedConfig?.field_overlay as MembersConfigValue) ?? {};
      setOverlay(overlayValue);
      setBaseline(JSON.stringify(overlayValue));
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

  const dirty = useMemo(() => JSON.stringify(overlay) !== baseline, [overlay, baseline]);
  const provByKey = useMemo(() => provenanceByKey(fieldConfig), [fieldConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await saveMembersParameter('field_overlay', overlay, null);
      if (res.success) {
        // Honest delivery status (reliability): the save committed to MySQL, but if the
        // projection to the module's DynamoDB config FAILED, say so instead of a false
        // "Saved" — the edit is persisted but not yet live to the Members module.
        if (res.projected === false) {
          toast({
            title: t('Opgeslagen, maar niet geprojecteerd', 'Saved, but not delivered'),
            description:
              res.projection_error ??
              t(
                'De wijziging is opgeslagen maar nog niet naar de module geprojecteerd.',
                'The change was saved but has not yet been projected to the module.',
              ),
            status: 'warning',
            duration: 9000,
            isClosable: true,
          });
        } else {
          toast({ title: t('Opgeslagen', 'Saved'), status: 'success', duration: 3000 });
        }
        await load();
      } else {
        toast({ title: 'Error', description: res.error, status: 'error', duration: 6000 });
      }
    } catch (e) {
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setSaving(false);
    }
  };

  const openFields = (groupKey: string) => setOpenGroupKey(groupKey);
  const backToGroups = () => setOpenGroupKey(null);

  const openEditField = (fieldKey: string) => {
    setFieldModalMode('edit');
    setFieldModalKey(fieldKey);
    setFieldModalOpen(true);
  };
  const openAddField = (groupKey: string | null) => {
    if (groupKey === null) return; // the ungrouped bucket is not an authoring target
    setOpenGroupKey(groupKey);
    setFieldModalMode('create');
    setFieldModalKey(undefined);
    setFieldModalOpen(true);
  };

  if (loading) {
    return (
      <Box p={4}>
        <Spinner color="orange.400" />
        <Text color="gray.400" display="inline" ml={2}>
          {t('Configuratie laden…', 'Loading configuration…')}
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

  // The open-group heading resolves from the RESOLVED config's group `label{}` (R4): the served
  // per-language label for the open functional group, falling through to its key (never blank).
  const openGroupLabel =
    openGroupKey != null
      ? (fieldConfig?.functional_groups ?? []).find((g) => g.key === openGroupKey)?.label
      : undefined;
  const openGroupHeading =
    openGroupKey != null ? resolveFieldConfigLabel(openGroupLabel, lang, openGroupKey) : '';

  return (
    <Box data-testid="members-config-editor">
      <MembersConfigStatus status={configStatus} lang={lang} />

      {/* Drill-down body: the groups table, or the fields table of the opened group. */}
      {openGroupKey === null ? (
        <MembersGroupsTable
          fieldConfig={fieldConfig}
          overlay={overlay}
          onChange={setOverlay}
          onOpenFields={openFields}
          lang={lang}
        />
      ) : (
        <VStack align="stretch" spacing={2}>
          <HStack>
            <Button
              size="sm"
              variant="ghost"
              colorScheme="orange"
              onClick={backToGroups}
              data-testid="members-drilldown-back"
            >
              {t('← Groepen', '← Groups')}
            </Button>
            <Text fontSize="sm" color="gray.300" fontWeight="semibold">
              {openGroupHeading}
            </Text>
          </HStack>
          <MembersFieldsTable
            fieldConfig={fieldConfig}
            overlay={overlay}
            groupKey={openGroupKey}
            onEditField={openEditField}
            onAddField={openAddField}
            lang={lang}
          />
        </VStack>
      )}

      {/* Single save path: one Save → one request → reload (Property 8). */}
      <Box borderTopWidth="1px" borderColor="gray.700" mt={2} pt={4}>
        <HStack justify="flex-end">
          {dirty && (
            <Text fontSize="sm" color="yellow.300" mr="auto" data-testid="members-unsaved-indicator">
              {t('Niet-opgeslagen wijzigingen', 'Unsaved changes')}
            </Text>
          )}
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isLoading={saving}
            isDisabled={!dirty}
            loadingText={t('Opslaan…', 'Saving…')}
            data-testid="members-config-save"
          >
            {t('Opslaan', 'Save')}
          </Button>
        </HStack>
      </Box>

      {/* The field modal — opened from the fields table. Provenance governs its actions slot. */}
      {openGroupKey != null && (
        <MembersFieldModal
          isOpen={fieldModalOpen}
          onClose={() => setFieldModalOpen(false)}
          mode={fieldModalMode}
          fieldKey={fieldModalKey}
          groupKey={openGroupKey}
          overlay={overlay}
          fieldConfig={fieldConfig}
          onChange={setOverlay}
          availableRoles={availableRoles}
          lang={lang}
          actionsSlot={
            fieldModalMode === 'edit' && fieldModalKey ? (
              <MembersFieldActions
                fieldKey={fieldModalKey}
                currentGroupKey={openGroupKey}
                provenance={provByKey[fieldModalKey]}
                overlay={overlay}
                onChange={setOverlay}
                onClose={() => setFieldModalOpen(false)}
                lang={lang}
              />
            ) : null
          }
        />
      )}
    </Box>
  );
};

export default MembersConfigEditor;
