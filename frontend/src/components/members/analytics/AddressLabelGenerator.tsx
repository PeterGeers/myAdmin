/**
 * AddressLabelGenerator — the Member Analytics address-label UI (C5, task 8.2).
 *
 * The ported h-dcn `AddressLabelGenerator.tsx`, generalized to be **generic +
 * multi-tenant** (R6.1): no h-dcn field literals — the address lines come from the
 * tenant's resolved `analytics.address_mapping` via the pure
 * {@link addressLabelService}. This component is only the UI shell: it collects
 * the per-run options (format, start position, sort order, font size, alignment,
 * border, country) and calls the service to build + download the PDF.
 *
 * Gating + availability:
 *   - **`members:export` (capabilities.canExport)** gates the whole generator —
 *     without it, nothing renders (R4.11, same capability as CSV/PDF export).
 *   - When the tenant's `address_mapping` is absent / unresolvable
 *     ({@link resolveAddressMapping} returns no slots), the generator is
 *     UNAVAILABLE and the shared degradation notice explains why (R4.10). CSV
 *     export stays available elsewhere regardless.
 *
 * Accessibility (R6.6): native `<select>` / `<input>` controls are
 * keyboard-navigable; the label-count / excluded-count / page-count are TEXT
 * badges (not colour-only). No hardcoded English — every label resolves from the
 * `members` namespace (`analytics.export.*`, `analytics.labels.*`,
 * `analytics.degradation.addressMappingAbsent`), bilingual via the active
 * language.
 *
 * @module components/members/analytics/AddressLabelGenerator
 * @see .kiro/specs/Members/member-analytics (design C5; requirements R4.9, R4.10, R4.11, R6.1)
 */

import React, { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Select,
  Text,
  VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type { FieldConfig, MemberRow } from '../../../types/members';
import { resolveAddressMapping } from './analyticsConfig';
import AnalyticsStateNotice from './areas/AnalyticsStateNotice';
import { recordAnalyticsOutput } from '../../../services/memberAnalyticsAuditService';
import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  MAX_FONT_SIZE,
  MIN_FONT_SIZE,
  generateAddressLabelPdf,
  getLabelFormat,
  labelsPerPage,
  type LabelAlignment,
  type LabelSortOrder,
} from './addressLabelService';

export interface AddressLabelGeneratorProps {
  /**
   * The rows the labels are generated for — the set's resolved rows within the
   * caller's scope-authorized, filtered dataset (R4.11). Never a wider set.
   */
  rows: MemberRow[];
  /** Resolved field config (incl. `analytics.address_mapping`). */
  fieldConfig: FieldConfig | null;
  /**
   * Whether the caller holds `members:export`. The generator renders ONLY when
   * `true` (R4.11); the parent also gates the surrounding actions slot.
   */
  canExport: boolean;
  /** Optional base filename for the downloaded PDF (default `address-labels`). */
  filenameBase?: string;
  /**
   * Optional audit label for the set that produced the labels (metadata only,
   * R8.1). Surfaced in the PDF-generate audit record; never member data.
   */
  setKey?: string;
}

/** Available text alignments (keeps the select options + type in lock-step). */
const ALIGNMENTS: LabelAlignment[] = ['left', 'center', 'right'];
/** Available sort orders. */
const SORT_ORDERS: LabelSortOrder[] = ['name', 'postcode', 'region'];

const AddressLabelGenerator: React.FC<AddressLabelGeneratorProps> = ({
  rows,
  fieldConfig,
  canExport,
  filenameBase = 'address-labels',
  setKey,
}) => {
  const { t } = useTypedTranslation('members');

  // The resolved address mapping decides availability (R4.10). Memoized on the
  // field config so the "unavailable" decision is stable across renders.
  const resolvedMapping = useMemo(
    () => resolveAddressMapping(fieldConfig ?? undefined),
    [fieldConfig],
  );
  const hasMapping = Object.keys(resolvedMapping).length > 0;

  // Per-run options.
  const [formatKey, setFormatKey] = useState<string>(DEFAULT_LABEL_FORMAT_KEY);
  const [sortOrder, setSortOrder] = useState<LabelSortOrder>('name');
  const [alignment, setAlignment] = useState<LabelAlignment>('left');
  const [fontSize, setFontSize] = useState<number>(10);
  const [showBorder, setShowBorder] = useState<boolean>(false);
  const [showCountry, setShowCountry] = useState<boolean>(true);
  const [startPosition, setStartPosition] = useState<number>(0);

  // Last-generation counts, surfaced as text badges (R6.6).
  const [lastResult, setLastResult] = useState<{
    labelCount: number;
    excludedCount: number;
    pages: number;
  } | null>(null);

  const selectedFormat = useMemo(
    () => getLabelFormat(formatKey) ?? AVERY_LABEL_FORMATS[0],
    [formatKey],
  );
  const maxStart = Math.max(0, labelsPerPage(selectedFormat) - 1);

  const handleGenerate = () => {
    const result = generateAddressLabelPdf(rows, fieldConfig ?? undefined, selectedFormat, {
      fontSize,
      alignment,
      showBorder,
      showCountry,
      startPosition,
      sortOrder,
    });
    setLastResult({
      labelCount: result.labelCount,
      excludedCount: result.excludedCount,
      pages: result.pages,
    });
    result.doc.save(`${filenameBase}.pdf`);

    // Audit the PDF-label generate (C7 / R8.1): metadata only — the set that
    // produced it, the label count (records printed), and the output kind. NO
    // member rows / addresses leave the client; `filter_summary` carries only the
    // generation shape (format + page/excluded counts), never member values.
    // Fire-and-forget — never blocks the download (R8.3).
    void recordAnalyticsOutput({
      outputKind: 'pdf_labels',
      setKey,
      recordCount: result.labelCount,
      filterSummary: {
        format: selectedFormat.key,
        pages: result.pages,
        excluded: result.excludedCount,
      },
    });
  };

  // `members:export` gates the whole generator (R4.11).
  if (!canExport) {
    return null;
  }

  // No resolvable address mapping → generator unavailable, with the shared
  // degradation reason (R4.10). CSV export stays available elsewhere.
  if (!hasMapping) {
    return (
      <Box data-testid="address-label-generator-unavailable">
        <AnalyticsStateNotice
          kind="degradation"
          message={t('analytics.degradation.addressMappingAbsent')}
          testId="address-label-mapping-absent"
        />
      </Box>
    );
  }

  return (
    <Box data-testid="address-label-generator">
      <VStack align="stretch" spacing={4}>
        <HStack align="flex-end" spacing={3} flexWrap="wrap">
          <FormControl maxW="xs">
            <FormLabel htmlFor="label-format" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.labels.format')}
            </FormLabel>
            <Select
              id="label-format"
              value={formatKey}
              onChange={(e) => {
                setFormatKey(e.target.value);
                setStartPosition(0);
              }}
              bg="gray.700"
              color="white"
              data-testid="label-format-select"
            >
              {AVERY_LABEL_FORMATS.map((fmt) => (
                <option key={fmt.key} value={fmt.key}>
                  {fmt.name}
                </option>
              ))}
            </Select>
          </FormControl>

          <FormControl maxW="xs">
            <FormLabel htmlFor="label-sort" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.labels.sortOrder')}
            </FormLabel>
            <Select
              id="label-sort"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as LabelSortOrder)}
              bg="gray.700"
              color="white"
              data-testid="label-sort-select"
            >
              {SORT_ORDERS.map((order) => (
                <option key={order} value={order}>
                  {t(`analytics.labels.sort.${order}`)}
                </option>
              ))}
            </Select>
          </FormControl>

          <FormControl maxW="36">
            <FormLabel htmlFor="label-start" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.labels.startPosition')}
            </FormLabel>
            <Input
              id="label-start"
              type="number"
              min={0}
              max={maxStart}
              value={startPosition}
              onChange={(e) => {
                const next = Number.parseInt(e.target.value, 10);
                setStartPosition(
                  Number.isFinite(next) ? Math.max(0, Math.min(next, maxStart)) : 0,
                );
              }}
              bg="gray.700"
              color="white"
              data-testid="label-start-input"
            />
          </FormControl>
        </HStack>

        <HStack align="flex-end" spacing={3} flexWrap="wrap">
          <FormControl maxW="xs">
            <FormLabel htmlFor="label-align" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.labels.alignment')}
            </FormLabel>
            <Select
              id="label-align"
              value={alignment}
              onChange={(e) => setAlignment(e.target.value as LabelAlignment)}
              bg="gray.700"
              color="white"
              data-testid="label-align-select"
            >
              {ALIGNMENTS.map((a) => (
                <option key={a} value={a}>
                  {t(`analytics.labels.align.${a}`)}
                </option>
              ))}
            </Select>
          </FormControl>

          <FormControl maxW="36">
            <FormLabel htmlFor="label-font" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.labels.fontSize')}
            </FormLabel>
            <Input
              id="label-font"
              type="number"
              min={MIN_FONT_SIZE}
              max={MAX_FONT_SIZE}
              value={fontSize}
              onChange={(e) => {
                const next = Number.parseInt(e.target.value, 10);
                setFontSize(Number.isFinite(next) ? next : 10);
              }}
              bg="gray.700"
              color="white"
              data-testid="label-font-input"
            />
          </FormControl>

          <Checkbox
            isChecked={showBorder}
            onChange={(e) => setShowBorder(e.target.checked)}
            color="gray.300"
            data-testid="label-border-checkbox"
          >
            {t('analytics.labels.showBorder')}
          </Checkbox>

          <Checkbox
            isChecked={showCountry}
            onChange={(e) => setShowCountry(e.target.checked)}
            color="gray.300"
            data-testid="label-country-checkbox"
          >
            {t('analytics.labels.showCountry')}
          </Checkbox>
        </HStack>

        <HStack spacing={4} align="center">
          <Button
            colorScheme="orange"
            onClick={handleGenerate}
            data-testid="label-generate"
          >
            {t('analytics.export.pdfLabels')}
          </Button>

          {/* Text badges — label / excluded / page counts (R6.6: text, not
              colour-only). Shown after a generation. */}
          {lastResult && (
            <HStack spacing={4} data-testid="label-counts">
              <Text color="gray.300" fontSize="sm" data-testid="label-count">
                {t('analytics.labels.labelCount', { count: lastResult.labelCount })}
              </Text>
              <Text color="gray.300" fontSize="sm" data-testid="label-pages">
                {t('analytics.labels.pageCount', { count: lastResult.pages })}
              </Text>
              {lastResult.excludedCount > 0 && (
                <Text color="yellow.300" fontSize="sm" data-testid="label-excluded">
                  {t('analytics.labels.excludedCount', {
                    count: lastResult.excludedCount,
                  })}
                </Text>
              )}
            </HStack>
          )}
        </HStack>
      </VStack>
    </Box>
  );
};

export default AddressLabelGenerator;
