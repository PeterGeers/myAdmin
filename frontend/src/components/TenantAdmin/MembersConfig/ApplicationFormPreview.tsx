/**
 * Application live preview — an `<iframe>` to the CloudFront-hosted public form (spec 11 task 4.2;
 * R7.1–R7.4, design §4/§6/§9 S1·S2/§10).
 *
 * The R7 panel of the Application Form Builder. The preview is NOT a client-side re-render of the
 * filtered schema — it is an `<iframe>` pointed at the REAL CloudFront-hosted public form URL
 * (derived `https://<slug>.jabaki.nl`, the same host the public form answers on). Because the
 * preview IS the live form, the preview and the live render are the SAME code path by construction
 * — authoring can never drift from what an applicant sees (design Property 4 / §6).
 *
 * ## What the hosted form shows (R7.1–R7.3)
 *
 * The preview just shows whatever the hosted form renders for this tenant:
 *  - a send-ready tenant → the filtered public form (R7.1);
 *  - a NOT-send-ready tenant → the hosted form's OWN neutral 409 "not available" state (R7.3). The
 *    builder does NOT re-implement that filter/guard client-side; it relies on the hosted form.
 *
 * ## Last-saved state + "save to update preview" (R7.4 / §9 S2)
 *
 * The iframe reflects the LAST-SAVED `config#fields` / `config#mail` (the hosted form reads the
 * live config). After a save the builder bumps a `reloadToken`; that token drives the iframe `key`
 * (and a cache-busting query param) so the iframe remounts and re-fetches the hosted form — the
 * "save to update preview" affordance. A manual "Update preview" button also bumps a local token so
 * the admin can force a reload without a save.
 *
 * ## No public URL yet (R5.1 / E4)
 *
 * When the tenant has no slug (no public address), there is nothing to embed — the panel shows a
 * neutral "no preview available yet" placeholder pointing at the Landing Page editor (where the
 * slug is set), mirroring the form-shell panel's "no address yet" posture.
 */
import React, { useMemo, useState } from 'react';
import { Box, Button, HStack, Link, Text, VStack } from '@chakra-ui/react';
import { derivePublicUrl } from './applicationShellForm';

export interface ApplicationFormPreviewProps {
  /** The resolved landing-page slug (null/absent = no public address yet, R5.1). */
  slug: string | null;
  /**
   * A reload token the builder bumps after each successful save (R7.4). Changing it remounts the
   * iframe (via `key`) so the preview re-fetches the hosted form and reflects the last-saved state.
   */
  reloadToken?: number;
  lang: 'nl' | 'en';
}

export const ApplicationFormPreview: React.FC<ApplicationFormPreviewProps> = ({
  slug,
  reloadToken = 0,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // A local token lets the admin force a reload WITHOUT a save ("Update preview"). The effective
  // token combines the builder's save-driven token with this manual one — either bump reloads.
  const [manualToken, setManualToken] = useState(0);
  const effectiveToken = reloadToken + manualToken;

  const publicUrl = useMemo(() => derivePublicUrl(slug), [slug]);

  // Cache-busting src: appends the reload token so a remount actually re-fetches the hosted form
  // (the `key` remount is the primary mechanism; the query param guards against an aggressive
  // iframe/browser cache). The hosted form ignores the extra query param.
  const iframeSrc = useMemo(() => {
    if (!publicUrl) return null;
    const sep = publicUrl.includes('?') ? '&' : '?';
    return `${publicUrl}${sep}preview=${effectiveToken}`;
  }, [publicUrl, effectiveToken]);

  // No slug → nothing to embed: a neutral placeholder pointing at the Landing Page editor (R5.1).
  if (!publicUrl || !iframeSrc) {
    return (
      <Box data-testid="application-form-preview-no-url">
        <Text fontSize="sm" color="yellow.300">
          {t(
            'Nog geen voorbeeld beschikbaar.',
            'No preview available yet.',
          )}
        </Text>
        <Text fontSize="sm" color="gray.500">
          {t(
            'Het formulier heeft nog geen publiek adres. Stel eerst een slug in via de ',
            'The form has no public address yet. Set a slug first in the ',
          )}
          <Link
            color="orange.300"
            href="#landing-page"
            data-testid="application-form-preview-landing-link"
          >
            {t('Landingspagina-editor', 'Landing Page editor')}
          </Link>
          .
        </Text>
      </Box>
    );
  }

  return (
    <VStack align="stretch" spacing={3} data-testid="application-form-preview">
      <HStack justify="space-between">
        <Text fontSize="xs" color="gray.500">
          {t(
            'Toont de laatst opgeslagen versie van het publieke formulier. Sla op om bij te werken.',
            'Shows the last-saved version of the public form. Save to update.',
          )}
        </Text>
        <Button
          size="xs"
          variant="outline"
          onClick={() => setManualToken((n) => n + 1)}
          data-testid="application-form-preview-reload"
        >
          {t('Voorbeeld bijwerken', 'Update preview')}
        </Button>
      </HStack>
      <Box
        borderWidth="1px"
        borderColor="gray.700"
        borderRadius="md"
        overflow="hidden"
        bg="white"
      >
        <iframe
          // The token drives the `key` so a save (or a manual reload) REMOUNTS the iframe, forcing
          // a fresh fetch of the hosted form — the "save to update preview" affordance (R7.4).
          key={effectiveToken}
          src={iframeSrc}
          title={t('Voorbeeld aanmeldformulier', 'Application form preview')}
          data-testid="application-form-preview-iframe"
          style={{ width: '100%', height: 900, border: 0 }}
          loading="lazy"
        />
      </Box>
    </VStack>
  );
};

export default ApplicationFormPreview;
