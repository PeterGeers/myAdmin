/**
 * Members typed MAIL function — the single authoring door for the SAM-owned `config#mail`
 * scalars (Members config SAM-owned write path, task 7.1; Requirement 20.1/20.2/9.1/14.4/15.2).
 *
 * A typed, bilingual (nl/en), no-raw-JSON Chakra form for the per-tenant mail configuration. It
 * authors EXACTLY the reader-shaped `config#mail` body the SAM `MembersProjectionReader` mail
 * accessors read back (and the Flask `build_config_mail_row` builder mirrors): `mail_enabled`,
 * `mail_domain`, `mail_local_part`, `mail_certified`, `mail_reply_to_default`, and the optional
 * versioned bilingual `consent_notice`.
 *
 * ## The single save path (Property 8)
 *
 * ONE **Save** button commits the whole body in a SINGLE request via `saveMembersMailConfig`
 * (`PUT /members/config/mail`). The SAM write is AUTHORITATIVE — the returned `version` IS the
 * authored state, there is no pending-projection UX. There is no second authoring door for the
 * mail scalars (the Advanced raw editor excludes every `members.*` key — task 7.2).
 *
 * ## Three-surface model
 *
 * This function writes ONLY the `config#mail` scalars. The sender-identity surface
 * (`MemberSenderIdentitiesTab`) is CO-LOCATED on the same screen but keeps its own Flask
 * `/api/members/sender-identities` route — it is a separate dataset / write mechanism and is NOT
 * folded into the `config#mail` put. The invoice-SES sender surface is untouched here.
 *
 * ## Authoritative load (reads the same source it writes)
 *
 * Initial values are loaded from `GET /members/field-config`'s `mail_config` object — the
 * AUTHORITATIVE SAM `config#mail` body (the same row this form writes via
 * `PUT /members/config/mail`). It does NOT read the mail scalars from the legacy MySQL
 * `members.*` params: those are SAM-owned/retired now, and `mail_reply_to_default` is SAM-only
 * net-new (no MySQL row), so reading from MySQL would make a just-saved value read back blank.
 * After a successful save the form RE-FETCHES the field config and re-seeds from the fresh
 * `mail_config`, so the save demonstrably round-trips through the real read path. A load
 * failure degrades to the fail-closed defaults and NEVER blocks authoring.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Code,
  FormControl,
  FormErrorMessage,
  FormHelperText,
  FormLabel,
  HStack,
  Heading,
  Input,
  Spinner,
  Switch,
  Text,
  Textarea,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import type { FieldProps, FormikHelpers } from 'formik';
import * as Yup from 'yup';
import { useTranslation } from 'react-i18next';
import {
  getMembersFieldConfig,
  saveMembersMailConfig,
} from '../../../services/membersConfigService';
import {
  type MailFormValues,
  DEFAULT_LOCAL_PART,
  EMAIL_RE,
  INITIAL_VALUES,
  mailConfigToFormValues,
  toMailConfigBody,
} from './mailConfigForm';

interface Props {
  tenant: string;
}

export const MembersMailConfigEditor: React.FC<Props> = ({ tenant }) => {
  const { i18n } = useTranslation();
  const lang = (i18n.language?.startsWith('nl') ? 'nl' : 'en') as 'nl' | 'en';
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [initialValues, setInitialValues] = useState<MailFormValues>(INITIAL_VALUES);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      // Load the mail scalars from the AUTHORITATIVE SAM source — GET /members/field-config's
      // `mail_config` body (the same config#mail row this form writes). Never reads the legacy
      // MySQL members.* params: those are SAM-owned/retired, and mail_reply_to_default is
      // SAM-only net-new, so MySQL is the wrong source (a saved value would read back blank). A
      // failure degrades to the fail-closed defaults and never blocks authoring.
      let next: MailFormValues = { ...INITIAL_VALUES };
      try {
        next = mailConfigToFormValues(await getMembersFieldConfig());
      } catch {
        // ignore — best-effort; keep the fail-closed defaults.
      }
      if (!cancelled) {
        setInitialValues(next);
        setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [tenant]);

  // Yup validation — client-side guards BEFORE any API call. Only mail_reply_to_default has a
  // format constraint (a valid email when non-blank); every other field is free-form/optional.
  const schema = useMemo(
    () =>
      Yup.object().shape({
        mail_reply_to_default: Yup.string()
          .trim()
          .test(
            'reply-to-email',
            t('Voer een geldig e-mailadres in', 'Enter a valid email address'),
            (v) => !v || EMAIL_RE.test(v),
          ),
      }),
    [lang], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleSave = async (
    values: MailFormValues,
    { setSubmitting }: FormikHelpers<MailFormValues>,
  ) => {
    try {
      const res = await saveMembersMailConfig(toMailConfigBody(values));
      if (res.success) {
        // Re-seed from the AUTHORITATIVE read (GET /members/field-config mail_config) so the save
        // demonstrably round-trips through the real read path — not an optimistic reflect of the
        // submitted values. With enableReinitialize the form updates to the persisted state. A
        // re-fetch failure leaves the just-entered values on screen (still the saved state).
        try {
          setInitialValues(mailConfigToFormValues(await getMembersFieldConfig()));
        } catch {
          // ignore — best-effort; the toast below still confirms the authoritative save.
        }
        toast({ title: t('Opgeslagen', 'Saved'), status: 'success', duration: 3000 });
      } else {
        toast({ title: 'Error', description: res.error, status: 'error', duration: 6000 });
      }
    } catch (e) {
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Box p={4}>
        <Spinner color="orange.400" />
        <Text color="gray.400" display="inline" ml={2}>
          {t('Mailconfiguratie laden…', 'Loading mail configuration…')}
        </Text>
      </Box>
    );
  }

  return (
    <Box data-testid="members-mail-config-editor">
      <Formik<MailFormValues>
        initialValues={initialValues}
        enableReinitialize
        validationSchema={schema}
        onSubmit={handleSave}
      >
        {({ values, isSubmitting }) => {
          const fromPreview = `${values.mail_local_part.trim() || DEFAULT_LOCAL_PART}@${
            values.mail_domain.trim() || '<domain>'
          }`;
          return (
            <Form>
              <VStack align="stretch" spacing={5}>
                {/* mail_enabled — the "cleared to send" gate. */}
                <Field name="mail_enabled">
                  {({ field, form }: FieldProps<boolean, MailFormValues>) => (
                    <FormControl display="flex" alignItems="center">
                      <Switch
                        id="mail_enabled"
                        isChecked={field.value}
                        onChange={(e) => form.setFieldValue('mail_enabled', e.target.checked)}
                        colorScheme="orange"
                        data-testid="members-mail-config-enabled"
                      />
                      <FormLabel htmlFor="mail_enabled" mb={0} ml={3}>
                        {t('Mail inschakelen', 'Mail enabled')}
                      </FormLabel>
                    </FormControl>
                  )}
                </Field>

                {/* mail_domain — optional, no safe default. */}
                <Field name="mail_domain">
                  {({ field }: FieldProps<string, MailFormValues>) => (
                    <FormControl>
                      <FormLabel>{t('Maildomein', 'Mail domain')}</FormLabel>
                      <Input
                        {...field}
                        placeholder="h-dcn.nl"
                        data-testid="members-mail-config-domain"
                      />
                      <FormHelperText>
                        {t(
                          'Het eigen maildomein van de tenant (optioneel).',
                          "The tenant's own mail domain (optional).",
                        )}
                      </FormHelperText>
                    </FormControl>
                  )}
                </Field>

                {/* mail_local_part — defaults to noreply. */}
                <Field name="mail_local_part">
                  {({ field }: FieldProps<string, MailFormValues>) => (
                    <FormControl>
                      <FormLabel>{t('Lokaal deel afzender', 'From local part')}</FormLabel>
                      <Input
                        {...field}
                        placeholder={DEFAULT_LOCAL_PART}
                        data-testid="members-mail-config-local-part"
                      />
                    </FormControl>
                  )}
                </Field>

                {/* From preview — read-only derived hint. */}
                <FormControl>
                  <FormLabel>{t('Afzender (preview)', 'From (preview)')}</FormLabel>
                  <Code data-testid="members-mail-config-from-preview">{fromPreview}</Code>
                </FormControl>

                {/* mail_certified — the SES-verified gate. */}
                <Field name="mail_certified">
                  {({ field, form }: FieldProps<boolean, MailFormValues>) => (
                    <FormControl display="flex" alignItems="center">
                      <Switch
                        id="mail_certified"
                        isChecked={field.value}
                        onChange={(e) => form.setFieldValue('mail_certified', e.target.checked)}
                        colorScheme="orange"
                        data-testid="members-mail-config-certified"
                      />
                      <FormLabel htmlFor="mail_certified" mb={0} ml={3}>
                        {t('SES-gecertificeerd', 'SES certified')}
                      </FormLabel>
                    </FormControl>
                  )}
                </Field>

                {/* mail_reply_to_default — optional; validated as email when non-blank. */}
                <Field name="mail_reply_to_default">
                  {({ field, form }: FieldProps<string, MailFormValues>) => (
                    <FormControl
                      isInvalid={
                        !!form.errors.mail_reply_to_default &&
                        !!form.touched.mail_reply_to_default
                      }
                    >
                      <FormLabel>
                        {t('Standaard Reply-To', 'Default Reply-To')}
                      </FormLabel>
                      <Input
                        {...field}
                        placeholder="noreply@h-dcn.nl"
                        data-testid="members-mail-config-reply-to"
                      />
                      <FormHelperText>
                        {t(
                          'Gebruikt voor geplande/onbeheerde verzending (optioneel).',
                          'Used for scheduled/unattended sends (optional).',
                        )}
                      </FormHelperText>
                      <FormErrorMessage data-testid="members-mail-config-reply-to-error">
                        {form.errors.mail_reply_to_default}
                      </FormErrorMessage>
                    </FormControl>
                  )}
                </Field>

                {/* application_consent_notice — optional bilingual versioned notice. */}
                <Box borderTopWidth="1px" borderColor="gray.700" pt={4}>
                  <Heading size="sm" mb={3} color="gray.300">
                    {t('Toestemmingsverklaring (optioneel)', 'Consent notice (optional)')}
                  </Heading>
                  <VStack align="stretch" spacing={3}>
                    <Field name="consent_version">
                      {({ field }: FieldProps<string, MailFormValues>) => (
                        <FormControl>
                          <FormLabel>{t('Versie', 'Version')}</FormLabel>
                          <Input
                            {...field}
                            placeholder="2026-01"
                            data-testid="members-mail-config-consent-version"
                          />
                        </FormControl>
                      )}
                    </Field>
                    <Field name="consent_text_nl">
                      {({ field }: FieldProps<string, MailFormValues>) => (
                        <FormControl>
                          <FormLabel>{t('Tekst (NL)', 'Body (NL)')}</FormLabel>
                          <Textarea
                            {...field}
                            data-testid="members-mail-config-consent-nl"
                          />
                        </FormControl>
                      )}
                    </Field>
                    <Field name="consent_text_en">
                      {({ field }: FieldProps<string, MailFormValues>) => (
                        <FormControl>
                          <FormLabel>{t('Tekst (EN)', 'Body (EN)')}</FormLabel>
                          <Textarea
                            {...field}
                            data-testid="members-mail-config-consent-en"
                          />
                        </FormControl>
                      )}
                    </Field>
                    <Text fontSize="xs" color="gray.500">
                      {t(
                        'De verklaring wordt alleen opgeslagen met een versie én minstens één taalversie.',
                        'The notice is saved only with a version AND at least one locale body.',
                      )}
                    </Text>
                  </VStack>
                </Box>

                {/* Single save path: one Save → one PUT /members/config/mail (Property 8). */}
                <Box borderTopWidth="1px" borderColor="gray.700" pt={4}>
                  <HStack justify="flex-end">
                    <Button
                      type="submit"
                      colorScheme="orange"
                      isLoading={isSubmitting}
                      loadingText={t('Opslaan…', 'Saving…')}
                      data-testid="members-mail-config-save"
                    >
                      {t('Opslaan', 'Save')}
                    </Button>
                  </HStack>
                </Box>
              </VStack>
            </Form>
          );
        }}
      </Formik>
    </Box>
  );
};

export default MembersMailConfigEditor;
