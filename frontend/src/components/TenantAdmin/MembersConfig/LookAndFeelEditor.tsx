/**
 * Look-and-feel editor — the Layer-1 preferences editor for the Application Form Builder
 * (spec 15 — SAM Page Look-and-Feel, task 12.2; design §C3, DD-2/DD-3).
 *
 * The admin-facing control that closes the steering-40 all-planes gap: the backend
 * (`sam/members` Layer-1 service + routes), the stored `look_and_feel` slice, and the preview
 * Layer-2 React mirror all exist and are tested, but there was NO admin UI to author the values.
 * This component is that UI — the seven-attribute preferences editor mounted as a panel/slot in
 * `ApplicationFormBuilder.tsx`.
 *
 * ## Values-only, never CSS, never a whole record (design §C3 / steering 39)
 *
 * The editor authors the SEVEN supported attributes (`color_primary`, `color_accent`,
 * `font_heading`, `font_body`, `base_spacing`, `border_radius_global`, `shadow_style`) as
 * VALUES. It is a CONTROLLED component: it never owns the network write and never generates CSS.
 *
 *  - every edit lifts the new VALUE up via `onChange` so the builder can feed it to BOTH this
 *    editor and the `ApplicationFormPreview lookAndFeel` prop — an unsaved edit previews live
 *    (Req 7.2), with no server round-trip; and
 *  - a deliberate persist calls `onSave(attribute, value)` (a `null` value clears the attribute,
 *    reverting it to the Layer-2 default). The builder wires `onSave` to
 *    `setLookAndFeelSetting` and surfaces the caller-safe error envelope (422 identifying the
 *    rejected setting, 403 cross-tenant copy, 409 stale version) exactly as it surfaces slug /
 *    prefix author errors (ApiError → toast).
 *
 * The permitted enum values + defaults come from the SAME `pageStyles.ts` the preview and (via
 * the Python mirror) the publish step use (`SUPPORTED_ATTRIBUTES`, the enum maps, `DEFAULTS`), so
 * the editor, the preview, and the server generator cannot drift.
 *
 * ## Accessibility + i18n (steering 33 / NFR — WCAG 2.2 AA)
 *
 * Every control has an accessible name via Chakra `FormControl` + `FormLabel` association; the
 * two colour controls pair a native colour `<input type="color">` with a text input so the value
 * is both pickable and typeable. Labels are bilingual via the builder's `t(nl, en)` helper.
 */
import React, { useRef, useState } from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Image,
  Heading,
  Input,
  Select,
  Text,
  VStack,
} from '@chakra-ui/react';
import {
  DEFAULTS,
  type LookAndFeelSettings,
  type SupportedAttribute,
} from './pageStyles';

/** The shape the editor reads/writes: the seven supported attributes, VALUES only. */
export type LookAndFeelValues = Partial<Record<SupportedAttribute, string | null>>;

/**
 * The three VALUES-ONLY attributes the bugfix `bugfix-published-form-styling` adds (bugfix 3.4 /
 * design §C) — authored here but kept SEPARATE from the seven {@link SupportedAttribute} the
 * preview path renders (`pageStyles.renderPageStyles` only knows the seven until that plane is
 * extended, so routing these three through the preview map would reject). They persist via the
 * SAME values-only `setLookAndFeelSetting` Change-Op path as the seven — never CSS, never a whole
 * record (steering 39):
 *
 *  - `logo`         — a URL / asset reference to the tenant logo;
 *  - `header_title` — the form header/title text (length-bounded, HTML-escaped on render); and
 *  - `columns`      — a bounded column-count (1..4, matching the service/generator clamp).
 */
export type ExtraAttribute = 'logo' | 'header_title' | 'columns';

/** The VALUES for the three new attributes (values-only; never CSS). */
export type ExtraLookAndFeelValues = Partial<Record<ExtraAttribute, string | null>>;

/** SAM-owned defaults for the three new attributes — mirror of the Python `_DEFAULTS`. */
const EXTRA_DEFAULTS: Readonly<Record<ExtraAttribute, string>> = {
  logo: '',
  header_title: '',
  columns: '2',
};

/** Permitted column counts — mirror of the service/generator clamp (`1 .. _MAX_FORM_COLUMNS`). */
const COLUMN_OPTIONS = ['1', '2', '3', '4'] as const;

/** The upper bound on the header/title length — mirror of the service `_MAX_HEADER_TITLE_LENGTH`. */
const MAX_HEADER_TITLE_LENGTH = 200;

/**
 * One enum attribute's permitted option set, sourced from the same enum maps `pageStyles.ts`
 * uses so the editor can only ever offer a value the Layer-2 generator accepts. Keys are the
 * permitted values; the bilingual label renders the choice.
 */
interface EnumOption {
  value: string;
  nl: string;
  en: string;
}

/** `base_spacing` permitted values — mirror of the pageStyles `SPACING_MAP` keys. */
const SPACING_OPTIONS: EnumOption[] = [
  { value: 'compact', nl: 'Compact', en: 'Compact' },
  { value: 'normal', nl: 'Normaal', en: 'Normal' },
  { value: 'relaxed', nl: 'Ruim', en: 'Relaxed' },
];

/** `border_radius_global` permitted values — mirror of the pageStyles `GLOBAL_RADIUS_MAP` keys. */
const RADIUS_OPTIONS: EnumOption[] = [
  { value: 'sharp', nl: 'Scherp', en: 'Sharp' },
  { value: 'rounded', nl: 'Afgerond', en: 'Rounded' },
  { value: 'pill', nl: 'Pil', en: 'Pill' },
];

/** `shadow_style` permitted values — mirror of the pageStyles `SHADOW_MAP` keys. */
const SHADOW_OPTIONS: EnumOption[] = [
  { value: 'none', nl: 'Geen', en: 'None' },
  { value: 'subtle', nl: 'Subtiel', en: 'Subtle' },
  { value: 'medium', nl: 'Gemiddeld', en: 'Medium' },
  { value: 'dramatic', nl: 'Sterk', en: 'Dramatic' },
];

/**
 * `font_heading` / `font_body` permitted values — `system` (the default stack) plus a small set
 * of web fonts. `system` is NOT a web font (no stylesheet is loaded); any other value is passed
 * to the Layer-2 generator as a Google-Fonts family (mirrors `pageStyles.buildFontLinks`).
 */
const FONT_OPTIONS: EnumOption[] = [
  { value: 'system', nl: 'Systeem', en: 'System' },
  { value: 'Inter', nl: 'Inter', en: 'Inter' },
  { value: 'Roboto', nl: 'Roboto', en: 'Roboto' },
  { value: 'Lora', nl: 'Lora', en: 'Lora' },
  { value: 'Merriweather', nl: 'Merriweather', en: 'Merriweather' },
];

export interface LookAndFeelEditorProps {
  /**
   * The current WORKING look-and-feel values (the builder's state, seeded from
   * `getLookAndFeelSettings` and updated by this editor's `onChange`). An absent attribute shows
   * its Layer-2 default so the control always reflects what publish would bake (Req 7.3).
   */
  values: LookAndFeelValues;
  /**
   * Lift a changed VALUE up to the builder (values-only). The builder stores it so BOTH this
   * editor and the `ApplicationFormPreview lookAndFeel` prop reflect the unsaved edit live
   * (Req 7.2). `null` clears the attribute (revert to the Layer-2 default).
   */
  onChange: (attribute: SupportedAttribute, value: string | null) => void;
  /**
   * Persist ONE attribute VALUE via the authoring client (values-only Change-Op). The builder
   * wires this to `setLookAndFeelSetting(attribute, value)` and surfaces the caller-safe error
   * envelope (422/403/409) as a toast. `null` clears the attribute.
   */
  onSave: (attribute: SupportedAttribute, value: string | null) => void;
  /**
   * The current WORKING values for the three NEW attributes (`logo`/`header_title`/`columns`).
   * Kept SEPARATE from {@link values} because the preview path renders only the seven today; an
   * absent attribute shows its SAM-owned default so the control never renders blank.
   */
  extraValues?: ExtraLookAndFeelValues;
  /** Lift a changed NEW-attribute VALUE up to the builder (values-only). `null` clears it. */
  onExtraChange?: (attribute: ExtraAttribute, value: string | null) => void;
  /**
   * Persist ONE NEW attribute VALUE via the authoring client (values-only Change-Op) — the SAME
   * `setLookAndFeelSetting` path as {@link onSave}. The builder surfaces the caller-safe error
   * envelope (422/403/409) as a toast. `null` clears the attribute.
   */
  onExtraSave?: (attribute: ExtraAttribute, value: string | null) => void;
  /**
   * Persist ALL current look-and-feel values at once (the explicit Save action). The builder
   * commits the whole working map (seven + the three extras) in one pass and surfaces the result.
   * Optional so existing per-field callers keep working; when provided, the editor shows a Save
   * button so persisting is an obvious, deliberate action rather than an invisible blur-save.
   */
  onSaveAll?: () => void | Promise<void>;
  /**
   * Upload a new logo image: stores it (tenant-scoped S3, via the builder's reuse of the existing
   * image-upload path) and returns the stored public URL, which the control sets as the `logo`
   * value. When omitted, the control is paste-only. The persist still happens on the single Save.
   */
  onUploadLogo?: (file: File) => Promise<string>;
  /** Whether a look-and-feel persist is in flight (disables the controls + shows a loading state). */
  saving?: boolean;
  lang: 'nl' | 'en';
}

/**
 * Resolve the control's current display value for an attribute: the working value when set, else
 * the SAM-owned default (so the control never renders blank and always shows what publish bakes).
 */
function current(values: LookAndFeelValues, attribute: SupportedAttribute): string {
  const v = values[attribute];
  return v === undefined || v === null ? DEFAULTS[attribute] : String(v);
}

export const LookAndFeelEditor: React.FC<LookAndFeelEditorProps> = ({
  values,
  onChange,
  onSave,
  extraValues,
  onExtraChange,
  onExtraSave,
  onSaveAll,
  onUploadLogo,
  saving,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // Logo upload state (reuses the builder's `onUploadLogo` — the existing tenant-scoped S3 path).
  const logoFileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [logoError, setLogoError] = useState<string | null>(null);

  const onPickLogoFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file || !onUploadLogo) return;
    setLogoError(null);
    setUploadingLogo(true);
    try {
      await onUploadLogo(file); // the builder lifts the stored URL into the `logo` value
    } catch (err) {
      setLogoError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploadingLogo(false);
    }
  };

  /**
   * Lift an edit up for LIVE PREVIEW only (no network). Used on every keystroke of a free-text /
   * colour control so the preview tracks the edit without a per-keystroke persist.
   */
  const changeOnly = (attribute: SupportedAttribute, value: string | null) => {
    onChange(attribute, value);
  };

  /**
   * COMMIT one edit: lift it up AND persist it (values-only). Used for atomic controls (selects,
   * the native colour picker) on change, and for free-text / colour-hex inputs on BLUR — so a
   * multi-character value is persisted ONCE, when the user is done, not per keystroke.
   */
  const commit = (attribute: SupportedAttribute, value: string | null) => {
    onChange(attribute, value);
    onSave(attribute, value);
  };

  /**
   * All controls are EDIT-ONLY: they lift the value for the LIVE PREVIEW and never touch the
   * network. Persisting is done ONCE, deliberately, via the Save button (`onSaveAll`) — never
   * per keystroke, per change, or per blur. This is the right model for a serverless edge
   * (one batched Change-Op pass on Save, not a Lambda+DynamoDB write per interaction).
   */
  const edit = changeOnly;
  // `commit`/`onSave` are retained for callers that still want per-attribute persistence, but the
  // editor itself no longer calls them — Save is the single write path.
  void commit;

  /**
   * Resolve a NEW-attribute control's display value: the working value when set, else its
   * SAM-owned default (so the control never renders blank).
   */
  const currentExtra = (attribute: ExtraAttribute): string => {
    const v = extraValues?.[attribute];
    return v === undefined || v === null ? EXTRA_DEFAULTS[attribute] : String(v);
  };

  /**
   * Apply + persist one NEW-attribute edit via the SAME values-only Change-Op path as `edit`.
   * The three new attributes do NOT feed the preview map today (that plane renders only the
   * seven), so only the extra working map + the persist are driven here. An empty string on
   * `logo`/`header_title` CLEARS the attribute (persist `null`) so the control can revert to the
   * SAM-owned default; `columns` always carries a bounded value.
   */
  const normalizeExtra = (attribute: ExtraAttribute, raw: string): string | null =>
    (attribute === 'logo' || attribute === 'header_title') && raw.trim() === '' ? null : raw;

  /** Lift a NEW-attribute edit for LIVE PREVIEW only (no network) — used on keystroke. */
  const changeExtraOnly = (attribute: ExtraAttribute, raw: string) => {
    onExtraChange?.(attribute, normalizeExtra(attribute, raw));
  };

  /** COMMIT a NEW-attribute edit: lift + persist (values-only). Selects on change; text on blur. */
  const commitExtra = (attribute: ExtraAttribute, raw: string) => {
    const value = normalizeExtra(attribute, raw);
    onExtraChange?.(attribute, value);
    onExtraSave?.(attribute, value);
  };

  /** Edit-only for the extra controls too: preview on change, persist only via Save. */
  const editExtra = changeExtraOnly;
  void commitExtra;

  /** A labelled enum <select> for one attribute (shared across spacing/radius/shadow/font). */
  const renderEnum = (
    attribute: SupportedAttribute,
    labelNl: string,
    labelEn: string,
    options: EnumOption[],
  ) => (
    <FormControl>
      <FormLabel htmlFor={`lookandfeel-${attribute}`} fontSize="sm" color="gray.300">
        {t(labelNl, labelEn)}
      </FormLabel>
      <Select
        id={`lookandfeel-${attribute}`}
        data-testid={`lookandfeel-${attribute}`}
        size="sm"
        value={current(values, attribute)}
        onChange={(e) => edit(attribute, e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {t(o.nl, o.en)}
          </option>
        ))}
      </Select>
    </FormControl>
  );

  /**
   * A labelled colour control for one attribute: a native colour picker paired with a text input
   * (both author the SAME value) so the colour is pickable AND typeable. The hex value is the
   * authored value (never generated CSS).
   */
  const renderColor = (
    attribute: 'color_primary' | 'color_accent',
    labelNl: string,
    labelEn: string,
  ) => {
    const value = current(values, attribute);
    return (
      <FormControl>
        <FormLabel htmlFor={`lookandfeel-${attribute}`} fontSize="sm" color="gray.300">
          {t(labelNl, labelEn)}
        </FormLabel>
        <HStack>
          <Input
            id={`lookandfeel-${attribute}`}
            data-testid={`lookandfeel-${attribute}`}
            type="color"
            size="sm"
            w="3rem"
            p={0}
            value={value}
            onChange={(e) => commit(attribute, e.target.value)}
            // A visible FormLabel is associated above; the colour swatch needs its own name too.
            aria-label={t(labelNl, labelEn)}
          />
          <Input
            data-testid={`lookandfeel-${attribute}-hex`}
            size="sm"
            value={value}
            onChange={(e) => changeOnly(attribute, e.target.value)}
            aria-label={t(`${labelNl} (hex)`, `${labelEn} (hex)`)}
          />
        </HStack>
      </FormControl>
    );
  };

  return (
    <VStack align="stretch" spacing={3} data-testid="lookandfeel-editor">
      <Box>
        <Heading size="sm" color="gray.300">
          {t('Uiterlijk', 'Look and feel')}
        </Heading>
        <Text fontSize="sm" color="gray.500">
          {t(
            'Stel de stijl van het gepubliceerde formulier in. Wijzigingen verschijnen direct in het voorbeeld.',
            'Set the style of the published form. Changes appear instantly in the preview.',
          )}
        </Text>
      </Box>

      {renderColor('color_primary', 'Primaire kleur', 'Primary colour')}
      {renderColor('color_accent', 'Accentkleur', 'Accent colour')}
      {renderEnum('font_heading', 'Kopletter­type', 'Heading font', FONT_OPTIONS)}
      {renderEnum('font_body', 'Bodyletter­type', 'Body font', FONT_OPTIONS)}
      {renderEnum('base_spacing', 'Witruimte', 'Spacing', SPACING_OPTIONS)}
      {renderEnum('border_radius_global', 'Hoekafronding', 'Corner rounding', RADIUS_OPTIONS)}
      {renderEnum('shadow_style', 'Schaduw', 'Shadow', SHADOW_OPTIONS)}

      {/*
        The three VALUES-ONLY attributes the bugfix `bugfix-published-form-styling` adds
        (bugfix 3.4 / design §C): a tenant logo (URL/asset reference), a form header/title, and
        the number of columns. They persist via the SAME values-only `setLookAndFeelSetting`
        Change-Op path as the seven above — never CSS, never a whole record (steering 39). The
        logo/title default to EMPTY (= absent → no logo / no heading) and clear when blanked.
      */}
      <FormControl>
        <FormLabel htmlFor="lookandfeel-logo" fontSize="sm" color="gray.300">
          {t('Logo', 'Logo')}
        </FormLabel>
        {/* Preview of the currently-referenced logo (the stored S3 URL or a pasted one). */}
        {currentExtra('logo').trim() !== '' && (
          <Image
            src={currentExtra('logo')}
            alt={t('Huidig logo', 'Current logo')}
            data-testid="lookandfeel-logo-preview"
            maxH="64px"
            mb={2}
            objectFit="contain"
            bg="gray.800"
            p={1}
            borderRadius="md"
            fallback={
              <Text fontSize="xs" color="red.300" data-testid="lookandfeel-logo-broken">
                {t('Logo kon niet worden geladen', 'Logo could not be loaded')}
              </Text>
            }
          />
        )}
        <HStack align="stretch">
          <Input
            id="lookandfeel-logo"
            data-testid="lookandfeel-logo"
            size="sm"
            type="url"
            inputMode="url"
            placeholder="https://…/logo.png"
            value={currentExtra('logo')}
            onChange={(e) => changeExtraOnly('logo', e.target.value)}
            aria-label={t('Logo-URL', 'Logo URL')}
          />
          {onUploadLogo && (
            <>
              <input
                ref={logoFileInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                data-testid="lookandfeel-logo-file"
                onChange={onPickLogoFile}
              />
              <Button
                size="sm"
                flexShrink={0}
                onClick={() => logoFileInputRef.current?.click()}
                isLoading={uploadingLogo}
                loadingText={t('Uploaden…', 'Uploading…')}
                data-testid="lookandfeel-logo-upload"
              >
                {t('Uploaden', 'Upload')}
              </Button>
            </>
          )}
        </HStack>
        {logoError && (
          <Text fontSize="xs" color="red.300" mt={1} data-testid="lookandfeel-logo-error">
            {logoError}
          </Text>
        )}
      </FormControl>

      <FormControl>
        <FormLabel htmlFor="lookandfeel-header_title" fontSize="sm" color="gray.300">
          {t('Koptekst / titel', 'Header / title')}
        </FormLabel>
        <Input
          id="lookandfeel-header_title"
          data-testid="lookandfeel-header_title"
          size="sm"
          maxLength={MAX_HEADER_TITLE_LENGTH}
          value={currentExtra('header_title')}
          onChange={(e) => changeExtraOnly('header_title', e.target.value)}
          aria-label={t('Koptekst van het formulier', 'Form header title')}
        />
      </FormControl>

      <FormControl>
        <FormLabel htmlFor="lookandfeel-columns" fontSize="sm" color="gray.300">
          {t('Aantal kolommen', 'Number of columns')}
        </FormLabel>
        <Select
          id="lookandfeel-columns"
          data-testid="lookandfeel-columns"
          size="sm"
          value={currentExtra('columns')}
          onChange={(e) => editExtra('columns', e.target.value)}
        >
          {COLUMN_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </Select>
      </FormControl>

      <Text color="gray.500" fontSize="xs">
        {t(
          'Wijzigingen verschijnen direct in het voorbeeld. Klik op Opslaan om ze op te slaan voor dit formulier.',
          'Changes appear instantly in the preview. Click Save to store them for this form.',
        )}
      </Text>

      <HStack justify="flex-end">
        {onSaveAll && (
          <Button
            size="sm"
            colorScheme="orange"
            onClick={() => void onSaveAll()}
            isLoading={saving}
            loadingText={t('Opslaan…', 'Saving…')}
            data-testid="lookandfeel-editor-save"
          >
            {t('Opslaan', 'Save')}
          </Button>
        )}
        {!onSaveAll && saving && (
          <Button
            size="sm"
            variant="ghost"
            isLoading
            loadingText={t('Opslaan…', 'Saving…')}
            data-testid="lookandfeel-editor-saving"
          >
            {t('Opslaan…', 'Saving…')}
          </Button>
        )}
      </HStack>
    </VStack>
  );
};

export default LookAndFeelEditor;
