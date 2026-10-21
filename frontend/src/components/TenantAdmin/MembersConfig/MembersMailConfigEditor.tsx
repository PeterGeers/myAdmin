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
 * ## Best-effort load
 *
 * Current values are loaded best-effort from `GET /members/field-config` (the resolved
 * config#mail-backed values via the reader) and the legacy `members.*` parameter rows, mirroring
 * `MembersConfigEditor`'s best-effort posture — a load failure degrades to the fail-closed
 * defaults and NEVER blocks authoring.
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
  getMembersParameters,
  saveMembersMailConfig,
} from '../../../services/membersConfigService';
import type { MembersMailConfigBody } from '../../../services/membersConfigService';

interface Props {
  tenant: string;
}

/**
 * The flat Formik form shape. It keeps the two consent-notice locale bodies as flat strings for
 * the controlled fields; `toMailConfigBody` assembles them into the nested
 * `consent_notice.text{nl,en}` the reader expects (and OMITS the notice when not well-formed).
 */
interface MailFormValues {
  mail_enabled: boolean;
  mail_domain: string;
  mail_local_part: string;
  mail_certified: boolean;
  mail_reply_to_default: string;
  consent_version: string;
  consent_text_nl: string;
  consent_text_en: string;
}

const DEFAULT_LOCAL_PART = 'noreply';

const INITIAL_VALUES: MailFormValues = {
  mail_enabled: false,
  mail_domain: '',
  mail_local_part: DEFAULT_LOCAL_PART,
  mail_certified: false,
  mail_reply_to_default: '',
  consent_version: '',
  consent_text_nl: '',
  consent_text_en: '',
};

/** A loose, blank-tolerant email check — mirrors the sender-identities tab's pattern. */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Assemble the reader-shaped `config#mail` body from the form values. The `consent_notice`
 * attribute is INCLUDED only when well-formed — a non-blank version AND at least one non-blank
 * locale body; otherwise it is OMITTED entirely (matching the SAM reader / Flask builder shaping).
 */
export function toMailConfigBody(values: MailFormValues): MembersMailConfigBody {
  const body: MembersMailConfigBody = {
    mail_enabled: values.mail_enabled,
    mail_local_part: values.mail_local_part.trim() || DEFAULT_LOCAL_PART,
    mail_certified: values.mail_certified,
  };

  const domain = values.mail_domain.trim();
  if (domain) body.mail_domain = domain;

  const replyTo = values.mail_reply_to_default.trim();
  if (replyTo) body.mail_reply_to_default = replyTo;

  const version = values.consent_version.trim();
  const text: Record<string, string> = {};
  if (values.consent_text_nl.trim()) text.nl = values.consent_text_nl;
  if (values.consent_text_en.trim()) text.en = values.consent_text_en;
  // Well-formed = a non-blank version AND >= 1 non-blank locale body; else omit the attribute.
  if (version && Object.keys(text).length > 0) {
    body.consent_notice = { version, text };
  }

  return body;
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
      // Best-effort: field-config carries the resolved config#mail-backed values via the reader;
      // the legacy members.* param rows carry the author-time values while they still exist. A
      // failure of EITHER degrades to the fail-closed defaults and never blocks authoring.
      const next: MailFormValues = { ...INITIAL_VALUES };
      try {
        const cfg = await getMembersFieldConfig();
        if (cfg && typeof cfg.mail_enabled === 'boolean') {
          next.mail_enabled = cfg.mail_enabled;
        }
      } catch {
        // ignore — best-effort
      }
      try {
        const params = await getMembersParameters();
        const readStr = (key: string): string => {
          const v = params[key]?.value;
          return typeof v === 'string' ? v : '';
        };
        const readBool = (key: string): boolean | undefined => {
          const v = params[key]?.value;
          return typeof v === 'boolean' ? v : undefined;
        };
        const enabled = readBool('mail_enabled');
        if (typeof enabled === 'boolean') next.mail_enabled = enabled;
        const certified = readBool('mail_certified');
        if (typeof certified === 'boolean') next.mail_certified = certified;
        next.mail_domain = readStr('mail_domain') || next.mail_domain;
        next.mail_local_part = readStr('mail_local_part') || next.mail_local_part;
        next.mail_reply_to_default = readStr('mail_reply_to_default') || next.mail_reply_to_default;
        const notice = params['application_consent_notice']?.value;
        if (notice && typeof notice === 'object' && !Array.isArray(notice)) {
          const n = notice as { version?: unknown; text?: unknown };
          if (typeof n.version === 'string') next.consent_version = n.version;
          if (n.text && typeof n.text === 'object' && !Array.isArray(n.text)) {
            const txt = n.text as Record<string, unknown>;
            if (typeof txt.nl === 'string') next.consent_text_nl = txt.nl;
            if (typeof txt.en === 'string') next.consent_text_en = txt.en;
          }
        }
      } catch {
        // ignore — best-effort
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
