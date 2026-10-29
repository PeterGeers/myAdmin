/**
 * Application field modal — the per-field authoring modal of the Application Form Builder
 * (spec 12 — Application Form Serving Redesign, task 4.1; R1.1/R1.2, design §C1 / redesign A).
 *
 * ## What this replaces (redesign A)
 *
 * Spec 11 authored a field's application attributes through a bespoke `ApplicationFieldList`
 * toggle-list PLUS a cramped attributes panel buried under a ~100-field list. That surface is
 * RETIRED. In its place the builder keeps its group ▸ field surface, but clicking a field now
 * opens THIS modal — the proven `MembersFieldModal` authoring pattern reused for the application
 * form (R1.1).
 *
 * ## It reuses `MembersFieldModal`'s ENGINE, not a forked write path (R1.1 / design §C1)
 *
 * The write engine is the SAME three primitives `MembersFieldModal` authors with — there is no
 * second overlay-write code path (design §C1 / R1.4):
 *   - `resolveWriteTarget` (ported verbatim from `MembersFieldModal`) derives the origin-aware
 *     IN-MEMORY working-buffer slice + key from the resolved field's provenance: a tenant-added
 *     field authors under `fields[key]`, a platform base field under `fixed_overrides[{group}.{key}]`,
 *     and a calculated field is read-only (never written). This placement is buffer-only — the dotted
 *     `{group}.{key}` key NEVER crosses the wire; the Change-Op builder strips it to the bare identity
 *     and the SERVER owns storage placement (spec 03 task 5.1/5.2, steering 39);
 *   - `buildField`/`upsertField` — every attribute the modal authors is a pure
 *     `overlayModel.upsertField` transform of the ONE working `field_overlay` object, bubbled up via
 *     `onChange`; the builder root commits that working overlay ONCE by diffing it into an
 *     identity-keyed Change-Op list (`deriveFieldConfigChangeOps` → `saveFieldConfigChangeOps` →
 *     `PUT /members/config/fields` `{ops}` body — the whole-object overlay write is retired). This
 *     modal NEVER makes a network call.
 *
 * ## The application-form attributes section is shown ONLY when a form is in scope (R1.2)
 *
 * The modal carries an **application-form attributes section** that renders ONLY when
 * `formInScope` is true — i.e. when an application form is being authored (the Application Form
 * Builder context), never in the generic Members field-config context. In scope, the section
 * authors the on-the-form state (`application_visible`) directly onto the one overlay through the
 * shared engine.
 *
 * ## Scope of THIS task (4.1) — the modal + the on-the-form attribute scaffold
 *
 * Task 4.1 stood up: the modal-open-on-field-click replacement of the toggle-list + panel, the
 * `MembersFieldModal`-engine wiring, and the application-form attributes SECTION shown only when a
 * form is in scope, with the on-the-form toggle.
 *
 * ## Task 4.2 — the enum-subset picker whose SOURCE adapts to the field kind (R1.3 / design §C1)
 *
 * This task adds the enum-subset picker (`application_choices`) into that same section. Its SOURCE
 * adapts to the FIELD KIND (via the pure `applicationChoiceSource` helpers — kept out of this
 * component so the rules are unit-testable):
 *   - a REFERENCE field (e.g. `membership_type`) sources from the tenant's LIVE catalog
 *     (the field's OWN resolved `options` — spec 03b; the live catalog is retired);
 *   - a SCOPE axis sources from the scope DIMENSION values (= the field's own options under the
 *     single-vocabulary model, R3.2/R3.3);
 *   - an ENUM/choices field sources from its OWN options.
 * The picker renders ONLY for a choice-bearing field — NEVER for a plain string field (R1.3, fixes
 * the spec 11 choice-on-string bug). The chosen subset is written onto the ONE working overlay as
 * `application_choices` through the SAME `upsertField` engine (origin-aware); "all selected" (the
 * full set) is stored as `null`/absent, only a genuine proper subset persists as a list.
 *
 * ## Task 4.3 — the remaining two attributes (`application_required`, `format`) on the ONE overlay
 *
 * This task completes the four-attribute write-through, replacing the task-4.1 scaffold placeholder
 * with the remaining per-field application attributes — authored onto the SAME single
 * `field_overlay` object through the SAME origin-aware `upsertField` engine (R1.4 / R2.1/R2.2); no
 * forked write path:
 *   - **`application_required`** — a required-on-the-form toggle. It can TIGHTEN an optional field
 *     to required, but NEVER RELAX a platform-required one (R2 no-relax, carried from spec 11): for
 *     a platform-required field (`field.required === true`) the toggle is FORCED ON + disabled with
 *     an explanatory note — the UI never offers a relax (the SAM write is authoritative regardless).
 *     The membership-type reference field is likewise forced-required when on the form (spec 10 D21).
 *   - **`format`** — a declarative validator-token picker fed STRICTLY by the platform's KNOWN
 *     tokens (`fieldConfig.field_format_tokens`, the SAME source the retired spec-11
 *     `ApplicationFieldAttributes` panel used — `field_formats.known_tokens()` via SAM). Only a
 *     known token is authorable (an unknown token is never offerable); selecting "none" clears it to
 *     `null`. A currently-authored checker not in the known set is shown so it stays clearable.
 *
 * Field `order` is NOT authored here: the application-form builder's group ▸ field surface is a
 * pure DISPLAY ordered by the catalog rule `(group.order, field.order, key)`; `order` is authored on
 * the generic Field-configuration surface (`MembersFieldModal`), not duplicated into this modal.
 *
 * The DEFERRED pieces live in a later wave and are NOT built here:
 *   - the dedicated full modal test matrix + axe — task 4.4.
 */
import React, { useMemo } from 'react';
import {
  Badge,
  Box,
  Button,
  Checkbox,
  Divider,
  FormControl,
  FormLabel,
  Heading,
  HStack,
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
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import { resolveFieldConfigLabel } from '../../../services/membersConfigService';
import { findField, upsertField, type FieldOrigin } from './overlayModel';
import { isChoiceBearingField, resolveChoiceSource } from './applicationChoiceSource';
import { isMembershipTypeField } from './applicationMembershipType';

/** The back-office STORAGE group whose fields default OFF the public form (R2.4, carried from spec 11). */
const MEMBERSHIP_STORAGE_GROUP = 'membership';

export interface ApplicationFieldModalProps {
  isOpen: boolean;
  onClose: () => void;
  /**
   * The key of the field being authored (the field the admin clicked in the list). `null`/absent
   * → the modal renders nothing (it only opens on a field click).
   */
  fieldKey: string | null;
  /**
   * The resolved `FieldConfig` (`GET /members/field-config`) — the DISPLAY/seed source: the field's
   * label, type, provenance (origin-aware write target), and served application attributes.
   */
  fieldConfig?: FieldConfig | null;
  /** The ONE working `field_overlay` object (the WRITE model + the current authored state). */
  overlay: MembersConfigValue | undefined;
  /** Apply a mutated overlay — the modal never saves; the builder commits once (Property 8). */
  onChange: (next: MembersConfigValue) => void;
  /**
   * Whether an application FORM is in scope (R1.2). The application-form attributes section renders
   * ONLY when this is true — the Application Form Builder passes `true`; a generic field-config
   * context would pass `false` (no application attributes authored there).
   */
  formInScope: boolean;
  lang: 'nl' | 'en';
}

/**
 * The ORIGIN-AWARE overlay write target for a field's application attribute — ported VERBATIM from
 * `MembersFieldModal.resolveWriteTarget` (reusing the SAME engine logic, R1.1): a tenant-ADDED field
 * authors under `fields[key]`; a base / base_overridden field under `fixed_overrides[{group}.{key}]`;
 * a CALCULATED field is read-only (`writable: false`, never written). `upsertField` never moves a
 * field across maps, so the storage-group key only matters on the FIRST write of a base field.
 */
export function resolveWriteTarget(
  field: FieldConfigField | undefined,
): { writable: boolean; origin: FieldOrigin; overlayKey: string } {
  if (!field) return { writable: true, origin: 'fields', overlayKey: '' };
  // Calculated / derived fields are platform-owned + read-only — never authored by the tenant.
  if (field.origin === 'calculated') {
    return { writable: false, origin: 'fields', overlayKey: field.key };
  }
  const isBase =
    field.origin === 'fixed' ||
    field.provenance === 'base' ||
    field.provenance === 'base_overridden';
  if (isBase) {
    const group = typeof field.group === 'string' && field.group ? field.group : '';
    const overlayKey = group ? `${group}.${field.key}` : field.key;
    return { writable: true, origin: 'fixed_overrides', overlayKey };
  }
  return { writable: true, origin: 'fields', overlayKey: field.key };
}

/**
 * Is this resolved field OFFERABLE on the public form (R2.5, carried from spec 11)? Calculated /
 * derived fields and platform read-only fields are never authorable onto the form.
 */
function isOfferable(field: FieldConfigField): boolean {
  if (field.origin === 'calculated') return false;
  if (field.read_only === true) return false;
  return true;
}

/**
 * Is this resolved field PLATFORM-REQUIRED (R2 no-relax)? A platform-required field's
 * application-required state can never be RELAXED to optional — the modal forces the toggle ON +
 * disabled with an explanatory note (identical to the retired `ApplicationFieldAttributes` panel;
 * the SAM write rejects a relax regardless, R8.1c).
 */
function isPlatformRequired(field: FieldConfigField): boolean {
  return field.required === true;
}

/**
 * The effective on-the-form state for a field (R2.2/R2.3/R2.4, carried from spec 11). Precedence:
 *  1. the WORKING overlay's authored `application_visible` (an unsaved edit wins — by the
 *     origin-aware override key or the bare key);
 *  2. the resolved field's served `application_visible`;
 *  3. default OFF (membership-admin fields and everything else start off).
 */
function isOnForm(overlay: MembersConfigValue | undefined, field: FieldConfigField): boolean {
  const target = resolveWriteTarget(field);
  const authored =
    findField(overlay, target.overlayKey)?.field.application_visible ??
    findField(overlay, field.key)?.field.application_visible;
  if (typeof authored === 'boolean') return authored;
  const served = (field as { application_visible?: boolean }).application_visible;
  if (typeof served === 'boolean') return served;
  return false;
}

export const ApplicationFieldModal: React.FC<ApplicationFieldModalProps> = ({
  isOpen,
  onClose,
  fieldKey,
  fieldConfig,
  overlay,
  onChange,
  formInScope,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // The resolved descriptor for the authored field — the seed source + the origin-aware write
  // target. Absent (fetch gap / unknown key) → the modal degrades to a neutral "unavailable" body.
  const field = useMemo(
    () =>
      fieldKey ? (fieldConfig?.fields ?? []).find((f) => f.key === fieldKey) ?? null : null,
    [fieldConfig, fieldKey],
  );

  // Nothing to author (closed, no key, or an unresolved key) — render only the modal shell so the
  // close affordance still works, never a blank or crashing body.
  const label = field ? resolveFieldConfigLabel(field.label, lang, field.key) : (fieldKey ?? '');
  const offerable = field ? isOfferable(field) : false;
  const onFormNow = field ? isOnForm(overlay, field) : false;
  const isMembershipAdmin = field?.group === MEMBERSHIP_STORAGE_GROUP;

  /**
   * Author the on-the-form state onto the ONE overlay through the SHARED engine (R1.1 / §3.1).
   * Toggling ON writes `application_visible: true`; toggling OFF writes an EXPLICIT
   * `application_visible: false` (spec 03b BU-5 / Req 2.1 — the toggle root-cause fix: a dropped
   * `undefined` was treated as "unchanged" and silently reverted on reload). The write target is
   * origin-aware (`resolveWriteTarget`), so a tenant field lands under `fields[key]` and a base
   * field under `fixed_overrides[{group}.{key}]`.
   */
  const toggleOnForm = (on: boolean) => {
    if (!field) return;
    const target = resolveWriteTarget(field);
    if (!target.writable) return; // calculated/read-only — never authored (R2.5)
    // Send the EXPLICIT boolean (spec 03b BU-5 / Req 2.1): turning a field OFF the form must persist
    // as `false`, not a dropped `undefined` the change-op diff treats as "unchanged" (the toggle
    // root cause). The diff against the LOADED state emits the explicit OFF so a reload shows OFF.
    onChange(
      upsertField(overlay, target.overlayKey, { application_visible: on }, target.origin),
    );
  };

  // ---- Enum-subset picker (task 4.2 / R1.3) ---------------------------------------------------
  // The picker SOURCE adapts to the field kind (reference → live catalog; scope → the scope
  // dimension values; enum → own options). `resolveChoiceSource` returns null for a plain string
  // field — the picker then does NOT render (R1.3, the spec 11 choice-on-string fix).
  const choiceSource = useMemo(
    // Spec 03b: membership_type sources from the field's own options (resolveChoiceSource reads
    // field.options); the live catalog is retired, so no catalog is threaded in anymore.
    () => (field ? resolveChoiceSource(field, null, lang) : null),
    [field, lang],
  );
  const showPicker = field ? isChoiceBearingField(field) : false;

  // The field's CURRENT authored overlay entry — the working overlay (an unsaved edit wins), by the
  // origin-aware override key, falling back to the bare key.
  const authoredField = field
    ? (findField(overlay, resolveWriteTarget(field).overlayKey)?.field ??
      findField(overlay, field.key)?.field ??
      null)
    : null;

  // Seed the selected subset: an authored proper subset wins; else the full set (all selected =
  // full set = null/absent, R3.2). A non-array authored value (null/absent) means the full set.
  const authoredSubset = Array.isArray(authoredField?.application_choices)
    ? (authoredField!.application_choices as unknown[]).map((v) => String(v))
    : null;
  const pickerChoices = choiceSource?.choices ?? [];
  const selectedValues = new Set(authoredSubset ?? pickerChoices.map((c) => c.value));

  /**
   * Toggle one choice in/out of the subset and write `application_choices` onto the ONE overlay
   * through the SAME `upsertField` engine (origin-aware). "All of the source's values selected" ===
   * the full set === `null`/absent (R3.2); only a genuine proper subset persists as a list. Order
   * follows the source's own order.
   */
  const toggleChoice = (value: string, included: boolean) => {
    if (!field) return;
    const target = resolveWriteTarget(field);
    if (!target.writable) return;
    const nextSet = new Set(selectedValues);
    if (included) nextSet.add(value);
    else nextSet.delete(value);
    const nextList = pickerChoices.map((c) => c.value).filter((v) => nextSet.has(v));
    const isFullSet = nextList.length === pickerChoices.length;
    onChange(
      upsertField(
        overlay,
        target.overlayKey,
        { application_choices: isFullSet ? null : (nextList as unknown as MembersConfigValue) },
        target.origin,
      ),
    );
  };

  // ---- application_required (task 4.3 / R2 no-relax) ------------------------------------------
  // The required-on-the-form toggle. It can TIGHTEN an optional field to required, but NEVER RELAX
  // a platform-required one: for a platform-required field (and the membership-type reference field
  // when on the form, spec 10 D21) the toggle is FORCED ON + disabled with an explanatory note (the
  // UI never offers a relax; the SAM write stays authoritative, R8.1c). Seeds from the working
  // overlay's authored `application_required`, else off.
  const isMembershipType = field ? isMembershipTypeField(field) : false;
  const requiredForced = field ? isPlatformRequired(field) || isMembershipType : false;
  const requiredChecked = requiredForced
    ? true // forced on — a platform-required / membership-type field is always required on the form
    : typeof authoredField?.application_required === 'boolean'
      ? (authoredField.application_required as boolean)
      : false;

  const toggleRequired = (on: boolean) => {
    if (!field) return;
    if (requiredForced) return; // no-relax: a platform-required field is never relaxed (R2)
    const target = resolveWriteTarget(field);
    if (!target.writable) return;
    // Send the EXPLICIT boolean (spec 03b BU-5 / Req 2.1): turning required OFF must persist as
    // `false`, not a dropped `undefined` the change-op diff treats as "unchanged" (the toggle root
    // cause). Same uniform fix as the on-the-form toggle (Req 2.3 — not a special-cased subset).
    onChange(
      upsertField(overlay, target.overlayKey, { application_required: on }, target.origin),
    );
  };

  // ---- format (task 4.3 / R3.3) ---------------------------------------------------------------
  // A declarative validator-token picker fed STRICTLY by the platform's KNOWN tokens
  // (`fieldConfig.field_format_tokens`) — only a known token is authorable (an unknown token is
  // never offerable). Selecting "none" clears `format` to null. A currently-authored checker not in
  // the known set is still shown so it stays clearable rather than silently dropped.
  const formatTokens = Array.isArray(fieldConfig?.field_format_tokens)
    ? fieldConfig!.field_format_tokens!
    : [];
  const authoredFormat =
    authoredField?.format &&
      typeof authoredField.format === 'object' &&
      !Array.isArray(authoredField.format)
      ? (authoredField.format as { checker?: string })
      : null;
  const currentChecker =
    typeof authoredFormat?.checker === 'string' ? authoredFormat.checker : '';

  const selectFormat = (checker: string) => {
    if (!field) return;
    const target = resolveWriteTarget(field);
    if (!target.writable) return;
    // "none" clears to null (R3.3); a known token writes `{ checker }` (params authored elsewhere).
    onChange(
      upsertField(
        overlay,
        target.overlayKey,
        { format: checker ? ({ checker } as unknown as MembersConfigValue) : null },
        target.origin,
      ),
    );
  };

  const sourceHint = (kind: 'reference' | 'scope' | 'enum'): string => {
    if (kind === 'reference') {
      return t(
        'Keuzes uit de eigen opties van dit veld. Alles aangevinkt = de volledige set.',
        'Choices from this field\u2019s own options. All checked = the full set.',
      );
    }
    if (kind === 'scope') {
      return t(
        'Keuzes uit de scope-dimensiewaarden. Alles aangevinkt = de volledige set.',
        'Choices from the scope dimension values. All checked = the full set.',
      );
    }
    return t(
      'Alles aangevinkt = de volledige set. Vink uit om een subset te tonen.',
      'All checked = the full set. Uncheck to show a subset.',
    );
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" data-testid="application-field-modal" lang={lang}>
        <ModalHeader color="orange.400">
          {t('Veldinstellingen', 'Field attributes')}
          {field && (
            <Text fontSize="sm" color="gray.400" fontWeight="normal" mt={1}>
              {label}
              {field.type && (
                <Badge ml={2} fontSize="0.6rem" colorScheme="purple">
                  {field.type}
                </Badge>
              )}
              {isMembershipAdmin && (
                <Badge ml={1} fontSize="0.6rem" colorScheme="gray">
                  {t('beheer', 'admin')}
                </Badge>
              )}
            </Text>
          )}
        </ModalHeader>
        <ModalCloseButton color="white" />

        <ModalBody>
          {!field ? (
            <Text fontSize="sm" color="gray.500" data-testid="application-field-modal-unavailable">
              {t(
                'Dit veld is niet beschikbaar. Configureer het eerst onder Veldconfiguratie.',
                'This field is unavailable. Configure it first under Field configuration.',
              )}
            </Text>
          ) : (
            <VStack align="stretch" spacing={4} pb={2}>
              <Box>
                <Text fontSize="xs" color="gray.500">
                  {field.key}
                </Text>
              </Box>

              {/* Application-form attributes section — rendered ONLY when a form is in scope (R1.2).
                  In the generic field-config context (`formInScope === false`) nothing application-
                  specific is authored here. */}
              {formInScope ? (
                <Box data-testid="application-field-modal-app-attrs">
                  <Heading size="xs" color="gray.400" textTransform="uppercase" mb={3}>
                    {t('Formulierinstellingen', 'Application form attributes')}
                  </Heading>

                  {offerable ? (
                    <>
                      {/* On-the-form toggle (`application_visible`) — the primary application
                          attribute, authored through the shared engine (R1.1). */}
                      <FormControl
                        display="flex"
                        alignItems="center"
                        justifyContent="space-between"
                      >
                        <FormLabel color="gray.300" mb={0}>
                          {t('Op het formulier', 'On the form')}
                        </FormLabel>
                        <Switch
                          isChecked={onFormNow}
                          onChange={(e) => toggleOnForm(e.target.checked)}
                          colorScheme="orange"
                          data-testid="application-field-modal-on-form-toggle"
                          aria-label={t(
                            `${label} op het formulier`,
                            `${label} on the form`,
                          )}
                        />
                      </FormControl>

                      {/* Enum-subset picker (task 4.2 / R1.3) — renders ONLY for a choice-bearing
                          field (reference / scope / enum), NEVER for a plain string field. Its
                          SOURCE adapts to the field kind (resolveChoiceSource); the chosen subset is
                          written as `application_choices` onto the ONE overlay via the shared engine. */}
                      {showPicker && choiceSource && (
                        <>
                          <Divider borderColor="gray.600" my={3} />
                          <FormControl data-testid="application-field-modal-subset">
                            <FormLabel color="gray.300">
                              {t('Keuzes op formulier', 'Choices on the form')}
                            </FormLabel>
                            <Text
                              fontSize="xs"
                              color="gray.500"
                              mb={2}
                              data-source-kind={choiceSource.kind}
                              data-testid="application-field-modal-subset-source"
                            >
                              {sourceHint(choiceSource.kind)}
                            </Text>
                            {pickerChoices.length === 0 ? (
                              // A choice-bearing field with no values to offer yet (e.g. an empty
                              // membership catalog, or a scope axis whose values are not authored).
                              <Text
                                fontSize="xs"
                                color="yellow.300"
                                data-testid="application-field-modal-subset-empty-source"
                              >
                                {choiceSource.kind === 'reference'
                                  ? t(
                                    'Geen lidmaatschapstypes in de catalogus. Maak er eerst een aan.',
                                    'No membership types in the catalog. Create one first.',
                                  )
                                  : t(
                                    'Nog geen keuzes beschikbaar voor dit veld.',
                                    'No choices available for this field yet.',
                                  )}
                              </Text>
                            ) : (
                              <VStack align="stretch" spacing={1}>
                                {pickerChoices.map((choice) => (
                                  <Checkbox
                                    key={choice.value}
                                    isChecked={selectedValues.has(choice.value)}
                                    onChange={(e) => toggleChoice(choice.value, e.target.checked)}
                                    colorScheme="orange"
                                    data-testid={`application-field-modal-subset-option-${choice.value}`}
                                  >
                                    <Text fontSize="sm" color="gray.200">
                                      {lang === 'nl' ? choice.label.nl : choice.label.en}
                                    </Text>
                                  </Checkbox>
                                ))}
                              </VStack>
                            )}
                          </FormControl>
                        </>
                      )}

                      {/* Required-on-the-form toggle (`application_required`, task 4.3 / R2). It can
                          TIGHTEN an optional field, but for a platform-required (or membership-type)
                          field it is FORCED ON + disabled with an explanatory note — the UI never
                          offers a relax (NO-RELAX, R2). Written onto the ONE overlay via the shared
                          engine (origin-aware). */}
                      <Divider borderColor="gray.600" my={3} />
                      <FormControl data-testid="application-field-modal-required">
                        <HStack justify="space-between" align="start">
                          <Box>
                            <FormLabel color="gray.300" mb={0}>
                              {t('Verplicht op formulier', 'Required on the form')}
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
                            isDisabled={requiredForced}
                            onChange={(e) => toggleRequired(e.target.checked)}
                            colorScheme="orange"
                            data-testid="application-field-modal-required-toggle"
                            aria-label={t(
                              `${label} verplicht op formulier`,
                              `${label} required on the form`,
                            )}
                          />
                        </HStack>
                        {requiredForced && (
                          <Text
                            fontSize="xs"
                            color="gray.500"
                            mt={1}
                            data-testid="application-field-modal-required-locked-note"
                          >
                            {isPlatformRequired(field)
                              ? t(
                                'Een platform-verplicht veld blijft altijd verplicht op het formulier.',
                                'A platform-required field is always required on the form.',
                              )
                              : t(
                                'Een lidmaatschapstype op het formulier is altijd verplicht.',
                                'A membership-type on the form is always required.',
                              )}
                          </Text>
                        )}
                      </FormControl>

                      {/* Format picker (`format`, task 4.3 / R3.3) — fed STRICTLY by the platform's
                          KNOWN tokens; an unknown token is never offerable. "none" clears to null. */}
                      <Divider borderColor="gray.600" my={3} />
                      <FormControl data-testid="application-field-modal-format">
                        <FormLabel color="gray.300">
                          {t('Formaatcontrole', 'Format check')}
                        </FormLabel>
                        <Select
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          value={currentChecker}
                          onChange={(e) => selectFormat(e.target.value)}
                          data-testid="application-field-modal-format-select"
                          aria-label={t('Formaatcontrole', 'Format check')}
                        >
                          <option value="">{t('— geen —', '— none —')}</option>
                          {/* A currently-authored checker NOT in the known set is still shown so it
                              is visible + clearable, never silently dropped by the controlled value. */}
                          {currentChecker && !formatTokens.includes(currentChecker) && (
                            <option value={currentChecker}>{currentChecker}</option>
                          )}
                          {formatTokens.map((token) => (
                            <option key={token} value={token}>
                              {token}
                            </option>
                          ))}
                        </Select>
                        {formatTokens.length === 0 && (
                          <Text
                            fontSize="xs"
                            color="gray.500"
                            mt={1}
                            data-testid="application-field-modal-format-empty"
                          >
                            {t(
                              'Geen formaatcontroles beschikbaar.',
                              'No format checks available.',
                            )}
                          </Text>
                        )}
                      </FormControl>
                    </>
                  ) : (
                    // A calculated / read-only field is never offerable on the form (R2.5): no
                    // toggle, a clear note instead (mirrors the retired list's behaviour).
                    <Text
                      fontSize="sm"
                      color="gray.500"
                      fontStyle="italic"
                      data-testid="application-field-modal-not-offerable"
                    >
                      {t(
                        'Dit veld kan niet op het formulier worden gezet.',
                        'This field cannot be put on the form.',
                      )}
                    </Text>
                  )}
                </Box>
              ) : (
                <Text fontSize="sm" color="gray.500" data-testid="application-field-modal-no-form">
                  {t(
                    'Geen formulier in beeld.',
                    'No form in scope.',
                  )}
                </Text>
              )}
            </VStack>
          )}
        </ModalBody>

        <ModalFooter>
          <HStack justify="flex-end" width="100%">
            <Button
              colorScheme="orange"
              onClick={onClose}
              data-testid="application-field-modal-done-btn"
            >
              {t('Klaar', 'Done')}
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default ApplicationFieldModal;
