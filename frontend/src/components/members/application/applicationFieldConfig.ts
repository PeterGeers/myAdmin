/**
 * Back-compat RE-EXPORT shim (spec `Members/application-app`).
 *
 * Task 9.2 originally defined the public field-config type contract here. Task 9.3 CONSOLIDATED it
 * onto a single shared source — `components/public/application/applicationFieldConfig.ts` — so the
 * renderer (9.1), the Yup schema generator (9.2), and the submit wiring (9.3) all import ONE type
 * and cannot drift (R10a.2). This module now simply re-exports that single source, so any existing
 * import of these symbols from this path keeps resolving unchanged.
 *
 * New code SHOULD import directly from `components/public/application/applicationFieldConfig`.
 */

export type {
  ApplicationFormatChecker,
  ApplicationFieldFormat,
  ApplicationField,
  ApplicationFieldConfig,
  PublicField,
  PublicFieldConfig,
  PublicFieldFormat,
  PublicFieldOption,
  PublicChoiceEntry,
  PublicConsentNotice,
} from '../../public/application/applicationFieldConfig';

export {
  applicationChoiceValues,
  isEnumField,
  formKey,
} from '../../public/application/applicationFieldConfig';
