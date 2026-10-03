/**
 * Shared, sectioned form BODY for the Members add/edit modals (s5c task 4.4, design C-SURFACE;
 * R5.5, R4.8, R4.9, R4.11, R4.12).
 *
 * Renders the RESOLVED field set (fixed base ⊕ tenant overlay ⊕ calculated) — NOT a hardcoded
 * field list — as Formik fields, SECTIONED by each field's parameter-driven `functional_group`
 * (R4.9), honoring:
 *
 * - field-level VIEW/EDIT permissions — a `read_only` / calculated field (R4.4) is rendered
 *   disabled (shown for context, never editable);
 * - `show_when` CONDITIONAL VISIBILITY (R4.12) — a field is rendered only when its condition
 *   holds against the CURRENT Formik values (so a hidden field is never shown/required/sent),
 *   using the SAME predicate the server enforces;
 * - VALUE-LEVEL role-restricted enum options (R4.11/R4.12) — a rich-enum dropdown renders only
 *   the options the caller may select (convenience filtering; the domain rejects a disallowed
 *   value authoritatively);
 * - `member_number` MANUAL ENTRY (R4.8) — a typed string with immediate tenant-format feedback
 *   (the server validates the format + uniqueness authoritatively);
 * - the `membership_type` reference dropdown fed by its resolved `options` (the tenant's active
 *   catalog feed — the active-catalog dropdown proper is task 4.7), and the scope dimension
 *   (`region`) dropdown fed by the field config's dimension values.
 *
 * Authority is server-side (R2.3): this body only presents + gives early feedback. It is a pure
 * presentation component driven by the injected resolved `sections` + `values` — the parent
 * modal owns Formik, submission, and the write payload shaping.
 */

import React from 'react';
import {
  FormControl, FormLabel, FormErrorMessage, FormHelperText,
  Input, VStack, Heading, Divider, Box,
} from '@chakra-ui/react';
import { Field, type FieldProps } from 'formik';
import type {
  EnumOptionConfig, FieldConfig, FieldConfigField, MembershipType,
} from '../../types/members';
import { LazySelect } from '../common/LazySelect';
import type { LazyOption } from '../common/lazySelect.types';
import { listMembershipTypes } from '../../services/membersApiService';
import {
  type FieldSection,
  resolveLabel,
  evaluateShowWhen,
  richEnumOptions,
  enumOptionToLazyOption,
  optionsForCaller,
  memberNumberError,
  isEditableField,
  isMembershipTypeField,
  membershipTypeOptions,
} from './fieldForm';

interface MembersFieldFormBodyProps {
  /** The resolved sections to render (from `groupFieldsBySection`). */
  sections: FieldSection[];
  /** The resolved field config (for the scope dimension + labels). */
  fieldConfig: FieldConfig | null;
  /** The current Formik values (drives `show_when` visibility). */
  values: Record<string, unknown>;
  /** The caller's roles (drives value-level enum option filtering, R4.12). */
  callerRoles: string[];
  /** Current UI language (2-letter). */
  lang: string;
  /** i18n translate fn (namespace already bound by the parent). */
  t: (key: string) => string;
  /** The scope dimension key (e.g. "region") + its allowed values, from the field config. */
  dimensionKey: string;
  regionValues: string[];
  dimensionLabel?: string;
  /**
   * The tenant's ACTIVE **Lidmaatschap Beheer** catalog entries (R5.8), fetched by the parent via
   * `listMembershipTypes(true)`. These feed the `membership_type` dropdown so it lists ONLY active
   * types — the domain re-validates the chosen type authoritatively. `null`/omitted falls back to
   * the field-config's embedded catalog options.
   */
  membershipTypes?: MembershipType[] | null;
}

/** Keys the parent renders as first-class controls elsewhere (not as generic overlay inputs). */
const SCOPE_KEYS = new Set<string>(['region']);

export const MembersFieldFormBody: React.FC<MembersFieldFormBodyProps> = ({
  // `fieldConfig` and `dimensionKey` remain on the props contract (parent passes them) but are no
  // longer read here: labels come from each field's own config and the LazySelect trigger carries
  // its accessible name via `label` (the old `data-dimension` hook on the native <select> is gone).
  sections, values, callerRoles, lang, t,
  regionValues, dimensionLabel, membershipTypes,
}) => {
  return (
    <VStack spacing={4} align="stretch">
      {sections.map((section) => {
        // A section renders only if it has at least one currently-visible field.
        const visibleFields = section.fields.filter((f) =>
          evaluateShowWhen(f.show_when, values),
        );
        if (visibleFields.length === 0) return null;

        return (
          <Box key={section.key}>
            {section.label && (
              <>
                <Heading size="xs" color="orange.300" mb={2} textTransform="uppercase">
                  {resolveLabel(section.label, lang, section.key)}
                </Heading>
                <Divider borderColor="gray.600" mb={3} />
              </>
            )}
            <VStack spacing={3} align="stretch">
              {visibleFields.map((f) => (
                <FieldRow
                  key={`${f.group ?? ''}.${f.key}`}
                  field={f}
                  callerRoles={callerRoles}
                  lang={lang}
                  t={t}
                  isScope={SCOPE_KEYS.has(f.key)}
                  regionValues={regionValues}
                  dimensionLabel={dimensionLabel}
                  membershipTypes={membershipTypes}
                />
              ))}
            </VStack>
          </Box>
        );
      })}
    </VStack>
  );
};

interface FieldRowProps {
  field: FieldConfigField;
  callerRoles: string[];
  lang: string;
  t: (key: string) => string;
  isScope: boolean;
  regionValues: string[];
  dimensionLabel?: string;
  membershipTypes?: MembershipType[] | null;
}

/** One field control: dispatches on the field's type/role to the right input. */
const FieldRow: React.FC<FieldRowProps> = ({
  field, callerRoles, lang, t, isScope, regionValues, dimensionLabel, membershipTypes,
}) => {
  const editable = isEditableField(field);
  const label = isScope
    ? (dimensionLabel || resolveLabel(field.label, lang, field.key))
    : resolveLabel(field.label, lang, field.key);

  // membership_type (R5.8): the dropdown is fed by the ACTIVE catalog (listMembershipTypes(true))
  // when the parent injected it; otherwise fall back to the field-config's embedded options.
  const isMembershipType = isMembershipTypeField(field);
  const catalogOptions =
    isMembershipType && membershipTypes != null ? membershipTypeOptions(membershipTypes) : null;
  const rich = catalogOptions ?? richEnumOptions(field);

  // The Formik field name: the scope dimension binds to `region`; every other field to its key.
  const name = isScope ? 'region' : field.key;

  return (
    <Field name={name}>
      {({ field: formikField, form }: FieldProps<string, Record<string, string>>) => {
        const error = form.errors[name] as string | undefined;
        const touched = form.touched[name] as boolean | undefined;
        const showError = !!error && !!touched;

        // member_number manual-entry immediate format feedback (R4.8).
        const fmtError =
          field.key === 'member_number'
            ? memberNumberError(field, formikField.value ?? '', t('addModal.validation.memberNumberFormat'))
            : null;

        // ── Scope dimension (region) or a reference/rich-enum → LazySelect ────────────
        // The generic edit-on-click dropdown adopted platform-wide; it tolerates a legacy /
        // role-gated / out-of-set current value (shows it at rest, never blanks it) so the old
        // synthetic-current-value prepend is no longer needed. This ONE branch covers EVERY
        // enum/reference/scope dropdown (Gender, Clubblad, Motorbrand, region, membership_type,
        // and any future rich-enum/reference field) — no per-field enumeration.
        // See .kiro/specs/Common/Frameworks/lazy-select/ (Requirements 8.1, 8.4, 8.5).
        if (isScope || field.type === 'reference' || rich) {
          // Options by source shape (all fit LazyOptionsSource):
          //  - membership_type → ASYNC source: fetch the ACTIVE catalog on open (R8.1 async feed);
          //  - scope (region)  → EAGER array from the field config's dimension values;
          //  - rich enum       → EAGER array from the rich `{ value, label, roles }` options;
          //  - bare string[]   → EAGER array mapped to `{ value }` (matches the old else-branch).
          const optionsSource = isMembershipType
            ? async (): Promise<LazyOption[]> => {
              // `membershipTypeOptions` yields `EnumOptionConfig[]` (its `label` is a
              // `LocalizedLabel`, wider than `LazyOption.label`); MAP each through
              // `enumOptionToLazyOption` rather than returning it raw, so the async feed
              // satisfies `LazyOption[]` the same way the eager rich-enum branch does.
              const types = await listMembershipTypes<MembershipType[]>(true);
              return membershipTypeOptions(types).map(enumOptionToLazyOption);
            }
            : isScope
              ? regionValues.map((v): LazyOption => ({ value: v }))
              : rich
                ? rich.map(enumOptionToLazyOption)
                : (field.options ?? [])
                  .filter((o): o is string => typeof o === 'string')
                  .map((v): LazyOption => ({ value: v }));

          // Value-level role gating (R5): an option is offered iff `optionsForCaller` keeps it.
          // An out-of-set / role-gated CURRENT value still shows at rest (LazySelect R1) but is
          // never offered as a selectable option.
          const filterOption = (opt: LazyOption): boolean =>
            optionsForCaller([opt as EnumOptionConfig], callerRoles).length > 0;

          return (
            <FormControl
              isRequired={!!field.required}
              isInvalid={showError}
              isDisabled={!editable}
            >
              <FormLabel color="gray.300" fontSize="sm">{label}</FormLabel>
              <LazySelect
                name={name}
                label={label}
                value={formikField.value ?? ''}
                onChange={(v) => {
                  form.setFieldValue(name, v);
                  form.setFieldTouched(name, true);
                }}
                options={optionsSource}
                optionsDepKey={isMembershipType ? 'membership_type' : undefined}
                filterOption={filterOption}
                placeholder={t('addModal.fields.selectPlaceholder')}
                isDisabled={!editable}
                isInvalid={showError}
                size="sm"
              />
              <FormErrorMessage>{error}</FormErrorMessage>
            </FormControl>
          );
        }

        // ── A plain input (string / number / date), including member_number ───────────
        return (
          <FormControl
            isRequired={!!field.required}
            isInvalid={showError || !!fmtError}
            isDisabled={!editable}
          >
            <FormLabel color="gray.300" fontSize="sm">{label}</FormLabel>
            <Input
              {...formikField}
              type={inputType(field)}
              size="sm" bg="gray.700" color="white" borderColor="gray.600"
              isDisabled={!editable}
              isReadOnly={!editable}
            />
            {field.member_number_format?.example && !fmtError && (
              <FormHelperText color="gray.500" fontSize="xs">
                {`${t('addModal.fields.memberNumberHint')} ${field.member_number_format.example}`}
              </FormHelperText>
            )}
            <FormErrorMessage>{error || fmtError}</FormErrorMessage>
          </FormControl>
        );
      }}
    </Field>
  );
};

/** Map a field type to an HTML input type. */
function inputType(field: FieldConfigField): string {
  if (field.type === 'number') return 'number';
  if (field.type === 'date') return 'date';
  return 'text';
}

// NOTE: the former `renderOptions` helper (and its synthetic-current-value prepend, the s5j
// stopgap that kept a legacy/out-of-set value visible in a plain `<select>`) has been REMOVED.
// The generic `LazySelect` building block now owns "tolerate legacy, enforce on change" — it
// shows the current value at rest whether or not it is in the option set (Requirement 1) — so
// every enum/reference/scope dropdown here routes through it. See
// .kiro/specs/Common/Frameworks/lazy-select/ (Requirements 8.1, 8.4, 8.5).

export default MembersFieldFormBody;
