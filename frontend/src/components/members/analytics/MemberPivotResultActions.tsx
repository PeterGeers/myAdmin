/**
 * MemberPivotResultActions — the produced-result region of the Pivot Views
 * panel: the reused `PivotResultTable` plus the capability-gated export-actions
 * slot (CSV menu, Mail, Generate address labels).
 *
 * Extracted verbatim from `MemberPivotViews.tsx` (code-quality split 2026-10-15,
 * task 4) with ZERO behaviour change: this is a pure presentational component
 * driven entirely by props — every gate (`capabilities.canExport`, `mailEnabled`,
 * `canGenerateLabels`), every testid, and every i18n key is identical to the
 * inline block it replaces. All state and handlers stay in the parent; this
 * component only renders them.
 *
 * It imports `PivotResultTable` via the SAME relative specifier the parent used
 * (`../../pivot/PivotResultTable`) so the component test's module mock still
 * intercepts it unchanged.
 *
 * @module components/members/analytics/MemberPivotResultActions
 */

import React from 'react';
import { Box, Button, HStack, Menu, MenuButton, MenuList, MenuItem } from '@chakra-ui/react';
import PivotResultTable from '../../pivot/PivotResultTable';
import AnalyticsStateNotice from './areas/AnalyticsStateNotice';
import type { PivotConfig, PivotResult } from '../../../types/pivot';
import type { MemberAnalyticsCapabilities } from './areas/types';

/**
 * The members-namespace translator, typed to its usage here: a key plus an
 * optional interpolation bag, returning a string. Matches the shape the parent's
 * `useTypedTranslation('members')` `t` provides without pulling in a brittle
 * i18next generic.
 */
type TFunction = (key: string, options?: Record<string, unknown>) => string;

export interface MemberPivotResultActionsProps {
  /** The produced result (non-null — the parent only mounts this when a result exists). */
  result: PivotResult;
  /** The config that produced the result (drives the table's formatting). */
  resultConfig: PivotConfig;
  /** True while an execute is in flight (passed through to the table's loading state). */
  isExecuting: boolean;
  /** The result table reports its post-filter visible rows here (drives exports). */
  onVisibleRowsChange: (rows: Record<string, unknown>[]) => void;
  /** name→localized label map for the result columns (headers + CSV headers). */
  columnLabels: Record<string, string>;
  /** The caller's capability flags (gates the export-actions slot). */
  capabilities: MemberAnalyticsCapabilities;
  /** Whether the tenant is mail-enabled (gates the Mail action — a tenant gate). */
  mailEnabled: boolean;
  /** Whether the labels action is available (members:export + ≥1 label template). */
  canGenerateLabels: boolean;
  /** Download the CURRENT result as a CSV. */
  onExportCsv: () => void;
  /** Open the "Send CSV by email" dialog. */
  onOpenCsvMail: () => void;
  /** Open the SES mail compose modal. */
  onOpenMail: () => void;
  /** Open the address-labels modal. */
  onOpenLabels: () => void;
  /** The members-namespace translator (keys unchanged from the inline block). */
  t: TFunction;
}

/**
 * The produced-result block (REUSE PivotResultTable, R4.7) + the
 * capability-gated `pivot-result-actions` slot. Rendered only AFTER an explicit
 * Execute (the parent gates mounting on `result && resultConfig`).
 */
const MemberPivotResultActions: React.FC<MemberPivotResultActionsProps> = ({
  result,
  resultConfig,
  isExecuting,
  onVisibleRowsChange,
  columnLabels,
  capabilities,
  mailEnabled,
  canGenerateLabels,
  onExportCsv,
  onOpenCsvMail,
  onOpenMail,
  onOpenLabels,
  t,
}) => {
  return (
    <Box data-testid="member-pivot-result">
      <PivotResultTable
        data={result.data}
        columns={result.columns}
        config={resultConfig}
        isLoading={isExecuting}
        hideExportMenu
        onVisibleRowsChange={onVisibleRowsChange}
        columnLabels={columnLabels}
      />

      {capabilities.canExport && (
        <HStack
          mt={3}
          spacing={2}
          data-testid="pivot-result-actions"
          aria-label={t('analytics.export.csv')}
        >
          <Menu>
            <MenuButton
              as={Button}
              variant="outline"
              colorScheme="orange"
              data-testid="member-pivot-export-csv"
            >
              {t('analytics.export.csv')}
            </MenuButton>
            <MenuList bg="gray.800" borderColor="gray.600">
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onExportCsv}
                data-testid="member-pivot-export-csv-download"
              >
                {t('analytics.export.csvDownload')}
              </MenuItem>
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onOpenCsvMail}
                data-testid="member-pivot-export-csv-email"
              >
                {t('analytics.export.csvEmail')}
              </MenuItem>
            </MenuList>
          </Menu>
          {/* Mail (R1 / pivot-output-actions task 1.3) — OFFERED only when the
              tenant is mail-enabled (the R0 `config#mail` gate surfaced as
              `fieldConfig.mail_enabled`). When enabled, the compose action /
              send path is offered; when NOT enabled the action is HIDDEN and
              the shared degradation reason explains why
              (`analytics.degradation.mailNotEnabled`), mirroring how the labels
              action degrades on an absent address mapping. A tenant ONBOARDING
              gate, not a capability gate: CSV + labels stay available regardless. */}
          {mailEnabled ? (
            <Button
              variant="outline"
              colorScheme="orange"
              onClick={onOpenMail}
              data-testid="member-pivot-mail"
            >
              {t('analytics.export.mail')}
            </Button>
          ) : (
            <AnalyticsStateNotice
              kind="degradation"
              message={t('analytics.degradation.mailNotEnabled')}
              testId="member-pivot-mail-unavailable"
            />
          )}
          {/* Generate address labels (labels sub-spec R-L2 / Property 3) —
              a first-class result action beside CSV / Mail. Opens the
              labels options UI in a modal.

              Availability gate (labels sub-spec R-L2 / Property 3): the
              slot already requires `members:export`, so the one remaining
              condition is that at least one LABEL template exists — together
              `canGenerateLabels`. The gate depends ONLY on
              `canExport` + `hasLabelTemplate` and deliberately NOT on the
              address mapping / any `analytics.*` config (R6). When it holds,
              the action is OFFERED; when there is NO label template (or no
              export) the action is HIDDEN with the bilingual labels-namespace
              degradation reason (`analytics.labels.noTemplate`). A
              config/capability gate — NOT a tenant gate: CSV + Mail stay
              available regardless. */}
          {canGenerateLabels ? (
            <Button
              variant="outline"
              colorScheme="orange"
              onClick={onOpenLabels}
              data-testid="member-pivot-labels"
            >
              {t('analytics.labels.action')}
            </Button>
          ) : (
            <AnalyticsStateNotice
              kind="degradation"
              message={t('analytics.labels.noTemplate')}
              testId="member-pivot-labels-unavailable"
            />
          )}
        </HStack>
      )}
    </Box>
  );
};

export default MemberPivotResultActions;
