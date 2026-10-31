/**
 * Submit container for the PUBLIC member-application form
 * (spec `Members/application-app`, task 9.3).
 *
 * This is the page that COMPOSES the three Phase-9 seams into a working form:
 *  - the config-driven renderer (task 9.1, {@link ApplicationFormRenderer});
 *  - the config-generated Yup schema (task 9.2, {@link buildApplicationValidationSchema});
 *  - the submit wiring (this task) over the public API client (`submitApplication`).
 *
 * What task 9.3 adds on top of 9.1/9.2:
 *  - **Server-authoritative 422 mapping (R2.3/R10a.3):** on submit the form un-flattens the flat
 *    `{ dotted_key: value }` values and POSTs. A 422 `errors[]` (`{field,code,detail}`) is mapped
 *    into Formik error state BY the dotted `field` key — the SAME key the renderer draws errors
 *    from — so a server-rejected field shows through the identical `FormErrorMessage` as a client
 *    error, and the SERVER error WINS over / augments any client Yup error (R6.6).
 *  - **ARIA live-region error summary (R10a.3/R10a.5):** a `role="alert"` / `aria-live` region that
 *    announces the error count and links to each offending field — the one accessibility element
 *    Chakra's per-field wiring does not provide.
 *  - **Locale selector (R6b, default `nl`):** drives BOTH the rendered labels (via the renderer's
 *    `locale`) AND the submitted `locale`; it also sets the page `lang` (R10a.6). An absent/invalid
 *    value falls back to `nl` (R6b.2).
 *  - **Consent checkbox (R12.1):** a non-pre-ticked checkbox bound to the config's VERSIONED notice
 *    (`notice.version`, D26). Required to submit; the submit sends `consent={accepted:true,
 *    notice_version}` and the SERVER stamps version/accepted_at authoritatively (2.6).
 *
 * The readiness-gate 409 ("not available") + 404 RENDERING of the whole page is task 9.4's job;
 * this component takes an already-loaded `config` (the `success` arm of 9.1's `FieldConfigResult`)
 * and owns only the submit/consent/locale concern, so 9.4's state handling slots in around it.
 *
 * _Requirements: R1a, R2.3, R6b, R6.6, R10a.3, R10a.5, R10a.6, R12.1_
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useFormik } from 'formik';
import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormLabel,
  Heading,
  Image,
  Select,
  Text,
  VStack,
} from '@chakra-ui/react';

import { ApplicationFormRenderer } from './ApplicationFormRenderer';
import {
  resolveLabel,
  resolveLocale,
  buildInitialValues,
  SUPPORTED_LOCALES,
  DEFAULT_LOCALE,
  type SupportedLocale,
} from './applicationForm.model';
import {
  buildApplicationValidationSchema,
  validateApplication,
} from '../../members/application/applicationFormSchema';
import type { PublicFieldConfig } from './applicationFieldConfig';
import {
  submitApplication,
  fetchPublicLogo,
  type ApplicationFieldError,
  type SubmitApplicationResult,
} from '../../../services/applicationApi';

/** Localized labels for the chrome this page owns (selector/consent/summary) in nl + en (R6b). */
const UI_TEXT = {
  nl: {
    heading: 'Aanmeldformulier',
    localeLabel: 'Taal',
    consentPrefix: 'Ik ga akkoord met',
    consentNoticeFallback: 'de privacyverklaring',
    consentRequired: 'U moet akkoord gaan om door te gaan.',
    submit: 'Versturen',
    submitting: 'Bezig met versturen…',
    success: 'Bedankt. Uw aanmelding is ontvangen.',
    errorSummaryTitle: (n: number) =>
      n === 1 ? 'Er is 1 probleem gevonden:' : `Er zijn ${n} problemen gevonden:`,
    submitFailed: 'Versturen is niet gelukt. Probeer het later opnieuw.',
  },
  en: {
    heading: 'Application form',
    localeLabel: 'Language',
    consentPrefix: 'I agree to',
    consentNoticeFallback: 'the privacy notice',
    consentRequired: 'You must agree in order to continue.',
    submit: 'Submit',
    submitting: 'Submitting…',
    success: 'Thank you. Your application has been received.',
    errorSummaryTitle: (n: number) =>
      n === 1 ? '1 problem was found:' : `${n} problems were found:`,
    submitFailed: 'Submission failed. Please try again later.',
  },
} as const satisfies Record<SupportedLocale, Record<string, unknown>>;

/** The locale names shown in the selector. */
const LOCALE_NAMES: Record<SupportedLocale, string> = { nl: 'Nederlands', en: 'English' };

/** Generate a session de-dup key (R3a) — a resend with the same key UPDATES the same record. */
function newSessionKey(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  // Fallback for environments without `randomUUID` but with Web Crypto: derive the
  // random suffix from CSPRNG bytes rather than `Math.random()` (CWE-338). Every
  // browser this public form runs in ships Web Crypto, so this path is defensive.
  if (c && typeof c.getRandomValues === 'function') {
    const bytes = c.getRandomValues(new Uint8Array(16));
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `sess-${Date.now()}-${hex}`;
  }
  // Last resort (no Web Crypto at all): the key is only a submit de-dup token, not a
  // security credential, so a timestamp suffix is acceptable here.
  return `sess-${Date.now()}`;
}

/** Turn a dotted key into the DOM id the renderer assigns (so the summary links can focus it). */
function fieldAnchorId(dottedKey: string, idPrefix = 'app-field'): string {
  return `${idPrefix}-${dottedKey.replace(/\./g, '-')}`;
}

export interface ApplicationFormPageProps {
  /** The tenant slug segment (path-carried, resolved server-side). */
  tenantSlug: string;
  /** The already-loaded public field-config (the `success` arm of 9.1's FieldConfigResult). */
  config: PublicFieldConfig;
  /** Optional initial locale (e.g. from a URL param); falls back to `nl` (R6b.2). */
  initialLocale?: string;
  /** Optional pre-resolved API base URL (tests inject the MSW origin). */
  apiBaseUrl?: string;
  /**
   * Optional pre-resolved base URL for the Flask-plane branding-logo read (R5). Distinct from
   * `apiBaseUrl` (the public SAM API): the logo endpoint lives on the Flask backend
   * (`/api/public/landing/<slug>/logo`). Defaults to the app's `API_BASE_URL` when omitted;
   * tests inject an explicit origin.
   */
  logoBaseUrl?: string;
  /** Optional tenant display name used as the logo's accessible `alt` (falls back to "logo"). */
  tenantName?: string;
  /** Optional callback after a neutral 202 so a host page can swap to a thank-you view. */
  onAccepted?: () => void;
}

export const ApplicationFormPage: React.FC<ApplicationFormPageProps> = ({
  tenantSlug,
  config,
  initialLocale,
  apiBaseUrl,
  logoBaseUrl,
  tenantName,
  onAccepted,
}) => {
  const [locale, setLocale] = useState<SupportedLocale>(() => resolveLocale(initialLocale));
  // The tenant's ONE branding logo (R5): resolved from the Flask-plane branding read. `null`
  // means "no logo / not yet loaded" — the form renders NOTHING in its place (no broken image,
  // R5.3). A failed/absent read never blocks the form.
  const [logo, setLogo] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [submitFailed, setSubmitFailed] = useState(false);
  // A stable session key for the life of this mounted form (R3a de-dup).
  const [sessionKey] = useState(newSessionKey);

  // Resolve the tenant branding logo once per slug (R5). Abortable so a slug change / unmount
  // never writes stale state; a missing logo is a graceful "no logo" (the client fn never throws).
  const logoActiveRef = useRef(true);
  useEffect(() => {
    logoActiveRef.current = true;
    const controller = new AbortController();
    fetchPublicLogo(tenantSlug, { baseUrl: logoBaseUrl, signal: controller.signal }).then(
      (resolved) => {
        if (logoActiveRef.current) setLogo(resolved);
      },
    );
    return () => {
      logoActiveRef.current = false;
      controller.abort();
    };
  }, [tenantSlug, logoBaseUrl]);

  const ui = UI_TEXT[locale];
  const fields = config.fields ?? [];

  // The Yup schema GENERATED from the config (R10a.2) — keyed by dotted key, like the form state.
  const validationSchema = useMemo(() => buildApplicationValidationSchema(fields), [fields]);

  const formik = useFormik<Record<string, string>>({
    initialValues: buildInitialValues(fields),
    // Use `validate` (not `validationSchema`) so client Yup errors come back keyed by the PLAIN
    // dotted key (R10a.3) — the SAME key the renderer draws errors from and the server 422 uses,
    // so client + server errors collide on one key. (A dotted-keyed Yup schema otherwise reports
    // escaped `["a.b"]` paths.)
    validate: (values) => validateApplication(validationSchema, values),
    // The server is authoritative; run the client gate on submit, not on every keystroke.
    validateOnChange: false,
    validateOnBlur: false,
    onSubmit: async (values, helpers) => {
      setSubmitFailed(false);

      // Consent is required to submit (R12.1) — a non-pre-ticked checkbox.
      if (!consent) {
        setConsentError(ui.consentRequired);
        helpers.setSubmitting(false);
        return;
      }
      setConsentError(null);

      const result: SubmitApplicationResult = await submitApplication(
        tenantSlug,
        {
          session_key: sessionKey,
          locale,
          consent: { accepted: true, notice_version: config.notice?.version },
          fields: values,
        },
        { baseUrl: apiBaseUrl },
      );

      if (result.status === 'accepted') {
        setAccepted(true);
        onAccepted?.();
      } else if (result.status === 'validation_error') {
        // Map the server's authoritative 422 errors into Formik BY the dotted field key (R10a.3).
        // The server WINS: its message overwrites/augments any client Yup error on the same key.
        helpers.setErrors(mapServerErrors(result.errors, locale));
      } else if (result.status === 'not_available' || result.status === 'not_found') {
        // Rendering these page-level arms is task 9.4; surface the generic failure for now so the
        // applicant is never left without feedback.
        setSubmitFailed(true);
      } else {
        setSubmitFailed(true);
      }
      helpers.setSubmitting(false);
    },
  });

  if (accepted) {
    return (
      <Box data-testid="application-accepted" role="status">
        <Text>{ui.success}</Text>
      </Box>
    );
  }

  // The current error set (client Yup + merged server errors), keyed by dotted key — the SAME
  // keying the renderer + the summary consume.
  const errors = formik.errors as Record<string, string>;
  const errorEntries = Object.entries(errors).filter(([, msg]) => !!msg);
  const showSummary = errorEntries.length > 0 || !!consentError;

  const noticeLabel = resolveLabel(config.notice?.text, locale, ui.consentNoticeFallback);

  return (
    <Box as="main" lang={locale} data-testid="application-form-page">
      {/* Tenant branding logo (R5): constrained + centered ABOVE the heading when resolved;
          render NOTHING when absent so there is no broken-image placeholder (R5.3). Works
          whether or not the tenant has a published landing page. */}
      {logo && (
        <Image
          src={logo}
          alt={tenantName ?? 'logo'}
          data-testid="application-logo"
          maxH={{ base: '48px', md: '72px' }}
          width="auto"
          mx="auto"
          mb={4}
        />
      )}

      <Heading as="h1">{ui.heading}</Heading>

      {/* Locale selector — drives labels + submitted locale + page lang (R6b/R10a.6). */}
      <FormControl>
        <FormLabel htmlFor="application-locale">{ui.localeLabel}</FormLabel>
        <Select
          id="application-locale"
          data-testid="locale-select"
          value={locale}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
            setLocale(resolveLocale(e.target.value))
          }
        >
          {SUPPORTED_LOCALES.map((loc) => (
            <option key={loc} value={loc}>
              {LOCALE_NAMES[loc]}
            </option>
          ))}
        </Select>
      </FormControl>

      {/* ARIA live-region error summary (R10a.3/R10a.5): announces the count + links each field. */}
      <Box
        role="alert"
        aria-live="assertive"
        data-testid="error-summary"
        hidden={!showSummary}
      >
        {showSummary && (
          <>
            <Text data-testid="error-summary-title">
              {ui.errorSummaryTitle(errorEntries.length + (consentError ? 1 : 0))}
            </Text>
            <Box as="ul">
              {errorEntries.map(([key, msg]) => (
                <Box as="li" key={key}>
                  <a href={`#${fieldAnchorId(key)}`}>{msg}</a>
                </Box>
              ))}
              {consentError && (
                <Box as="li" key="__consent__">
                  <a href="#application-consent">{consentError}</a>
                </Box>
              )}
            </Box>
          </>
        )}
      </Box>

      <form onSubmit={formik.handleSubmit} noValidate>
        <VStack spacing={6} align="stretch">
          <ApplicationFormRenderer
            config={config}
            locale={locale}
            values={formik.values}
            errors={errors}
            onChange={(dottedKey, value) => {
              // Update the FLAT value map directly. We must NOT use Formik's `setFieldValue` /
              // `setFieldError` here: those apply lodash `setIn` dot-path semantics, which would
              // treat `personal.first_name` as a NESTED path and write `values.personal.first_name`
              // — but the renderer (9.1) keeps a FLAT map keyed by the dotted key. `setValues` /
              // `setErrors` write the object wholesale, preserving the flat dotted keys.
              formik.setValues({ ...formik.values, [dottedKey]: value });
              // A server/client error on this key is no longer authoritative once the applicant
              // edits the field — clear it (flat) so the stale message disappears.
              if (errors[dottedKey]) {
                const next = { ...errors };
                delete next[dottedKey];
                formik.setErrors(next);
              }
            }}
          />

          {/* Consent checkbox (R12.1) — non-pre-ticked, bound to the versioned notice (D26). */}
          <FormControl isInvalid={!!consentError}>
            <Checkbox
              id="application-consent"
              data-testid="consent-checkbox"
              isChecked={consent}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                setConsent(e.target.checked);
                if (e.target.checked) setConsentError(null);
              }}
            >
              {ui.consentPrefix} {noticeLabel}
            </Checkbox>
            {consentError && (
              <Text role="alert" data-testid="consent-error">
                {consentError}
              </Text>
            )}
          </FormControl>

          {submitFailed && (
            <Text role="alert" data-testid="submit-failed">
              {ui.submitFailed}
            </Text>
          )}

          <Button
            type="submit"
            data-testid="submit-button"
            isLoading={formik.isSubmitting}
            loadingText={ui.submitting}
          >
            {ui.submit}
          </Button>
        </VStack>
      </form>
    </Box>
  );
};

/**
 * Map the server's 422 `errors[]` into a Formik error object keyed by the dotted `field` (R10a.3).
 * The server is authoritative: its `detail` (or `code` when no detail) becomes the field message,
 * OVERWRITING any client Yup error already on that key. Multiple errors on one field join into a
 * single message so the field surface shows them all.
 */
function mapServerErrors(
  serverErrors: ApplicationFieldError[],
  locale: SupportedLocale,
): Record<string, string> {
  void locale;
  const mapped: Record<string, string> = {};
  for (const e of serverErrors) {
    const message = (e.detail && e.detail.trim()) || e.code || 'Invalid value';
    mapped[e.field] = mapped[e.field] ? `${mapped[e.field]} ${message}` : message;
  }
  return mapped;
}

export default ApplicationFormPage;
