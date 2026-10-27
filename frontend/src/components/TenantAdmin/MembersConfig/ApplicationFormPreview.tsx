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
 */
import React, { useMemo } from 'react';
import { Box, Text, VStack } from '@chakra-ui/react';
import { ApplicationFormRenderer } from '../../public/application/ApplicationFormRenderer';
import type { FieldConfig, MembershipType } from '../../../types/members';
import type { MembersConfigValue } from '../../../types/membersConfig';
import { buildPreviewConfig } from './applicationPreviewFilter';

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
  /**
   * The tenant's LIVE membership-type catalog — the subset SOURCE for the `membership_type`
   * reference field (R4.1), so the preview offers the real catalog values, not static choices.
   */
  membershipTypeCatalog?: MembershipType[] | null;
  /** The applicant locale the preview renders labels in (nl/en). */
  lang: 'nl' | 'en';
}

export const ApplicationFormPreview: React.FC<ApplicationFormPreviewProps> = ({
  fieldConfig,
  overlay,
  membershipTypeCatalog,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // Re-derive the applicant-facing schema IN-BROWSER whenever the working draft changes. Pure +
  // synchronous — the preview reflects an unsaved edit on the very next render, no round-trip (R3.1).
  const schema = useMemo(
    () => buildPreviewConfig(fieldConfig, overlay, membershipTypeCatalog),
    [fieldConfig, overlay, membershipTypeCatalog],
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
