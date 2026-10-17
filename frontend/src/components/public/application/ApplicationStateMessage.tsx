/**
 * Non-form states for the PUBLIC member-application form
 * (spec Members/application-app, task 9.4).
 *
 * The public application page branches on the discriminated {@link FieldConfigResult} from
 * `fetchPublicFieldConfig` (task 9.1). Task 9.3 owns the `success` arm (the renderer + submit
 * wiring); THIS component owns the three NON-form arms so the two compose on the same page without
 * stepping on each other:
 *  - `not_available` (409, D15/R5.4) — a NEUTRAL "this organisation is not accepting applications
 *    yet" message. The server already sent only the neutral `code`; we render fixed i18n copy and
 *    NEVER surface the `code`, the tenant's mail-config, or any send-readiness detail (R5.4);
 *  - `not_found` (404, R1a.4) — a "no such application form" message, deliberately indistinguishable
 *    from an unknown endpoint so the slug/tenant allow-list cannot be probed (R1a.4);
 *  - `error` — a generic bilingual failure state.
 *
 * Bilingual by design (R5.4/R6b): these states render BEFORE the form's locale selector exists, so
 * there is no applicant locale to key off yet. We therefore show BOTH the Dutch and the English
 * copy (nl first, the default — R6b.2) so the message is understandable regardless of the visitor's
 * language, pulled from the `members` i18n namespace (`publicApplication.*`) via a fixed translator
 * per locale rather than the ambient UI language.
 *
 * _Requirements: R5.4, R1a, R1a.4, R6b_
 */

import React from 'react';
import { Alert, AlertIcon, AlertTitle, AlertDescription, Box, VStack } from '@chakra-ui/react';
import i18n from '../../../i18n';
import type { FieldConfigResult } from '../../../services/applicationApi';

/** The non-success arms this component renders — the `success` arm is task 9.3's form path. */
export type ApplicationNonFormResult = Exclude<FieldConfigResult, { status: 'success' }>;

/** Map a non-form result arm to its i18n key stem under `members:publicApplication`. */
function i18nKeyFor(status: ApplicationNonFormResult['status']): string {
  switch (status) {
    case 'not_available':
      return 'publicApplication.notAvailable';
    case 'not_found':
      return 'publicApplication.notFound';
    case 'error':
    default:
      return 'publicApplication.error';
  }
}

/** Chakra alert status per arm: `not_available` is informational/neutral, the rest are errors. */
function alertStatusFor(status: ApplicationNonFormResult['status']): 'info' | 'error' {
  return status === 'not_available' ? 'info' : 'error';
}

export interface ApplicationStateMessageProps {
  /** The non-success result arm from `fetchPublicFieldConfig` (task 9.1). */
  result: ApplicationNonFormResult;
  /** Locales to render, in order. Defaults to `['nl','en']` — nl first (R6b.2 default). */
  locales?: readonly string[];
}

/**
 * Render a neutral, bilingual message for a non-form state of the public application page.
 *
 * Reads fixed-locale translators off the shared i18n instance so the copy does NOT depend on the
 * visitor's ambient UI language — each requested locale is rendered. The `not_available` arm shows
 * ONLY the neutral i18n copy; the server's `code` is intentionally NOT rendered (no mail-config
 * leak, R5.4). The `not_found` arm is identical whether or not the slug/tenant exists (R1a.4).
 */
export const ApplicationStateMessage: React.FC<ApplicationStateMessageProps> = ({
  result,
  locales = ['nl', 'en'],
}) => {
  const keyStem = i18nKeyFor(result.status);
  const chakraStatus = alertStatusFor(result.status);

  return (
    <Box data-testid="application-state" data-state={result.status}>
      <Alert status={chakraStatus} variant="subtle" flexDirection="column" alignItems="start">
        <AlertIcon />
        <VStack align="start" spacing={4}>
          {locales.map((locale) => {
            const t = i18n.getFixedT(locale, 'members');
            return (
              <Box key={locale} lang={locale} data-locale={locale}>
                <AlertTitle>{t(`${keyStem}.title`)}</AlertTitle>
                <AlertDescription>{t(`${keyStem}.body`)}</AlertDescription>
              </Box>
            );
          })}
        </VStack>
      </Alert>
    </Box>
  );
};

export default ApplicationStateMessage;
