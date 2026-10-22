/**
 * Application Form Builder — the "Application form" sub-tab ROOT (spec 11, R1.3, design §3/§3.1).
 *
 * The authoring counterpart to the public member application form (spec 10): a focused *view* over
 * the SAME two SAM-owned config rows the Field-configuration + Mail editors already author —
 * `config#fields` (the per-field application attributes) and `config#mail` (the form-shell mail
 * settings). It does NOT introduce a parallel write path or a second store (design Property 1 /
 * steering 38 rule 5 — one authoring surface per row).
 *
 * ## The one-object/one-save contract (design §3.1)
 *
 * The builder loads the resolved field config (`GET /members/field-config`, which also carries the
 * current `mail_config` body) and the tenant's `field_overlay` row, then holds exactly ONE working
 * `field_overlay` object in state. Every per-field attribute toggle is a pure `overlayModel`
 * transform of that one object (exactly as `MembersFieldModal` authors it) — no per-field network
 * call. The ONE **Save** commits the whole object via `saveMembersParameter('field_overlay', …)`
 * → `writeFieldConfig` → `PUT /members/config/fields`. The form-shell mail settings commit once via
 * `writeConfig('mail', body)` → `PUT /members/config/mail` (the Mail editor's existing path).
 *
 * ## This file (task 2.1) — the SCAFFOLD + four panel SLOTS
 *
 * This task stands up the sub-tab root: the load, the single working-overlay state + commit wiring,
 * and the four-panel layout. The four panel bodies are PLACEHOLDERS here; the real sub-components
 * are built in later tasks:
 *   - field list + per-field attributes — `ApplicationFieldList` / `ApplicationFieldAttributes`
 *     (tasks 2.3 / 3.1);
 *   - form-shell panel — `ApplicationFormShellPanel` (task 3.2);
 *   - readiness panel — `ApplicationReadinessPanel` (task 4.1);
 *   - live preview — `ApplicationFormPreview` (task 4.2).
 *
 * A failed field-config fetch degrades to empty/"unavailable" and NEVER blocks authoring (mirrors
 * `MembersConfigEditor`'s best-effort posture).
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Grid,
  GridItem,
  HStack,
  Heading,
  Spinner,
  Text,
  useToast,
} from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import {
  getMembersFieldConfig,
  saveMembersMailConfig,
  saveMembersParameter,
} from '../../../services/membersConfigService';
import { getSlug } from '../../../services/landingPageApi';
import { listMembershipTypes } from '../../../services/members/membersConfigApi';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, MembershipType } from '../../../types/members';
import { ApplicationFieldList } from './ApplicationFieldList';
import { ApplicationFieldAttributes } from './ApplicationFieldAttributes';
import { ApplicationFormShellPanel } from './ApplicationFormShellPanel';
import { ApplicationReadinessPanel } from './ApplicationReadinessPanel';
import { ApplicationFormPreview } from './ApplicationFormPreview';
import {
  type ShellFormValues,
  mailConfigToShellValues,
  resolveConsentVersion,
  toShellMailBody,
} from './applicationShellForm';

interface Props {
  tenant: string;
}

export const ApplicationFormBuilder: React.FC<Props> = ({ tenant }) => {
  const { i18n } = useTranslation();
  const lang = (i18n.language?.startsWith('nl') ? 'nl' : 'en') as 'nl' | 'en';
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingMail, setSavingMail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The resolved field config — the source for the field list + its current application attributes,
  // the mail_config body, and the readiness signal. Best-effort (null when the fetch fails).
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  // The tenant's LIVE membership-type catalog (task 3.3 / R4). Needed so the membership-type field's
  // subset picker authors over the real catalog (not the field's static choices) and the subset is
  // validated against it. Best-effort: a failed/empty load leaves it null and the generic R3
  // controls apply — the membership-type panel then shows "no types in the catalog yet".
  const [membershipTypeCatalog, setMembershipTypeCatalog] = useState<MembershipType[] | null>(null);

  // The ONE working field_overlay object the whole builder authors (design §3.1). Every per-field
  // attribute toggle transforms THIS object; the single Save commits it once.
  const [overlay, setOverlay] = useState<MembersConfigValue>({});
  // Baseline to detect unsaved edits (one Save → one request).
  const [baseline, setBaseline] = useState<string>('{}');
  // The field selected in the list whose application attributes the attributes panel authors
  // (task 3.1). Selection drives the panel; it is NOT persisted (pure view state).
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  // The form-shell working values (slug/URL display, embed, consent — task 3.2). Seeded from the
  // loaded `config#mail` + the landing-page slug; committed once via `saveMembersMailConfig` →
  // `PUT /members/config/mail` (the Mail editor's existing path, R5.5). A separate baseline tracks
  // the form-shell "dirty" state independently of the field_overlay save.
  const [shell, setShell] = useState<ShellFormValues>(() => mailConfigToShellValues(null, null));
  const [shellBaseline, setShellBaseline] = useState<ShellFormValues>(() =>
    mailConfigToShellValues(null, null),
  );

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      // Load the resolved field config FIRST — it carries the RAW stored `config#fields`
      // overlay (`field_overlay`) the builder seeds + writes back (spec 11 bugfix). GET and PUT
      // are the SAME SAM row, so a save is loss-free. A failed fetch resolves to null (panels
      // show "unavailable") and NEVER blocks authoring. The retired Flask `members.field_overlay`
      // param is no longer read here — SAM `config#fields` is the single source of truth.
      const cfg = await getMembersFieldConfig();
      setFieldConfig(cfg);
      // Seed the ONE working overlay from the authoritative SAM row. The reader serves the
      // overlay in the AUTHORING WIRE shape already (`fields` / `fixed_overrides` /
      // `functional_groups`, the one-key contract), so the overlay model reads + writes it with
      // NO client-side translation — GET and PUT are symmetric by construction.
      const overlayValue = (cfg?.field_overlay as MembersConfigValue) ?? {};
      setOverlay(overlayValue);
      setBaseline(JSON.stringify(overlayValue));
      // The LIVE membership-type catalog (task 3.3 / R4) — best-effort, like the field config. A
      // failure leaves it null; the membership-type subset picker then shows "no types yet".
      try {
        const catalog = await listMembershipTypes<MembershipType[]>();
        setMembershipTypeCatalog(Array.isArray(catalog) ? catalog : []);
      } catch {
        // ignore — best-effort; a missing catalog just shows "no membership types yet".
      }
      // The public slug is read-mostly here (E4): the builder DISPLAYS the derived URL and points
      // at the Landing Page editor to change it. A slug read failure degrades to "no address yet".
      let slug: string | null = null;
      try {
        slug = (await getSlug()).data?.slug ?? null;
      } catch {
        // ignore — best-effort; a missing slug just shows "no public address yet".
      }
      // Seed the form-shell working values from the authoritative `config#mail` body + the slug.
      const shellValues = mailConfigToShellValues(cfg, slug);
      setShell(shellValues);
      setShellBaseline(shellValues);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [tenant]);

  const dirty = useMemo(() => JSON.stringify(overlay) !== baseline, [overlay, baseline]);
  const mailDirty = useMemo(
    () => JSON.stringify(shell) !== JSON.stringify(shellBaseline),
    [shell, shellBaseline],
  );

  /**
   * The single `field_overlay` commit (design §3.1): one Save → one `PUT /members/config/fields`.
   * The per-field panels mutate the one `overlay` via `overlayModel` helpers; this is the only
   * network write for the field attributes.
   */
  const handleSaveFields = async () => {
    setSaving(true);
    try {
      const res = await saveMembersParameter('field_overlay', overlay, null);
      if (res.success) {
        toast({ title: t('Opgeslagen', 'Saved'), status: 'success', duration: 3000 });
        await load();
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
      setSaving(false);
    }
  };

  /**
   * The single form-shell mail commit (design §3.1 / R5.5): one Save → one
   * `PUT /members/config/mail` (the Mail editor's existing path). The body is SEEDED from the
   * loaded `mail_config` so every Mail-sub-tab scalar is carried through verbatim; the panel
   * overlays only the consent notice + embed origins. The consent version is BUMPED only when the
   * notice TEXT changed from the last-saved baseline (R5.3) — an already-recorded applicant version
   * is never retroactively changed. Task 3.4 formally wires this into the builder's save flow.
   */
  const handleSaveMail = async () => {
    setSavingMail(true);
    try {
      const version = resolveConsentVersion(shell, shellBaseline);
      const body = toShellMailBody(shell, fieldConfig?.mail_config, version);
      const res = await saveMembersMailConfig(body);
      if (res.success) {
        toast({ title: t('Opgeslagen', 'Saved'), status: 'success', duration: 3000 });
        await load();
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
      setSavingMail(false);
    }
  };

  if (loading) {
    return (
      <Box p={4} lang={lang}>
        <Spinner color="orange.400" />
        <Text color="gray.400" display="inline" ml={2}>
          {t('Aanmeldformulier laden…', 'Loading application form…')}
        </Text>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={4}>
        <Text color="red.300">{error}</Text>
      </Box>
    );
  }

  return (
    // `lang` declares the content language of the whole builder (nl/en) so assistive tech
    // pronounces the bilingual labels correctly (WCAG 2.2 AA / NFR — nl/en `lang` wiring).
    <Box data-testid="application-form-builder" lang={lang}>
      {/*
        Four-panel layout (R1.3 / design §3). The panel bodies are PLACEHOLDERS in this scaffold;
        the sub-components (ApplicationFieldList/-Attributes, -FormShellPanel, -ReadinessPanel,
        -FormPreview) land in tasks 2.3/3.1/3.2/4.1/4.2 and consume the one working `overlay`,
        the resolved `fieldConfig`, and the two commit handlers.
      */}
      <Grid
        templateColumns={{ base: '1fr', lg: '2fr 1fr' }}
        templateRows={{ base: 'auto', lg: 'auto auto' }}
        gap={4}
      >
        {/* Slot 1 — field list + per-field attributes (R2/R3; tasks 2.3/3.1). */}
        <GridItem
          data-testid="application-form-builder-panel-fields"
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          p={4}
          rowSpan={{ base: 1, lg: 2 }}
        >
          <Heading size="sm" mb={2} color="gray.300">
            {t('Velden op het formulier', 'Fields on the form')}
          </Heading>
          <Text fontSize="sm" color="gray.500" mb={3}>
            {t(
              'Kies welke velden op het publieke aanmeldformulier verschijnen.',
              'Choose which fields appear on the public application form.',
            )}
          </Text>
          {/* R2 — the grouped/ordered field list + per-row on-the-form toggle. It mutates the ONE
              working overlay via overlayModel.upsertField; the single Save below commits it (§3.1).
              Selecting a row drives the per-field attributes panel below (task 3.1). */}
          <ApplicationFieldList
            fieldConfig={fieldConfig}
            overlay={overlay}
            onChange={setOverlay}
            lang={lang}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
          />

          {/* R3/R4 — the selected field's application attributes (required / subset / format). It
              authors the SAME one working overlay via overlayModel.upsertField (task 3.1 / §3.1). */}
          <Box
            borderTopWidth="1px"
            borderColor="gray.700"
            mt={4}
            pt={4}
            data-testid="application-form-builder-field-attributes"
          >
            <Heading size="xs" mb={3} color="gray.400" textTransform="uppercase">
              {t('Veldinstellingen', 'Field attributes')}
            </Heading>
            <ApplicationFieldAttributes
              fieldConfig={fieldConfig}
              selectedKey={selectedKey}
              overlay={overlay}
              onChange={setOverlay}
              membershipTypeCatalog={membershipTypeCatalog}
              lang={lang}
            />
          </Box>
        </GridItem>

        {/* Slot 2 — form-shell panel (slug/URL, embed, consent; R5; task 3.2). */}
        <GridItem
          data-testid="application-form-builder-panel-shell"
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          p={4}
        >
          <Heading size="sm" mb={2} color="gray.300">
            {t('Formulierinstellingen', 'Form settings')}
          </Heading>
          {/* R5 — the form-shell panel: derived public URL (display-only), embed mode + snippet +
              allowed origins, and the versioned bilingual consent notice. It lifts a working
              `config#mail` body up via onChange; the single Save below commits it once via
              `saveMembersMailConfig` → PUT /members/config/mail (R5.5). */}
          <ApplicationFormShellPanel
            values={shell}
            onChange={setShell}
            mailConfig={fieldConfig?.mail_config}
            onSaveMail={handleSaveMail}
            savingMail={savingMail}
            mailDirty={mailDirty}
            lang={lang}
          />
        </GridItem>

        {/* Slot 3 — readiness panel (R6; task 4.1). */}
        <GridItem
          data-testid="application-form-builder-panel-readiness"
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          p={4}
        >
          <Heading size="sm" mb={2} color="gray.300">
            {t('Gereedheid', 'Readiness')}
          </Heading>
          {/* R6 — the readiness summary: certified sender / slug / >=1-field-on-form states +
              neutral "not available" guidance (no mail-config leak) + a link to sender
              verification. It reuses the spec-10 send-ready signal (certified sender + slug) over
              the already-loaded fieldConfig/mail_config + the one working overlay + the slug — a
              pure view, no network (task 4.1, design §6). */}
          <ApplicationReadinessPanel
            fieldConfig={fieldConfig}
            overlay={overlay}
            slug={shell.slug}
            lang={lang}
          />
        </GridItem>

        {/* Slot 4 — live preview (R7; task 4.2). */}
        <GridItem
          data-testid="application-form-builder-panel-preview"
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          p={4}
          colSpan={{ base: 1, lg: 2 }}
        >
          <Heading size="sm" mb={2} color="gray.300">
            {t('Voorbeeld', 'Live preview')}
          </Heading>
          {/* R7 — the live preview: an IN-APP render of the public form via the shared spec-10
              ApplicationFormRenderer, fed by POST /members/application-preview over the ONE working
              overlay. It shows UNSAVED edits live (debounced) through the server's real filter — a
              single rendering path AND a single filtering authority, no client mirror to drift
              (R7.1/R7.2, design §4/§6/§9 S1·S2). The "open live form" link to the hosted form is the
              form-shell panel's concern (R7.3). */}
          <ApplicationFormPreview overlay={overlay} lang={lang} />
        </GridItem>
      </Grid>

      {/* Single save path: one Save → one PUT /members/config/fields (design §3.1 / Property 8). */}
      <Box borderTopWidth="1px" borderColor="gray.700" mt={4} pt={4}>
        <HStack justify="flex-end">
          {dirty && (
            <Text
              fontSize="sm"
              color="yellow.300"
              mr="auto"
              data-testid="application-form-builder-unsaved-indicator"
            >
              {t('Niet-opgeslagen wijzigingen', 'Unsaved changes')}
            </Text>
          )}
          <Button
            colorScheme="orange"
            onClick={handleSaveFields}
            isLoading={saving}
            isDisabled={!dirty}
            loadingText={t('Opslaan…', 'Saving…')}
            data-testid="application-form-builder-save"
          >
            {t('Opslaan', 'Save')}
          </Button>
        </HStack>
      </Box>
    </Box>
  );
};

export default ApplicationFormBuilder;
