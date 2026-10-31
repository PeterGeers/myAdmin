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
  SimpleGrid,
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
  isWideField,
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
  const groups = groupFieldsByFunctionalGroup(config.fields ?? [], config.functional_groups);

  return (
    <VStack spacing={6} align="stretch" data-testid="application-form">
      {groups.map((group) => {
        // A group renders only when it has at least one currently-visible field (R6.3).
        const visibleFields = group.fields.filter((f) => evaluateShowWhen(f.show_when, values));
        if (visibleFields.length === 0) return null;

        // Prefer the AUTHORED group label from the catalog (spec 13 R2), resolved for the
        // applicant locale; fall back to the humanized key when the config carries no label.
        const heading = group.label
          ? resolveLabel(group.label, lang, humanizeGroupKey(group.key))
          : groupHeading(config, group.key, lang);

        return (
          <Box key={group.key} as="fieldset" data-group={group.key}>
            {/* The synthesized `__default__` bucket carries no authored group name, so it renders
                WITHOUT a legend rather than an empty-legend artifact (R1.2). Every named group
                gets a styled, readable section heading so the form reads as sections (R1.2). */}
            {heading ? (
              <Box
                as="legend"
                data-testid={`group-heading-${group.key}`}
                fontSize="lg"
                fontWeight="semibold"
                mb={3}
              >
                {heading}
              </Box>
            ) : null}
            {/* Multi-column group layout (R4.2): a single column on a narrow (mobile) viewport
                (`base`), at least two columns on `md`+ (laptop/desktop). `SimpleGrid` lays out in
                DOM order, so the logical reading + tab order stays the config-resolved
                `(group order → field (order,key))` sequence and the error-summary anchors keep
                focusing the right control (R4.4 / HC2). Driven purely by Chakra's responsive
                `columns` object — no viewport sniffing (R4.3). */}
            <SimpleGrid
              columns={{ base: 1, md: 2 }}
              spacing={4}
              data-testid={`group-grid-${group.key}`}
            >
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
            </SimpleGrid>
          </Box>
        );
      })}
    </VStack>
  );
};

/**
 * Resolve a group section heading (R1.2). The public schema carries `functional_group` as a plain
 * string (no label catalog, design §3.1), so there is no label to look up — the heading is a
 * PRESENTABLE form of the group KEY (underscores/dots/hyphens → spaces, each word capitalized),
 * e.g. `basic_info` → "Basic Info". The synthesized `__default__` bucket (fields with no
 * `functional_group`) has no authored name, so it returns '' and the renderer omits its legend
 * entirely rather than drawing an empty-legend artifact (design R1: the lighter choice). A later
 * task may enrich this if the schema grows a group-label carry.
 */
function groupHeading(config: PublicFieldConfig, groupKey: string, lang: string): string {
  void config;
  void lang;
  if (groupKey === '__default__') return '';
  return humanizeGroupKey(groupKey);
}

/**
 * Turn a machine group key into a presentable heading: split on word separators (`_`, `-`, `.`,
 * whitespace), drop empties, and Title-Case each token. Stays generic over whatever the config
 * lists (HC1) — no per-group hard-coding. An already-presentable key (e.g. `Address`) is left
 * sensible.
 */
function humanizeGroupKey(groupKey: string): string {
  const words = groupKey
    .split(/[\s._-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1));
  // Fall back to the raw key if it had no splittable content (never render blank for a named group).
  return words.length > 0 ? words.join(' ') : groupKey;
}

/**
 * Shared control styling for the PUBLIC application form (R3). Applied UNIFORMLY to BOTH the text
 * `<Input>` and the enum `<Select>` so the two read at the SAME visual weight — a neutral `outline`
 * variant with a grey resting border rather than the app's saturated orange accent (R3.1/R3.2).
 *
 * The accent is RESERVED FOR FOCUS: `focusBorderColor` recolours the border AND draws Chakra's
 * `boxShadow` focus ring on keyboard/mouse focus, so the control stays clearly discoverable and
 * WCAG-adequate (R3.3 / HC2) while at rest it is quiet. `<Select>` keeps its default chevron
 * affordance (we do NOT override its `icon`), so it still reads as a dropdown (R3.1).
 *
 * This lives at the renderer boundary and is spread onto the two controls only, so the softening is
 * SCOPED to the public application form — the rest of the app's orange theme is untouched (design
 * R3: the renderer/page is the boundary, no global theme change).
 */
const PUBLIC_FORM_CONTROL_STYLE = {
  // Spec 13 R3: the public form sits on a WHITE page, so every control reads QUIET — a light
  // neutral border on a white fill with dark text, at the SAME visual weight for inputs and
  // selects. The app's saturated orange accent is RESERVED FOR FOCUS only (`focusBorderColor`
  // recolours the border + draws Chakra's focus ring on focus), so the form matches the page
  // instead of carrying the admin app's heavy orange. The chevron affordance on the select is
  // left as Chakra's default. Scoped here at the renderer boundary — the global app theme is
  // untouched.
  variant: 'outline',
  bg: 'white',
  color: 'gray.800',
  borderColor: 'gray.300',
  _hover: { borderColor: 'gray.400' },
  focusBorderColor: 'orange.400',
} as const;

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
  const wide = isWideField(field);

  return (
    <FormControl
      isRequired={required}
      isInvalid={invalid}
      // An intrinsically-wide field (e.g. a notes/textarea) spans the FULL grid row rather than a
      // single column, so its control is not squeezed into one of the responsive columns (R4.3).
      // `1 / -1` spans from the first to the last grid line on `md`+; on `base` the grid is a
      // single column anyway, so the span is a no-op there.
      gridColumn={wide ? { md: '1 / -1' } : undefined}
      // Responsive label placement (R4.1): label ABOVE the control on a narrow (mobile)
      // viewport, label BESIDE the control on `md`+ (laptop/desktop). Driven purely by Chakra's
      // responsive `display` — no viewport sniffing (R4.3). The `htmlFor`/`id` association is on
      // the `FormLabel`/control pair and is unaffected by this layout change (HC2).
      display={{ base: 'block', md: 'flex' }}
      alignItems={{ md: 'center' }}
    >
      <FormLabel
        htmlFor={id}
        // On `md`+ the label takes a fixed share of the row so the controls line up in a column;
        // on `base` it falls back to the full-width, label-above layout. `mb` is reset to 0 beside
        // the control (Chakra's default bottom margin is only wanted in the stacked layout).
        flexShrink={0}
        width={{ base: 'auto', md: '12rem' }}
        mb={{ base: 2, md: 0 }}
      >
        {label}
      </FormLabel>
      <Box flex={{ md: 1 }} width={{ base: '100%', md: 'auto' }}>
        {isSelectField(field) ? (
          <Select
            id={id}
            name={field.key}
            value={value}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(field.key, e.target.value)}
            aria-required={required}
            aria-invalid={invalid}
            aria-describedby={invalid ? errorId : undefined}
            {...PUBLIC_FORM_CONTROL_STYLE}
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
            {...PUBLIC_FORM_CONTROL_STYLE}
          />
        )}
        <FormErrorMessage id={errorId}>{error}</FormErrorMessage>
      </Box>
    </FormControl>
  );
};

export default ApplicationFormRenderer;
