/**
 * Field modal — every editable field option as an attribute (Members config drill-down — Phase 3,
 * task 4.6; R2.1/R2.2/R3.2/R3.3/R4.3/R4.6).
 *
 * The leaf of the group → field → attribute drill-down: opened by a row-click on the fields table
 * (edit mode) or its add action (create mode). It exposes ALL editable field options AS ATTRIBUTES
 * on the one field:
 *   - identity: name/`key` (locked in edit mode), `type`, bilingual `label`, `order`;
 *   - flags: `required`, `visible`, `read_only` (calculated/derived);
 *   - enum `choices` (reusing `EnumOptionsEditor`, the shared rich-option editor) — the ONE
 *     vocabulary (single-vocabulary rule, R3.2);
 *   - the **scope-binding** attribute (remediation task 3.3, R3.1–R3.3): `scope = { enabled,
 *     required_for }` declaring the field is a scope axis. The scope section is JUST an `enabled`
 *     toggle + a `required_for` roles control — it does NOT carry its own value list: the scope
 *     VALUES ARE the field's enum values (the `choices` editor above is the single vocabulary).
 *     This REPLACES the retired standalone scope_dimensions editor (R2.2) and the former separate
 *     comma-separated "scope values" input (which duplicated the enum vocabulary — removed R3.2);
 *
 * NOT authored here: the catalog `alias` attribute (`attribute_catalog.py`) is a Phase-1
 * DECLARED-ONLY stub with no runtime consumer in the SAM resolver/repository/handler; wiring it is
 * a separate deliberate change, not a Phase-3 deliverable, so the modal does not expose it. (It is
 * also NOT the deleted analytics field role.) The former "analytics role" input (an earlier task
 * 4.6 mistake that revived the removed role concept) has been removed.
 *
 * CONTROLLED + save-free: every change is applied to the working `field_overlay` through the pure
 * `overlayModel` (`createField` for new tenant fields / `upsertField` for the origin-aware edit) and
 * bubbled up via `onChange`; the editor (task 4.8)
 * commits the one object once (Property 8). The provenance-driven DESTRUCTIVE actions (delete /
 * reset / hide) and MOVE-TO-GROUP are layered on by task 4.7 (passed in via props); this task owns
 * the attribute-authoring surface + the create/edit save. Follows the Chakra `Modal` pattern.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Divider,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Switch,
  Text,
  VStack,
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { EnumOptionConfig, FieldConfig, FieldConfigField } from '../../../types/members';
import {
  createField,
  findField,
  upsertField,
  type FieldOrigin,
  type OverlayField,
} from './overlayModel';
import { EnumOptionsEditor } from './EnumOptionsEditor';

export type FieldModalMode = 'create' | 'edit';

/** The field `type` options the modal offers (mirrors the field_def `type` enum). */
const FIELD_TYPES = ['string', 'number', 'boolean', 'date', 'enum', 'reference'] as const;

export interface MembersFieldModalProps {
  isOpen: boolean;
  onClose: () => void;
  mode: FieldModalMode;
  /** The field key being edited (edit mode); ignored in create mode. */
  fieldKey?: string;
  /** The group the field belongs to / is created in. */
  groupKey: string;
  /** The working field_overlay the modal reads from and writes back to. */
  overlay: MembersConfigValue | undefined;
  /**
   * The RESOLVED `FieldConfig` (`GET /members/field-config`). In EDIT mode the modal SEEDS its
   * initial values from the resolved field (R2.1–R2.3): `type` from the resolved `field.type`
   * (NO silent `string` default), the enum vocabulary from the served `options` (rich or bare —
   * NOT the overlay's `choices`), and the bilingual label from the resolved `label{}`. Absent /
   * null (fetch failure, older module build) → the modal falls back to the working overlay field,
   * so authoring never blocks (R1.4). Ignored in create mode.
   */
  fieldConfig?: FieldConfig | null;
  /** Apply a mutated overlay (the modal never saves — the editor commits once). */
  onChange: (next: MembersConfigValue) => void;
  /** Known role names for the enum-option role gate (reuses the editor's roles help). */
  availableRoles?: string[];
  lang: 'nl' | 'en';
  /**
   * Optional pointer for a `reference`-type field (R3.1): invoked when the admin clicks the
   * "manage values" link to reach the membership-type catalog manager. The catalog manager is a
   * SIBLING sub-tab in the TenantAdmin Members area, not a routable URL, so switching to it is the
   * parent's concern — passing this lets a parent wire the tab-switch. Left optional/unwired is
   * fine: the reference note still renders the instructional pointer (naming the
   * "Lidmaatschapstypes" tab), so the field editor is never a dead end even without a handler.
   */
  /**
   * Optional provenance-driven action slot (task 4.7). When provided, rendered in the modal footer
   * (left side) — e.g. delete / reset / hide + move-to-group. Kept as a slot so task 4.6 owns only
   * the attribute surface and 4.7 supplies the gated actions.
   */
  actionsSlot?: React.ReactNode;
}

/** The editable form shape (strings for inputs; parsed on save). */
interface FieldForm {
  key: string;
  type: string;
  label_en: string;
  label_nl: string;
  order: string;
  required: boolean;
  visible: boolean;
  read_only: boolean;
  choices: MembersConfigValue; // rich enum options (the SINGLE scope vocabulary), via EnumOptionsEditor
  scopeEnabled: boolean;
  scopeRequiredFor: string[]; // roles the scope axis is required for (NO separate values list, R3.2)
}

const EMPTY_FORM: FieldForm = {
  key: '',
  type: 'string',
  label_en: '',
  label_nl: '',
  order: '',
  required: false,
  visible: true,
  read_only: false,
  choices: [],
  scopeEnabled: false,
  scopeRequiredFor: [],
};

function strArray(v: MembersConfigValue | undefined): string[] {
  return Array.isArray(v) ? (v as unknown[]).map((x) => String(x)) : [];
}

/**
 * Normalise the RESOLVED field's served enum vocabulary (`options`) into the rich-choices shape the
 * `EnumOptionsEditor` consumes (R2.1). The server serves enum values ALWAYS under `options` — a
 * rich `{ value, label{nl,en}, roles? }` list OR a bare `string[]` — and NEVER a standalone
 * `choices` key (verified server-truth pass). A bare string is upgraded to a rich option whose
 * labels mirror the value; a rich option is carried verbatim (empty `roles` dropped). An absent /
 * non-array `options` yields an empty list.
 */
function optionsToChoices(
  options: Array<string | EnumOptionConfig> | null | undefined,
): MembersConfigValue {
  if (!Array.isArray(options)) return [];
  return options.map((opt) => {
    if (typeof opt === 'string') {
      return { value: opt, label: { nl: opt, en: opt } };
    }
    const value = typeof opt.value === 'string' ? opt.value : String(opt.value ?? '');
    const label = {
      nl: opt.label?.nl ?? value,
      en: opt.label?.en ?? value,
    };
    const roles = Array.isArray(opt.roles) ? opt.roles.filter(Boolean) : [];
    // Carry the 03b retire/grandfather flag + rank so the inline editor shows the retired state
    // and the save round-trips it (absent `allowed` === offered; only `false` is carried).
    const allowed = (opt as { allowed?: boolean }).allowed;
    const order = (opt as { order?: number }).order;
    return {
      value,
      label,
      ...(roles.length ? { roles } : {}),
      ...(allowed === false ? { allowed: false } : {}),
      ...(typeof order === 'number' ? { order } : {}),
    };
  }) as unknown as MembersConfigValue;
}

/**
 * Seed the editable form from the RESOLVED field descriptor (R2.1–R2.3; Property P1 — the modal's
 * initial values come from the resolved `FieldConfig`). The resolved field is the display source
 * (`GET /members/field-config` serves the full fixed ⊕ overlay ⊕ calculated set with the correct
 * `type`, enum `options`, and `label{}`):
 *
 *  - `type` is seeded from the resolved `field.type` with NO silent `string` default (R2.2): if the
 *    resolved type is missing it is left EMPTY, surfacing the defect rather than papering over it
 *    with `'string'`;
 *  - the enum vocabulary is seeded from the served `options` (rich or bare — NOT `choices`, R2.1),
 *    normalised to the editor's rich shape;
 *  - the bilingual label is seeded from the resolved `label{}` dict.
 *
 * Scope seeding (remediation task 3.3, R3.5/R3.6): read the RESOLVED field's served `scope`
 * (`{ enabled, required_for }` — no `values`, single-vocabulary) when present; fall back to the
 * overlay field's `scope` only when the resolved config does not serve one (older module build /
 * fetch gap). The scope VALUES are NOT seeded here — they ARE the enum vocabulary (`choices`),
 * seeded above (R3.2): the ONE editor.
 */
function formFromResolvedField(
  key: string,
  resolved: FieldConfigField | undefined,
  overlayField: OverlayField | undefined,
): FieldForm {
  // No resolved descriptor (fetch failure / older module build) → degrade to the overlay field.
  if (!resolved) return formFromOverlayField(key, overlayField);

  const label =
    resolved.label && typeof resolved.label === 'object' && !Array.isArray(resolved.label)
      ? (resolved.label as Record<string, string | undefined>)
      : {};

  // Prefer the SERVED scope (`{ enabled, required_for }`); fall back to the overlay scope object
  // when the resolved config carries none (so authoring never regresses on an older read path).
  const servedScope =
    resolved.scope && typeof resolved.scope === 'object' && !Array.isArray(resolved.scope)
      ? (resolved.scope as { enabled?: boolean; required_for?: string[] })
      : null;
  const overlayScope =
    overlayField?.scope && typeof overlayField.scope === 'object' && !Array.isArray(overlayField.scope)
      ? (overlayField.scope as Record<string, MembersConfigValue>)
      : null;
  const scopeEnabled = servedScope ? servedScope.enabled === true : overlayScope?.enabled === true;
  const scopeRequiredFor = servedScope
    ? strArray(servedScope.required_for as MembersConfigValue)
    : strArray(overlayScope?.required_for);

  return {
    key,
    // NO silent `string` default — use the resolved type as-is (missing → empty, a surfaced defect).
    type: typeof resolved.type === 'string' ? resolved.type : '',
    label_en: typeof label.en === 'string' ? label.en : '',
    label_nl: typeof label.nl === 'string' ? label.nl : '',
    order: typeof resolved.order === 'number' ? String(resolved.order) : '',
    required: resolved.required === true,
    visible: resolved.visible !== false,
    read_only: resolved.read_only === true,
    // Enum vocabulary from the served `options` (rich or bare — NOT the overlay's `choices`, R2.1).
    // This is also the SINGLE scope vocabulary (R3.2) — the scope section carries no value list.
    choices: optionsToChoices(resolved.options),
    scopeEnabled,
    scopeRequiredFor,
  };
}

/**
 * Fallback seed from the raw OVERLAY field — used only when the resolved descriptor is unavailable
 * (R1.4 degrade-never-block). Reads the overlay's ONE canonical `options` vocabulary (spec 03a /
 * C1 — never a `choices` key) and the flat `label_*`, with an absent `type` left EMPTY rather than
 * silently defaulted to `'string'` (R2.2).
 */
function formFromOverlayField(key: string, field: OverlayField | undefined): FieldForm {
  if (!field) return { ...EMPTY_FORM, key, type: '' };
  const scope =
    field.scope && typeof field.scope === 'object' && !Array.isArray(field.scope)
      ? (field.scope as Record<string, MembersConfigValue>)
      : {};
  return {
    key,
    type: typeof field.type === 'string' ? field.type : '',
    label_en: typeof field.label_en === 'string' ? field.label_en : '',
    label_nl: typeof field.label_nl === 'string' ? field.label_nl : '',
    order: typeof field.order === 'number' ? String(field.order) : '',
    required: field.required === true,
    visible: field.visible !== false,
    read_only: field.read_only === true,
    // Seed the editor's `choices` form state from the overlay's ONE canonical `options` (never a
    // legacy `choices` key) — the single vocabulary (spec 03a / C1, F6).
    choices: (field.options as MembersConfigValue) ?? [],
    scopeEnabled: scope.enabled === true,
    // Single-vocabulary (R3.2): no scope values here — only `required_for`. A legacy stored
    // `scope.values` is honoured server-side as a migration fallback; the modal never edits it.
    scopeRequiredFor: strArray(scope.required_for),
  };
}

/**
 * The ORIGIN-AWARE write-back routing for an EDITED field (remediation task 2.2, R1). The WRITE
 * target per field is provenance/origin-dependent — the display model (resolved `FieldConfig`) and
 * the write model (raw `field_overlay`) are distinct, so a modal edit maps to the right overlay
 * slice by the resolved field's `origin`/`provenance`:
 *
 *  - a tenant-ADDED field (`origin: 'variable'` / `provenance: 'tenant_added'`) → `fields[key]`;
 *  - a base / base_overridden field (`origin: 'fixed'` / `provenance: 'base' | 'base_overridden'`)
 *    — a presentation override (relabel / reorder / hide / enum options / scope / move group) →
 *    `fixed_overrides[dottedKey]`, keyed `{group}.{key}` by the resolved storage group;
 *  - a CALCULATED field (`origin: 'calculated'`) is READ-ONLY → `writable: false` (no write).
 *
 * Absent resolved descriptor (fetch failure / older module build) → fall back to a tenant-added
 * write under `fields` so authoring never blocks (R1.4); the field already living in `fields`
 * keeps being edited there (the overlayModel upsert never moves a field across maps).
 */
function resolveWriteTarget(
  key: string,
  resolved: FieldConfigField | undefined,
): { writable: boolean; origin: FieldOrigin; overlayKey: string } {
  // Calculated fields are derived + read-only — never authored by the tenant (R1.5).
  if (resolved?.origin === 'calculated') {
    return { writable: false, origin: 'fields', overlayKey: key };
  }
  const isBase =
    resolved?.origin === 'fixed' ||
    resolved?.provenance === 'base' ||
    resolved?.provenance === 'base_overridden';
  if (isBase) {
    // A base-field presentation override lives under `fixed_overrides`, keyed `{group}.{key}` by
    // the resolved storage bucket. When the storage group is absent fall back to the bare key.
    const group = typeof resolved?.group === 'string' && resolved.group ? resolved.group : '';
    const overlayKey = group ? `${group}.${key}` : key;
    return { writable: true, origin: 'fixed_overrides', overlayKey };
  }
  // Tenant-added (or unknown provenance) → the tenant `fields` slice.
  return { writable: true, origin: 'fields', overlayKey: key };
}

export const MembersFieldModal: React.FC<MembersFieldModalProps> = ({
  isOpen,
  onClose,
  mode,
  fieldKey,
  groupKey,
  overlay,
  fieldConfig,
  onChange,
  availableRoles = [],
  lang,
  actionsSlot,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  const existing = useMemo(
    () => (mode === 'edit' && fieldKey ? findField(overlay, fieldKey) : null),
    [mode, fieldKey, overlay],
  );

  // The RESOLVED descriptor for the edited field — the SEED source for type / enum options / label
  // (R2.1–R2.3, Property P1). Absent → the seed degrades to the overlay field (R1.4).
  const resolvedField = useMemo(
    () =>
      mode === 'edit' && fieldKey
        ? (fieldConfig?.fields ?? []).find((f) => f.key === fieldKey)
        : undefined,
    [mode, fieldKey, fieldConfig],
  );

  const [form, setForm] = useState<FieldForm>(() =>
    mode === 'edit' && fieldKey
      ? formFromResolvedField(fieldKey, resolvedField, existing?.field)
      : { ...EMPTY_FORM },
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (isOpen) {
      setForm(
        mode === 'edit' && fieldKey
          ? formFromResolvedField(fieldKey, resolvedField, existing?.field)
          : { ...EMPTY_FORM },
      );
      setErrors({});
    }
  }, [isOpen, mode, fieldKey, existing, resolvedField]);

  const set = <K extends keyof FieldForm>(k: K, v: FieldForm[K]) => {
    setForm((prev) => ({ ...prev, [k]: v }));
    if (errors[k as string]) setErrors((prev) => ({ ...prev, [k as string]: '' }));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    const key = form.key.trim();
    if (!key) {
      next.key = t('Veldsleutel is verplicht', 'Field key is required');
    } else if (mode === 'create' && findField(overlay, key)) {
      next.key = t('Deze veldsleutel bestaat al', 'This field key already exists');
    }
    if (form.order.trim() && Number.isNaN(Number(form.order))) {
      next.order = t('Volgorde moet een getal zijn', 'Order must be a number');
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  /**
   * Assemble the field attributes from the form (omitting empty/default-valued attributes).
   *
   * `functional_group` single source of truth (remediation task 5.1, R6.1–R6.3): the field's group
   * is OWNED by the field's stored value (edited by the move action), NOT re-authored to the
   * opened-group prop on every save. So `buildField` emits `functional_group: groupKey` ONLY in
   * CREATE mode (a brand-new tenant field lands in the group it was added from, scope boundary of
   * 5.1). On EDIT it leaves `functional_group` UNSET — the origin-aware `upsertField` merge then
   * preserves whatever the working overlay currently holds (incl. a prior move-to-group), so a
   * moved field is no longer reverted to the stale group the modal was opened under (I-8).
   */
  function buildField(): OverlayField {
    const field: OverlayField = {
      type: form.type || undefined,
      label_en: form.label_en.trim() || undefined,
      label_nl: form.label_nl.trim() || undefined,
      // CREATE only — on edit the stored `functional_group` is the single source of truth (R6.1).
      functional_group: mode === 'create' ? groupKey : undefined,
      order: form.order.trim() ? Number(form.order) : undefined,
    };
    // CREATE authors a brand-new tenant VARIABLE field under `fields`, diffed against an EMPTY
    // baseline — there is no prior stored `required: true` to overwrite, so `required` OFF ≡ absent
    // (the diff emits nothing either way and the resolved field is not-required). Hence create does
    // NOT need the explicit-`false` the edit path needs; authoring `required: false` here would only
    // add a redundant op. Left as-is deliberately (the absent==false equivalence holds only on create
    // against an empty baseline — on EDIT a stored `true` must be explicitly cleared, see handleSave).
    if (form.required) field.required = true;
    if (!form.visible) field.visible = false;
    if (form.read_only) field.read_only = true;
    if (
      (form.type === 'enum' || form.type === 'reference') &&
      Array.isArray(form.choices) &&
      form.choices.length > 0
    ) {
      // Single-vocabulary (spec 03a / C1): the enum vocabulary is authored under the ONE canonical
      // `options` key on the working overlay — NEVER `choices` — so the Change-Op write emits only
      // `options` (the `choices` key was dropped from DEFINITION_ATTRS). The in-memory form field is
      // still called `choices` (it drives the shared EnumOptionsEditor), but it is stored as `options`.
      field.options = form.choices;
    }
    // Scope-binding attribute (remediation task 3.3, R3.2/R3.3) — only when enabled. SINGLE
    // vocabulary: the stored `scope` is `{ enabled, required_for? }` ONLY; it carries NO `values`
    // list — the scope VALUES ARE the field's enum values (`choices` above). The Flask builder
    // derives the `config#scope` dimension values from those enum values on save (R3.4).
    if (form.scopeEnabled) {
      const requiredFor = form.scopeRequiredFor.map((r) => r.trim()).filter(Boolean);
      field.scope = { enabled: true, ...(requiredFor.length ? { required_for: requiredFor } : {}) };
    }
    // NOTE: the catalog `alias` attribute is a Phase-1 DECLARED-ONLY stub with no runtime consumer
    // (nothing in the SAM resolver/repository/handler reads it); wiring it is a separate, deliberate
    // change, not a Phase-3 deliverable. So the field modal does NOT author it — authoring an
    // unwired attribute would mislead the tenant admin. (It is NOT the deleted analytics role.)
    return field;
  }

  const handleSave = () => {
    if (!validate()) return;
    const key = form.key.trim();
    const field = buildField();
    if (mode === 'create') {
      // "Add field" always creates a tenant VARIABLE field under `fields` (R1.5) — a tenant cannot
      // add a predefined (fixed/calculated) field, so create is never routed to `fixed_overrides`.
      onChange(createField(overlay, key, field, 'fields' as FieldOrigin));
    } else {
      // ORIGIN-AWARE write-back (task 2.2, R1): route the edit to the right overlay slice by the
      // resolved field's origin/provenance. A CALCULATED field is read-only — no write at all.
      const target = resolveWriteTarget(key, resolvedField);
      if (!target.writable) {
        // Calculated / derived field — value/type/inputs are platform-owned, never authored here.
        onClose();
        return;
      }
      // Replace the field's authored attributes with the form's (edit is a full re-author of the
      // modal-managed attributes; keys the modal does not manage are preserved by the upsert merge).
      // Explicitly clear attributes that were turned off so they do not linger.
      const patch: Partial<OverlayField> = {
        ...field,
        // Send the EXPLICIT boolean for BOTH `required` and `visible` so a toggle flipped either
        // way reaches the server as a deliberate `true`/`false`, never a dropped `undefined`. The
        // Change-Op diff (`fieldConfigChangeOps`) treats both as DEFINITION_BOOLEAN_ATTRS and only
        // emits an attr when it is `!== undefined`; a `? undefined : false` pattern can set a
        // stored override to `false` but can NEVER clear it back to `true` (the attr is dropped on
        // the ON path), so re-enabling a previously-hidden/required field silently no-ops. Sending
        // the raw boolean makes both transitions symmetric — the exact fix the `required` toggle
        // already uses, now applied to `visible` too (the reported visible-stuck-off bug).
        required: form.required,
        visible: form.visible,
        // `read_only` is PLATFORM-OWNED, not a clearable tenant override: the resolver pins it `true`
        // ONLY for CALCULATED fields (which are not writable here — the modal returns early for them)
        // and `false` for every fixed/variable field. It is NOT in the backend `FIELD_DEFINITION_ATTRS`
        // write surface nor in the client `DEFINITION_ATTRS` diff list, so it never crosses the wire
        // via a Change-Op regardless of what we put here. There is therefore no stored `read_only: true`
        // override a user needs to clear, so absence==false is correct and the `required` bug does NOT
        // apply — kept as-is deliberately.
        read_only: form.read_only ? true : undefined,
        // Single-vocabulary (spec 03a / C1): clear/author the enum vocabulary under the ONE
        // canonical `options` key — never `choices`.
        options: field.options ?? undefined,
        scope: field.scope ?? undefined,
      };
      // `functional_group` single source of truth (task 5.1, R6.1/R6.2): the modal does NOT
      // re-author the group on edit — the stored value (edited by the move action) is authoritative.
      // DELETE the key from the patch entirely so the merge PRESERVES the stored group (a bare
      // `functional_group: undefined` would instead be read by `editField` as "delete the
      // attribute", silently orphaning a moved field — the very revert we are fixing, I-8).
      delete patch.functional_group;
      // A tenant-added edit targets `fields[key]`; a base/base_overridden edit targets
      // `fixed_overrides[{group}.{key}]`. The single-save contract is unchanged — one `onChange`.
      onChange(upsertField(overlay, target.overlayKey, patch, target.origin));
    }
    onClose();
  };

  const inputProps = {
    bg: 'gray.700',
    color: 'white',
    borderColor: 'gray.600',
  } as const;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" data-testid="members-field-modal">
        <ModalHeader color="orange.400">
          {mode === 'create' ? t('Veld toevoegen', 'Add field') : t('Veld bewerken', 'Edit field')}
        </ModalHeader>
        <ModalCloseButton color="white" />

        <ModalBody>
          <VStack spacing={4} align="stretch" pb={2}>
            {/* Identity */}
            <FormControl isInvalid={!!errors.key} isRequired>
              <FormLabel color="gray.300">{t('Veldsleutel', 'Field key')}</FormLabel>
              <Input
                {...inputProps}
                value={form.key}
                onChange={(e) => set('key', e.target.value)}
                isDisabled={mode === 'edit'}
                aria-label={t('Veldsleutel', 'Field key')}
              />
              {errors.key && <FormErrorMessage>{errors.key}</FormErrorMessage>}
              {mode === 'edit' && (
                <Text fontSize="xs" color="gray.500" mt={1}>
                  {t('De sleutel kan niet worden gewijzigd', 'The key cannot be changed')}
                </Text>
              )}
            </FormControl>

            <FormControl>
              <FormLabel color="gray.300">{t('Type', 'Type')}</FormLabel>
              <Select
                {...inputProps}
                value={form.type}
                onChange={(e) => set('type', e.target.value)}
                aria-label={t('Type', 'Type')}
              >
                {/* A resolved field with NO type seeds an EMPTY type (R2.2 — no silent `string`
                    default). Surface that as a selectable placeholder rather than papering over it,
                    so the defect is visible to the admin instead of masquerading as `string`. */}
                {!FIELD_TYPES.includes(form.type as (typeof FIELD_TYPES)[number]) && (
                  <option value="">{t('— geen type —', '— no type —')}</option>
                )}
                {FIELD_TYPES.map((ty) => (
                  <option key={ty} value={ty}>
                    {ty}
                  </option>
                ))}
              </Select>
            </FormControl>

            <HStack align="start" spacing={3}>
              <FormControl>
                <FormLabel color="gray.300">{t('Label (Engels)', 'Label (English)')}</FormLabel>
                <Input
                  {...inputProps}
                  value={form.label_en}
                  onChange={(e) => set('label_en', e.target.value)}
                  aria-label={t('Label (Engels)', 'Label (English)')}
                />
              </FormControl>
              <FormControl>
                <FormLabel color="gray.300">{t('Label (Nederlands)', 'Label (Dutch)')}</FormLabel>
                <Input
                  {...inputProps}
                  value={form.label_nl}
                  onChange={(e) => set('label_nl', e.target.value)}
                  aria-label={t('Label (Nederlands)', 'Label (Dutch)')}
                />
              </FormControl>
              <FormControl isInvalid={!!errors.order} maxW="24">
                <FormLabel color="gray.300">{t('Volgorde', 'Order')}</FormLabel>
                <Input
                  {...inputProps}
                  type="number"
                  value={form.order}
                  onChange={(e) => set('order', e.target.value)}
                  aria-label={t('Volgorde', 'Order')}
                />
                {errors.order && <FormErrorMessage>{errors.order}</FormErrorMessage>}
              </FormControl>
            </HStack>

            {/* Flags */}
            <HStack spacing={6}>
              <FormControl display="flex" alignItems="center" w="auto">
                <FormLabel color="gray.300" mb={0} mr={2}>
                  {t('Verplicht', 'Required')}
                </FormLabel>
                <Switch
                  isChecked={form.required}
                  onChange={(e) => set('required', e.target.checked)}
                  colorScheme="orange"
                  aria-label={t('Verplicht', 'Required')}
                />
              </FormControl>
              <FormControl display="flex" alignItems="center" w="auto">
                <FormLabel color="gray.300" mb={0} mr={2}>
                  {t('Zichtbaar', 'Visible')}
                </FormLabel>
                <Switch
                  isChecked={form.visible}
                  onChange={(e) => set('visible', e.target.checked)}
                  colorScheme="orange"
                  aria-label={t('Zichtbaar', 'Visible')}
                />
              </FormControl>
              <FormControl display="flex" alignItems="center" w="auto">
                <FormLabel color="gray.300" mb={0} mr={2}>
                  {t('Alleen-lezen', 'Read-only')}
                </FormLabel>
                <Switch
                  isChecked={form.read_only}
                  onChange={(e) => set('read_only', e.target.checked)}
                  colorScheme="orange"
                  aria-label={t('Alleen-lezen', 'Read-only')}
                />
              </FormControl>
            </HStack>

            {/* Enum choices (only for enum type) */}
            {(form.type === 'enum' || form.type === 'reference') && (
              <FormControl>
                <FormLabel color="gray.300">{t('Keuzes', 'Choices')}</FormLabel>
                {/* Spec 03b unified enum model: membership_type (a `reference` field) is a NORMAL
                    enum that owns its own `options` — edited inline here exactly like any enum, with
                    the per-option retire/grandfather (`allowed`) toggle serving as the reference
                    status. The retired `membershiptype#` catalog + its "managed elsewhere" pointer
                    are gone; the field IS the single vocabulary (stored under `options`, never the
                    retired `choices` key — the form field name is historical). */}
                <EnumOptionsEditor
                  value={form.choices}
                  onChange={(next) => set('choices', next)}
                  availableRoles={availableRoles}
                  lang={lang}
                />
              </FormControl>
            )}

            <Divider borderColor="gray.600" />

            {/* Scope-binding attribute (remediation task 3.3, R3.1–R3.3) — single-vocabulary.
                The scope section is JUST an `enabled` toggle + a `required_for` roles control; it
                has NO separate values list — the scope VALUES ARE the field's enum values, edited
                in the ONE enum `Choices` editor above (R3.2). */}
            <Box data-testid="members-field-modal-scope">
              <FormControl display="flex" alignItems="center" w="auto" mb={2}>
                <FormLabel color="gray.300" mb={0} mr={2}>
                  {t('Scope-as', 'Scope axis')}
                </FormLabel>
                <Switch
                  isChecked={form.scopeEnabled}
                  onChange={(e) => set('scopeEnabled', e.target.checked)}
                  colorScheme="teal"
                  aria-label={t('Scope-as', 'Scope axis')}
                />
              </FormControl>
              {form.scopeEnabled && (
                <>
                  <Text fontSize="xs" color="gray.500" mb={2}>
                    {t(
                      'Scope-waarden zijn de enum-waarden van dit veld (één woordenlijst).',
                      'Scope values are this field\u2019s enum values (one vocabulary).',
                    )}
                  </Text>
                  <FormControl>
                    <FormLabel color="gray.300" fontSize="sm">
                      {t('Verplicht voor rollen', 'Required for roles')}
                    </FormLabel>
                    {availableRoles.length === 0 ? (
                      <Input
                        {...inputProps}
                        value={form.scopeRequiredFor.join(', ')}
                        onChange={(e) =>
                          set(
                            'scopeRequiredFor',
                            e.target.value
                              .split(',')
                              .map((r) => r.trim())
                              .filter(Boolean),
                          )
                        }
                        placeholder="Members_CRUD"
                        aria-label={t('Verplicht voor rollen', 'Required for roles')}
                      />
                    ) : (
                      <HStack spacing={3} wrap="wrap">
                        {availableRoles.map((role) => (
                          <HStack key={role} spacing={1}>
                            <Switch
                              size="sm"
                              colorScheme="teal"
                              isChecked={form.scopeRequiredFor.includes(role)}
                              onChange={(e) =>
                                set(
                                  'scopeRequiredFor',
                                  e.target.checked
                                    ? [...form.scopeRequiredFor, role]
                                    : form.scopeRequiredFor.filter((r) => r !== role),
                                )
                              }
                              aria-label={t(`Scope verplicht voor ${role}`, `Scope required for ${role}`)}
                            />
                            <Text fontSize="xs" color="gray.400">
                              {role}
                            </Text>
                          </HStack>
                        ))}
                      </HStack>
                    )}
                  </FormControl>
                </>
              )}
            </Box>


          </VStack>
        </ModalBody>

        <ModalFooter>
          <HStack justify="space-between" width="100%">
            {/* Provenance-driven actions + move-to-group (task 4.7) slot in on the left. */}
            <Box>{actionsSlot}</Box>
            <Box flex={1} />
            <HStack spacing={3}>
              <Button variant="ghost" onClick={onClose} color="white">
                {t('Annuleren', 'Cancel')}
              </Button>
              <Button colorScheme="orange" onClick={handleSave} data-testid="members-field-modal-save-btn">
                {mode === 'create' ? t('Aanmaken', 'Create') : t('Opslaan', 'Save')}
              </Button>
            </HStack>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MembersFieldModal;
