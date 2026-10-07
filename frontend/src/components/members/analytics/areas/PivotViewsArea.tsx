/**
 * PivotViewsArea — the Pivot Views area of the Member Analytics panel.
 *
 * As a `React.lazy` DEFAULT export (mounted by `MemberAnalyticsPanel`) this
 * area's chunk loads only when the Pivot Views area is selected (R1.3, R1.6).
 * The `capabilities.canExport` prop is plumbed through because the exports it
 * gates (R4.9/R4.11) live in this area.
 *
 * Task 7.3 scope (THIS task): mount the real `MemberPivotViews` sub-panel —
 * the predefined-preset + saved-member-model dropdown with an explicit Execute
 * that runs the client pivot adapter and renders the result through the reused
 * `PivotResultTable` (R4.1/R4.6/R4.7/R5.2). Nothing runs until Execute (R1.6).
 * The 3.4 "no analytics config" degradation notice below is PRESERVED: the
 * config-dependent sets live in this area, so when the tenant has not authored
 * an analytics config the bilingual degradation reason still renders above the
 * sub-panel (the fixed/calculated presets stay usable).
 *
 * Task 3.4 scope (THIS task): the "no analytics config" degradation signal
 * (R1.4). The config-DEPENDENT sets (the role-backed presets — cancellations,
 * clubblad paper/digital, referral source — and the jubilee rule) live in THIS
 * area, so when the tenant has not authored an analytics config
 * (`hasAnalyticsConfig === false`) this area surfaces a bilingual degradation
 * REASON (`analytics.degradation.noConfig`) explaining those sets are
 * unavailable — never an error, never a crash (R1.4 / R9.5). The
 * fixed/calculated areas (Overview, Distributions) are unaffected and still
 * render; this is why the degradation lives here and not at the page level. The
 * empty-set + load-failure states are the page's distinct responsibility.
 *
 * @module components/members/analytics/areas/PivotViewsArea
 * @see .kiro/specs/Members/member-analytics (design C1/C4; requirements R1.3, R1.4, R1.6, R4, R9.5)
 */

import React from 'react';
import { Box, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../../../../hooks/useTypedTranslation';
import type { MemberAnalyticsAreaProps } from './types';
import AnalyticsStateNotice from './AnalyticsStateNotice';
import MemberPivotViews from '../MemberPivotViews';

const PivotViewsArea: React.FC<MemberAnalyticsAreaProps> = (props) => {
  const { t } = useTypedTranslation('members');
  const { hasAnalyticsConfig } = props;
  return (
    <Box data-testid="analytics-area-pivotViews">
      <VStack align="stretch" spacing={3}>
        {/* No analytics config (R1.4, distinct from empty/error): the
            config-dependent sets degrade with a bilingual reason, while the
            fixed/calculated areas keep working. Not an error state. Preserved
            from task 3.4. */}
        {!hasAnalyticsConfig && (
          <AnalyticsStateNotice
            kind="degradation"
            message={t('analytics.degradation.noConfig')}
          />
        )}
        {/* The real pivot/list sub-panel (task 7.3): preset + saved-model
            dropdown, explicit Execute → client adapter → reused result table. */}
        <MemberPivotViews {...props} />
      </VStack>
    </Box>
  );
};

export default PivotViewsArea;
