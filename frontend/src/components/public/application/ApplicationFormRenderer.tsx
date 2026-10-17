/**
 * Config-driven renderer for the PUBLIC member-application form
 * (spec Members/application-app, task 9.1).
 *
 * Renders WHATEVER the public field-config ({@link PublicFieldConfig}) lists — NOT a hand-coded
 * field list (R4 hard constraint). Each field becomes one Chakra `FormControl` / `FormLabel` /
 * `FormErrorMessage` with the widget chosen by its `type` (string→Input, enum/reference→Select
 * from `options`, date→date input), SECTIONED + ordered by `functional_group` then `order`
 * (R4.1/R4.6), with labels in the applicant locale (`label[locale]`, nl fallback, R6b), and
 * `show_when` conditional visibility honored (R6.3).
 *
 * This is a CONTROLLED presentation component: the parent owns the flat form state (keyed by each
 * field's DOTTED `key` — the R10a.4 submit shape) and passes it in via `values` + `onChange`. That
 * keeps this renderer free of a form library so the Yup generation (task 9.2), the server
 * 422→Formik merge + ARIA error summary + consent/locale selector (task 9.3), and the readiness
 * 409 / 404 page handling (task 9.4) layer on top without reshaping it. It accepts an optional
 * `errors` map (dotted key → message) so task 9.3's server-authoritative errors render through the
 * SAME `FormErrorMessage` wiring as client errors (R10a.3).
 *
 * Accessibility seam (R10a.4): beyond Chakra's `FormControl` wiring, each control carries EXPLICIT
 * `id` / `htmlFor` label association and `aria-invalid` / `aria-required` / `aria-describedby`, so
 * the accessible association holds regardless of the Chakra implementation. The axe gate itself is
 * task 9.5.
 *
 * _Requirements: R4, R4.1, R4.6, R6.3, R6b, R10a.3, R10a.4_
 */

import React from 'react';
import {
  Box,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Input,
  Select,
  VStack,
} from '@chakra-ui/react';
import type { PublicFieldConfig, PublicField, PublicFieldOption } from './applicationFieldConfig';
import {
  resolveLabel,
  resolveLocale,
  evaluateShowWhen,
  groupFieldsByFunctionalGroup,
  inputTypeFor,
  isSelectField,
  optionEntries,
} from './applicationForm.model';

export interface ApplicationFormRendererProps {
  /** The public field-config the form is driven by (from `fetchPublicFieldConfig`). */
  config: PublicFieldConfig;
  /** The applicant locale (nl/en); an absent/invalid value falls back to `nl` (R6b). */
  locale?: string;
  /** The flat form state keyed by each field's DOTTED key (the R10a.4 submit shape). */
  values: Record<string, string>;
  /** Called with the DOTTED key + new value when any control changes. */
  onChange: (dottedKey: string, value: string) => void;
  /**
   * Per-field error messages keyed by DOTTED key — the SAME keying as the submit shape, so a
   * server 422 error (mapped in by dotted `field`, task 9.3) renders through `FormErrorMessage`
   * identically to a client error (R10a.3). Optional: this renderer produces no errors itself.
   */
  errors?: Record<string, string>;
  /** Optional id prefix so multiple forms on a page keep unique control ids. Default `app-field`. */
  idPrefix?: string;
}

/**
 * Turn a dotted key into a DOM-safe id fragment (dots → dashes), namespaced by `idPrefix`.
 * Keeps the `htmlFor`/`id`/`aria-describedby` association stable + unique per field.
 */
function controlId(idPrefix: string, dottedKey: string): string {
  return `${idPrefix}-${dottedKey.replace(/\./g, '-')}`;
}

export const ApplicationFormRenderer: React.FC<ApplicationFormRendererProps> = ({
  config,
  locale,
  values,
  onChange,
  errors,
  idPrefix = 'app-field',
}) => {
  const lang = resolveLocale(locale);
  const groups = groupFieldsByFunctionalGroup(config.fields ?? []);

  return (
    <VStack spacing={6} align="stretch" data-testid="application-form">
      {groups.map((group) => {
        // A group renders only when it has at least one currently-visible field (R6.3).
        const visibleFields = group.fields.filter((f) => evaluateShowWhen(f.show_when, values));
        if (visibleFields.length === 0) return null;

        return (
          <Box key={group.key} as="fieldset" data-group={group.key}>
            <Box as="legend" data-testid={`group-heading-${group.key}`}>
              {groupHeading(config, group.key, lang)}
            </Box>
            <VStack spacing={4} align="stretch">
              {visibleFields.map((field) => (
                <FieldControl
                  key={field.key}
                  field={field}
                  lang={lang}
                  idPrefix={idPrefix}
                  value={values[field.key] ?? ''}
                  error={errors?.[field.key]}
                  onChange={onChange}
                />
              ))}
            </VStack>
          </Box>
        );
      })}
    </VStack>
  );
};

/**
 * Resolve a group section heading. The public schema carries `functional_group` as a plain string
 * (no label catalog, design §3.1), so the heading is that group value; the synthesized default
 * bucket key renders without a visible catalog name. A later task may enrich this if the schema
 * grows a group-label carry.
 */
function groupHeading(config: PublicFieldConfig, groupKey: string, lang: string): string {
  void config;
  void lang;
  return groupKey === '__default__' ? '' : groupKey;
}

interface FieldControlProps {
  field: PublicField;
  lang: string;
  idPrefix: string;
  value: string;
  error?: string;
  onChange: (dottedKey: string, value: string) => void;
}

/** One field: a Chakra `FormControl` with the widget chosen by `type`. */
const FieldControl: React.FC<FieldControlProps> = ({
  field,
  lang,
  idPrefix,
  value,
  error,
  onChange,
}) => {
  const id = controlId(idPrefix, field.key);
  const label = resolveLabel(field.label, lang, field.key);
  const required = !!field.required;
  const invalid = !!error;
  const errorId = `${id}-error`;

  return (
    <FormControl isRequired={required} isInvalid={invalid}>
      <FormLabel htmlFor={id}>{label}</FormLabel>
      {isSelectField(field) ? (
        <Select
          id={id}
          name={field.key}
          value={value}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(field.key, e.target.value)}
          aria-required={required}
          aria-invalid={invalid}
          aria-describedby={invalid ? errorId : undefined}
        >
          {/* An empty placeholder so a required enum does not silently default to its first
              option; the Yup generator (task 9.2) + the server (R4a.3) enforce the chosen value. */}
          <option value="">—</option>
          {optionEntries(field).map((opt: PublicFieldOption) => (
            <option key={opt.value} value={opt.value}>
              {resolveLabel(opt.label, lang, opt.value)}
            </option>
          ))}
        </Select>
      ) : (
        <Input
          id={id}
          name={field.key}
          type={inputTypeFor(field)}
          value={value}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(field.key, e.target.value)}
          aria-required={required}
          aria-invalid={invalid}
          aria-describedby={invalid ? errorId : undefined}
        />
      )}
      <FormErrorMessage id={errorId}>{error}</FormErrorMessage>
    </FormControl>
  );
};

export default ApplicationFormRenderer;
