/**
 * ApplicationAddressFields — the Public-address group's prefix + slug inputs (grouped
 * per-group-save redesign, Task 5).
 *
 * A pure CONTROLLED component: it owns no state and no network call. The two inputs bind to the
 * builder-owned deferred drafts (`prefixDraft` / `slugDraft`) and lift edits up via
 * `onPrefixChange` / `onSlugChange`. NOTHING is written here — the Public-address group's single
 * `GroupSaveBar` Save commits both (prefix first, then slug) via `handleSaveAddress`. This replaces
 * the two immediate-write Save buttons that previously lived inside `ApplicationFormShellPanel`.
 *
 * The prefix is rendered ABOVE the slug because a slug must sit under the tenant's prefix (SEC-4
 * prefix-ownership). The derived public URL (display-only) is shown when a slug is stored.
 */
import React from 'react';
import {
  Box,
  Code,
  FormControl,
  FormHelperText,
  FormLabel,
  Input,
  Link,
  Text,
} from '@chakra-ui/react';

export interface ApplicationAddressFieldsProps {
  /** The deferred prefix draft (builder-owned). */
  prefixDraft: string;
  /** The deferred slug draft (builder-owned). */
  slugDraft: string;
  /** Lift a prefix edit up to the builder (no write). */
  onPrefixChange: (value: string) => void;
  /** Lift a slug edit up to the builder (no write). */
  onSlugChange: (value: string) => void;
  /** The public URL derived from the STORED slug (display-only); null when no slug is stored yet. */
  publicUrl: string | null;
  /** Whether an address commit is in flight (disables the inputs). */
  busy?: boolean;
  lang: 'nl' | 'en';
}

export const ApplicationAddressFields: React.FC<ApplicationAddressFieldsProps> = ({
  prefixDraft,
  slugDraft,
  onPrefixChange,
  onSlugChange,
  publicUrl,
  busy = false,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  return (
    <Box data-testid="application-form-address-fields">
      {/* Public URL (derived from the STORED slug) — display-only. */}
      {publicUrl ? (
        <FormControl mb={4}>
          <FormLabel>{t('Publieke URL', 'Public URL')}</FormLabel>
          <Code data-testid="application-form-address-public-url">{publicUrl}</Code>{' '}
          <Link
            href={publicUrl}
            target="_blank"
            rel="noopener noreferrer"
            color="orange.300"
            fontWeight="semibold"
            data-testid="application-form-address-open-live"
          >
            {t('Open live formulier', 'Open live form')}
          </Link>
        </FormControl>
      ) : (
        <Text fontSize="sm" color="yellow.300" mb={4} data-testid="application-form-address-no-url">
          {t(
            'Dit formulier heeft nog geen publiek adres. Stel hieronder een voorvoegsel en slug in.',
            'This form has no public address yet. Set a prefix and slug below.',
          )}
        </Text>
      )}

      {/* Prefix (above the slug — a slug must sit under the prefix). */}
      <FormControl mb={4} data-testid="application-form-address-prefix-editor">
        <FormLabel htmlFor="application-form-address-prefix-input">
          {t('Publiek voorvoegsel (slug-prefix)', 'Public prefix (slug prefix)')}
        </FormLabel>
        <Input
          id="application-form-address-prefix-input"
          value={prefixDraft}
          onChange={(e) => onPrefixChange(e.target.value)}
          placeholder={t('bijv. h-dcn', 'e.g. h-dcn')}
          data-testid="application-form-address-prefix-input"
          maxW="sm"
          isDisabled={busy}
        />
        <FormHelperText>
          {t(
            'Het korte publieke voorvoegsel van je organisatie. Elke formulier-slug moet hieronder vallen (bijv. voorvoegsel \u2018h-dcn\u2019 \u2192 slug \u2018h-dcn-aanmelden\u2019). Leeg maken wist het voorvoegsel.',
            'Your organisation\u2019s short public prefix. Every form slug must sit under it (e.g. prefix \u2018h-dcn\u2019 \u2192 slug \u2018h-dcn-apply\u2019). Clearing it removes the prefix.',
          )}
        </FormHelperText>
      </FormControl>

      {/* Slug. */}
      <FormControl data-testid="application-form-address-slug-editor">
        <FormLabel htmlFor="application-form-address-slug-input">
          {t('Formulier-slug (publiek adres)', 'Form slug (public address)')}
        </FormLabel>
        <Input
          id="application-form-address-slug-input"
          value={slugDraft}
          onChange={(e) => onSlugChange(e.target.value)}
          placeholder={t('bijv. h-dcn-aanmelden', 'e.g. h-dcn-apply')}
          data-testid="application-form-address-slug-input"
          maxW="sm"
          isDisabled={busy}
        />
        <FormHelperText>
          {t(
            'Het eigen publieke adres van het formulier, opgeslagen bij de formulierconfiguratie (niet de landingspagina). Moet voldoen aan het toegestane voorvoegsel van je organisatie. Leeg maken wist het adres.',
            'The form\u2019s own public address, stored with the form configuration (not the landing page). Must match your organisation\u2019s allowed prefix. Clearing it removes the address.',
          )}
        </FormHelperText>
      </FormControl>
    </Box>
  );
};

export default ApplicationAddressFields;
