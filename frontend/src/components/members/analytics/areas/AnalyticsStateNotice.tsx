/**
 * AnalyticsStateNotice — the shared presentation for the Member Analytics
 * non-happy states (task 3.4, R1.4).
 *
 * The analytics surface must distinguish THREE non-happy states and render each
 * one DISTINCTLY so a user can tell them apart (R1.4) — never a crash, and never
 * two of them looking the same:
 *
 *   - **empty**        — the scope-authorized / filtered set has zero rows. A
 *                        NEUTRAL, informational empty state (not an error, not a
 *                        warning). Rendered by the page when `processedData` is
 *                        empty, and by any area that can be entered with zero
 *                        rows.
 *   - **degradation**  — the tenant has not authored the analytics config (R9),
 *                        so the config-DEPENDENT sets are unavailable while the
 *                        fixed/calculated areas still work. A WARNING-level
 *                        notice carrying the bilingual REASON — explicitly NOT an
 *                        error (nothing failed) and NOT empty (there are rows).
 *   - **error**        — a load failure (`GET /members` failed). An ERROR state
 *                        with a retry affordance. The page renders this as a
 *                        Chakra `Alert status="error"`; this component covers the
 *                        other two kinds, which share one neutral/degraded shape.
 *
 * The three kinds are kept visually + semantically distinct (R1.4) and
 * accessible (R6.6 — colour is NEVER the sole signal): each kind pairs a
 * distinct icon with its own `data-testid` and a bilingual text reason, so the
 * state is conveyed by icon + text as well as colour, and is addressable in
 * tests. `role="status"` (empty) vs `role="alert"` (degradation) also exposes
 * the distinction to assistive tech.
 *
 * @module components/members/analytics/areas/AnalyticsStateNotice
 * @see .kiro/specs/Members/member-analytics (design C1, "Error handling"; requirements R1.4, R6.6)
 */

import React from 'react';
import { Box, HStack, Text } from '@chakra-ui/react';
import { InfoOutlineIcon, WarningTwoIcon } from '@chakra-ui/icons';

/** The non-error notice kinds this component renders (R1.4). */
export type AnalyticsNoticeKind = 'empty' | 'degradation';

export interface AnalyticsStateNoticeProps {
  /** Which distinct non-happy state this is (R1.4). */
  kind: AnalyticsNoticeKind;
  /** The already-resolved, bilingual message for the state (no raw i18n keys). */
  message: string;
  /** Optional explicit test id (defaults to `analytics-{kind}`). */
  testId?: string;
}

/**
 * The per-kind presentation: icon, colour, ARIA role, and default test id. Each
 * kind is deliberately distinct on EVERY axis (icon + colour + role + testid) so
 * the states never collapse into one another and colour is not the sole signal
 * (R1.4 / R6.6).
 */
const KIND_PRESENTATION: Record<
  AnalyticsNoticeKind,
  { icon: typeof InfoOutlineIcon; color: string; role: 'status' | 'alert'; testId: string }
> = {
  // Empty is neutral + informational — a muted info icon, polite `status`.
  empty: {
    icon: InfoOutlineIcon,
    color: 'gray.400',
    role: 'status',
    testId: 'analytics-empty',
  },
  // Degradation is a warning — a warning icon, assertive `alert`, warning colour.
  degradation: {
    icon: WarningTwoIcon,
    color: 'yellow.300',
    role: 'alert',
    testId: 'analytics-degradation',
  },
};

const AnalyticsStateNotice: React.FC<AnalyticsStateNoticeProps> = ({ kind, message, testId }) => {
  const { icon: StateIcon, color, role, testId: defaultTestId } = KIND_PRESENTATION[kind];

  return (
    <Box
      role={role}
      data-testid={testId ?? defaultTestId}
      data-notice-kind={kind}
      bg="gray.900"
      borderWidth="1px"
      borderColor={kind === 'degradation' ? 'yellow.700' : 'gray.700'}
      borderRadius="md"
      px={4}
      py={3}
    >
      <HStack spacing={3} align="flex-start">
        {/* Icon is decorative — the text carries the meaning (R6.6). The icon
            is the non-colour signal that keeps the kinds distinct for users who
            do not perceive the colour difference. */}
        <StateIcon color={color} boxSize={4} mt="2px" aria-hidden="true" />
        <Text color="gray.200" fontSize="sm">
          {message}
        </Text>
      </HStack>
    </Box>
  );
};

export default AnalyticsStateNotice;
