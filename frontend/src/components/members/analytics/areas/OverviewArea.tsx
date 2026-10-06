/**
 * OverviewArea — the Overview area of the Member Analytics panel (default landing).
 *
 * The Overview summary (count / avg age / avg years-member) is rendered by
 * `MemberOverviewStats` (task 4.1, design C2). This area is the thin lazy
 * boundary: a `React.lazy` DEFAULT export so entering the area is what loads +
 * mounts + computes it — areas not yet shown never compute (R1.3, R1.6). It
 * forwards the panel's prop bundle straight through to the stats component.
 *
 * @module components/members/analytics/areas/OverviewArea
 * @see .kiro/specs/Members/member-analytics (design C1/C2; requirements R1.3, R1.6, R2)
 */

import React from 'react';
import MemberOverviewStats from '../MemberOverviewStats';
import type { MemberAnalyticsAreaProps } from './types';

const OverviewArea: React.FC<MemberAnalyticsAreaProps> = (props) => {
  return <MemberOverviewStats {...props} />;
};

export default OverviewArea;
