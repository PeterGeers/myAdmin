/**
 * Per-field application attributes — the R3/R4 panel of the Application Form Builder (spec 11,
 * R3.1–R3.5 / R4.1, design §3 table / §3.1 / §4 / §10).
 *
 * For the ONE field currently SELECTED in the field list (task 2.3) AND on the form
 * (`application_visible`), this surface authors the three remaining per-field application
 * attributes directly onto that field's entry in the ONE working `field_overlay` object:
 *
 *  - **application-required** toggle → `application_required` (R3.1). The admin freely sets
 *    requiredness on the form for ANY field; the toggle merely SEEDS from the platform-required
 *    default when the field has no authored value. The former force-on/disable binding for
 *    platform-required / membership-type fields OVERRULED the admin and is REMOVED (03b Req 1).
 *  - **enum subset picker** → `application_choices` (R3.2 / R4.1). Offered ONLY on a field that has
 *    choices (an enum / reference field). It is a strict SUBSET over the field's OWN resolved
 *    choices — the picker can only toggle values that ARE choices of the field, so an out-of-set
 *    value is structurally impossible. "All selected" (or none selected) means the FULL set, stored
 *    as `null`/absent — only a genuine proper subset is persisted as a list.
 *  - **format** dropdown → `format` (R3.3). Fed STRICTLY by the platform's known format tokens
 *    (`fieldConfig.field_format_tokens`, served by SAM task 1.3 from `field_formats.known_tokens()`)
 *    — never a free-typed token. Selecting "none" clears it to `null`.
 *
 * ## Membership-type coherence (R4, task 3.3)
 *
 * The membership-type field (`membership.membership_type`) is SPECIAL. When IT is the selected
 * field and on the form, this panel layers the R4 coherence on top of the generic controls:
 *  - the subset picker sources its options from the tenant's LIVE membership-type catalog
 *    (the field's OWN resolved `options` — spec 03b; the live catalog is retired) —
 *    so the public-safe subset is authored over the real catalog (R4.1/R4.3);
 *  - the application-required toggle is NO LONGER forced/disabled (03b Req 1) — the admin sets it;
 *  - an EMPTY authored subset on the exposed-required field is flagged as incoherent, and any subset
 *    value NOT in the live catalog is flagged (R4.2/R4.3) — convenience guards; the SAM write
 *    re-validates `subset ⊆ choices` / the catalog reference (task 1.1, R8).
 *
 * ## One object, one save (design §3.1 / steering 38 rule 5)
 *
 * This component NEVER makes a network call. Exactly like `ApplicationFieldList` and
 * `MembersFieldModal`, every change is a pure `overlayModel.upsertField` transform of the one
 * working overlay, bubbled up via `onChange`; the builder root (`ApplicationFormBuilder`) commits
 * that working overlay once by DIFFING it into an identity-keyed Change-Op list
 * (`deriveFieldConfigChangeOps` → `saveFieldConfigChangeOps` → `PUT /members/config/fields` `{ops}`
 * body — spec 03 task 5.1/5.2; the whole-object overlay write is retired). The overlay write target
 * here only places the edit into the IN-MEMORY working buffer; it is provenance/origin-aware
 * (mirrors the list's `writeTarget`
 * and the modal's `resolveWriteTarget`): a tenant-added field is authored under `fields[key]`, a
 * platform base field under `fixed_overrides[{group}.{key}]`.
 *
 * ## Gating + seeding (R3.4)
 *
 * The controls are shown ONLY for a field that is on the form (`application_visible`); otherwise a
 * neutral hint tells the admin to put the field on the form first. Each control seeds from the
 * field's CURRENT authored value — the working overlay first (an unsaved edit wins), falling back
 * to the resolved field's served value, then the back-compatible default.
 */
import React, { useMemo } from 'react';
import {
  Badge,
  Box,
  Checkbox,
  FormControl,
  FormLabel,
  Heading,
  Select,
  Switch,
  Text,
  VStack,
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type {
  EnumOptionConfig,
  FieldConfig,
  FieldConfigField,
} from '../../../types/members';
import { resolveFieldConfigLabel } from '../../../services/membersConfigService';
import { findField, upsertField, type FieldOrigin } from './overlayModel';
import { isMembershipTypeField } from './applicationMembershipType';

export interface ApplicationFieldAttributesProps {
  /** The resolved `FieldConfig` (the DISPLAY/seed source + the known format tokens). */
  fieldConfig?: FieldConfig | null;
  /** The key of the field currently selected in the list (null = nothing selected yet). */
  selectedKey: string | null;
  /** The ONE working `field_overlay` object (the WRITE model + current authored state). */
  overlay: MembersConfigValue | undefined;
  /** Apply a mutated overlay — the panel never saves; the builder commits once (Property 8). */
  onChange: (next: MembersConfigValue) => void;
  lang: 'nl' | 'en';
}

/** A resolved field choice normalised to `{ value, label }` for the subset picker. */
interface ResolvedChoice {
  value: string;
  label: { nl: string; en: string };
}

/**
 * Normalise a resolved field's served enum vocabulary (`options`) to `{ value, label{nl,en} }`
 * (mirrors `MembersFieldModal.optionsToChoices`). The server serves enum values under `options` —
 * a rich `{ value, label{nl,en}, roles? }` list OR a bare `string[]`. An absent / non-array
 * `options` yields an empty list (→ the field is NOT enum, so no subset picker).
 */
function resolveChoices(
  options: Array<string | EnumOptionConfig> | null | undefined,
): ResolvedChoice[] {
  if (!Array.isArray(options)) return [];
  return options
    // Spec 03b: a RETIRED option (`allowed:false`) is grandfathered-only, never OFFERED on the
    // application form. A bare string or an absent `allowed` is offered.
    .filter((opt) => typeof opt === 'string' || (opt as EnumOptionConfig).allowed !== false)
    .map((opt) => {
      if (typeof opt === 'string') return { value: opt, label: { nl: opt, en: opt } };
      const value = typeof opt.value === 'string' ? opt.value : String(opt.value ?? '');
      return { value, label: { nl: opt.label?.nl ?? value, en: opt.label?.en ?? value } };
    });
}

/**
 * The origin-aware overlay write target for a field's application attributes (identical to
 * `ApplicationFieldList.writeTarget` / `MembersFieldModal.resolveWriteTarget`): a base /
 * base_overridden field authors under `fixed_overrides[{group}.{key}]`; a tenant-added (or
 * unknown-provenance) field authors under `fields[key]`. `upsertField` never moves a field across
 * maps, so the group key only matters on the FIRST write of a base field.
 */
function writeTarget(field: FieldConfigField): { origin: FieldOrigin; overlayKey: string } {
  const isBase =
    field.origin === 'fixed' ||
    field.provenance === 'base' ||
    field.provenance === 'base_overridden';
  if (isBase) {
    const group = typeof field.group === 'string' && field.group ? field.group : '';
    return { origin: 'fixed_overrides', overlayKey: group ? `${group}.${field.key}` : field.key };
  }
  return { origin: 'fields', overlayKey: field.key };
}

/**
 * Is this resolved field platform-required? Used only to SEED the application-required toggle's
 * default and to surface the informational `platform-required` badge — NOT to force or disable the
 * toggle (that force-on/disable binding overruled the admin and is removed, 03b Req 1.2/1.3).
 */
function isPlatformRequired(field: FieldConfigField): boolean {
  return field.required === true;
}

/**
 * Read the field's current authored overlay entry (prefer the origin-aware override key, falling
 * back to the bare key — an unsaved edit under either key is honoured).
 */
function authoredField(
  overlay: MembersConfigValue | undefined,
  field: FieldConfigField,
): Record<string, unknown> | null {
  const target = writeTarget(field);
  const entry = findField(overlay, target.overlayKey) ?? findField(overlay, field.key);
  return (entry?.field as Record<string, unknown> | undefined) ?? null;
}

export const ApplicationFieldAttributes: React.FC<ApplicationFieldAttributesProps> = ({
  fieldConfig,
  selectedKey,
  overlay,
  onChange,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  const field = useMemo(
    () =>
      selectedKey
        ? (fieldConfig?.fields ?? []).find((f) => f.key === selectedKey) ?? null
        : null,
    [fieldConfig, selectedKey],
  );

  const tokens = useMemo(
    () => (Array.isArray(fieldConfig?.field_format_tokens) ? fieldConfig!.field_format_tokens! : []),
    [fieldConfig],
  );

  // Membership-type coherence (R4, task 3.3): when the SELECTED field is the membership-type field
  // the subset picker sources its options from the LIVE catalog (R4.1) and the field is forced
  // application-required (R4.2) — exactly like a platform-required field. Otherwise this is false
  // and every control behaves generically (R3).
  const isMembershipType = useMemo(() => isMembershipTypeField(field), [field]);

  // Spec 03b: membership_type is a normal enum field that owns its vocabulary — the subset picker
  // (for EVERY field, incl. membership_type) sources from the field's OWN resolved `options`, NOT a
  // live catalog. The live `membershiptype#` catalog is retired (Task 10).
  const choices = useMemo(
    () => (field ? resolveChoices(field.options) : []),
    [field],
  );

  if (!field) {
    return (
      <Box data-testid="application-field-attributes-empty">
        <Text fontSize="sm" color="gray.500">
          {t(
            'Selecteer een veld in de lijst om de formulierinstellingen te bewerken.',
            'Select a field in the list to edit its form attributes.',
          )}
        </Text>
      </Box>
    );
  }

  const label = resolveFieldConfigLabel(field.label, lang, field.key);
  const authored = authoredField(overlay, field);

  // On-the-form gate (R3.4): the attribute controls apply ONLY to a field on the form.
  const onForm =
    typeof authored?.application_visible === 'boolean'
      ? (authored.application_visible as boolean)
      : (field as { application_visible?: boolean }).application_visible === true;

  const target = writeTarget(field);
  const patch = (p: Record<string, MembersConfigValue | undefined>) =>
    onChange(upsertField(overlay, target.overlayKey, p, target.origin));

  // ---- application_required (R3.1) --------------------------------------------------------------
  // 03b Req 1.2/1.3: no field is force-on or disabled. Application-requiredness is the admin's to
  // set for ANY field — the former `requiredForced = isPlatformRequired || isMembershipType`
  // force-on/disable binding OVERRULED the admin and is removed. The toggle seeds from the field's
  // authored value, falling back to the platform-required default (a sensible initial state, not a
  // lock), and the admin may freely turn it off.
  const requiredChecked =
    typeof authored?.application_required === 'boolean'
      ? (authored.application_required as boolean)
      : isPlatformRequired(field);

  const onToggleRequired = (next: boolean) => {
    // Send the EXPLICIT boolean (spec 03b BU-5 / Req 2.1): turning OFF must persist as `false`, not
    // a dropped `undefined` the change-op diff treats as "unchanged" (the toggle root cause). The
    // backend `set_field_application` SETs `false` correctly; the diff emits the explicit OFF.
    patch({ application_required: next });
  };

  // ---- application_choices subset (R3.2 / R4.1) -------------------------------------------------
  const hasChoices = choices.length > 0;
  const authoredSubset = Array.isArray(authored?.application_choices)
    ? (authored!.application_choices as unknown[]).map((v) => String(v))
    : null;
  // Seed: an authored subset (a proper subset), else the full set (all selected = full set = null).
  const selectedValues = new Set(authoredSubset ?? choices.map((c) => c.value));

  // Spec 03b: the subset picker offers ONLY the field's own options, so an out-of-vocabulary
  // subset value is structurally impossible — the former live-catalog subset validation is no
  // longer needed (the server re-validates against the field's options authoritatively).
  const membershipSubsetValidation = null;

  const onToggleChoice = (value: string, included: boolean) => {
    const nextSet = new Set(selectedValues);
    if (included) nextSet.add(value);
    else nextSet.delete(value);
    // "All of the field's own choices selected" === the full set === null/absent (R3.2); only a
    // genuine proper subset persists as a list. Order follows the field's own choice order.
    const nextList = choices.map((c) => c.value).filter((v) => nextSet.has(v));
    const isFullSet = nextList.length === choices.length;
    patch({ application_choices: isFullSet ? null : (nextList as unknown as MembersConfigValue) });
  };

  // ---- format (R3.3) ----------------------------------------------------------------------------
  const authoredFormat =
    authored?.format && typeof authored.format === 'object' && !Array.isArray(authored.format)
      ? (authored.format as { checker?: string })
      : null;
  const currentChecker =
    typeof authoredFormat?.checker === 'string' ? authoredFormat.checker : '';

  const onSelectFormat = (checker: string) => {
    // "none" clears to null (R3.3); a known token writes `{ checker }` (params authored elsewhere).
    patch({ format: checker ? ({ checker } as unknown as MembersConfigValue) : null });
  };

  return (
    <VStack align="stretch" spacing={4} data-testid="application-field-attributes">
      <Box>
        <Heading size="xs" color="gray.300">
          {label}
        </Heading>
        <Text fontSize="xs" color="gray.500">
          {field.key}
        </Text>
      </Box>

      {!onForm ? (
        <Text
          fontSize="sm"
          color="gray.500"
          data-testid="application-field-attributes-not-on-form"
        >
          {t(
            'Zet dit veld eerst op het formulier om de instellingen te bewerken.',
            'Put this field on the form first to edit its attributes.',
          )}
        </Text>
      ) : (
        <>
          {/* application-required (R3.1) */}
          <FormControl display="flex" alignItems="center" justifyContent="space-between">
            <Box>
              <FormLabel color="gray.300" mb={0}>
                {t('Verplicht op formulier', 'Required on form')}
              </FormLabel>
              {isPlatformRequired(field) && (
                <Badge colorScheme="orange" fontSize="0.6rem" mt={1}>
                  {t('platform-verplicht', 'platform-required')}
                </Badge>
              )}
              {isMembershipType && (
                <Badge colorScheme="purple" fontSize="0.6rem" mt={1} ml={1}>
                  {t('lidmaatschapstype', 'membership-type')}
                </Badge>
              )}
            </Box>
            <Switch
              isChecked={requiredChecked}
              onChange={(e) => onToggleRequired(e.target.checked)}
              colorScheme="orange"
              data-testid="application-field-required-toggle"
              aria-label={t(`${label} verplicht op formulier`, `${label} required on form`)}
            />
          </FormControl>

          {/* enum subset picker (R3.2 / R4.1) — on a field with choices, or the membership-type
              field (whose vocabulary is the LIVE catalog, R4.1). */}
          {(hasChoices || isMembershipType) && (
            <FormControl data-testid="application-field-subset">
              <FormLabel color="gray.300">{t('Keuzes op formulier', 'Choices on the form')}</FormLabel>
              <Text fontSize="xs" color="gray.500" mb={2}>
                {isMembershipType
                  ? t(
                    'Keuzes uit de live lidmaatschapstypecatalogus. Alles aangevinkt = de volledige set.',
                    'Choices from the live membership-type catalog. All checked = the full set.',
                  )
                  : t(
                    'Alles aangevinkt = de volledige set. Vink uit om een subset te tonen.',
                    'All checked = the full set. Uncheck to show a subset.',
                  )}
              </Text>
              {/* Membership-type field with an empty live catalog — nothing to author yet (R4.1). */}
              {isMembershipType && !hasChoices && (
                <Text
                  fontSize="xs"
                  color="yellow.300"
                  data-testid="application-field-subset-empty-catalog"
                >
                  {t(
                    'Geen lidmaatschapstypes in de catalogus. Maak er eerst een aan onder Lidmaatschapstypes.',
                    'No membership types in the catalog. Create one first under Membership types.',
                  )}
                </Text>
              )}
              <VStack align="stretch" spacing={1}>
                {choices.map((choice) => (
                  <Checkbox
                    key={choice.value}
                    isChecked={selectedValues.has(choice.value)}
                    onChange={(e) => onToggleChoice(choice.value, e.target.checked)}
                    colorScheme="orange"
                    data-testid={`application-field-subset-option-${choice.value}`}
                  >
                    <Text fontSize="sm" color="gray.200">
                      {lang === 'nl' ? choice.label.nl : choice.label.en}
                    </Text>
                  </Checkbox>
                ))}
              </VStack>
              {/* Membership-type coherence validation (R4.2/R4.3) — surfaced, not silently stored. */}
              {membershipSubsetValidation && membershipSubsetValidation.empty && (
                <Text
                  fontSize="xs"
                  color="red.300"
                  mt={2}
                  data-testid="application-field-subset-empty-error"
                >
                  {t(
                    'Een lidmaatschapstype op het formulier moet minstens één keuze hebben.',
                    'A membership-type on the form must have at least one choice.',
                  )}
                </Text>
              )}
              {membershipSubsetValidation &&
                membershipSubsetValidation.unknownValues.length > 0 && (
                  <Text
                    fontSize="xs"
                    color="red.300"
                    mt={2}
                    data-testid="application-field-subset-unknown-error"
                  >
                    {t(
                      `Onbekende keuze(s) niet in de catalogus: ${membershipSubsetValidation.unknownValues.join(', ')}`,
                      `Unknown choice(s) not in the catalog: ${membershipSubsetValidation.unknownValues.join(', ')}`,
                    )}
                  </Text>
                )}
            </FormControl>
          )}

          {/* format dropdown (R3.3) — fed strictly by the platform-known tokens */}
          <FormControl data-testid="application-field-format">
            <FormLabel color="gray.300">{t('Formaatcontrole', 'Format check')}</FormLabel>
            <Select
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={currentChecker}
              onChange={(e) => onSelectFormat(e.target.value)}
              data-testid="application-field-format-select"
              aria-label={t('Formaatcontrole', 'Format check')}
            >
              <option value="">{t('— geen —', '— none —')}</option>
              {/* A currently-authored checker that is NOT in the known set is still shown so it is
                  visible (and can be cleared) rather than silently dropped by the controlled value. */}
              {currentChecker && !tokens.includes(currentChecker) && (
                <option value={currentChecker}>{currentChecker}</option>
              )}
              {tokens.map((token) => (
                <option key={token} value={token}>
                  {token}
                </option>
              ))}
            </Select>
            {tokens.length === 0 && (
              <Text fontSize="xs" color="gray.500" mt={1}>
                {t(
                  'Geen formaatcontroles beschikbaar.',
                  'No format checks available.',
                )}
              </Text>
            )}
          </FormControl>
        </>
      )}
    </VStack>
  );
};

export default ApplicationFieldAttributes;
