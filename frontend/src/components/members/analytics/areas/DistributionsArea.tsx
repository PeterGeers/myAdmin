/**
 * DistributionsArea — the Distributions / Violins area of the Member Analytics panel.
 *
 * Hosts `MemberDistributions` (the Plotly-backed violin distributions for `age`
 * and `years_member`, task 5.1). Because this is a `React.lazy` DEFAULT export,
 * its chunk — and the heavy Plotly bundle `MemberDistributions` pulls in via the
 * shared `ViolinChart` — is NOT loaded on page open; it loads only when the user
 * selects the Distributions area (R1.3, R1.6). The whole prop bundle
 * (`processedData`, `members`, `fieldConfig`, `language`, `capabilities`) is
 * forwarded unchanged so the distributions derive from the page's OWN filtered
 * dataset (Option A, R1.5/R5.1).
 *
 * @module components/members/analytics/areas/DistributionsArea
 * @see .kiro/specs/Members/member-analytics (design C1/C3; requirements R1.3, R1.6, R3)
 */

import React from 'react';
import MemberDistributions from '../MemberDistributions';
import type { MemberAnalyticsAreaProps } from './types';

const DistributionsArea: React.FC<MemberAnalyticsAreaProps> = (props) => {
  return (
    <div data-testid="analytics-area-distributions">
      <MemberDistributions {...props} />
    </div>
  );
};

export default DistributionsArea;
