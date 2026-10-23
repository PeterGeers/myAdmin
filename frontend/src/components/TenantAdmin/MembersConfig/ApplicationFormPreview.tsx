/**
 * Application live preview — an IN-APP render of the public form via the shared spec-10
 * `ApplicationFormRenderer`, fed by the server-side preview endpoint (spec 11 task 4.2;
 * R7.1/R7.2/R7.4, design §4/§6/§9 S1·S2/§10).
 *
 * The R7 panel of the Application Form Builder. The preview is NOT an iframe to the hosted form and
 * NOT a client-side re-implementation of the field filter — both would reflect only the LAST-SAVED
 * config or risk drifting from the server. Instead (design §9 S1/S2, the resolved decision):
 *
 *  1. the builder's WORKING (in-memory, UNSAVED) `field_overlay` is DEBOUNCED and
 *  2. POSTed to `POST /members/application-preview` (`members:admin`), which runs the EXACT server
 *     `get_public_field_config` filter over it and returns the applicant-facing schema, and
 *  3. that returned schema is fed to the shared spec-10 `ApplicationFormRenderer`.
 *
 * So the preview shows UNSAVED edits live (R7.1), shares a SINGLE rendering code path with the
 * public form AND a SINGLE filtering authority with the server (no client mirror to drift —
 * correctness property 4 / §6). The "open live form" link to the real CloudFront-hosted form is the
 * form-shell panel's concern (R7.3), not this panel.
 *
 * ## Read-only (R7.4)
 *
 * This is a render-only preview: the `ApplicationFormRenderer` is a CONTROLLED component, so it is
 * driven with empty `values` + a no-op `onChange` and no submit affordance — the admin cannot type
 * into or submit the preview. It reflects the WORKING overlay; the hosted form reflects the LAST
 * SAVED config (a save shows there on its next load), which the panel states.
 *
 * ## Debounce (R7.1 / §9 S2)
 *
 * A change to the working overlay debounces the preview POST (default {@link PREVIEW_DEBOUNCE_MS})
 * so rapid toggles collapse into one request; the latest overlay always wins (a newer change
 * cancels the pending timer). The panel keeps the LAST good schema visible while a new request is
 * in flight so the preview does not flicker to empty on every keystroke.
 *
 * ## Not-send-ready + errors
 *
 * The preview endpoint deliberately BYPASSES the public send-ready gate, so the schema renders even
 * before the sender is certified (R6.2) — the readiness panel carries the "not available" state,
 * not this preview. A deliberate authoring error (a 400 on a malformed overlay — e.g. an enum
 * subset ⊄ the field's choices) is surfaced as a neutral inline message rather than a blank form.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Spinner, Text, VStack } from '@chakra-ui/react';
import { ApplicationFormRenderer } from '../../public/application/ApplicationFormRenderer';
import type { PublicFieldConfig } from '../../public/application/applicationFieldConfig';
import { previewMembersApplicationConfig } from '../../../services/membersConfigService';
import type { MembersConfigValue } from '../../../types/membersConfig';

/** Default debounce (ms) before the working overlay is POSTed to the preview endpoint (R7.1). */
export const PREVIEW_DEBOUNCE_MS = 400;

export interface ApplicationFormPreviewProps {
  /**
   * The builder's ONE working `field_overlay` object (design §3.1). A change to it is debounced and
   * POSTed to `POST /members/application-preview`; the returned schema drives the renderer so the
   * preview reflects UNSAVED edits live (R7.1).
   */
  overlay: MembersConfigValue;
  /** The applicant locale the preview renders labels in (nl/en). */
  lang: 'nl' | 'en';
  /** Debounce window override (ms) — tests pass `0` for a deterministic, immediate POST. */
  debounceMs?: number;
}

export const ApplicationFormPreview: React.FC<ApplicationFormPreviewProps> = ({
  overlay,
  lang,
  debounceMs = PREVIEW_DEBOUNCE_MS,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // The last schema the server returned for a working overlay — kept visible across a new in-flight
  // request so the preview does not flicker to empty while the next POST resolves.
  const [schema, setSchema] = useState<PublicFieldConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Serialize the overlay so the debounce effect re-runs on a VALUE change (not a new object
  // identity each render) — the builder replaces the overlay object on every edit.
  const overlayKey = useMemo(() => JSON.stringify(overlay ?? {}), [overlay]);

  // A monotonically increasing request id so a stale (superseded) response can never overwrite a
  // newer one — the LATEST working overlay always wins (debounce + out-of-order guard).
  const reqSeq = useRef(0);

  useEffect(() => {
    const seq = ++reqSeq.current;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const next = await previewMembersApplicationConfig(overlay ?? {});
        if (seq !== reqSeq.current) return; // a newer request superseded this one — drop it.
        setSchema(next);
      } catch (e) {
        if (seq !== reqSeq.current) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (seq === reqSeq.current) setLoading(false);
      }
    };

    if (debounceMs <= 0) {
      run();
      return;
    }
    const timer = setTimeout(run, debounceMs);
    return () => clearTimeout(timer);
    // overlayKey captures the overlay value; debounceMs is stable per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, debounceMs]);

  const fieldCount = schema?.fields?.length ?? 0;

  return (
    <VStack align="stretch" spacing={3} data-testid="application-form-preview">
      <Text fontSize="xs" color="gray.500">
        {t(
          'Toont het publieke formulier met je niet-opgeslagen wijzigingen. Het gehoste formulier toont de laatst opgeslagen versie.',
          'Shows the public form with your unsaved edits. The hosted form shows the last-saved version.',
        )}
      </Text>

      {loading && schema === null && (
        <Box data-testid="application-form-preview-loading">
          <Spinner size="sm" color="orange.400" />
          <Text display="inline" ml={2} fontSize="sm" color="gray.400">
            {t('Voorbeeld laden…', 'Loading preview…')}
          </Text>
        </Box>
      )}

      {error && (
        <Text fontSize="sm" color="red.300" data-testid="application-form-preview-error">
          {t(
            'Het voorbeeld kon niet worden bijgewerkt. Controleer je veldinstellingen.',
            'The preview could not be updated. Check your field settings.',
          )}
        </Text>
      )}

      {schema && fieldCount === 0 && !loading && (
        <Text fontSize="sm" color="gray.500" data-testid="application-form-preview-empty">
          {t(
            'Nog geen velden op het formulier. Zet hierboven velden aan om ze hier te zien.',
            'No fields on the form yet. Turn fields on above to see them here.',
          )}
        </Text>
      )}

      {schema && fieldCount > 0 && (
        <Box
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          p={4}
          bg="white"
          color="gray.800"
          // The renderer is CONTROLLED but the preview is READ-ONLY (R7.4): empty values + a no-op
          // onChange, and no submit affordance — the admin cannot type into or submit the preview.
          // (No `aria-readonly` here: it is not a supported ARIA attribute on a generic container;
          // the read-only posture is structural — no submit control, no committed input.)
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
