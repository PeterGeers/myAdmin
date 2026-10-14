/**
 * PivotViewsArea — the Pivot Views area of the Member Analytics panel.
 *
 * As a `React.lazy` DEFAULT export (mounted by `MemberAnalyticsPanel`) this
 * area's chunk loads only when the Pivot Views area is selected (R1.3, R1.6).
 * The `capabilities.canExport` prop is plumbed through because the exports it
 * gates (R4.9/R4.11) live in this area.
 *
 * Task 7.3 scope: mount the real `MemberPivotViews` sub-panel — the
 * saved-member-set dropdown with an explicit Execute that runs the client pivot
 * adapter and renders the result through the reused `PivotResultTable`
 * (R4.1/R4.6/R4.7/R5.2). Nothing runs until Execute (R1.6).
 *
 * The former "no analytics config" degradation notice is GONE: the role /
 * jubilee / address-mapping machinery it described has been removed, so there is
 * no analytics-config signal to degrade on. A tenant with no saved sets now sees
 * the empty-state hint built into `MemberPivotViews` (reused
 * `AnalyticsStateNotice` + the "New set" CTA) instead. The empty-set +
 * load-failure states remain the page's distinct responsibility.
 *
 * @module components/members/analytics/areas/PivotViewsArea
 * @see .kiro/specs/Members/members-analytics-role-removal (design Step A; Empty Pivot Views entry point)
 */

import React from 'react';
import { Box, VStack } from '@chakra-ui/react';
import type { MemberAnalyticsAreaProps } from './types';
import MemberPivotViews from '../MemberPivotViews';

const PivotViewsArea: React.FC<MemberAnalyticsAreaProps> = (props) => {
  return (
    <Box data-testid="analytics-area-pivotViews">
      <VStack align="stretch" spacing={3}>
        {/* The real pivot/list sub-panel: saved-set dropdown, explicit Execute →
            client adapter → reused result table. A tenant with no saved sets
            sees the empty-state hint built into the sub-panel. */}
        <MemberPivotViews {...props} />
      </VStack>
    </Box>
  );
};

export default PivotViewsArea;
