/**
 * MemberAnalyticsPanel — the Member Analytics view switch (C1, task 3.3).
 *
 * Presents the three analytics areas (Overview / Distributions / Pivot Views) as
 * a view switch that shows ONE area at a time, following the h-dcn
 * `AnalyticsSection` view-mode pattern (a single active area, not stacked tabs
 * all mounted at once). Overview is the default landing area (R1.6).
 *
 * Lazy mounting (R1.3, R1.6): each area is a `React.lazy` import, so a given
 * area's chunk — and, for Distributions, the heavy Plotly bundle it will pull in
 * (phase 5) — loads only when that area becomes the active area. Only the active
 * area is rendered (the inactive areas are not in the tree at all), so an area
 * that has never been shown never mounts, computes, or loads its bundle. On open
 * only Overview mounts; selecting Distributions / Pivot Views mounts them then.
 *
 * Prop plumbing (R1.5/R5.1): the panel receives the page's OWN filtered dataset
 * (`processedData`), the full scope-authorized `members`, the resolved
 * `fieldConfig`, the active `language`, and the caller `capabilities`, and hands
 * the same bundle to whichever area is active. The areas themselves are
 * lightweight placeholders in this task; the real Overview (phase 4),
 * Distributions (phase 5), and Pivot Views (phase 7) land later behind this same
 * switch + prop contract.
 *
 * Accessibility (R6.6): the switch is an ARIA `tablist` with roving tabindex —
 * Left/Right (and Up/Down) move between tabs, Home/End jump to first/last, and
 * the active tab is the sole tab-stop; each area is a labelled `tabpanel`.
 *
 * @module components/members/analytics/MemberAnalyticsPanel
 * @see .kiro/specs/Members/member-analytics (design C1; requirements R1.3, R1.6, R6.6)
 */

import React, { Suspense, useCallback, useMemo, useRef, useState } from 'react';
import { Box, HStack, Button, Spinner, Flex } from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type { Member, MemberRow, FieldConfig } from '../../../types/members';
import type { MemberAnalyticsCapabilities } from './areas/types';

// Lazy area imports — one code-split chunk per area, so entering an area is what
// loads + mounts it (R1.3/R1.6). Overview is the default landing area.
const OverviewArea = React.lazy(() => import('./areas/OverviewArea'));
const DistributionsArea = React.lazy(() => import('./areas/DistributionsArea'));
const PivotViewsArea = React.lazy(() => import('./areas/PivotViewsArea'));

/** The three analytics areas, in display order (Overview is the default). */
export type AnalyticsAreaKey = 'overview' | 'distributions' | 'pivotViews';

interface AreaDef {
  key: AnalyticsAreaKey;
  /** i18n key under `analytics.areas.*` (bilingual, from task 0.3). */
  labelKey: string;
  Component: React.LazyExoticComponent<React.ComponentType<any>>;
}

const AREAS: AreaDef[] = [
  { key: 'overview', labelKey: 'analytics.areas.overview', Component: OverviewArea },
  { key: 'distributions', labelKey: 'analytics.areas.distributions', Component: DistributionsArea },
  { key: 'pivotViews', labelKey: 'analytics.areas.pivotViews', Component: PivotViewsArea },
];

export interface MemberAnalyticsPanelProps {
  /** The page's OWN filtered dataset (Option A, R1.5/R5.1). */
  processedData: MemberRow[];
  /** The full scope-authorized member set (pre page-filter). */
  members: Member[];
  /** Resolved field config (fixed ⊕ overlay ⊕ calculated + analytics config). */
  fieldConfig: FieldConfig | null;
  /**
   * Whether the tenant authored an analytics config block (R1.4 "no analytics
   * config" signal). Plumbed unchanged to every area so the config-dependent
   * sets can degrade with a bilingual reason while the fixed/calculated areas
   * keep working — the third distinct non-happy state (R1.4 / R9.5).
   */
  hasAnalyticsConfig: boolean;
  /** Active language for bilingual label resolution. */
  language: string;
  /** Caller capabilities (e.g. `canExport`). */
  capabilities: MemberAnalyticsCapabilities;
}

const MemberAnalyticsPanel: React.FC<MemberAnalyticsPanelProps> = ({
  processedData,
  members,
  fieldConfig,
  hasAnalyticsConfig,
  language,
  capabilities,
}) => {
  const { t } = useTypedTranslation('members');

  // Overview is the default landing area (R1.6). Only the active area is in the
  // tree, so inactive areas never mount/compute until selected.
  const [activeArea, setActiveArea] = useState<AnalyticsAreaKey>('overview');

  // Roving-tabindex refs so keyboard navigation can move focus to the newly
  // selected tab (WAI-ARIA tabs pattern).
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const activeIndex = AREAS.findIndex(a => a.key === activeArea);

  const selectByIndex = useCallback((index: number) => {
    const next = AREAS[(index + AREAS.length) % AREAS.length];
    setActiveArea(next.key);
    // Move focus to the newly active tab (roving tabindex).
    tabRefs.current[next.key]?.focus();
  }, []);

  const onTabKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
      switch (event.key) {
        case 'ArrowRight':
        case 'ArrowDown':
          event.preventDefault();
          selectByIndex(index + 1);
          break;
        case 'ArrowLeft':
        case 'ArrowUp':
          event.preventDefault();
          selectByIndex(index - 1);
          break;
        case 'Home':
          event.preventDefault();
          selectByIndex(0);
          break;
        case 'End':
          event.preventDefault();
          selectByIndex(AREAS.length - 1);
          break;
        default:
          break;
      }
    },
    [selectByIndex],
  );

  // The prop bundle handed to whichever area is active (one shape, task 3.3).
  const areaProps = useMemo(
    () => ({ processedData, members, fieldConfig, hasAnalyticsConfig, language, capabilities }),
    [processedData, members, fieldConfig, hasAnalyticsConfig, language, capabilities],
  );

  const ActiveComponent = AREAS[activeIndex].Component;

  return (
    <Box data-testid="analytics-panel">
      {/* View switch — ARIA tablist with roving tabindex (R6.6). */}
      <HStack
        role="tablist"
        aria-label={t('analytics.title')}
        spacing={2}
        mb={4}
        data-testid="analytics-view-switch"
      >
        {AREAS.map((area, index) => {
          const selected = area.key === activeArea;
          return (
            <Button
              key={area.key}
              ref={(el) => { tabRefs.current[area.key] = el; }}
              role="tab"
              id={`analytics-tab-${area.key}`}
              aria-selected={selected}
              aria-controls={`analytics-panel-${area.key}`}
              // Roving tabindex: only the active tab is in the tab order.
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveArea(area.key)}
              onKeyDown={(e) => onTabKeyDown(e, index)}
              size="sm"
              variant={selected ? 'solid' : 'ghost'}
              colorScheme="orange"
              color={selected ? undefined : 'gray.300'}
              data-testid={`analytics-tab-${area.key}`}
            >
              {t(area.labelKey)}
            </Button>
          );
        })}
      </HStack>

      {/* Only the active area is rendered (one area visible at a time). Suspense
          covers the lazy chunk load so a slow area never blocks the others. */}
      <Box
        role="tabpanel"
        id={`analytics-panel-${activeArea}`}
        aria-labelledby={`analytics-tab-${activeArea}`}
        data-testid={`analytics-panel-${activeArea}`}
      >
        <Suspense
          fallback={
            <Flex color="white" align="center" gap={3} data-testid="analytics-area-loading">
              <Spinner color="orange.300" size="sm" />
            </Flex>
          }
        >
          <ActiveComponent {...areaProps} />
        </Suspense>
      </Box>
    </Box>
  );
};

export default MemberAnalyticsPanel;
