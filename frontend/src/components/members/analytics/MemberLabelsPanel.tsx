/**
 * MemberLabelsPanel — the template-driven address-label panel hosted inside the
 * "Generate address labels" modal of {@link MemberPivotViews} (labels sub-spec
 * task 3.2, R-L2 / R-L3 / R-L4).
 *
 * The user picks a stored LABEL template (`kind:"label"`) + an Avery format,
 * tunes the shared per-run {@link LabelStyleOptions} (font size, alignment,
 * border, start position, shrink-to-fit), then Generates. On Generate the panel
 * composes the CURRENT result rows through the chosen template via
 * {@link generateLabelTemplatePdf} — which uses {@link composeLabelLines}, NOT
 * `composeAddresses`/`resolveAddressMapping`, so it reads NO `analytics.*`
 * (R6 / Property 4) — lays them onto the chosen format with the ONE shared Avery
 * generator (R-L5, no forked options shape / no second draw loop), and downloads
 * the PDF (R-L4; a Print affordance opens the blob for printing).
 *
 * It operates on `rows` (the table's current post-filter visible rows, R2/R3).
 * The label/excluded/page counts of the last run surface as the existing i18n
 * count badges. Every string resolves from the `members` namespace
 * (`analytics.labels.*`) — bilingual, no hardcoded English (steering 32).
 *
 * The template `lines` are read from the list DTO directly when present (the list
 * serializer carries `kind` + `lines`, task 0.2); only when a chosen template's
 * `lines` are somehow absent does the panel fetch the full template by id.
 *
 * @module components/members/analytics/MemberLabelsPanel
 * @see .kiro/specs/Members/pivot-output-actions/labels (design "Labels modal"; R-L2/R-L3/R-L4/R-L5)
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Checkbox,
  Divider,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Select,
  Text,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type { FieldConfig, MemberRow } from '../../../types/members';
import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  getLabelFormat,
  generateLabelTemplatePdf,
  composeLabelLines,
  labelsPerPage,
  MIN_FONT_SIZE,
  MAX_FONT_SIZE,
  type GenerateResult,
  type LabelAlignment,
  type LabelStyleOptions,
} from './addressLabelService';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';
import { groupForKey } from '../fieldValue';
import MemberTemplateManager from './MemberTemplateManager';

/** The injectable generator (defaults to the real service — a test injects a spy). */
type GenerateFn = typeof generateLabelTemplatePdf;
/** The injectable full-template loader (used only when a list DTO lacks `lines`). */
type GetTemplateFn = (
  id: string,
) => Promise<{ ok: true; data: MemberTemplateDto } | { ok: false }>;

export interface MemberLabelsPanelProps {
  /** The CURRENT (post-filter) result rows the labels are built from (R2/R3). */
  rows: MemberRow[];
  /** The field config the row accessor resolves field keys against. */
  fieldConfig: FieldConfig | undefined;
  /** The tenant's `kind:"label"` templates (already loaded + filtered). */
  templates: MemberTemplateDto[];
  /** Active language — resolves the editor's pickers. */
  language: string;
  /**
   * The fields the label lines may use — the CURRENT pivot RESULT's columns
   * (NOT the whole tenant field catalog). Each is `{ key, label }` where `key`
   * is the result row's data key (the same key {@link composeLabelLines} reads
   * via `valueFor`) and `label` is the localized header shown in the pickers.
   * Supplied by the parent from `result.columns` + its `columnLabels` map, so a
   * line can only ever reference a field that is actually in the result.
   */
  resultFields: Array<{ key: string; label: string }>;
  /** Called after the embedded editor creates/edits/deletes a template, so the
      parent can refresh the label-template list it passes in. */
  onTemplatesChanged?: () => void;
  /** Injectable generator; defaults to the real {@link generateLabelTemplatePdf}. */
  generate?: GenerateFn;
  /** Injectable full-template loader; defaults to the real `getMemberTemplate`. */
  getTemplate?: GetTemplateFn;
}

/** The alignment options the shared options model exposes. */
const ALIGNMENTS: readonly LabelAlignment[] = ['left', 'center', 'right'];
/** The selectable font sizes (the clamp band, R4.10). */
const FONT_SIZES: readonly number[] = [8, 9, 10, 11, 12];

/**
 * Resolve a chosen template's `lines`. The list DTO already carries `lines`
 * (task 0.2), so this is normally a no-op pass-through; the full-template fetch
 * is a defensive fallback for a (malformed) DTO without `lines`.
 */
async function resolveLines(
  template: MemberTemplateDto,
  getTemplate: GetTemplateFn,
): Promise<string[][]> {
  if (Array.isArray(template.lines)) {
    return template.lines;
  }
  const res = await getTemplate(template.template_id);
  if (res.ok && Array.isArray(res.data.lines)) {
    return res.data.lines;
  }
  return [];
}

const MemberLabelsPanel: React.FC<MemberLabelsPanelProps> = ({
  rows,
  fieldConfig,
  templates,
  language,
  resultFields,
  onTemplatesChanged,
  generate = generateLabelTemplatePdf,
  getTemplate,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  // Default the loader to the real service lazily so a test can inject a fake
  // without importing the service module.
  const loadTemplate = useCallback<GetTemplateFn>(
    async (id) => {
      if (getTemplate) {
        return getTemplate(id);
      }
      const { getMemberTemplate } = await import(
        '../../../services/memberTemplateService'
      );
      return getMemberTemplate(id);
    },
    [getTemplate],
  );

  // Selection state — default to the first template + the shipped default format.
  const [templateId, setTemplateId] = useState<string>(
    templates[0]?.template_id ?? '',
  );
  const [formatKey, setFormatKey] = useState<string>(DEFAULT_LABEL_FORMAT_KEY);

  // The ONE shared per-run options model (R-L5) — no forked shape. sortOrder /
  // showCountry are address-path concepts, omitted for template labels (there is
  // no name/postcode sort key to invent).
  const [fontSize, setFontSize] = useState<number>(10);
  const [alignment, setAlignment] = useState<LabelAlignment>('left');
  const [showBorder, setShowBorder] = useState<boolean>(false);
  const [autoFit, setAutoFit] = useState<boolean>(false);
  const [startPosition, setStartPosition] = useState<number>(0);

  // The last run's counts (null until the first Generate), surfaced as badges.
  const [counts, setCounts] = useState<Pick<
    GenerateResult,
    'labelCount' | 'excludedCount' | 'pages'
  > | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  // The unified template editor (MemberTemplateManager) opened from the Edit
  // button, so the user can see/change the template's LINES (incl. putting two
  // fields on one line) without leaving the labels flow.
  const [isEditorOpen, setIsEditorOpen] = useState(false);

  // The currently-selected template object (for the lines view + preview).
  const selectedTemplate = useMemo(
    () => templates.find((tpl) => tpl.template_id === templateId),
    [templates, templateId],
  );

  // A readable label for a result field key, falling back to the raw key — so the
  // lines view reads the localized header (e.g. "Postcode"), not "postal_code".
  const fieldLabel = useCallback(
    (key: string): string => resultFields.find((f) => f.key === key)?.label ?? key,
    [resultFields],
  );

  // A first-row MERGED preview of the selected template over the current rows, so
  // the user sees the ACTUAL label text (not just field names) and updates it live
  // when switching templates. Pure composeLabelLines — reads no analytics.* (R6).
  const previewLines: string[] = useMemo(() => {
    const lines = selectedTemplate?.lines;
    if (!Array.isArray(lines) || lines.length === 0 || rows.length === 0) {
      return [];
    }
    const composed = composeLabelLines([rows[0]], fieldConfig, { lines });
    return composed[0]?.lines ?? [];
  }, [selectedTemplate, rows, fieldConfig]);

  const selectedFormat = useMemo(
    () => getLabelFormat(formatKey) ?? AVERY_LABEL_FORMATS[0],
    [formatKey],
  );
  // Clamp the start position to this format's capacity (last reusable cell).
  const maxStart = Math.max(0, labelsPerPage(selectedFormat) - 1);

  const buildOptions = useCallback(
    (): LabelStyleOptions => ({
      fontSize,
      alignment,
      showBorder,
      autoFit,
      startPosition: Math.max(0, Math.min(startPosition, maxStart)),
    }),
    [fontSize, alignment, showBorder, autoFit, startPosition, maxStart],
  );

  // Build the PDF for the chosen template + format over the CURRENT rows, then
  // hand the doc to `sink` (download or print). Shared by both buttons so the
  // compose/layout path is identical.
  const runGenerate = useCallback(
    async (sink: (result: GenerateResult) => void) => {
      const template = templates.find((tpl) => tpl.template_id === templateId);
      if (!template) {
        return;
      }
      setIsGenerating(true);
      try {
        const lines = await resolveLines(template, loadTemplate);
        const result = generate(
          rows,
          fieldConfig,
          { lines },
          selectedFormat,
          buildOptions(),
        );
        setCounts({
          labelCount: result.labelCount,
          excludedCount: result.excludedCount,
          pages: result.pages,
        });
        sink(result);
      } finally {
        setIsGenerating(false);
      }
    },
    [
      templates,
      templateId,
      loadTemplate,
      generate,
      rows,
      fieldConfig,
      selectedFormat,
      buildOptions,
    ],
  );

  const handleDownload = useCallback(() => {
    void runGenerate((result) => {
      result.doc.save('member-labels.pdf');
      // Confirm the download so the action has visible feedback (the user asked:
      // "no idea what happens"). Reports the labels + pages produced.
      toast({
        title: t('analytics.labels.downloaded', {
          count: result.labelCount,
          pages: result.pages,
        }),
        status: 'success',
      });
    });
  }, [runGenerate, toast, t]);

  const handlePrint = useCallback(() => {
    void runGenerate((result) => {
      // Open the generated PDF in a new tab for printing (nice-to-have; the
      // download above is the required R-L4 path). A blocked popup is harmless.
      const url = result.doc.output('bloburl') as unknown as string;
      window.open(url, '_blank', 'noopener');
    });
  }, [runGenerate]);

  const hasTemplate = templates.length > 0 && templateId !== '';

  return (
    <VStack align="stretch" spacing={4} data-testid="member-labels-panel">
      <FormControl>
        <FormLabel htmlFor="member-pivot-labels-template">
          {t('analytics.labels.template')}
        </FormLabel>
        <Select
          id="member-pivot-labels-template"
          data-testid="member-pivot-labels-template"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          bg="gray.900"
          color="white"
        >
          {templates.map((tpl) => (
            <option key={tpl.template_id} value={tpl.template_id}>
              {tpl.name}
            </option>
          ))}
        </Select>
      </FormControl>

      {/* The selected template's CONTENT — so the user can SEE what the template
          lays out (incl. which fields share a line) and update it live when they
          switch templates. Plus an Edit button into the line editor. */}
      {selectedTemplate && (
        <Box
          bg="gray.900"
          borderRadius="md"
          px={3}
          py={2}
          data-testid="member-pivot-labels-template-view"
        >
          <HStack justify="space-between" mb={1}>
            <Text fontSize="sm" fontWeight="semibold" color="gray.300">
              {t('analytics.labels.linesTitle')}
            </Text>
            <Button
              size="xs"
              variant="outline"
              colorScheme="orange"
              onClick={() => setIsEditorOpen(true)}
              data-testid="member-pivot-labels-edit"
            >
              {t('analytics.labels.edit')}
            </Button>
          </HStack>
          {/* Each line = its field keys resolved to readable labels, space-joined
              exactly as they will render (two fields on a line show together). */}
          <VStack align="stretch" spacing={0} data-testid="member-pivot-labels-lines">
            {(selectedTemplate.lines ?? []).map((line, i) => (
              <Text key={i} fontSize="sm" color="white">
                {line.length > 0
                  ? line.map((k) => fieldLabel(k)).join(' ')
                  : t('analytics.labels.emptyLine')}
              </Text>
            ))}
          </VStack>

          {/* First-row MERGED preview — the ACTUAL label text for the first result
              member, so the user sees real content, not just field names. */}
          {previewLines.length > 0 && (
            <>
              <Divider my={2} borderColor="gray.600" />
              <Text fontSize="xs" fontWeight="semibold" color="gray.400" mb={1}>
                {t('analytics.labels.previewTitle')}
              </Text>
              <Box
                borderWidth="1px"
                borderColor="gray.500"
                borderRadius="sm"
                px={2}
                py={1}
                data-testid="member-pivot-labels-preview"
              >
                {previewLines.map((line, i) => (
                  <Text key={i} fontSize="sm" color="white">
                    {line}
                  </Text>
                ))}
              </Box>
            </>
          )}
        </Box>
      )}

      <FormControl>
        <FormLabel htmlFor="member-pivot-labels-format">
          {t('analytics.labels.format')}
        </FormLabel>
        <Select
          id="member-pivot-labels-format"
          data-testid="member-pivot-labels-format"
          value={formatKey}
          onChange={(e) => {
            setFormatKey(e.target.value);
            // A new format has a different capacity — reset the start position so
            // a stale offset never exceeds the new sheet.
            setStartPosition(0);
          }}
          bg="gray.900"
          color="white"
        >
          {AVERY_LABEL_FORMATS.map((fmt) => (
            <option key={fmt.key} value={fmt.key}>
              {fmt.name}
            </option>
          ))}
        </Select>
      </FormControl>

      <HStack align="start" spacing={4}>
        <FormControl>
          <FormLabel htmlFor="member-pivot-labels-font">
            {t('analytics.labels.fontSize')}
          </FormLabel>
          <Select
            id="member-pivot-labels-font"
            data-testid="member-pivot-labels-font"
            value={fontSize}
            onChange={(e) => setFontSize(Number(e.target.value))}
            bg="gray.900"
            color="white"
          >
            {FONT_SIZES.filter(
              (size) => size >= MIN_FONT_SIZE && size <= MAX_FONT_SIZE,
            ).map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </Select>
        </FormControl>

        <FormControl>
          <FormLabel htmlFor="member-pivot-labels-align">
            {t('analytics.labels.alignment')}
          </FormLabel>
          <Select
            id="member-pivot-labels-align"
            data-testid="member-pivot-labels-align"
            value={alignment}
            onChange={(e) => setAlignment(e.target.value as LabelAlignment)}
            bg="gray.900"
            color="white"
          >
            {ALIGNMENTS.map((a) => (
              <option key={a} value={a}>
                {t(`analytics.labels.align.${a}`)}
              </option>
            ))}
          </Select>
        </FormControl>

        <FormControl>
          <FormLabel htmlFor="member-pivot-labels-start">
            {t('analytics.labels.startPosition')}
          </FormLabel>
          <Input
            id="member-pivot-labels-start"
            data-testid="member-pivot-labels-start"
            type="number"
            min={0}
            max={maxStart}
            value={startPosition}
            onChange={(e) => {
              const next = Number(e.target.value);
              setStartPosition(
                Number.isFinite(next) ? Math.max(0, Math.min(next, maxStart)) : 0,
              );
            }}
            bg="gray.900"
            color="white"
          />
        </FormControl>
      </HStack>

      <HStack spacing={6}>
        <Checkbox
          data-testid="member-pivot-labels-border"
          isChecked={showBorder}
          onChange={(e) => setShowBorder(e.target.checked)}
        >
          {t('analytics.labels.showBorder')}
        </Checkbox>
        <Checkbox
          data-testid="member-pivot-labels-autofit"
          isChecked={autoFit}
          onChange={(e) => setAutoFit(e.target.checked)}
        >
          {t('analytics.labels.autoFit')}
        </Checkbox>
      </HStack>

      <HStack spacing={3}>
        <Button
          colorScheme="orange"
          onClick={handleDownload}
          isDisabled={!hasTemplate}
          isLoading={isGenerating}
          data-testid="member-pivot-labels-generate"
        >
          {t('analytics.labels.download')}
        </Button>
        <Button
          variant="outline"
          onClick={handlePrint}
          isDisabled={!hasTemplate}
          isLoading={isGenerating}
          data-testid="member-pivot-labels-print"
        >
          {t('analytics.labels.print')}
        </Button>
      </HStack>

      {counts !== null && (
        <Box data-testid="member-pivot-labels-counts">
          <Text fontSize="sm" color="gray.300">
            {t('analytics.labels.labelCount', { count: counts.labelCount })}
            {' · '}
            {t('analytics.labels.pageCount', { count: counts.pages })}
            {counts.excludedCount > 0 && (
              <>
                {' · '}
                {t('analytics.labels.excludedCount', { count: counts.excludedCount })}
              </>
            )}
          </Text>
        </Box>
      )}

      {/* The unified template editor (see/change the LINES — incl. putting two
          fields on one line). Opened from the Edit button; it offers ONLY the
          current result's columns (`resultFields`, R6). On any change it calls
          onTemplatesChanged so the parent refreshes the picked list. */}
      <MemberTemplateManager
        isOpen={isEditorOpen}
        onClose={() => setIsEditorOpen(false)}
        language={language}
        resultFields={resultFields}
        onTemplatesChanged={onTemplatesChanged}
      />
    </VStack>
  );
};

export default MemberLabelsPanel;
