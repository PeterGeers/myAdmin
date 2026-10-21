/**
 * Application readiness panel — "can this form actually go live?" summary (spec 11 task 4.1;
 * R6.1–R6.3, design §3 table / §6 / §10).
 *
 * The R6 panel of the Application Form Builder. It SHOWS the tenant's send-readiness rather than
 * silently blocking (E5): three plain boolean states the admin can act on —
 *
 *  - **Certified sender (R6.1).** Whether the tenant has a certified sender — the spec-10 pair
 *    `mail_certified` + a non-blank `mail_domain`. Computed from the loaded `config#mail`; the
 *    panel surfaces ONLY the boolean, never WHICH mail fact is missing and never the domain (NO
 *    mail-config leak in any public-facing string, R6.2 / NFR).
 *  - **Public slug (R6.1).** Whether a resolvable public slug exists (the form has a public
 *    address). Derived from the slug the builder already loaded (read-mostly, E4).
 *  - **≥1 field on the form (R6.1).** Whether at least one field is on the public form
 *    (`application_visible`) — an authoring-completeness hint so an empty form is obvious.
 *
 * ## Reuses the public edge's signal (R6.3 / design §6)
 *
 * The certified-sender + slug pair IS the public edge's send-ready signal (spec 10
 * `application_readiness.is_send_ready`) — computed here by {@link computeReadiness} so the panel
 * and the live form never disagree. When NOT send-ready the panel gives NEUTRAL guidance (no mail
 * internals) and links to the sender-verification surface (the Mail sub-tab, R6.2/R6.3); the live
 * preview (task 4.2) reflects the SAME neutral 409 "not available" the public read returns.
 *
 * ## Pure view (no network, no save)
 *
 * The panel owns no state and makes no network call: it reads the already-loaded `fieldConfig`
 * (carrying `mail_config`), the ONE working `overlay`, and the resolved `slug` the builder holds,
 * and derives the booleans via the pure `applicationReadiness` helpers.
 */
import React, { useMemo } from 'react';
import { Badge, Box, HStack, Icon, Link, Text, VStack } from '@chakra-ui/react';
import { CheckCircleIcon, WarningIcon } from '@chakra-ui/icons';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig } from '../../../types/members';
import { computeReadiness } from './applicationReadiness';

export interface ApplicationReadinessPanelProps {
  /** The resolved field config (carries `mail_config` + the served fields), best-effort. */
  fieldConfig?: FieldConfig | null;
  /** The ONE working `field_overlay` object (the current on-the-form state for the field count). */
  overlay: MembersConfigValue | undefined;
  /** The resolved landing-page slug (null/absent = no public address yet, R6.1). */
  slug: string | null;
  lang: 'nl' | 'en';
}

/** One readiness row: a pass/fail icon + label + state badge. */
const ReadinessRow: React.FC<{
  ok: boolean;
  label: string;
  okText: string;
  notOkText: string;
  testId: string;
}> = ({ ok, label, okText, notOkText, testId }) => (
  <HStack justify="space-between" data-testid={testId} data-state={ok ? 'ok' : 'not-ok'}>
    <HStack spacing={2} minW={0}>
      <Icon
        as={ok ? CheckCircleIcon : WarningIcon}
        color={ok ? 'green.400' : 'yellow.400'}
        aria-hidden
      />
      <Text fontSize="sm" color="gray.200" noOfLines={1}>
        {label}
      </Text>
    </HStack>
    <Badge colorScheme={ok ? 'green' : 'yellow'}>{ok ? okText : notOkText}</Badge>
  </HStack>
);

export const ApplicationReadinessPanel: React.FC<ApplicationReadinessPanelProps> = ({
  fieldConfig,
  overlay,
  slug,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  const readiness = useMemo(
    () => computeReadiness(fieldConfig, overlay, slug),
    [fieldConfig, overlay, slug],
  );

  const yes = t('ja', 'yes');
  const no = t('nee', 'no');

  return (
    <VStack align="stretch" spacing={3} data-testid="application-readiness-panel">
      <VStack align="stretch" spacing={2}>
        <ReadinessRow
          ok={readiness.certifiedSender}
          label={t('Gecertificeerde afzender', 'Certified sender')}
          okText={yes}
          notOkText={no}
          testId="application-readiness-certified-sender"
        />
        <ReadinessRow
          ok={readiness.slugPresent}
          label={t('Publiek adres (slug)', 'Public address (slug)')}
          okText={yes}
          notOkText={no}
          testId="application-readiness-slug"
        />
        <ReadinessRow
          ok={readiness.hasFieldOnForm}
          label={t('Minstens één veld op het formulier', 'At least one field on the form')}
          okText={yes}
          notOkText={no}
          testId="application-readiness-field-on-form"
        />
      </VStack>

      {readiness.isSendReady ? (
        <Box
          borderTopWidth="1px"
          borderColor="gray.700"
          pt={3}
          data-testid="application-readiness-ready"
        >
          <Text fontSize="sm" color="green.300">
            {t(
              'Het formulier kan live verschijnen.',
              'The form can go live.',
            )}
          </Text>
        </Box>
      ) : (
        <Box
          borderTopWidth="1px"
          borderColor="gray.700"
          pt={3}
          data-testid="application-readiness-not-available"
        >
          {/*
            NEUTRAL guidance only (R6.2 / NFR): it states the form is not available yet and points
            at where to verify the sender — WITHOUT naming mail_domain / mail_certified or saying
            which fact is missing. A tenant's mail posture must not be probeable from this string.
          */}
          <Text fontSize="sm" color="yellow.300">
            {t(
              'Het formulier is nog niet beschikbaar.',
              'The form is not available yet.',
            )}
          </Text>
          <Text fontSize="sm" color="gray.500">
            {t('Verifieer eerst de afzender via ', 'Verify the sender first via ')}
            <Link
              color="orange.300"
              href="#members-mail"
              data-testid="application-readiness-sender-verification-link"
            >
              {t('Mail-instellingen', 'Mail settings')}
            </Link>
            .
          </Text>
        </Box>
      )}
    </VStack>
  );
};

export default ApplicationReadinessPanel;
