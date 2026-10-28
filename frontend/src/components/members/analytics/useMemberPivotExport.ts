/**
 * useMemberPivotExport — the produced-result EXPORT concerns of the Pivot Views
 * panel, extracted from `MemberPivotViews.tsx` (code-quality split 2026-10-28,
 * task 5).
 *
 * This hook carries ZERO behaviour change: it is the verbatim result/export
 * logic the panel held inline — the localized result-column header map
 * (`columnLabels`), the export row set (`exportRows` = the table's post-filter
 * visible rows else the full result), the CSV download (`handleExportCsv`,
 * REUSING `csvExport.ts`), the "Send CSV by email" dialog state + send
 * (`handleSendCsvMail`), the base64 CSV builder for the mail-compose attach
 * toggle (`buildCsvBase64`), and the two content gates the result-actions slot
 * reads: the labels-action gate (`canGenerateLabels` = members:export + ≥1 label
 * template) and the tenant mail gate (`mailEnabled`).
 *
 * All of it stays driven by the same inputs the component already had, so the
 * public component API and every rendered testid / i18n key are unchanged.
 *
 * @module components/members/analytics/useMemberPivotExport
 */

import { useCallback, useMemo, useRef, useState, type RefObject } from 'react';
import { useToast } from '@chakra-ui/react';
import type { PivotConfig, PivotResult } from '../../../types/pivot';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import {
  sendAdHocMail,
  type AdHocMailBody,
} from '../../../services/membersApiService';
import { applyApiError } from '../../../shared/api/applyApiError';
import { generateCsvFromObjects, downloadCsv, exportFileName } from '../../../utils/csvExport';
import { recordAnalyticsOutput } from '../../../services/memberAnalyticsAuditService';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';
import type { MemberAnalyticsCapabilities } from './areas/types';
import type { SelectableSet } from './memberPivotViewsHelpers';
import { resolveLabel, parseAggregateName } from './memberPivotViewsHelpers';

/** The members-namespace translator (key + optional interpolation bag → string). */
type TFunction = (key: string, options?: Record<string, unknown>) => string;

export interface UseMemberPivotExportArgs {
  result: PivotResult | null;
  resultConfig: PivotConfig | null;
  selectedSet: SelectableSet | undefined;
  fieldConfig: FieldConfig | null;
  language: string;
  capabilities: MemberAnalyticsCapabilities;
  labelTemplates: MemberTemplateDto[];
  currentTenant: string | null;
  /** The result table's post-filter visible rows (reported via onVisibleRowsChange). */
  visibleRows: Record<string, unknown>[];
  t: TFunction;
}

export interface UseMemberPivotExport {
  columnLabels: Record<string, string>;
  exportRows: Record<string, unknown>[];
  mailEnabled: boolean;
  canGenerateLabels: boolean;
  buildCsvBase64: () => string | null;
  handleExportCsv: () => void;
  // Send-CSV-by-email dialog
  isCsvMailOpen: boolean;
  setIsCsvMailOpen: (open: boolean) => void;
  csvMailTo: string;
  setCsvMailTo: (value: string) => void;
  csvMailSending: boolean;
  csvMailValid: boolean;
  csvMailCancelRef: RefObject<HTMLButtonElement | null>;
  handleOpenCsvMail: () => void;
  handleSendCsvMail: () => Promise<void>;
}

/**
 * The produced-result export bundle for the Pivot Views panel. Keeps all the
 * export state + handlers cohesive and out of the (very large) component body,
 * without changing any observable behaviour.
 */
export function useMemberPivotExport({
  result,
  resultConfig,
  selectedSet,
  fieldConfig,
  language,
  capabilities,
  labelTemplates,
  currentTenant,
  visibleRows,
  t,
}: UseMemberPivotExportArgs): UseMemberPivotExport {
  const toast = useToast();

  // The HEADER label map for the result table (issue 4 — "result column headers
  // stay English"). The pivot result's `columns[].name` is the raw field key or
  // an aggregate expression (`COUNT(*)`, `SUM(age)`); PivotResultTable renders it
  // verbatim, so a Dutch tenant sees English keys. Build a name→label map from
  // the field config (bilingual, resolved to the active language) for every
  // group/list column, and a readable localized label for each aggregate column
  // ("Aantal" / "Count", "Som (Leeftijd)" / "Sum (Age)"). Passed ONLY to the
  // member result table — FIN/STR omit the prop and keep raw DB keys unchanged.
  const columnLabels = useMemo<Record<string, string>>(() => {
    if (!resultConfig) {
      return {};
    }
    const lang = (language || 'nl').slice(0, 2);
    const byKey = new Map<string, FieldConfigField>();
    for (const f of fieldConfig?.fields ?? []) {
      if (f && typeof f.key === 'string' && f.key !== '') {
        byKey.set(f.key, f);
      }
    }
    const labelForKey = (key: string): string =>
      resolveLabel(byKey.get(key)?.label, lang, key);

    const map: Record<string, string> = {};
    for (const col of result?.columns ?? []) {
      const agg = parseAggregateName(col.name);
      if (col.type === 'aggregate' && agg) {
        // Localize the function (COUNT → Aantal/Count) and, for a column-scoped
        // aggregate, append the inner field's label: "Som (Leeftijd)".
        const fnLabel = t(`analytics.pivotViews.aggregates.${agg.fn}`);
        map[col.name] =
          agg.inner === '' || agg.inner === '*'
            ? fnLabel
            : `${fnLabel} (${labelForKey(agg.inner)})`;
      } else {
        map[col.name] = labelForKey(col.name);
      }
    }
    return map;
  }, [result, resultConfig, fieldConfig, language, t]);

  // The rows every export operates on: the table's VISIBLE (post-filter/sort)
  // rows when the table has reported them, else the full result. This is what
  // makes an export honor the in-table column filters (findings: "table filters
  // do not limit the export") — the table reports its filtered rows via
  // onVisibleRowsChange below, and CSV / mail / PDF all read THESE rows.
  const exportRows = useMemo<Record<string, unknown>[]>(
    () => (visibleRows.length > 0 ? visibleRows : (result?.data ?? [])),
    [visibleRows, result],
  );

  // CSV export of the produced result (task 8.1, R4.9/R4.11). REUSES
  // `csvExport.ts` — no bespoke CSV. The produced `PivotResult` is mapped onto
  // the util's `{ key, header }[]` + object-rows shape: a result column's `name`
  // is BOTH the key the util reads from each `data` row AND the header, so the
  // same mapping serves an AGGREGATE result (group + aggregate columns) and a
  // filtered-LIST result (one row per member, R4.11) without special-casing.
  // Gated by `capabilities.canExport` (members:export) at the slot below; this
  // handler is a no-op if there is no result to export.
  const handleExportCsv = useCallback(() => {
    if (!result || result.columns.length === 0) {
      return;
    }
    // The CSV HEADER uses the localized column label (same `columnLabels` map the
    // result table renders — Dutch/English per the active language); the KEY
    // stays the raw result column name so values still read from each data row.
    const columns = result.columns.map((col) => ({
      key: col.name,
      header: columnLabels[col.name] ?? col.name,
    }));
    const csv = generateCsvFromObjects(columns, exportRows);
    // Name the download by the SELECTED pivot/set via the shared tenant-pivot
    // rule (`{Tenant}-{Pivot}.csv`) instead of the old fixed `member-analytics.csv`.
    // An ad-hoc pivot with no named set falls back to the generic `member-analytics`
    // pivot label so the filename is still deterministic and never the fixed name.
    const pivotName = selectedSet?.label || 'member-analytics';
    downloadCsv(csv, exportFileName(currentTenant ?? '', pivotName));

    // Audit the export (C7 / R8.1): metadata only — the set that produced it, the
    // row count, and the output kind. NO member rows / PII leave the client; the
    // `filter_summary` carries only the shape of the result (column count), never
    // the filtered values. Fire-and-forget — never blocks the download (R8.3).
    void recordAnalyticsOutput({
      outputKind: 'csv_export',
      setKey: selectedSet?.optionValue,
      recordCount: exportRows.length,
      filterSummary: { columns: result.columns.length },
    });
  }, [result, selectedSet, exportRows, currentTenant, columnLabels]);

  // --- "Send CSV by email" (Export-CSV menu, pivot-output-actions C5) --------
  // The Export action is a MENU: "Save locally" (handleExportCsv above) OR "Send CSV by email"
  // — the latter mails the current result as a CSV attachment to one or more fixed addresses via
  // the SAME proven SAM `to_fixed` + `attachment:'csv'` path the compose uses (the worker builds
  // the CSV bytes on-plane; the frontend ships only the kind + rows). A small dialog collects the
  // address(es) and confirms before sending (R8.4).
  const [isCsvMailOpen, setIsCsvMailOpen] = useState(false);
  const [csvMailTo, setCsvMailTo] = useState('');
  const [csvMailSending, setCsvMailSending] = useState(false);
  const csvMailCancelRef = useRef<HTMLButtonElement>(null);

  const csvMailRecipients = useMemo(
    () =>
      csvMailTo
        .split(/[\s,;]+/)
        .map((a) => a.trim())
        .filter((a) => a.length > 0),
    [csvMailTo],
  );
  const csvMailValid =
    csvMailRecipients.length > 0 &&
    csvMailRecipients.every((a) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a));

  const handleOpenCsvMail = useCallback(() => {
    setCsvMailTo('');
    setIsCsvMailOpen(true);
  }, []);

  const handleSendCsvMail = useCallback(async () => {
    if (!csvMailValid || csvMailSending) {
      return;
    }
    setCsvMailSending(true);
    try {
      const body: AdHocMailBody = {
        mode: 'to_fixed',
        result_rows: exportRows as Array<Record<string, unknown>>,
        recipients: csvMailRecipients,
        template_id: null,
        attachment: 'csv',
        ...(selectedSet?.optionValue ? { set_id: selectedSet.optionValue } : {}),
      };
      const res = await sendAdHocMail(body);
      toast({
        title: t('analytics.export.csvMail.queued', { count: res.enqueued }),
        status: 'success',
      });
      // Audit the output (C7 / R8.1): metadata only, mirroring the download path.
      void recordAnalyticsOutput({
        outputKind: 'csv_export',
        setKey: selectedSet?.optionValue,
        recordCount: exportRows.length,
        filterSummary: { columns: result?.columns.length ?? 0, delivery: 'email' },
      });
      setIsCsvMailOpen(false);
    } catch (err) {
      applyApiError(err, { toast, t });
    } finally {
      setCsvMailSending(false);
    }
  }, [csvMailValid, csvMailSending, exportRows, csvMailRecipients, selectedSet, result, toast, t]);

  // Whether the tenant has at least one LABEL template (`kind:"label"`). This —
  // NOT the address mapping — is now the content precondition the labels action
  // depends on (labels sub-spec R-L2 / Property 3; R6 "no analytics config": the
  // action no longer reads any `analytics.*`). Fail-closed: an empty list (a
  // failed/absent load) means no template, so the action stays hidden.
  const hasLabelTemplate = labelTemplates.length > 0;

  // Availability gate for the "Generate address labels" action (labels sub-spec
  // R-L2 / Property 3). The action is OFFERED only when the caller holds
  // `members:export` AND at least one LABEL template exists. This is the NEW
  // gate: it depends ONLY on `capabilities.canExport` + `hasLabelTemplate`, and
  // deliberately NOT on any `analytics.*` config (R6). When
  // either condition is false the action is HIDDEN with a bilingual degradation
  // reason (below). `canGenerateLabels` is the single predicate the labels action
  // and its modal mount render on. It reads NO `analytics.*` config (R6) — the
  // address-mapping-driven label path was removed; only the template path
  // survives.
  const canGenerateLabels = capabilities.canExport && hasLabelTemplate;

  // The tenant's mail-enabled gate flag (pivot-output-actions R0/R1 task 1.3, design §6.3).
  // The per-tenant "mail-enabled / SES-certified" onboarding gate is OWNED by the tenant-admin
  // module (Flask writes it to MySQL `parameters`), projected one-directionally as `config#mail`,
  // and READ by the Members edge — surfaced to the SPA on the field config as `mail_enabled`
  // (NO live MySQL at request time). The pivot result's Mail output action (the compose action /
  // send path) is OFFERED only when this is true (R1); otherwise the action is HIDDEN with the
  // shared degradation reason, exactly mirroring how `canGenerateLabels` gates the labels action.
  // FAIL-CLOSED: a missing/absent flag means NOT enabled. This is a tenant onboarding gate, not a
  // capability gate — the surrounding slot still requires `members:export`; CSV + labels stay
  // available regardless. The send path re-checks the gate server-side (design §9).
  const mailEnabled = fieldConfig?.mail_enabled === true;

  // Build the CSV bytes of the CURRENT result, base64-encoded, for the mail
  // compose "attach CSV" toggle (task 9.2). REUSES the same `csvExport.ts`
  // mapping as the download path (a column's name is both key + header), so the
  // attached CSV is byte-identical to the downloaded one. Returns null when
  // there is no result to attach.
  const buildCsvBase64 = useCallback((): string | null => {
    if (!result || result.columns.length === 0) {
      return null;
    }
    // Localized headers, raw-name keys — identical mapping to the download path
    // so the attached CSV is byte-identical to the downloaded one.
    const columns = result.columns.map((col) => ({
      key: col.name,
      header: columnLabels[col.name] ?? col.name,
    }));
    const csv = generateCsvFromObjects(columns, exportRows);
    // Prepend the UTF-8 BOM to match the downloaded file, then base64-encode the
    // UTF-8 bytes (btoa needs a binary string, so encode via encodeURIComponent).
    const withBom = `\uFEFF${csv}`;
    return btoa(unescape(encodeURIComponent(withBom)));
  }, [result, exportRows, columnLabels]);

  return {
    columnLabels,
    exportRows,
    mailEnabled,
    canGenerateLabels,
    buildCsvBase64,
    handleExportCsv,
    isCsvMailOpen,
    setIsCsvMailOpen,
    csvMailTo,
    setCsvMailTo,
    csvMailSending,
    csvMailValid,
    csvMailCancelRef,
    handleOpenCsvMail,
    handleSendCsvMail,
  };
}
