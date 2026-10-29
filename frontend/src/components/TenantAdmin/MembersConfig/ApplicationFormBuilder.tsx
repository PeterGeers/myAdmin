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
 * call. The ONE **Save** derives a CHANGE-OP list from the (loaded baseline → edited working)
 * overlay diff and commits it BY IDENTITY via `saveFieldConfigChangeOps` → `applyFieldConfigChangeOps`
 * → `PUT /members/config/fields` with an `{ops}` body (spec 03 Phase 5 — the server owns storage
 * placement; the client never sends a whole catalog or a `{group}.{key}` key, steering 39). The
 * form-shell mail settings commit once via `writeConfig('mail', body)` → `PUT /members/config/mail`.
 *
 * ## This file (task 2.1) — the SCAFFOLD + four panel SLOTS
 *
 * This task stands up the sub-tab root: the load, the single working-overlay state + commit wiring,
 * and the four-panel layout. The four panel bodies are PLACEHOLDERS here; the real sub-components
 * are built in later tasks:
 *   - group ▸ field surface + per-field modal — `ApplicationFieldModalList` /
 *     `ApplicationFieldModal` (spec 12 task 4.1, redesign A — replaces the retired spec-11
 *     `ApplicationFieldList` toggle-list + `ApplicationFieldAttributes` buried panel);
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
  saveFieldConfigChangeOps,
} from '../../../services/membersConfigService';
import { deriveFieldConfigChangeOps } from './fieldConfigChangeOps';
import { getSlug } from '../../../services/landingPageApi';
import { publishApplicationForm } from '../../../services/members/membersConfigApi';
import { computeReadiness } from './applicationReadiness';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig } from '../../../types/members';
import { ApplicationFieldModalList } from './ApplicationFieldModalList';
import { ApplicationFieldModal } from './ApplicationFieldModal';
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
  const [publishing, setPublishing] = useState(false);
  // Whether a Save has committed draft changes that have NOT yet been (re)published (spec 12
  // R5.1a — save ≠ publish). Set on any successful field/mail save, cleared on a successful
  // publish and on a fresh load. Drives the "draft has unpublished changes" hint so the admin
  // sees that going-live is a separate, deliberate step.
  const [savedSincePublish, setSavedSincePublish] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The resolved field config — the source for the field list + its current application attributes,
  // the mail_config body, and the readiness signal. Best-effort (null when the fetch fails).
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  // The tenant's LIVE membership-type catalog (task 3.3 / R4). Needed so the membership-type field's
  // The ONE working field_overlay object the whole builder authors (design §3.1). Every per-field
  // attribute toggle transforms THIS object; the single Save commits it once.
  const [overlay, setOverlay] = useState<MembersConfigValue>({});
  // Baseline to detect unsaved edits (one Save → one request).
  const [baseline, setBaseline] = useState<string>('{}');
  // The field whose per-field MODAL is open (spec 12 task 4.1 / redesign A). Clicking a field in
  // the group ▸ field surface opens the modal for it; `null` = the modal is closed. Pure view state
  // (never persisted) — the modal authors the ONE working overlay through the shared engine.
  const [modalFieldKey, setModalFieldKey] = useState<string | null>(null);

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
    // A fresh load reflects the authoritative stored state; any "unpublished changes" accounting
    // restarts from the loaded publish stamp.
    setSavedSincePublish(false);
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
      // Phase 5 (spec 03): the per-field application attributes commit by IDENTITY via the
      // Change-Op path, not the whole overlay. Derive the ops from the loaded baseline → the edited
      // working overlay — a form-builder edit is a `set_field_application` by the BARE field key
      // (the four form attrs), with the server owning storage placement (steering 39). This replaces
      // the retired whole-overlay `saveMembersParameter('field_overlay')`.
      const baselineOverlay = JSON.parse(baseline) as MembersConfigValue;
      const ops = deriveFieldConfigChangeOps(baselineOverlay, overlay);
      const res = await saveFieldConfigChangeOps(ops);
      if (res.success) {
        toast({ title: t('Opgeslagen', 'Saved'), status: 'success', duration: 3000 });
        // Save ≠ publish (spec 12 R5.1a): a successful save commits the draft but the live form is
        // unchanged until a deliberate Publish — mark the draft as having unpublished changes.
        await load();
        setSavedSincePublish(true);
      } else if (res.conflict) {
        // Version-conditional write lost the race → prompt a reload, then reload the latest state.
        toast({
          title: t('Opnieuw laden vereist', 'Reload required'),
          description: t(
            'De configuratie is door iemand anders gewijzigd. De laatste versie wordt opnieuw geladen.',
            'The configuration was changed by someone else. Reloading the latest version.',
          ),
          status: 'warning',
          duration: 9000,
          isClosable: true,
        });
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
        // Save ≠ publish (spec 12 R5.1a): mark the draft as having unpublished changes.
        await load();
        setSavedSincePublish(true);
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

  // Readiness (spec 12 R5.4 / spec 11 R6) — reuse the SAME computation the readiness panel uses so
  // the Publish gate and the readiness panel can never disagree: certified sender + slug + ≥1
  // on-form field, over the loaded config, the ONE working overlay, and the FORM slug.
  const readiness = useMemo(
    () => computeReadiness(fieldConfig, overlay, shell.slug),
    [fieldConfig, overlay, shell.slug],
  );

  // Whether the form has ever been published (spec 12 R5 — `published_version`/`published_at` on
  // `config#fields`). Drives first-publish vs republish copy and the unpublished-changes hint.
  const everPublished = Boolean(
    (typeof fieldConfig?.published_version === 'number' && fieldConfig.published_version > 0) ||
    (typeof fieldConfig?.published_at === 'string' && fieldConfig.published_at.trim()),
  );

  // The draft has unpublished changes (spec 12 R5.1a — surface save ≠ publish) when there are
  // edits not yet live: unsaved draft dirt, a save committed since the last publish, OR a ready
  // form that has never been published (its config exists but no live artifact does yet).
  const hasUnpublishedChanges =
    dirty || mailDirty || savedSincePublish || (!everPublished && readiness.isSendReady);

  /**
   * Deliberately publish the application form (spec 12 R5 / OQ1 = option 1): the ONE explicit
   * go-live action. It calls `POST /members/application-form/publish` — NEVER triggered by a Save
   * (save ≠ publish). The SAM route re-renders the live artifact from the tenant's CURRENT stored
   * `config#fields`/`config#mail`, so publishing an unsaved draft would publish stale state; the
   * builder therefore saves nothing here — it publishes what is SAVED, and the unpublished-changes
   * hint tells the admin to Save first if they have pending edits.
   *
   * NOTE (spec 12 Phase 2/3): the live S3 write is DORMANT until the hosting migration + IAM land
   * and the SAM route (task 2.1) ships; until then the call may 404 — surfaced as a normal error
   * toast, not a crash. The button + readiness + save≠publish UX are account-agnostic and land now.
   */
  const handlePublish = async () => {
    setPublishing(true);
    try {
      const res = await publishApplicationForm();
      if (res.success) {
        toast({ title: t('Gepubliceerd', 'Published'), status: 'success', duration: 3000 });
        // A successful publish makes the live form match the saved config → no unpublished changes.
        setSavedSincePublish(false);
        await load();
      } else {
        toast({
          title: 'Error',
          description: t('Publiceren is mislukt', 'Publish failed'),
          status: 'error',
          duration: 6000,
        });
      }
    } catch (e) {
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setPublishing(false);
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
        Four-panel layout (R1.3 / design §3). The sub-components (ApplicationFieldModalList +
        ApplicationFieldModal, -FormShellPanel, -ReadinessPanel, -FormPreview) consume the one
        working `overlay`, the resolved `fieldConfig`, and the two commit handlers.
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
          {/* R1.1 (spec 12, redesign A) — the grouped/ordered group ▸ field surface. A row-click
              OPENS the per-field modal (below); there is no inline toggle and no buried attributes
              panel anymore. The retired `ApplicationFieldList` toggle-list + `ApplicationFieldAttributes`
              panel are replaced by this list + `ApplicationFieldModal`. The modal authors the ONE
              working overlay via the shared engine (overlayModel.upsertField); the single Save below
              commits it (§3.1). */}
          <ApplicationFieldModalList
            fieldConfig={fieldConfig}
            overlay={overlay}
            onOpenField={setModalFieldKey}
            lang={lang}
          />
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
            readiness={readiness}
            onPublish={handlePublish}
            publishing={publishing}
            hasUnpublishedChanges={hasUnpublishedChanges}
            everPublished={everPublished}
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
          {/* R3 (spec 12, redesign C) — the live preview: an IN-BROWSER render of the public form
              via the shared spec-10 ApplicationFormRenderer, fed by the PURE `buildPreviewConfig`
              filter over the WORKING draft (resolved fieldConfig ⊕ the ONE working overlay). It
              shows UNSAVED edits live with NO server round-trip — the retired
              `POST /members/application-preview` is gone (task 5.2); the client filter reproduces
              `get_public_field_config`'s applicant-facing selection, parity-pinned in task 5.3
              (design §C2/D4). The "open live form" link to the hosted form is the form-shell panel's
              concern (R3.3). */}
          <ApplicationFormPreview
            fieldConfig={fieldConfig}
            overlay={overlay}
            lang={lang}
          />
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

      {/* R1.1/R1.2 (spec 12, redesign A) — the per-field modal, opened by a row-click in the field
          list above. It reuses `MembersFieldModal`'s engine (`resolveWriteTarget` / `upsertField`)
          and renders the application-form attributes section ONLY when a form is in scope. The
          builder IS the application-form authoring context, so `formInScope` is always true here;
          the modal authors the ONE working overlay via `onChange`, committed by the single Save. */}
      <ApplicationFieldModal
        isOpen={modalFieldKey !== null}
        onClose={() => setModalFieldKey(null)}
        fieldKey={modalFieldKey}
        fieldConfig={fieldConfig}
        overlay={overlay}
        onChange={setOverlay}
        formInScope
        lang={lang}
      />
    </Box>
  );
};

export default ApplicationFormBuilder;
