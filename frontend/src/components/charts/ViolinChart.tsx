/**
 * ViolinChart — generic, domain-agnostic violin distribution chart.
 *
 * Extracted from the bespoke `ViolinChart` inside `reports/BnbViolinsReport.tsx`
 * so STR/BNB and Member Analytics consume ONE implementation (spec
 * `.kiro/specs/Members/member-analytics` design C3; R3.2/R3.3/R3.4/R6.6).
 *
 * The Plotly violin-trace construction (box + meanline + KDE, grouped by `group`)
 * is lifted VERBATIM in behavior from the BNB component. The chart renders through
 * the shared `PlotlyChart.tsx` `Plot` factory, lazy-loaded via `React.lazy` +
 * `<Suspense>` so the Plotly bundle never loads until the chart does.
 *
 * The per-group quartile summary is produced by the shared `violinStats` helper
 * (charts/violinStats.ts, task 1.2). That stats TABLE is the non-visual chart
 * alternative (R6.6) and is ALWAYS rendered when `showStats !== false`.
 *
 * This component is deliberately generic: it takes `ViolinDatum[]` ({group, value})
 * plus display labels as props, so it carries no `{listing, channel}` or any other
 * domain shape. Task 2.2 refactors BNB to map its data onto this.
 */
import React, { Suspense, useMemo } from 'react';
import {
  Box,
  Card,
  CardBody,
  Progress,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { violinStats, type ViolinStats } from './violinStats';

// Lazy load Plotly only when the chart renders (reduces initial bundle size),
// matching the BNB pattern — the shared Plot factory lives in PlotlyChart.tsx.
const Plot = React.lazy(() => import('../PlotlyChart'));

/** Generic data point: a numeric `value` tagged with the `group` it belongs to. */
export interface ViolinDatum {
  group: string;
  value: number;
}

export interface ViolinChartProps {
  /** The data to plot; grouped by `group`, one violin per group. */
  data: ViolinDatum[];
  /** Y-axis / metric label (bilingual-resolved by the caller). */
  metricLabel: string;
  /** Optional X-axis / grouping label. */
  groupLabel?: string;
  /**
   * Whether to render the quartile summary table. Defaults to `true`. The table
   * is the non-visual alternative to the chart (R6.6), so it is ALWAYS present
   * unless the caller explicitly passes `showStats={false}`.
   */
  showStats?: boolean;
}

interface GroupStats extends ViolinStats {
  name: string;
}

/**
 * ViolinChart — distribution chart with kernel-density violins and a quartile table.
 */
const ViolinChart: React.FC<ViolinChartProps> = ({
  data,
  metricLabel,
  groupLabel,
  showStats = true,
}) => {
  const { t } = useTypedTranslation('reports');

  const { plotData, statsData } = useMemo(() => {
    if (!data.length) {
      return { plotData: [] as any[], statsData: [] as GroupStats[] };
    }

    // Group values by `group` (verbatim behavior from the BNB original).
    const grouped = data.reduce((acc, item) => {
      const key = item.group;
      if (!acc[key]) acc[key] = [];
      acc[key].push(Number(item.value) || 0);
      return acc;
    }, {} as Record<string, number[]>);

    // Sort groups alphabetically (as BNB did).
    const sortedGroups = Object.keys(grouped).sort();

    // Build Plotly violin traces (box + meanline + KDE) — lifted verbatim.
    const plotData = sortedGroups.map((name) => ({
      type: 'violin',
      y: grouped[name],
      name,
      box: {
        visible: true,
        fillcolor: 'rgba(49, 130, 206, 0.5)',
        line: {
          color: 'rgb(49, 130, 206)',
          width: 2,
        },
      },
      meanline: {
        visible: true,
        color: 'rgb(245, 101, 0)',
        width: 2,
      },
      line: {
        color: 'rgb(49, 130, 206)',
        width: 2,
      },
      fillcolor: 'rgba(49, 130, 206, 0.3)',
      opacity: 0.6,
      points: false,
      hoveron: 'violins+points',
      hovertemplate:
        '<b>%{fullData.name}</b><br>' + 'Value: %{y}<br>' + '<extra></extra>',
    } as any));

    // Per-group quartile summary via the shared helper. `violinStats` sorts its
    // input in place, so pass a copy to leave each trace's `y` in insertion order.
    const statsData: GroupStats[] = sortedGroups.map((name) => ({
      name,
      ...violinStats([...grouped[name]]),
    }));

    return { plotData, statsData };
  }, [data]);

  if (!plotData.length) {
    return (
      <Box p={4} textAlign="center">
        <Text color="white">{t('charts.noData')}</Text>
      </Box>
    );
  }

  const groupHeading = groupLabel ?? t('charts.summary');

  return (
    <VStack spacing={4}>
      {/* Plotly Violin Chart */}
      <Box w="100%" bg="white" borderRadius="md" p={2}>
        <Suspense
          fallback={
            <Box p={8} textAlign="center">
              <Progress size="xs" isIndeterminate colorScheme="orange" mb={2} />
              <Text color="gray.600" fontSize="sm">
                {t('bnb.loadingViolinChart')}
              </Text>
            </Box>
          }
        >
          <Plot
            data={plotData as any}
            layout={
              {
                title: metricLabel + ' ' + t('charts.distribution'),
                yaxis: {
                  title: { text: metricLabel },
                  zeroline: false,
                  gridcolor: '#e2e8f0',
                },
                xaxis: {
                  title: groupLabel ? { text: groupLabel } : undefined,
                  gridcolor: '#e2e8f0',
                },
                paper_bgcolor: 'white',
                plot_bgcolor: 'white',
                showlegend: false,
                hovermode: 'closest',
                margin: { l: 60, r: 30, t: 50, b: 100 },
                height: 500,
              } as any
            }
            config={{
              responsive: true,
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            }}
            style={{ width: '100%', height: '500px' }}
          />
        </Suspense>
      </Box>

      {/* Quartile Summary Table — the non-visual alternative (R6.6). Always
          present unless the caller explicitly opts out via showStats={false}. */}
      {showStats && (
        <Card bg="gray.600" w="100%">
          <CardBody>
            <TableContainer>
              <Table size="sm" variant="simple">
                <Thead>
                  <Tr>
                    <Th color="white">{groupHeading}</Th>
                    <Th color="white" isNumeric>{t('charts.count')}</Th>
                    <Th color="white" isNumeric>{t('bnb.min')}</Th>
                    <Th color="white" isNumeric>{t('bnb.q1')}</Th>
                    <Th color="white" isNumeric>{t('charts.median')}</Th>
                    <Th color="white" isNumeric>{t('charts.average')}</Th>
                    <Th color="white" isNumeric>{t('bnb.q3')}</Th>
                    <Th color="white" isNumeric>{t('bnb.max')}</Th>
                    <Th color="white" isNumeric>{t('bnb.range')}</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {statsData.map((item, index) => (
                    <Tr key={index}>
                      <Td color="white" fontSize="sm">{item.name}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.count}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.min}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.q1}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.median}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.mean.toFixed(1)}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.q3}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.max}</Td>
                      <Td color="white" fontSize="sm" isNumeric>{item.range.toFixed(1)}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </TableContainer>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default ViolinChart;
