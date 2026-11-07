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
import { flatViewToOverlay } from './flatViewToOverlay';
import { uploadImage } from '../../../services/landingPageApi';
import {
  publishApplicationForm,
  setApplicationFormSlug,
  setApplicationFormPrefix,
  getLookAndFeelSettings,
  setLookAndFeelSetting,
  type LookAndFeelSettingsValues,
} from '../../../services/members/membersConfigApi';
import type { SupportedAttribute } from './pageStyles';
import type { ExtraAttribute, ExtraLookAndFeelValues } from './LookAndFeelEditor';
import { computeReadiness } from './applicationReadiness';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig } from '../../../types/members';
import { ApplicationFieldModalList } from './ApplicationFieldModalList';
import { ApplicationFieldModal } from './ApplicationFieldModal';
import { ApplicationFormShellPanel } from './ApplicationFormShellPanel';
import { ApplicationReadinessPanel } from './ApplicationReadinessPanel';
import { ApplicationFormPreview } from './ApplicationFormPreview';
import { LookAndFeelEditor } from './LookAndFeelEditor';
import {
  type ShellFormValues,
  mailConfigToShellValues,
  resolveConsentVersion,
  toShellMailBody,
} from './applicationShellForm';

interface Props {
  tenant: string;
}

/**
 * The two NEW look-and-feel attributes the bugfix `bugfix-published-form-styling` adds
 * (`logo`/`header_title`). They are authored through dedicated editor controls and ride a
 * separate working map. (The earlier `columns` attribute was removed — the form grid is now a
 * fully width-driven responsive auto-fit grid, so a column count has no effect.)
 */
const EXTRA_LOOKANDFEEL_ATTRIBUTES: readonly ExtraAttribute[] = [
  'logo',
  'header_title',
];

/**
 * Split a resolved `look_and_feel` slice into the seven preview-rendered attributes and the three
 * new values-only attributes. The seven feed the preview's `renderPageStyles` (which rejects any
 * key outside the seven today); the three new ones feed the separate `extraLookAndFeel` working
 * map. Values-only in both halves — never CSS.
 */
function splitLookAndFeel(settings: LookAndFeelSettingsValues): {
  seven: LookAndFeelSettingsValues;
  extra: ExtraLookAndFeelValues;
} {
  const seven: LookAndFeelSettingsValues = {};
  const extra: ExtraLookAndFeelValues = {};
  for (const [key, value] of Object.entries(settings)) {
    // Backward-compat: a stored slice may still carry a legacy `columns` key. It is no longer a
    // supported attribute (the grid is width-driven), so drop it — don't resurface or resend it.
    if (key === 'columns') continue;
    if ((EXTRA_LOOKANDFEEL_ATTRIBUTES as readonly string[]).includes(key)) {
      extra[key as ExtraAttribute] = value as string | null;
    } else {
      seven[key as keyof LookAndFeelSettingsValues] = value as string | null;
    }
  }
  return { seven, extra };
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
  // Whether a slug-author write is in flight (the `members:admin` set/change/clear control).
  const [settingSlug, setSettingSlug] = useState(false);
  // Whether a prefix-author write is in flight (the `members:admin` set/change/clear control for
  // the SAM-owned public slug prefix).
  const [settingPrefix, setSettingPrefix] = useState(false);
  // Whether a look-and-feel persist is in flight (the Layer-1 values-only Change-Op write).
  const [settingLookAndFeel, setSettingLookAndFeel] = useState(false);
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

  // The WORKING look-and-feel VALUES (spec 15 task 12.2 — SAM Page Look-and-Feel). Seeded from the
  // SAM-owned `look_and_feel` slice (`getLookAndFeelSettings`) on load, updated instantly by the
  // LookAndFeelEditor's onChange, and persisted one-value-at-a-time via `setLookAndFeelSetting`
  // (values-only Change-Op). It is fed to BOTH the editor AND the `ApplicationFormPreview
  // lookAndFeel` prop so an admin's stored + UNSAVED edits render live in the preview with no
  // server round-trip (Req 7.2) — closing the gap where the preview rendered with NO lookAndFeel.
  const [lookAndFeel, setLookAndFeel] = useState<LookAndFeelSettingsValues>({});

  // The WORKING values for the three NEW look-and-feel attributes the bugfix
  // `bugfix-published-form-styling` adds (`logo`/`header_title`/`columns`; bugfix 3.4 / design §C).
  // They ride their own working map because the editor exposes them through dedicated controls,
  // but as of Task 12 they are NOT isolated from the preview: the merged `previewLookAndFeel`
  // (below) feeds all ten to `renderPageStyles`, which was extended (Task 8) to accept them. They
  // persist via the SAME values-only `setLookAndFeelSetting` Change-Op path as the seven (never
  // CSS, never a whole record, steering 39) and are seeded from the same `getLookAndFeelSettings`
  // slice on load.
  const [extraLookAndFeel, setExtraLookAndFeel] = useState<ExtraLookAndFeelValues>({});
  // Baseline of the look-and-feel working maps at the last load/save, so the builder's single Save
  // can tell whether look-and-feel is dirty (same model as `baseline` for fields). JSON of
  // { seven, extra } captured on load and after a successful save.
  const [lookAndFeelBaseline, setLookAndFeelBaseline] = useState<string>('{"seven":{},"extra":{}}');

  // bugfix bugfix-published-form-styling Task 12 — the UNIFIED look-and-feel map fed to the
  // preview. The editor still authors the seven (`lookAndFeel`) and the three new attributes
  // (`extraLookAndFeel`) through their own controls, but the preview now consumes ALL TEN as one
  // set: `renderPageStyles` was extended (Task 8) to accept `logo`/`header_title`/`columns`, so
  // the preview reflects the three new values (grid columns, logo, heading) and matches the
  // published form (Req 2.6). Merging here keeps ONE SAM-owned attribute set feeding BOTH planes —
  // the seven/extra split is now purely an authoring-control detail, not a styling divergence.
  const previewLookAndFeel = useMemo(
    () => ({ ...lookAndFeel, ...extraLookAndFeel }),
    [lookAndFeel, extraLookAndFeel],
  );

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
      // Load the resolved field config FIRST — the SAM read resolves the stored `config#fields`
      // overlay INTO each `fields[]` entry (`application_required`, `format`, `functional_group`,
      // `origin`, …) and no longer surfaces the raw `field_overlay` key (steering 39). GET and PUT
      // are the SAME SAM row, so a save is loss-free. A failed fetch resolves to null (panels
      // show "unavailable") and NEVER blocks authoring. The retired Flask `members.field_overlay`
      // param is no longer read here — SAM `config#fields` is the single source of truth.
      const cfg = await getMembersFieldConfig();
      setFieldConfig(cfg);
      // Seed the ONE working overlay from the RESOLVED field config. Task 5.3 (steering 39)
      // stopped the backend surfacing the raw `field_overlay` key, so we reconstruct the
      // authoring-wire overlay (`fields` / `fixed_overrides` / `functional_groups`) from the
      // resolved `fields[]` / `functional_groups` the response DOES carry, via
      // `flatViewToOverlay(cfg)` — mirroring `MembersConfigEditor`. Baseline == the same seed, so
      // a clean load is NOT dirty and the diff-based save emits an op only for an identity the
      // user actually edits.
      const overlayValue = flatViewToOverlay(cfg);
      setOverlay(overlayValue);
      setBaseline(JSON.stringify(overlayValue));
      // The public slug is sourced from the SAM `config#fields.slug` served on the field-config
      // response (`cfg.slug`), NOT from the Flask landing plane (bugfix-slug-lifecycle R2.1/R2.2 —
      // the retired cross-plane `getSlug()` read is gone). A SAM screen reflects SAM state: when
      // `cfg.slug` is absent/null the panel shows "no public address yet", and `shell.slug` +
      // `computeReadiness` are driven by the SAM slug only — never a landing-plane slug. The slug
      // is now AUTHORED from this screen via `handleSetSlug` (the SAM slug-author endpoint), so
      // after a successful set a fresh load reflects the persisted SAM slug. Pass no fallback so
      // the ONLY source is `cfg.slug` (deriveFormSlug returns null when absent).
      const shellValues = mailConfigToShellValues(cfg, null);
      setShell(shellValues);
      setShellBaseline(shellValues);
      // Seed the working look-and-feel VALUES from the SAM-owned `look_and_feel` slice (spec 15
      // task 12.2). Best-effort and NON-BLOCKING: a failed read resolves to the empty map (→
      // Layer-2 defaults) and NEVER blocks authoring (same posture as the field-config load). The
      // read is values-only; it never carries CSS.
      try {
        const lf = await getLookAndFeelSettings();
        // Split the resolved slice: the three NEW attributes (`logo`/`header_title`/`columns`)
        // ride a SEPARATE working map (the preview path renders only the seven today — routing
        // these three through its `renderPageStyles` map would reject). The seven preview-rendered
        // attributes seed `lookAndFeel`; the three new ones seed `extraLookAndFeel`.
        const { seven, extra } = splitLookAndFeel(lf.settings ?? {});
        setLookAndFeel(seven);
        setExtraLookAndFeel(extra);
        setLookAndFeelBaseline(JSON.stringify({ seven, extra }));
      } catch {
        setLookAndFeel({});
        setExtraLookAndFeel({});
        setLookAndFeelBaseline(JSON.stringify({ seven: {}, extra: {} }));
      }
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
  // Look-and-feel is dirty when the working maps differ from the last-saved baseline — drives the
  // SINGLE builder Save (no separate look-and-feel Save button; one deliberate save for the form).
  const lookAndFeelDirty = useMemo(
    () => JSON.stringify({ seven: lookAndFeel, extra: extraLookAndFeel }) !== lookAndFeelBaseline,
    [lookAndFeel, extraLookAndFeel, lookAndFeelBaseline],
  );

  /**
   * Upload a new logo image and set the `logo` look-and-feel value to the stored reference. Reuses
   * the existing tenant-scoped S3 upload path (`uploadImage` -> `POST /api/landing/images/upload`)
   * rather than a new subsystem: the server stores the file under the tenant prefix and returns a
   * public `url`, which we lift into the working `extraLookAndFeel.logo` (so it shows in the preview
   * immediately and is persisted by the single bottom Save, like any other look-and-feel value).
   * Returns the stored URL (or throws a caller-safe error the control surfaces).
   */
  const handleUploadLogo = async (file: File): Promise<string> => {
    const { url } = await uploadImage(file);
    handleExtraLookAndFeelChange('logo', url);
    return url;
  };

  /**
   * Persist ALL current look-and-feel values in the builder's single bottom Save button (same model as fields: edits are in-memory, one Save persists). The
   * per-field blur persist stays as a convenience, but this is the clear, deliberate action an
   * admin can see and trigger. It walks the WORKING maps (the seven + the three extras) and issues
   * one values-only Change-Op per attribute via the same `setLookAndFeelSetting` path, then
   * surfaces one success / error toast. No response write-back (the optimistic working map is the
   * source of truth), so it is free of the overlapping-response race.
   */
  const persistLookAndFeel = async () => {
    const sevenEntries = Object.entries(lookAndFeel) as [SupportedAttribute, string | null][];
    const extraEntries = Object.entries(extraLookAndFeel) as [ExtraAttribute, string | null][];
    for (const [attribute, value] of sevenEntries) {
      await setLookAndFeelSetting(attribute, value);
    }
    for (const [attribute, value] of extraEntries) {
      await setLookAndFeelSetting(attribute, value);
    }
    // Clear the dirty flag: the working maps are now the saved baseline.
    setLookAndFeelBaseline(
      JSON.stringify({ seven: lookAndFeel, extra: extraLookAndFeel }),
    );
  };

  /**
   * The single `field_overlay` commit (design §3.1): one Save → one `PUT /members/config/fields`.
   * The per-field panels mutate the one `overlay` via `overlayModel` helpers; this is the only
   * network write for the field attributes.
   */
  const handleSaveFields = async () => {
    setSaving(true);
    try {
      // The SINGLE builder Save (serverless-friendly): persist the look-and-feel working maps in one
      // batched pass FIRST (values-only Change-Ops), then the field_overlay diff — there is no
      // separate look-and-feel Save button. Look-and-feel errors surface via the shared catch below.
      if (lookAndFeelDirty) {
        await persistLookAndFeel();
      }
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
   * Author / change / clear the application-form public slug on the SAM plane
   * (bugfix-slug-lifecycle task 3.3 / R2.3): the `members:admin` control that was MISSING (defect
   * B). It calls the SAM slug-author endpoint (`POST /members/application-form/slug` via
   * `setApplicationFormSlug`), NEVER the Flask `landingPageApi` — the SAM `config#fields.slug` is
   * the single source of truth. The server validates (format/reserved + SEC-4 prefix-ownership),
   * claims the shared `_slugs/{slug}` marker, and persists the slug via a single identity
   * Change-Op; an explicit empty value CLEARS it (`null`). On success the builder RE-LOADS so the
   * displayed public address + the Publish readiness signal reflect the persisted SAM slug (not an
   * optimistic local value) — the display and the authoritative SAM publish gate always agree
   * (R2.2). A validation / foreign-owner failure surfaces as a caller-safe error toast.
   */
  const handleSetSlug = async (nextSlug: string) => {
    setSettingSlug(true);
    try {
      const trimmed = nextSlug.trim();
      const res = await setApplicationFormSlug(trimmed ? trimmed : null);
      if (res.success) {
        toast({
          title: trimmed
            ? t('Publiek adres opgeslagen', 'Public address saved')
            : t('Publiek adres gewist', 'Public address cleared'),
          status: 'success',
          duration: 3000,
        });
        // Re-load so the SAM-sourced display + readiness reflect the persisted config#fields.slug.
        await load();
      } else {
        toast({
          title: 'Error',
          description: t('Publiek adres opslaan is mislukt', 'Saving the public address failed'),
          status: 'error',
          duration: 6000,
        });
      }
    } catch (e) {
      // Caller-safe: surface the structured ApiError message (validation 400/422, foreign-owner
      // 409) without leaking internals — the backend already returns a caller-safe envelope.
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setSettingSlug(false);
    }
  };

  /**
   * Author / change / clear the tenant's SAM-owned public slug PREFIX (slug-prefix SAM-owned):
   * the `members:admin` control that calls `setApplicationFormPrefix` (POST
   * /members/application-form/prefix). The prefix is the SEC-4 stem every form slug must sit under;
   * it lives only on the SAM plane (`config#fields.public_prefix`). On success a fresh load reflects
   * the persisted prefix (so the slug control's validation and the displayed value stay in step). A
   * validation failure surfaces as a caller-safe error toast.
   */
  const handleSetPrefix = async (nextPrefix: string) => {
    setSettingPrefix(true);
    try {
      const trimmed = nextPrefix.trim();
      const res = await setApplicationFormPrefix(trimmed ? trimmed : null);
      if (res.success) {
        toast({
          title: trimmed
            ? t('Voorvoegsel opgeslagen', 'Prefix saved')
            : t('Voorvoegsel gewist', 'Prefix cleared'),
          status: 'success',
          duration: 3000,
        });
        await load();
      } else {
        toast({
          title: 'Error',
          description: t('Voorvoegsel opslaan is mislukt', 'Saving the prefix failed'),
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
      setSettingPrefix(false);
    }
  };

  /**
   * Lift a look-and-feel edit into builder state (spec 15 task 12.2). Pure + synchronous — it
   * updates the ONE working `lookAndFeel` map so BOTH the editor and the preview reflect the edit
   * on the very next render (Req 7.2), with NO server round-trip. An explicit `null` clears the
   * attribute (the preview then falls back to the Layer-2 default for it, Req 7.3). Values-only.
   */
  const handleLookAndFeelChange = (attribute: SupportedAttribute, value: string | null) => {
    setLookAndFeel((prev) => {
      const next = { ...prev };
      if (value === null) {
        // Clear → revert to the Layer-2 default (store null so the preview resolves the default).
        next[attribute] = null;
      } else {
        next[attribute] = value;
      }
      return next;
    });
  };

  /**
   * Persist ONE look-and-feel attribute VALUE via the Layer-1 authoring client (spec 15 task 12.2;
   * design §C3, steering 39): `setLookAndFeelSetting(attribute, value)` sends a single values-only
   * Change-Op — NEVER generated CSS, NEVER a whole record. `null` clears the attribute. On success
   * the returned resolved values re-seed the working map so the editor + preview reflect the
   * authoritative stored state. A failure surfaces the SAM edge's CALLER-SAFE error envelope as a
   * toast (422 identifying the rejected setting, 403 cross-tenant copy, 409 stale version), exactly
   * as the slug / prefix author controls surface their ApiError — no internals leak.
   */
  const handleSetLookAndFeel = async (
    attribute: SupportedAttribute,
    value: string | null,
  ) => {
    setSettingLookAndFeel(true);
    try {
      await setLookAndFeelSetting(attribute, value);
      // Persist ONLY. The optimistic local edit (applied by handleLookAndFeelChange on change) is
      // the authoritative draft and already feeds the preview; the load-time GET is the seed. We do
      // NOT re-seed the working maps from the PUT response: each response carries the slice resolved
      // AT THAT REQUEST'S MOMENT, so when edits overlap (type title, then logo, before the first PUT
      // resolves) an older-but-later-arriving response would overwrite the newer edit and snap a
      // control back to its previous value. Writing nothing back on success removes that race.
    } catch (e) {
      // Caller-safe: the backend already returns a generic, caller-safe envelope (the structured
      // ApiError message names the client's OWN rejected setting on a 422, a generic "Forbidden"
      // on a 403, a reload-and-retry on a 409) — surface it without leaking internals.
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setSettingLookAndFeel(false);
    }
  };

  /**
   * Lift a NEW-attribute look-and-feel edit (`logo`/`header_title`/`columns`) into the
   * `extraLookAndFeel` working map (bugfix `bugfix-published-form-styling`, Task 11/12). Pure +
   * synchronous. As of Task 12 these three ARE reflected in the preview: the merged
   * `previewLookAndFeel` feeds all ten to `renderPageStyles`, so an unsaved edit to logo/title/
   * columns previews live on the very next render (Req 2.6/7.2), no server round-trip. An explicit
   * `null` clears the attribute (preview reverts to the Layer-2 default). Values-only.
   */
  const handleExtraLookAndFeelChange = (attribute: ExtraAttribute, value: string | null) => {
    setExtraLookAndFeel((prev) => ({ ...prev, [attribute]: value }));
  };

  /**
   * Persist ONE NEW look-and-feel attribute VALUE via the SAME Layer-1 authoring client as the
   * seven (`setLookAndFeelSetting`): a single values-only Change-Op — NEVER generated CSS, NEVER a
   * whole record (steering 39). `null` clears the attribute. A failure surfaces the SAM edge's
   * CALLER-SAFE error envelope as a toast (422 identifying the rejected setting, 403 cross-tenant,
   * 409 stale version), exactly as the seven-attribute control does — no internals leak.
   */
  const handleSetExtraLookAndFeel = async (
    attribute: ExtraAttribute,
    value: string | null,
  ) => {
    setSettingLookAndFeel(true);
    try {
      await setLookAndFeelSetting(attribute, value);
      // Persist ONLY — no re-seed from the response (same overlap race as handleSetLookAndFeel): the
      // optimistic local edit is the authoritative draft, so an older-but-later-arriving PUT response
      // must never overwrite a newer edit. The load-time GET remains the authoritative seed.
    } catch (e) {
      // Caller-safe: the backend already returns a generic, caller-safe envelope (the structured
      // ApiError message names the client's OWN rejected setting on a 422, a generic "Forbidden"
      // on a 403, a reload-and-retry on a 409) — surface it without leaking internals.
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setSettingLookAndFeel(false);
    }
  };

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
            onSetSlug={handleSetSlug}
            settingSlug={settingSlug}
            onSetPrefix={handleSetPrefix}
            settingPrefix={settingPrefix}
            currentPrefix={fieldConfig?.public_prefix ?? null}
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
          {/* spec 15 task 12.2 — the look-and-feel editor (the seven-attribute preferences editor).
              A values-only Layer-1 authoring control: each edit lifts the VALUE into the builder's
              working `lookAndFeel` map (handleLookAndFeelChange) AND persists it one-value-at-a-time
              via the authoring client (handleSetLookAndFeel → setLookAndFeelSetting) — never CSS,
              never a whole record. The SAME working map feeds this editor AND the preview below, so
              an unsaved edit previews live (Req 7.2). Caller-safe 422/403/409 surface as toasts. */}
          <Box
            mb={4}
            pb={4}
            borderBottomWidth="1px"
            borderColor="gray.700"
            data-testid="application-form-builder-lookandfeel"
          >
            <LookAndFeelEditor
              values={lookAndFeel}
              onChange={handleLookAndFeelChange}
              onSave={handleSetLookAndFeel}
              extraValues={extraLookAndFeel}
              onExtraChange={handleExtraLookAndFeelChange}
              onExtraSave={handleSetExtraLookAndFeel}
              onUploadLogo={handleUploadLogo}
              saving={settingLookAndFeel}
              lang={lang}
            />
          </Box>
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
            // bugfix bugfix-published-form-styling Task 12 — feed the UNIFIED look-and-feel values
            // (the seven + the three new `logo`/`header_title`/`columns`) into the preview. Now
            // that `renderPageStyles` accepts all ten (Task 8), the preview reflects the three new
            // values too (`columns` drives the grid, `logo`/`header_title` render in the body), so
            // the preview matches the published form (Req 2.6). The two working maps are merged
            // here — the one SAM-owned attribute set feeds BOTH the editor and the preview.
            lookAndFeel={previewLookAndFeel}
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
            isLoading={saving || settingLookAndFeel}
            isDisabled={!dirty && !lookAndFeelDirty}
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
