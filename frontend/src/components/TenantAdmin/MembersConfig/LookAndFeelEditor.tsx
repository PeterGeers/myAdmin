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
import React from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
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
  saving,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  /** Apply + persist one edit: lift it up (live preview) THEN persist it (values-only). */
  const edit = (attribute: SupportedAttribute, value: string | null) => {
    onChange(attribute, value);
    onSave(attribute, value);
  };

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
        isDisabled={saving}
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
            isDisabled={saving}
            onChange={(e) => edit(attribute, e.target.value)}
            // A visible FormLabel is associated above; the colour swatch needs its own name too.
            aria-label={t(labelNl, labelEn)}
          />
          <Input
            data-testid={`lookandfeel-${attribute}-hex`}
            size="sm"
            value={value}
            isDisabled={saving}
            onChange={(e) => edit(attribute, e.target.value)}
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

      <Text color="gray.500" fontSize="xs">
        {t(
          'Een wijziging wordt meteen opgeslagen voor dit formulier.',
          'A change is saved for this form immediately.',
        )}
      </Text>

      <HStack justify="flex-end">
        {saving && (
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
