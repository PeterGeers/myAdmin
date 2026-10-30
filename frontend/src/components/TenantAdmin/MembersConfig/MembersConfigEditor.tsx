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
 * derives a CHANGE-OP list from the (loaded baseline → edited working) overlay diff and commits it
 * BY IDENTITY in a SINGLE request via `saveFieldConfigChangeOps` → `PUT /members/config/fields`
 * with an `{ops}` body (spec 03 Phase 5 — the server owns storage placement), then reloads. There
 * is no per-field save, no second authoring door — group
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
  getMembersParameters,
  resolveFieldConfigLabel,
  saveFieldConfigChangeOps,
  saveMembersParameter,
} from '../../../services/membersConfigService';
import { deriveFieldConfigChangeOps } from './fieldConfigChangeOps';
import { deriveScopeDimensions } from './deriveScopeDimensions';
import { classifyScopeChange } from './classifyScopeChange';
import { flatViewToOverlay } from './flatViewToOverlay';
import { MembersConfigStatus } from './MembersConfigStatus';
import { MembersGroupsTable } from './MembersGroupsTable';
import { MembersFieldsTable } from './MembersFieldsTable';
import { MembersFieldModal, type FieldModalMode } from './MembersFieldModal';
import { MembersFieldActions } from './MembersFieldActions';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldProvenance } from '../../../types/members';
import type { Parameter } from '../../../types/parameterTypes';

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

  // Scope mirror RESYNC (spec 03b BU-6, task 6.2, Req 4.4): the two-call scope save is ATOMIC from
  // the admin's view. When the authoritative SAM `config#scope` write SUCCEEDS but the best-effort
  // Flask `members.scope_dimensions` MIRROR write fails, SAM stays authoritative and the two planes
  // are momentarily diverged. Rather than leave that silent, we surface a caller-safe error AND
  // stash the derived dimension set so an admin can RE-DRIVE just the mirror from the resynced SAM
  // truth with one button, instead of re-saving the whole field config. `null` = planes in sync.
  const [scopeMirrorRetry, setScopeMirrorRetry] = useState<
    { dimensions: unknown; message: string } | null
  >(null);
  const [resyncing, setResyncing] = useState(false);

  const load = async (): Promise<FieldConfig | null> => {
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
      // Seed the ONE working overlay from the RESOLVED Flat_View. Task 5.3 (steering 39) stopped
      // the backend surfacing the raw `field_overlay`, so we reconstruct the authoring-wire overlay
      // (`fields` / `fixed_overrides` / `functional_groups`) from the resolved `fields` the response
      // DOES carry. Baseline == the same seed, so the editor is NOT dirty on load and the diff-based
      // save (`deriveFieldConfigChangeOps`) emits an op ONLY for an identity the user actually edits
      // — a move/relabel now finds its field in the buffer instead of no-op'ing on an empty overlay.
      const overlayValue = flatViewToOverlay(resolvedConfig);
      setOverlay(overlayValue);
      setBaseline(JSON.stringify(overlayValue));
      return resolvedConfig;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
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

  /**
   * Persist one derived `config#scope` dimension set across the two planes and REPORT the outcome
   * (spec 03b BU-6, Req 4.2/4.3/4.4). The frontend is the only cross-plane coordinator — no runtime
   * SAM↔Flask call: `saveMembersParameter('scope_dimensions', …)` writes SAM `config#scope` FIRST
   * (authoritative), THEN mirrors the SAME set into the Flask `members.scope_dimensions` validator
   * copy. The Flask→SAM `scopegrant#` projection of user grants is a separate, unchanged pipeline.
   *
   * The save is ATOMIC from the admin's view: the return tells the caller exactly which plane
   * failed so neither a SAM-only nor a mirror-only failure is left silent —
   *  - `'ok'`      — both planes written; the two are in sync;
   *  - `'sam'`     — the authoritative SAM write failed → NOTHING was mirrored (planes never
   *                  diverged); the caller surfaces a hard error and does NOT offer a mirror resync;
   *  - `'mirror'`  — SAM is authoritative but the Flask mirror failed → the planes are momentarily
   *                  diverged; the caller surfaces the error AND offers a RESYNC of just the mirror,
   *                  re-driving it from the already-written SAM truth (the derived `dimensions`).
   */
  const persistScopeDimensions = async (
    dimensions: unknown,
  ): Promise<{ plane: 'ok' | 'sam' | 'mirror'; message?: string }> => {
    // Look up the existing tenant `members.scope_dimensions` param row so the mirror UPDATEs in
    // place (vs. creating a duplicate). Best-effort: a lookup glitch degrades to a create.
    let existing: Parameter | null = null;
    try {
      const params = await getMembersParameters();
      existing = params.scope_dimensions ?? null;
    } catch {
      existing = null;
    }
    const scopeRes = await saveMembersParameter(
      'scope_dimensions',
      dimensions as MembersConfigValue,
      existing,
    );
    if (scopeRes.success) return { plane: 'ok' };
    // A `version` present means the authoritative SAM write LANDED and only the Flask mirror failed
    // (planes diverged → resync offered); absent means SAM itself failed (nothing mirrored).
    const plane: 'sam' | 'mirror' = scopeRes.version ? 'mirror' : 'sam';
    const message =
      scopeRes.mirrorError ??
      scopeRes.error ??
      t('Scope-dimensie bijwerken mislukt', 'Updating the scope dimension failed');
    return { plane, message };
  };

  /**
   * Derive the `config#scope` dimension set from the RESOLVED field config and persist it via the
   * two-plane mirror (spec 03b BU-6, Req 4.2). Called ONLY for a VALUE change (the axis-vs-value
   * gate in {@link handleSave} already refused an AXIS change before anything was written). On a
   * mirror failure it arms the RESYNC affordance (Req 4.4) with the SAME derived set so the admin
   * re-drives the mirror from SAM truth, not a re-derivation that could drift.
   */
  const syncScopeDimensions = async (resolvedConfig: FieldConfig | null) => {
    const dimensions = deriveScopeDimensions(resolvedConfig);
    const res = await persistScopeDimensions(dimensions);
    if (res.plane === 'ok') {
      setScopeMirrorRetry(null);
      return;
    }
    const description =
      res.message ?? t('Scope-dimensie bijwerken mislukt', 'Updating the scope dimension failed');
    if (res.plane === 'mirror') {
      // SAM authoritative, Flask mirror stale → arm the resync button and warn (not a hard error).
      setScopeMirrorRetry({ dimensions, message: description });
      toast({
        title: t('Scope-spiegel niet bijgewerkt', 'Scope mirror not updated'),
        description,
        status: 'warning',
        duration: 9000,
        isClosable: true,
      });
    } else {
      // SAM write itself failed → nothing to resync; surface a hard error.
      setScopeMirrorRetry(null);
      toast({
        title: t('Scope niet bijgewerkt', 'Scope not updated'),
        description,
        status: 'error',
        duration: 9000,
        isClosable: true,
      });
    }
  };

  /**
   * RESYNC path (spec 03b BU-6, task 6.2, Req 4.4): re-drive JUST the Flask `members.scope_dimensions`
   * mirror from the already-authoritative SAM `config#scope` set after a transient mirror failure.
   * Re-uses the EXACT dimension set the failed save derived (stashed in `scopeMirrorRetry`) so the
   * resync cannot drift from the SAM truth it is reconciling to. On success it clears the armed
   * state; on repeated failure it re-arms so the admin can try again.
   */
  const resyncScopeMirror = async () => {
    if (!scopeMirrorRetry) return;
    setResyncing(true);
    try {
      const res = await persistScopeDimensions(scopeMirrorRetry.dimensions);
      if (res.plane === 'ok') {
        setScopeMirrorRetry(null);
        toast({
          title: t('Scope-spiegel bijgewerkt', 'Scope mirror resynced'),
          status: 'success',
          duration: 3000,
        });
      } else {
        const description =
          res.message ??
          t('Scope-spiegel opnieuw bijwerken mislukt', 'Resyncing the scope mirror failed');
        setScopeMirrorRetry({ dimensions: scopeMirrorRetry.dimensions, message: description });
        toast({
          title: t('Scope-spiegel niet bijgewerkt', 'Scope mirror not updated'),
          description,
          status: 'warning',
          duration: 9000,
          isClosable: true,
        });
      }
    } finally {
      setResyncing(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Phase 5 (spec 03): write by IDENTITY, not the whole object. Derive the Change-Op list from
      // the loaded baseline → the edited working overlay (set_field / set_group / set_field_application
      // / reset_field / delete_field / delete_group), keyed by the BARE field/group key; the SERVER
      // owns storage placement, so the client never sends a whole catalog or a `{group}.{key}` key
      // (steering 39). This replaces the retired whole-overlay `saveMembersParameter('field_overlay')`.
      const baselineOverlay = JSON.parse(baseline) as MembersConfigValue;

      // AXIS-vs-VALUE gate (spec 03b BU-6, task 6.2, Req 4.3/4.6). Classify the scope-relevant edit
      // BEFORE anything is persisted. A SCOPE-AXIS change — the set of fields with `scope.enabled`
      // changes (a different field becomes the scope axis, a combination changes, or scope is turned
      // off) — is a STRUCTURAL access-model change: refuse the WHOLE save ATOMICALLY so no
      // `scope.enabled` change lands on config#fields and the two planes never diverge on an
      // incoherent mixed write. The admin is told to create a project with their System Administrator
      // (Req 4.6); a pure VALUE add/remove falls through and auto-applies on both planes (Req 4.5).
      const scopeChange = classifyScopeChange(baselineOverlay, overlay);
      if (scopeChange === 'axis') {
        toast({
          title: t('Structurele scope-wijziging', 'Structural scope change'),
          description: t(
            'Een scope-as wijzigen is een structurele wijziging van het toegangsmodel. Maak hiervoor een project aan met uw Systeembeheerder.',
            'Changing a scope axis is a structural change to the access model. Create a project with your System Administrator to make this change.',
          ),
          status: 'warning',
          duration: 12000,
          isClosable: true,
        });
        return; // atomic refusal — nothing persisted on either plane
      }

      const ops = deriveFieldConfigChangeOps(baselineOverlay, overlay);
      const res = await saveFieldConfigChangeOps(ops);
      if (res.success) {
        // config#fields is authoritative and now saved. Reload the RESOLVED config so the derived
        // scope dimensions (below) read the authored option VALUES exactly as the module resolves
        // them — not the pre-save working buffer.
        const reloaded = await load();
        // Scope derive-on-save (spec 03b BU-6, Req 4.1/4.2/4.5). ONLY a VALUE change reaches here
        // (the axis gate above already refused an AXIS change). The field editor is the SINGLE
        // scope-authoring surface: derive the `config#scope` dimension set from each scope-axis
        // field's own options and persist it. The FRONTEND is the only cross-plane coordinator
        // (steering 35/39 — no runtime SAM↔Flask call): SAM `PUT /members/config/scope`
        // (authoritative) FIRST, THEN the Flask `members.scope_dimensions` mirror. A scope write
        // failure is surfaced (and, for a mirror-only failure, arms the resync button) but does NOT
        // undo the authoritative config#fields save that already landed. A `'none'` change skips the
        // scope sync entirely (no scope field was touched).
        if (scopeChange === 'value') {
          await syncScopeDimensions(reloaded);
        }
        toast({ title: t('Opgeslagen', 'Saved'), status: 'success', duration: 3000 });
      } else if (res.conflict) {
        // A version-conditional write lost the race (another admin edited the row): prompt a reload
        // rather than a silent failure, then reload to pick up the latest state.
        toast({
          title: t('Opnieuw laden vereist', 'Reload required'),
          description: t(
            'De configuratie is door iemand anders gewijzigd. De laatste versie wordt opnieuw geladen.',
            'The configuration was changed by someone else. Reloading the latest version.',
          ),
          status: 'warning',
          duration: 9000,
          isClosable: true,
        });
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

      {/* Scope-mirror RESYNC affordance (spec 03b BU-6, task 6.2, Req 4.4). Shown ONLY when the
          authoritative SAM `config#scope` write succeeded but the Flask mirror failed — the two
          planes are momentarily diverged. The admin re-drives JUST the mirror from SAM truth with
          one click (no full re-save), closing the divergence a transient failure opened. */}
      {scopeMirrorRetry && (
        <Box
          borderWidth="1px"
          borderColor="yellow.600"
          bg="yellow.900"
          borderRadius="md"
          mt={2}
          p={3}
          data-testid="members-scope-resync"
        >
          <HStack justify="space-between" align="start">
            <VStack align="start" spacing={0}>
              <Text fontSize="sm" color="yellow.200" fontWeight="semibold">
                {t('Scope-spiegel niet gesynchroniseerd', 'Scope mirror out of sync')}
              </Text>
              <Text fontSize="xs" color="yellow.300" data-testid="members-scope-resync-message">
                {t(
                  'De scope-definitie (SAM) is opgeslagen, maar de spiegel voor toegangsvalidatie kon niet worden bijgewerkt. Synchroniseer opnieuw.',
                  'The scope definition (SAM) was saved, but the access-validation mirror could not be updated. Resync to reconcile.',
                )}
              </Text>
            </VStack>
            <Button
              size="sm"
              colorScheme="yellow"
              onClick={resyncScopeMirror}
              isLoading={resyncing}
              loadingText={t('Synchroniseren…', 'Resyncing…')}
              data-testid="members-scope-resync-btn"
            >
              {t('Opnieuw synchroniseren', 'Resync')}
            </Button>
          </HStack>
        </Box>
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
                functionalGroups={fieldConfig?.functional_groups ?? []}
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
