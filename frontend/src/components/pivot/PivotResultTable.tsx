/**
 * PivotResultTable Component — Flat & Hierarchical Modes
 *
 * Renders pivot query results in a flat table layout or a hierarchical
 * tree layout using Chakra UI Table with FilterableHeader for sorting.
 * Displays group columns as row identifiers and aggregate columns as
 * formatted numeric values.
 *
 * Hierarchical mode uses buildHierarchicalTree() to construct a nested
 * tree from flat GROUP BY + WITH ROLLUP results. The first group column
 * defines top-level nodes; subsequent columns create nested children.
 * Parent rows show rolled-up aggregates and support expand/collapse.
 *
 * Supports loading state, empty state, and a three-way number format toggle
 * (decimal / whole / k-notation) applied to all aggregate measure columns.
 *
 * Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §5 PivotResultTable
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardBody,
  Flex,
  Icon,
  Spinner,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from '@chakra-ui/react';
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { FilterableHeader } from '../filters/FilterableHeader';
import { formatPivotNumber, resolveLocale } from '../../utils/pivotFormatting';
import {
  buildHierarchicalTree,
  flattenTree,
} from '../../utils/pivotTreeBuilder';
import type { PivotTreeNode } from '../../utils/pivotTreeBuilder';
import { PivotResultTablePivoted, isPivotedResult } from './PivotResultTablePivoted';
import { PivotExportMenu } from './PivotExportMenu';
import type {
  NumberFormat,
  PivotColumnMeta,
  PivotConfig,
} from '../../types/pivot';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PivotResultTableProps {
  /** Result rows from the pivot query */
  data: Record<string, any>[];
  /** Column metadata describing each column in the result */
  columns: PivotColumnMeta[];
  /** The pivot configuration that produced these results */
  config: PivotConfig;
  /** Whether a query is currently executing */
  isLoading: boolean;
  /** Override number format externally (when omitted, the internal toggle controls it) */
  numberFormat?: NumberFormat;
  /** Callback when the user changes the number format via the toggle */
  onNumberFormatChange?: (format: NumberFormat) => void;
}

/** The three available number format options for the toggle. */
const NUMBER_FORMAT_OPTIONS: NumberFormat[] = ['decimal', 'whole', 'k-notation'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Determine the default number format for an aggregate column based on its
 * data type and aggregation function. COUNT always uses whole numbers;
 * decimal/currency types use 2dp; integers use whole.
 */
function getDefaultFormat(col: PivotColumnMeta): NumberFormat {
  if (col.function === 'COUNT') return 'whole';
  if (col.dataType === 'decimal' || col.dataType === 'float' || col.dataType === 'double') {
    return 'decimal';
  }
  return 'whole';
}

/**
 * Format a cell value for display. Group columns are returned as-is;
 * aggregate columns are formatted using the pivot number formatter.
 *
 * When `activeFormat` is set (from the toggle), it overrides the per-column
 * default for all aggregate columns. When null, each column uses its own
 * default based on data type and aggregation function.
 */
function formatCellValue(
  value: any,
  col: PivotColumnMeta,
  activeFormat: NumberFormat | null,
  locale: string,
): string {
  if (value == null) return '';

  // Group columns: display raw value
  if (col.type === 'group') {
    return String(value);
  }

  // Aggregate columns: apply number formatting
  const numValue = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(numValue)) return String(value);

  const format = activeFormat ?? getDefaultFormat(col);
  return formatPivotNumber(numValue, format, locale);
}

/**
 * Build the initial filter state from column metadata.
 * Every column gets an empty string filter value.
 */
function buildInitialFilters(columns: PivotColumnMeta[]): Record<string, string> {
  const filters: Record<string, string> = {};
  for (const col of columns) {
    filters[col.name] = '';
  }
  return filters;
}

// ---------------------------------------------------------------------------
// Hierarchical mode helpers
// ---------------------------------------------------------------------------

/** Indentation per depth level in pixels. */
const INDENT_PX = 24;

/**
 * Build the aggregate function map from column metadata.
 * Maps aggregate column names to their aggregation function for rollup computation.
 */
function buildAggregateFunctionMap(
  columns: PivotColumnMeta[],
): Record<string, 'SUM' | 'COUNT' | 'AVG' | 'MIN' | 'MAX'> {
  const map: Record<string, 'SUM' | 'COUNT' | 'AVG' | 'MIN' | 'MAX'> = {};
  for (const col of columns) {
    if (col.type === 'aggregate' && col.function) {
      map[col.name] = col.function;
    }
  }
  return map;
}

/**
 * Determine whether hierarchical mode should be active.
 * Requires: displayMode === 'hierarchical' AND 2+ group columns.
 */
function shouldUseHierarchical(config: PivotConfig): boolean {
  return config.displayMode === 'hierarchical' && config.groupColumns.length >= 2;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PivotResultTable({
  data,
  columns,
  config,
  isLoading,
  numberFormat,
  onNumberFormatChange,
}: PivotResultTableProps): React.ReactElement {
  const { t, i18n } = useTypedTranslation('reports');
  const locale = resolveLocale(i18n.language);

  // Internal number format state — controlled externally when numberFormat prop is set
  const [internalFormat, setInternalFormat] = useState<NumberFormat>('decimal');
  const activeFormat = numberFormat ?? internalFormat;

  const handleFormatChange = (fmt: NumberFormat) => {
    setInternalFormat(fmt);
    onNumberFormatChange?.(fmt);
  };

  // Check if there are any aggregate columns (toggle only makes sense when there are)
  const hasAggregateColumns = columns.some((col) => col.type === 'aggregate');

  // Determine if hierarchical mode is active
  const isHierarchical = shouldUseHierarchical(config);

  // Determine if column-pivoted mode is active
  const isPivoted = isPivotedResult(columns);

  // -----------------------------------------------------------------------
  // Hierarchical tree state
  // -----------------------------------------------------------------------
  const groupColumnNames = useMemo(
    () => columns.filter((c) => c.type === 'group').map((c) => c.name),
    [columns],
  );
  const aggregateColumnNames = useMemo(
    () => columns.filter((c) => c.type === 'aggregate').map((c) => c.name),
    [columns],
  );
  const aggregateFunctionMap = useMemo(
    () => buildAggregateFunctionMap(columns),
    [columns],
  );

  // Build tree from flat data (only when hierarchical mode is active)
  const [treeNodes, setTreeNodes] = useState<PivotTreeNode[]>([]);

  // Rebuild tree when data or config changes
  useEffect(() => {
    if (isHierarchical && data.length > 0 && groupColumnNames.length >= 2) {
      const tree = buildHierarchicalTree(data, groupColumnNames, aggregateColumnNames, {
        aggregateFunctions: aggregateFunctionMap,
      });
      setTreeNodes(tree);
    } else {
      setTreeNodes([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, isHierarchical, groupColumnNames, aggregateColumnNames, aggregateFunctionMap]);

  // Flatten tree for rendering (respects expand/collapse state)
  const flatNodes = useMemo(() => flattenTree(treeNodes), [treeNodes]);

  // Toggle expand/collapse for a node
  const toggleNode = useCallback(
    (targetNode: PivotTreeNode) => {
      // Deep-clone tree and toggle the matching node
      const toggleInTree = (nodes: PivotTreeNode[]): PivotTreeNode[] =>
        nodes.map((node) => {
          if (node === targetNode) {
            return { ...node, isExpanded: !node.isExpanded, children: node.children };
          }
          if (node.children.length > 0) {
            return { ...node, children: toggleInTree(node.children) };
          }
          return node;
        });
      setTreeNodes((prev) => toggleInTree(prev));
    },
    [],
  );

  // Expand all / collapse all
  const setAllExpanded = useCallback(
    (expanded: boolean) => {
      const setExpanded = (nodes: PivotTreeNode[]): PivotTreeNode[] =>
        nodes.map((node) => ({
          ...node,
          isExpanded: node.children.length > 0 ? expanded : node.isExpanded,
          children: setExpanded(node.children),
        }));
      setTreeNodes((prev) => setExpanded(prev));
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Flat mode: filterable table
  // -----------------------------------------------------------------------
  const initialFilters = useMemo(() => buildInitialFilters(columns), [columns]);

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<Record<string, any>>(data, {
    initialFilters,
  });

  const columnSortDirection = (field: string): 'asc' | 'desc' | null => {
    return sortField === field ? sortDirection : null;
  };

  // -----------------------------------------------------------------------
  // Shared toolbar (only rendered when we have data)
  // -----------------------------------------------------------------------
  const hasData = columns.length > 0 && data.length > 0;

  const rowCount = isPivoted
    ? data.length
    : isHierarchical
      ? flatNodes.length
      : processedData.length;

  const toolbar = hasData ? (
    <Flex justify="space-between" align="center" mb={2} wrap="wrap" gap={2}>
      <Flex align="center" gap={3}>
        <Text color="gray.400" fontSize="xs">
          {t('pivot.results.rowCount', { count: rowCount })}
        </Text>

        {/* Expand/Collapse all — only in hierarchical mode without column pivot */}
        {isHierarchical && !isPivoted && (
          <ButtonGroup size="xs" isAttached variant="outline">
            <Button
              onClick={() => setAllExpanded(true)}
              color="white"
              data-testid="expand-all"
            >
              {t('pivot.results.expandAll')}
            </Button>
            <Button
              onClick={() => setAllExpanded(false)}
              color="white"
              data-testid="collapse-all"
            >
              {t('pivot.results.collapseAll')}
            </Button>
          </ButtonGroup>
        )}

        {/* CSV export menu */}
        <PivotExportMenu
          data={data}
          columns={columns}
          config={config}
          numberFormat={activeFormat}
        />
      </Flex>

      {/* Number format toggle — only shown when aggregate columns exist */}
      {hasAggregateColumns && (
        <Flex align="center" gap={2}>
          <Text color="gray.400" fontSize="xs">
            {t('pivot.numberFormat.label')}
          </Text>
          <ButtonGroup size="xs" isAttached variant="outline">
            {NUMBER_FORMAT_OPTIONS.map((fmt) => (
              <Button
                key={fmt}
                colorScheme={activeFormat === fmt ? 'orange' : 'gray'}
                variant={activeFormat === fmt ? 'solid' : 'outline'}
                onClick={() => handleFormatChange(fmt)}
                color="white"
                data-testid={`number-format-${fmt}`}
              >
                {t(`pivot.numberFormat.${fmt === 'k-notation' ? 'kNotation' : fmt}`)}
              </Button>
            ))}
          </ButtonGroup>
        </Flex>
      )}
    </Flex>
  ) : null;

  // -----------------------------------------------------------------------
  // Render — single root element with conditional content inside.
  // This avoids the React removeChild error caused by switching between
  // completely different root elements (fragment vs Card) across renders.
  // -----------------------------------------------------------------------

  // No columns means no query has been executed yet — render nothing
  if (columns.length === 0 && !isLoading) {
    return <Box />;
  }

  return (
    <Card bg="gray.700">
      <CardBody>
        {/* Loading state */}
        {isLoading && (
          <Flex align="center" justify="center" py={8} gap={3}>
            <Spinner size="md" color="orange.400" />
            <Text color="gray.300" fontSize="sm">
              {t('pivot.results.loading')}
            </Text>
          </Flex>
        )}

        {/* Empty results — query executed but returned zero rows */}
        {!isLoading && columns.length > 0 && data.length === 0 && (
          <Alert status="info" borderRadius="md" bg="gray.600">
            <AlertIcon />
            <Text color="white" fontSize="sm">
              {t('pivot.results.noData')}
            </Text>
          </Alert>
        )}

        {/* Data content — only rendered when we have results */}
        {!isLoading && hasData && (
          <>
            {toolbar}

            {/* Column-pivoted mode */}
            {isPivoted && (
              <PivotResultTablePivoted
                data={data}
                columns={columns}
                config={config}
                numberFormat={activeFormat}
              />
            )}

            {/* Hierarchical mode */}
            {!isPivoted && isHierarchical && (
              <TableContainer overflowX="auto">
                <Table size="sm" variant="simple" w="auto">
                  <Thead>
                    <Tr>
                      {/* Single "Group" header for the tree label column */}
                      <Th color="gray.300" fontSize="xs" borderColor="gray.600">
                        {groupColumnNames.join(' → ')}
                      </Th>
                      {/* Aggregate column headers */}
                      {columns
                        .filter((c) => c.type === 'aggregate')
                        .map((col) => (
                          <Th
                            key={col.name}
                            color="gray.300"
                            fontSize="xs"
                            borderColor="gray.600"
                            isNumeric
                          >
                            {col.name}
                          </Th>
                        ))}
                    </Tr>
                  </Thead>
                  <Tbody>
                    {flatNodes.map((node, idx) => {
                      const hasChildren = node.children.length > 0;
                      const isParent = hasChildren;

                      // Depth-based styling: higher levels are bolder with distinct backgrounds
                      const depthBg = node.depth === 0
                        ? 'gray.600'
                        : node.depth === 1
                          ? 'gray.650'
                          : undefined;
                      const depthFontWeight = node.depth === 0
                        ? 'bold'
                        : isParent
                          ? 'semibold'
                          : 'normal';
                      const depthFontSize = node.depth === 0
                        ? 'sm'
                        : node.depth === 1
                          ? 'sm'
                          : 'xs';
                      const depthBorderTop = node.depth === 0
                        ? '2px solid'
                        : node.depth === 1
                          ? '1px solid'
                          : undefined;
                      const depthBorderColor = node.depth === 0
                        ? 'orange.500'
                        : node.depth === 1
                          ? 'gray.500'
                          : undefined;

                      return (
                        <Tr
                          key={`${node.groupColumn}-${node.value}-${idx}`}
                          _hover={{ bg: 'gray.550' }}
                          cursor={isParent ? 'pointer' : 'default'}
                          onClick={isParent ? () => toggleNode(node) : undefined}
                          fontWeight={depthFontWeight}
                          bg={depthBg}
                          borderTop={depthBorderTop}
                          borderColor={depthBorderColor}
                          data-testid={`tree-row-${node.depth}-${node.value}`}
                        >
                          {/* Tree label cell with indentation and expand/collapse icon */}
                          <Td color="white" fontSize={depthFontSize}>
                            <Flex align="center">
                              <Box w={`${node.depth * INDENT_PX}px`} flexShrink={0} />
                              {isParent ? (
                                <Icon
                                  as={node.isExpanded ? ChevronDownIcon : ChevronRightIcon}
                                  boxSize={4}
                                  color="orange.400"
                                  mr={1}
                                  data-testid={`tree-toggle-${node.value}`}
                                />
                              ) : (
                                <Box w="20px" flexShrink={0} />
                              )}
                              <Text as="span" color={node.depth === 0 ? 'orange.300' : isParent ? 'orange.200' : 'white'}>
                                {node.value != null ? String(node.value) : t('pivot.results.grandTotal')}
                              </Text>
                            </Flex>
                          </Td>

                          {/* Aggregate value cells */}
                          {aggregateColumnNames.map((colName) => {
                            const col = columns.find((c) => c.name === colName);
                            const value = node.aggregates[colName];
                            return (
                              <Td
                                key={colName}
                                color="white"
                                fontSize={depthFontSize}
                                isNumeric
                              >
                                {col && value != null
                                  ? formatCellValue(value, col, activeFormat, locale)
                                  : ''}
                              </Td>
                            );
                          })}
                        </Tr>
                      );
                    })}
                  </Tbody>
                </Table>
              </TableContainer>
            )}

            {/* Flat mode */}
            {!isPivoted && !isHierarchical && (
              <TableContainer overflowX="auto">
                <Table size="sm" variant="simple" w="auto">
                  <Thead>
                    <Tr>
                      {columns.map((col) => (
                        <FilterableHeader
                          key={col.name}
                          label={col.name}
                          filterValue={filters[col.name]}
                          onFilterChange={(v) => setFilter(col.name, v)}
                          sortable
                          sortDirection={columnSortDirection(col.name)}
                          onSort={() => handleSort(col.name)}
                          isNumeric={col.type === 'aggregate'}
                        />
                      ))}
                    </Tr>
                  </Thead>
                  <Tbody>
                    {processedData.map((row, rowIndex) => (
                      <Tr
                        key={rowIndex}
                        _hover={{ bg: 'gray.600' }}
                      >
                        {columns.map((col) => (
                          <Td
                            key={col.name}
                            color="white"
                            fontSize="sm"
                            isNumeric={col.type === 'aggregate'}
                          >
                            {formatCellValue(row[col.name], col, activeFormat, locale)}
                          </Td>
                        ))}
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}

export default PivotResultTable;
