/**
 * Application form-shell panel — the slug/URL + embed + consent authoring surface (spec 11 task
 * 3.2; R5.1/R5.2/R5.3, design §2.3/§3/§3.1/§6).
 *
 * The R5 panel of the Application Form Builder. It authors the FORM-level settings onto the ONE
 * SAM-owned `config#mail` row — the SAME row the Mail sub-tab owns (one authoring surface per row,
 * steering 38 rule 5):
 *
 *  - **Public URL (R5.1 / E4).** DERIVED + DISPLAYED only — `<slug>.jabaki.nl` from the tenant's
 *    landing-page slug (spec 10 D19). The slug itself stays with the Landing Page editor, so this
 *    panel never authors it. When no slug exists the panel states the form has no public address
 *    yet and points the admin to the Landing Page editor.
 *  - **Embed (R5.2).** A mode chooser (standalone / iframe); for iframe a copy-ready `<iframe>`
 *    snippet referencing the public URL plus an allowed-origin input authoring
 *    `application_embed_origins: string[]`, SEEDED with the confirmed v1 targets
 *    (`https://sites.google.com`, `https://portal.h-dcn.nl`) when none are authored yet.
 *    Standalone = no origins.
 *  - **Consent notice (R5.3).** A bilingual (nl/en) versioned editor authoring
 *    `consent_notice {version, text{nl,en}}`, BUMPING the version when the text changes.
 *
 * ## One object, one save (design §3.1 / R5.5)
 *
 * The panel does NOT own the mail write. It lifts its working `config#mail` body up to the builder
 * root via `onChange`; the builder commits it ONCE via `saveMembersMailConfig` (the Mail editor's
 * existing `PUT /members/config/mail` path). The body is SEEDED from the loaded `mail_config` so a
 * form-shell save carries every Mail-sub-tab scalar through verbatim (never clobbers them). This
 * file builds the panel + its working-body state + surfaces the mail save; task 3.4 formally wires
 * the commit into the builder's save flow. `application_scope_copy` / `mail_reply_to_default` live
 * on the Mail sub-tab (spec 11 §0.3) and are only referenced here, not re-authored.
 */
import React, { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Code,
  FormControl,
  FormHelperText,
  FormLabel,
  HStack,
  Heading,
  Text,
  Textarea,
  VStack,
} from '@chakra-ui/react';
import type { FieldConfig } from '../../../types/members';
import {
  CONFIRMED_EMBED_ORIGINS,
  type EmbedMode,
  type ShellFormValues,
  buildIframeSnippet,
  deriveApplicationFormUrl,
  embedOriginsToText,
  parseEmbedOrigins,
} from './applicationShellForm';

export interface ApplicationFormShellPanelProps {
  /** The flat working form-shell values (lifted state the builder owns). */
  values: ShellFormValues;
  /** Apply mutated values — the panel never saves; the builder commits once (R5.5 / Property 8). */
  onChange: (next: ShellFormValues) => void;
  /** The loaded `mail_config` (read-only reference — scope-copy/Reply-To note, R5.4). */
  mailConfig?: FieldConfig['mail_config'] | null;
  lang: 'nl' | 'en';
}

export const ApplicationFormShellPanel: React.FC<ApplicationFormShellPanelProps> = ({
  values,
  onChange,
  mailConfig,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // The copy-ready iframe snippet references the public URL derived from the stored slug.
  const publicUrl = useMemo(() => deriveApplicationFormUrl(values.slug), [values.slug]);
  const iframeSnippet = useMemo(() => buildIframeSnippet(publicUrl), [publicUrl]);
  const [hasCopied, setHasCopied] = useState(false);

  // Copy-to-clipboard without Chakra's `useClipboard` (its named hook does not resolve cleanly
  // under the test ESM path). Best-effort: a clipboard failure is swallowed so the button never
  // throws; the snippet is also selectable text as a fallback.
  const onCopy = () => {
    void navigator.clipboard?.writeText(iframeSnippet).catch(() => undefined);
    setHasCopied(true);
    window.setTimeout(() => setHasCopied(false), 1500);
  };

  const set = (patch: Partial<ShellFormValues>) => onChange({ ...values, ...patch });

  // Switching into iframe mode with no origins authored yet SEEDS the confirmed v1 targets
  // (R5.2b) so the admin starts from the known-good list instead of a blank textarea. An
  // existing (non-empty) list is left untouched.
  const selectEmbedMode = (mode: EmbedMode) => {
    if (mode === 'iframe' && values.embedOrigins.length === 0) {
      set({ embedMode: mode, embedOrigins: [...CONFIRMED_EMBED_ORIGINS] });
      return;
    }
    set({ embedMode: mode });
  };

  return (
    <VStack align="stretch" spacing={5} data-testid="application-form-shell-panel">
      {/* The public URL + the slug/prefix author controls + the Publish control have moved OUT of
          this panel (grouped per-group-save redesign): the public address is the builder's
          "Public address" accordion group (ApplicationAddressFields), and Publish is its own
          always-visible section (PublishSection). This panel now authors ONLY embedding + the
          consent notice, lifting values up via onChange — no slug/prefix input, no save button. */}

      {/* ------------------------------------------------------------------ */}
      {/* Embed mode (R5.2) — standalone / iframe + snippet + origins.        */}
      {/* ------------------------------------------------------------------ */}
      <Box>
        <Heading size="xs" color="gray.400" mb={2} textTransform="uppercase">
          {t('Insluiten', 'Embedding')}
        </Heading>
        {/* A single-choice chooser → true RADIOGROUP semantics (not toggle buttons): each option
            is role="radio" + aria-checked, and the group carries an accessible name (WCAG 2.2 AA).
            Earlier this used aria-pressed (toggle-button semantics) inside a radiogroup, which is
            incoherent for assistive tech — a radiogroup's children must be radios. */}
        <HStack
          spacing={3}
          data-testid="application-form-shell-embed-mode"
          role="radiogroup"
          aria-label={t('Insluitmodus', 'Embed mode')}
        >
          {(['standalone', 'iframe'] as EmbedMode[]).map((mode) => (
            <Button
              key={mode}
              size="sm"
              variant={values.embedMode === mode ? 'solid' : 'outline'}
              colorScheme="orange"
              onClick={() => selectEmbedMode(mode)}
              role="radio"
              aria-checked={values.embedMode === mode}
              data-testid={`application-form-shell-embed-${mode}`}
            >
              {mode === 'standalone'
                ? t('Zelfstandig', 'Standalone')
                : t('Insluiten (iframe)', 'Embedded (iframe)')}
            </Button>
          ))}
        </HStack>

        {values.embedMode === 'iframe' && (
          <VStack align="stretch" spacing={3} mt={4}>
            {/* Display-only snippet (copy affordance), not an editable input → labelled Text
                region, not a FormLabel bound to no control (avoids an orphan label for axe). */}
            <Box>
              <Text fontSize="sm" color="gray.300" mb={1}>
                {t('Insluitfragment', 'Embed snippet')}
              </Text>
              <Code
                display="block"
                whiteSpace="pre-wrap"
                p={2}
                data-testid="application-form-shell-iframe-snippet"
              >
                {iframeSnippet ||
                  t('Beschikbaar zodra er een publieke URL is.', 'Available once a public URL exists.')}
              </Code>
              {iframeSnippet && (
                <Button
                  size="xs"
                  mt={2}
                  onClick={onCopy}
                  data-testid="application-form-shell-copy-snippet"
                >
                  {hasCopied ? t('Gekopieerd', 'Copied') : t('Kopieer', 'Copy')}
                </Button>
              )}
            </Box>

            <FormControl>
              <FormLabel htmlFor="application-form-shell-embed-origins-input">
                {t('Toegestane oorsprong(en)', 'Allowed origin(s)')}
              </FormLabel>
              <Textarea
                id="application-form-shell-embed-origins-input"
                value={embedOriginsToText(values.embedOrigins)}
                onChange={(e) => set({ embedOrigins: parseEmbedOrigins(e.target.value) })}
                placeholder="https://www.example.org"
                data-testid="application-form-shell-embed-origins"
                rows={3}
              />
              <FormHelperText>
                {t(
                  'Eén oorsprong per regel. Vooringevuld met de bevestigde doelen (Google Sites, h-dcn-portaal) — aanpasbaar. Bepaalt de CORS / frame-ancestors die de publieke edge afdwingt.',
                  'One origin per line. Pre-filled with the confirmed targets (Google Sites, h-dcn portal) — editable. Governs the CORS / frame-ancestors the public edge enforces.',
                )}
              </FormHelperText>
            </FormControl>
          </VStack>
        )}
      </Box>

      {/* ------------------------------------------------------------------ */}
      {/* Consent notice (R5.3) — bilingual, versioned (bump on text change). */}
      {/* ------------------------------------------------------------------ */}
      <Box borderTopWidth="1px" borderColor="gray.700" pt={4}>
        <Heading size="xs" color="gray.400" mb={2} textTransform="uppercase">
          {t('Toestemmingsverklaring', 'Consent notice')}
        </Heading>
        <VStack align="stretch" spacing={3}>
          {/* Display-only: the version is derived, not an editable control, so it is a labelled
              Text region (not a FormControl/FormLabel bound to no input — that orphans the label
              for assistive tech / axe). */}
          <Box>
            <Text fontSize="sm" color="gray.300" mb={1}>
              {t('Huidige versie', 'Current version')}
            </Text>
            <Code data-testid="application-form-shell-consent-version">
              {values.consentVersion ||
                t('(nog geen versie)', '(no version yet)')}
            </Code>
            <Text fontSize="xs" color="gray.500" mt={1}>
              {t(
                'Een nieuwe versie wordt automatisch toegekend wanneer de tekst verandert.',
                'A new version is assigned automatically when the text changes.',
              )}
            </Text>
          </Box>
          {/* Explicit id/htmlFor so the textarea has a guaranteed accessible name regardless of
              Chakra's FormControl auto-id context (which did not always wire in this layout). */}
          <FormControl>
            <FormLabel htmlFor="application-form-shell-consent-nl-input">
              {t('Tekst (NL)', 'Body (NL)')}
            </FormLabel>
            <Textarea
              id="application-form-shell-consent-nl-input"
              value={values.consentTextNl}
              onChange={(e) => set({ consentTextNl: e.target.value })}
              data-testid="application-form-shell-consent-nl"
            />
          </FormControl>
          <FormControl>
            <FormLabel htmlFor="application-form-shell-consent-en-input">
              {t('Tekst (EN)', 'Body (EN)')}
            </FormLabel>
            <Textarea
              id="application-form-shell-consent-en-input"
              value={values.consentTextEn}
              onChange={(e) => set({ consentTextEn: e.target.value })}
              data-testid="application-form-shell-consent-en"
            />
          </FormControl>
          <Text fontSize="xs" color="gray.500">
            {t(
              'De verklaring wordt alleen opgeslagen met een versie én minstens één taalversie.',
              'The notice is saved only with a version AND at least one locale body.',
            )}
          </Text>
        </VStack>
      </Box>

      {/* ------------------------------------------------------------------ */}
      {/* Scope-copy / Reply-To (R5.4) — owned by the Mail sub-tab; reference. */}
      {/* ------------------------------------------------------------------ */}
      <Box borderTopWidth="1px" borderColor="gray.700" pt={4}>
        <Text fontSize="xs" color="gray.500" data-testid="application-form-shell-mail-ref">
          {t(
            'Afzender, Reply-To en scope-kopie worden beheerd op het tabblad Mail.',
            'Sender, Reply-To and scope-copy are managed on the Mail sub-tab.',
          )}
          {typeof mailConfig?.application_scope_copy === 'boolean' && (
            <>
              {' '}
              {mailConfig.application_scope_copy
                ? t('Scope-kopie staat aan.', 'Scope-copy is on.')
                : t('Scope-kopie staat uit.', 'Scope-copy is off.')}
            </>
          )}
        </Text>
      </Box>

      {/* Publish + the mail Save have moved OUT of this panel (grouped per-group-save redesign):
          Publish is the builder's own always-visible PublishSection, and the mail commit is the
          Form-settings accordion group's GroupSaveBar → handleSaveMail. This panel only lifts the
          consent + embedding values up via onChange; it owns no save button and no publish control. */}
    </VStack>
  );
};

export default ApplicationFormShellPanel;
