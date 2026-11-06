/**
 * Application live preview — an IN-BROWSER render of the public form via the shared spec-10
 * `ApplicationFormRenderer`, fed by a PURE client filter over the builder's WORKING draft (spec 12 —
 * Application Form Serving Redesign, task 5.1; R3.1/R3.2, design §C2 / D4).
 *
 * The R7/R3 panel of the Application Form Builder. The preview is NOT an iframe to the hosted form
 * and — as of spec 12 — NO LONGER a server round-trip. The retired `POST /members/application-preview`
 * endpoint (deleted in task 5.2) POSTed the working overlay to the server's `get_public_field_config`
 * filter and rendered the returned schema; spec 11 `findings.md` observed that round-trip returning an
 * empty `fields: []` for working drafts. The redesign removes it entirely:
 *
 *  1. the builder's WORKING (in-memory, UNSAVED) draft — the RESOLVED `FieldConfig` ⊕ the one
 *     `field_overlay` object — is fed to the PURE {@link buildPreviewConfig} filter
 *     (`applicationPreviewFilter.ts`), which reproduces `get_public_field_config`'s applicant-facing
 *     SELECTION entirely in the browser (visible fields, enum subset, required, format), and
 *  2. the resulting schema is fed to the shared spec-10 `ApplicationFormRenderer`.
 *
 * So the preview shows UNSAVED edits LIVE with NO save and NO network call (R3.1), and shares a SINGLE
 * rendering code path with the public form. Task 5.3 (a later wave) PINS the pure filter's parity to
 * the server `get_public_field_config` via a shared fixture, so the client filter cannot drift from
 * the authoritative server selection. The "open live form" link to the real CloudFront-hosted form is
 * the form-shell panel's concern (R3.3), not this panel.
 *
 * ## Read-only (R7.4)
 *
 * This is a render-only preview: the `ApplicationFormRenderer` is a CONTROLLED component, so it is
 * driven with empty `values` + a no-op `onChange` and no submit affordance — the admin cannot type
 * into or submit the preview. It reflects the WORKING overlay; the hosted form reflects the LAST
 * PUBLISHED artifact (a deliberate Publish shows there), which the panel states.
 *
 * ## Look-and-feel parity (spec 15 — SAM Page Look-and-Feel, task 13.1; Req 4.2/4.3/7)
 *
 * The preview now also reflects the page's LOOK-AND-FEEL. It runs the browser-side TS Layer-2
 * generator {@link renderPageStyles} — the MIRROR of the SAM-owned Python Layer-2 generator
 * `sam/shared/page_styles` — over the same seven supported attributes and the same defaults the
 * publish step uses, and injects the resulting `:root` CSS-variable block into the preview
 * container. So what the admin sees while authoring matches what publish will bake (Req 7): identical
 * values → identical styling (Req 4.3), differing values → differing styling (Req 4.2). Task 13.2
 * (a LATER wave) pins this TS Layer-2 output to the Python output via a shared parity fixture; this
 * component only consumes the mirror. An absent/empty `lookAndFeel` resolves to the SAM-owned
 * defaults, exactly as the published page would (Req 7.3).
 */
import React, { useMemo } from 'react';
import { Box, Text, VStack } from '@chakra-ui/react';
import { ApplicationFormRenderer } from '../../public/application/ApplicationFormRenderer';
import type { FieldConfig } from '../../../types/members';
import type { MembersConfigValue } from '../../../types/membersConfig';
import { buildPreviewConfig } from './applicationPreviewFilter';
import { renderPageStyles, type LookAndFeelSettings } from './pageStyles';

export interface ApplicationFormPreviewProps {
  /**
   * The RESOLVED field config (`GET /members/field-config`) — the source field set + each field's
   * served application attributes, over which the working overlay's unsaved edits take precedence.
   */
  fieldConfig: FieldConfig | null | undefined;
  /**
   * The builder's ONE working `field_overlay` object (design §3.1). Carries the UNSAVED
   * application-attribute edits; a change to it re-derives the preview in memory (no network).
   */
  overlay: MembersConfigValue;
  /** The applicant locale the preview renders labels in (nl/en). */
  lang: 'nl' | 'en';
  /**
   * The page's WORKING `Look_And_Feel_Settings` VALUES (spec 15, task 13.1). Fed to the browser-side
   * Layer-2 mirror {@link renderPageStyles} so the preview carries the SAME styling the publish step
   * bakes (Req 4.2/4.3/7). Absent/empty → SAM-owned defaults, exactly as the published page would
   * (Req 7.3). Values-only; never generated CSS.
   */
  lookAndFeel?: LookAndFeelSettings;
}

export const ApplicationFormPreview: React.FC<ApplicationFormPreviewProps> = ({
  fieldConfig,
  overlay,
  lang,
  lookAndFeel,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // Re-derive the applicant-facing schema IN-BROWSER whenever the working draft changes. Pure +
  // synchronous — the preview reflects an unsaved edit on the very next render, no round-trip (R3.1).
  const schema = useMemo(
    () => buildPreviewConfig(fieldConfig, overlay),
    [fieldConfig, overlay],
  );

  // Layer 2 (spec 15, task 13.1): generate the page styling IN-BROWSER from the working look-and-feel
  // values via the mirror of the Python generator, so the preview matches what publish bakes (Req 7).
  // An unsaved look-and-feel edit re-derives on the very next render (no round-trip), exactly like the
  // schema above. Absent/empty values resolve to the SAM-owned defaults (Req 7.3).
  const pageStyles = useMemo(
    () => renderPageStyles(lookAndFeel ?? {}),
    [lookAndFeel],
  );

  const fieldCount = schema.fields.length;

  return (
    <VStack align="stretch" spacing={3} data-testid="application-form-preview">
      <Text fontSize="xs" color="gray.500">
        {t(
          'Toont het publieke formulier met je niet-opgeslagen wijzigingen. Het gehoste formulier toont de laatst gepubliceerde versie.',
          'Shows the public form with your unsaved edits. The hosted form shows the last-published version.',
        )}
      </Text>

      {fieldCount === 0 && (
        <Text fontSize="sm" color="gray.500" data-testid="application-form-preview-empty">
          {t(
            'Nog geen velden op het formulier. Zet hierboven velden aan om ze hier te zien.',
            'No fields on the form yet. Turn fields on above to see them here.',
          )}
        </Text>
      )}

      {fieldCount > 0 && (
        <Box
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          p={4}
          bg="white"
          color="gray.800"
          // The renderer is CONTROLLED but the preview is READ-ONLY (R7.4): empty values + a no-op
          // onChange, and no submit affordance — the admin cannot type into or submit the preview.
          data-testid="application-form-preview-render"
          // The look-and-feel CSS variables (spec 15, task 13.1) are applied to THIS preview
          // container's scope, so the `--font-*` / `--spacing-*` / `--radius-*` / `--shadow-*`
          // custom properties the form consumes resolve to the values publish will bake (Req 7).
          sx={pageStyles.cssVariableMap}
          data-lookandfeel-vars={pageStyles.cssVariables}
        >
          <ApplicationFormRenderer
            config={schema}
            locale={lang}
            values={{}}
            onChange={() => { }}
            idPrefix="application-preview"
          />
        </Box>
      )}
    </VStack>
  );
};

export default ApplicationFormPreview;
