/**
 * Hierarchical tree builder for pivot result data.
 *
 * Converts a flat GROUP BY result set (optionally with WITH ROLLUP rows)
 * into a nested tree structure suitable for hierarchical table rendering.
 *
 * The first group column defines top-level nodes, subsequent group columns
 * create nested children. Parent nodes carry rolled-up aggregate values.
 *
 * Requirements: 8.2, 8.3
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §5 PivotResultTable
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A generic row from a pivot query result. Keys are column names, values are scalars. */
export type PivotRow = Record<string, string | number | boolean | null | undefined>;

/** A single node in the hierarchical pivot tree. */
export interface PivotTreeNode {
  /** The group column value for this node (e.g. 'Airbnb', '2024'). Null for rollup rows. */
  value: string | number | null;
  /** The group column name this node represents (e.g. 'channel', 'year'). */
  groupColumn: string;
  /** Depth in the tree (0 = top-level). */
  depth: number;
  /** Aggregate values for this node (rolled up from children or from ROLLUP row). */
  aggregates: Record<string, number | null>;
  /** Child nodes (next group column level). Empty array for leaf nodes. */
  children: PivotTreeNode[];
  /** Whether this node is expanded in the UI (default true for top-level). */
  isExpanded: boolean;
  /** The original flat row data, if this is a leaf node. */
  originalRow?: PivotRow;
}

/** Options for tree building. */
export interface BuildTreeOptions {
  /** Aggregation functions per aggregate column, used for rollup computation. */
  aggregateFunctions?: Record<string, 'SUM' | 'COUNT' | 'AVG' | 'MIN' | 'MAX'>;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Build a hierarchical tree from flat pivot result rows.
 *
 * @param rows             - Flat result rows from the pivot query.
 * @param groupColumns     - Ordered list of group column names (first = top-level).
 * @param aggregateColumns - List of aggregate column names in the result.
 * @param options          - Optional configuration (aggregate functions for rollup).
 * @returns Array of top-level tree nodes.
 *
 * @example
 * const tree = buildHierarchicalTree(
 *   rows,
 *   ['channel', 'listing', 'year'],
 *   ['SUM_Amount', 'COUNT'],
 * );
 */
export function buildHierarchicalTree(
  rows: PivotRow[],
  groupColumns: string[],
  aggregateColumns: string[],
  options?: BuildTreeOptions,
): PivotTreeNode[] {
  if (!rows.length || !groupColumns.length) {
    return [];
  }

  // Filter out full-rollup rows (all group columns null) — these are grand totals
  const dataRows = rows.filter(
    (row) => !groupColumns.every((col) => row[col] == null),
  );

  return buildLevel(dataRows, groupColumns, aggregateColumns, 0, options);
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Recursively build one level of the tree.
 *
 * Groups rows by the current group column, creates a node per distinct value,
 * and recurses into the next group column for children.
 */
function buildLevel(
  rows: PivotRow[],
  groupColumns: string[],
  aggregateColumns: string[],
  depth: number,
  options?: BuildTreeOptions,
): PivotTreeNode[] {
  if (depth >= groupColumns.length || !rows.length) {
    return [];
  }

  const currentColumn = groupColumns[depth];
  const isLeafLevel = depth === groupColumns.length - 1;

  // Group rows by the current column value
  const groups = groupBy(rows, currentColumn);

  const nodes: PivotTreeNode[] = [];

  groups.forEach((groupRows, value) => {
    if (isLeafLevel) {
      // Leaf nodes: one node per row (or per distinct value if multiple rows share the value)
      const aggregates = computeAggregates(groupRows, aggregateColumns, options);
      nodes.push({
        value,
        groupColumn: currentColumn,
        depth,
        aggregates,
        children: [],
        isExpanded: false,
        originalRow: groupRows.length === 1 ? groupRows[0] : undefined,
      });
    } else {
      // Branch nodes: recurse into children
      const children = buildLevel(groupRows, groupColumns, aggregateColumns, depth + 1, options);
      const aggregates = rollUpAggregates(children, aggregateColumns, options);

      nodes.push({
        value,
        groupColumn: currentColumn,
        depth,
        aggregates,
        children,
        isExpanded: true, // Top-level and branch nodes default to expanded
      });
    }
  });

  return nodes;
}

/**
 * Group rows by a column value, preserving insertion order.
 * Null values (from WITH ROLLUP) are excluded — they represent subtotals
 * that we compute client-side instead.
 */
function groupBy(
  rows: PivotRow[],
  column: string,
): Map<string | number | null, PivotRow[]> {
  const map = new Map<string | number | null, PivotRow[]>();

  for (const row of rows) {
    const rawValue = row[column];
    // Skip rollup rows (null values for this group column)
    if (rawValue == null) continue;

    // Coerce boolean values to string for grouping key
    const value: string | number = typeof rawValue === 'boolean' ? String(rawValue) : rawValue;

    const existing = map.get(value);
    if (existing) {
      existing.push(row);
    } else {
      map.set(value, [row]);
    }
  }

  return map;
}

/**
 * Compute aggregate values from a set of rows (for leaf nodes or direct computation).
 */
function computeAggregates(
  rows: PivotRow[],
  aggregateColumns: string[],
  options?: BuildTreeOptions,
): Record<string, number | null> {
  const result: Record<string, number | null> = {};

  for (const col of aggregateColumns) {
    const fn = options?.aggregateFunctions?.[col] ?? 'SUM';
    result[col] = applyAggregation(
      rows.map((r) => r[col]).filter((v): v is string | number | null | undefined => typeof v !== 'boolean'),
      fn,
    );
  }

  return result;
}

/**
 * Roll up aggregate values from child nodes to produce parent aggregates.
 */
function rollUpAggregates(
  children: PivotTreeNode[],
  aggregateColumns: string[],
  options?: BuildTreeOptions,
): Record<string, number | null> {
  const result: Record<string, number | null> = {};

  for (const col of aggregateColumns) {
    const fn = options?.aggregateFunctions?.[col] ?? 'SUM';
    const childValues = children.map((child) => child.aggregates[col]);
    result[col] = applyAggregation(childValues, fn);
  }

  return result;
}

/**
 * Apply an aggregation function to a list of values.
 * Null/undefined values are excluded from computation.
 */
function applyAggregation(
  values: (number | string | null | undefined)[],
  fn: 'SUM' | 'COUNT' | 'AVG' | 'MIN' | 'MAX',
): number | null {
  const nums = values
    .map((v) => (v != null ? Number(v) : NaN))
    .filter((v): v is number => !Number.isNaN(v));

  if (nums.length === 0) return null;

  switch (fn) {
    case 'SUM':
      return nums.reduce((a, b) => a + b, 0);
    case 'COUNT':
      return nums.reduce((a, b) => a + b, 0);
    case 'AVG': {
      const sum = nums.reduce((a, b) => a + b, 0);
      return sum / nums.length;
    }
    case 'MIN':
      return Math.min(...nums);
    case 'MAX':
      return Math.max(...nums);
    default:
      return nums.reduce((a, b) => a + b, 0);
  }
}

/**
 * Flatten a tree back into an ordered list of nodes for table rendering.
 *
 * Walks the tree depth-first, including only expanded branches.
 * Each entry includes the node and its depth for indentation.
 */
export function flattenTree(nodes: PivotTreeNode[]): PivotTreeNode[] {
  const result: PivotTreeNode[] = [];

  function walk(nodeList: PivotTreeNode[]) {
    for (const node of nodeList) {
      result.push(node);
      if (node.isExpanded && node.children.length > 0) {
        walk(node.children);
      }
    }
  }

  walk(nodes);
  return result;
}
