/**
 * PublishSection — the deliberate go-live control for the Application Form Builder
 * (grouped per-group-save redesign).
 *
 * Extracted out of `ApplicationFormShellPanel` so that panel becomes a pure consent/embed
 * value-lifter. Publish is DISTINCT from Save (save ≠ publish, R5.1a): a per-group Save commits a
 * draft to `config#fields`/`config#mail` but NEVER republishes the live form; only THIS control
 * calls `POST /members/application-form/publish`. It is readiness-gated (slug + certified sender +
 * ≥1 on-form field, R5.4) — disabled with a clear per-precondition reason when not ready, so an
 * unready form never emits a broken live artifact. When the draft has saved-but-unpublished
 * changes, an "unpublished changes" hint surfaces the save/publish distinction.
 */
import React from 'react';
import { Box, Button, HStack, Heading, Text, VStack } from '@chakra-ui/react';
import type { ReadinessState } from './applicationReadiness';

export interface PublishSectionProps {
  /** Readiness facts (reused from `computeReadiness`); Publish is gated on all three. */
  readiness?: ReadinessState;
  /** Fire the explicit publish (`POST /members/application-form/publish`). */
  onPublish: () => void;
  /** Whether a publish is in flight. */
  publishing?: boolean;
  /** Whether the draft has saved-but-unpublished changes (surfaces the save ≠ publish hint). */
  hasUnpublishedChanges?: boolean;
  /** Whether the form has ever been published (controls first-publish vs re-publish copy). */
  everPublished?: boolean;
  lang: 'nl' | 'en';
}

export const PublishSection: React.FC<PublishSectionProps> = ({
  readiness,
  onPublish,
  publishing = false,
  hasUnpublishedChanges = false,
  everPublished = false,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // Readiness gate (R5.4): slug + certified sender + ≥1 on-form field — the SAME three facts the
  // readiness panel computes (reused, not re-derived). Disabled + explained until all three hold.
  const canPublish = Boolean(
    readiness &&
      readiness.slugPresent &&
      readiness.certifiedSender &&
      readiness.hasFieldOnForm,
  );

  return (
    <Box data-testid="application-form-publish">
      <Heading size="xs" color="gray.400" mb={2} textTransform="uppercase">
        {t('Publiceren', 'Publish')}
      </Heading>
      <Text fontSize="sm" color="gray.500" mb={3}>
        {t(
          'Publiceren is een aparte, bewuste stap: opslaan wijzigt het live formulier niet. Het live formulier verandert pas wanneer je hier publiceert.',
          'Publishing is a separate, deliberate step: saving does not change the live form. The live form only changes when you publish here.',
        )}
      </Text>

      {readiness && !canPublish && (
        <VStack align="stretch" spacing={1} mb={3} data-testid="application-form-publish-blocked">
          <Text fontSize="sm" color="yellow.300">
            {t('Nog niet klaar om te publiceren:', 'Not ready to publish yet:')}
          </Text>
          {!readiness.slugPresent && (
            <Text fontSize="sm" color="gray.400" data-testid="application-form-publish-need-slug">
              {t('\u2022 Stel een formulier-slug in (publiek adres).', '\u2022 Set a form slug (public address).')}
            </Text>
          )}
          {!readiness.certifiedSender && (
            <Text fontSize="sm" color="gray.400" data-testid="application-form-publish-need-sender">
              {t('\u2022 Verifieer een gecertificeerde afzender.', '\u2022 Verify a certified sender.')}
            </Text>
          )}
          {!readiness.hasFieldOnForm && (
            <Text fontSize="sm" color="gray.400" data-testid="application-form-publish-need-field">
              {t('\u2022 Zet minstens \u00e9\u00e9n veld op het formulier.', '\u2022 Put at least one field on the form.')}
            </Text>
          )}
        </VStack>
      )}

      <HStack justify="flex-end">
        {canPublish && hasUnpublishedChanges && (
          <Text
            fontSize="sm"
            color="yellow.300"
            mr="auto"
            data-testid="application-form-publish-unpublished-changes"
          >
            {t('Concept heeft niet-gepubliceerde wijzigingen', 'Draft has unpublished changes')}
          </Text>
        )}
        <Button
          colorScheme="orange"
          onClick={onPublish}
          isLoading={publishing}
          isDisabled={!canPublish}
          loadingText={t('Publiceren…', 'Publishing…')}
          data-testid="application-form-publish-button"
        >
          {everPublished ? t('Opnieuw publiceren', 'Republish') : t('Publiceren', 'Publish')}
        </Button>
      </HStack>
    </Box>
  );
};

export default PublishSection;
