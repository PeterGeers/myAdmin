/**
 * Unit tests for pivotTreeBuilder utilities.
 *
 * Tests buildHierarchicalTree() and flattenTree() with various
 * group column configurations and aggregate rollup scenarios.
 *
 * Requirements: 8.2, 8.3
 */

import {
  buildHierarchicalTree,
  flattenTree,
  PivotTreeNode,
} from './pivotTreeBuilder';

describe('buildHierarchicalTree', () => {
  it('returns empty array for empty rows', () => {
    const result = buildHierarchicalTree([], ['channel'], ['SUM_Amount']);
    expect(result).toEqual([]);
  });

  it('returns empty array for empty group columns', () => {
    const rows = [{ channel: 'Airbnb', SUM_Amount: 100 }];
    const result = buildHierarchicalTree(rows, [], ['SUM_Amount']);
    expect(result).toEqual([]);
  });

  it('builds single-level tree with one group column', () => {
    const rows = [
      { channel: 'Airbnb', SUM_Amount: 100, COUNT: 5 },
      { channel: 'Booking.com', SUM_Amount: 200, COUNT: 10 },
    ];

    const tree = buildHierarchicalTree(rows, ['channel'], ['SUM_Amount', 'COUNT']);

    expect(tree).toHaveLength(2);
    expect(tree[0].value).toBe('Airbnb');
    expect(tree[0].groupColumn).toBe('channel');
    expect(tree[0].depth).toBe(0);
    expect(tree[0].aggregates).toEqual({ SUM_Amount: 100, COUNT: 5 });
    expect(tree[0].children).toEqual([]);

    expect(tree[1].value).toBe('Booking.com');
    expect(tree[1].aggregates).toEqual({ SUM_Amount: 200, COUNT: 10 });
  });

  it('builds two-level tree with two group columns', () => {
    const rows = [
      { channel: 'Airbnb', year: 2024, SUM_Amount: 100 },
      { channel: 'Airbnb', year: 2025, SUM_Amount: 150 },
      { channel: 'Booking.com', year: 2024, SUM_Amount: 200 },
    ];

    const tree = buildHierarchicalTree(rows, ['channel', 'year'], ['SUM_Amount']);

    expect(tree).toHaveLength(2);

    // Airbnb parent
    const airbnb = tree[0];
    expect(airbnb.value).toBe('Airbnb');
    expect(airbnb.depth).toBe(0);
    expect(airbnb.children).toHaveLength(2);
    expect(airbnb.aggregates.SUM_Amount).toBe(250); // 100 + 150

    // Airbnb children
    expect(airbnb.children[0].value).toBe(2024);
    expect(airbnb.children[0].depth).toBe(1);
    expect(airbnb.children[0].aggregates.SUM_Amount).toBe(100);

    expect(airbnb.children[1].value).toBe(2025);
    expect(airbnb.children[1].aggregates.SUM_Amount).toBe(150);

    // Booking.com parent
    const booking = tree[1];
    expect(booking.value).toBe('Booking.com');
    expect(booking.children).toHaveLength(1);
    expect(booking.aggregates.SUM_Amount).toBe(200);
  });

  it('builds three-level tree', () => {
    const rows = [
      { channel: 'Airbnb', listing: 'Amsterdam', year: 2024, SUM_Amount: 100 },
      { channel: 'Airbnb', listing: 'Amsterdam', year: 2025, SUM_Amount: 150 },
      { channel: 'Airbnb', listing: 'Rotterdam', year: 2024, SUM_Amount: 80 },
    ];

    const tree = buildHierarchicalTree(
      rows,
      ['channel', 'listing', 'year'],
      ['SUM_Amount'],
    );

    expect(tree).toHaveLength(1); // Only Airbnb
    const airbnb = tree[0];
    expect(airbnb.aggregates.SUM_Amount).toBe(330); // 100 + 150 + 80
    expect(airbnb.children).toHaveLength(2); // Amsterdam, Rotterdam

    const amsterdam = airbnb.children[0];
    expect(amsterdam.value).toBe('Amsterdam');
    expect(amsterdam.aggregates.SUM_Amount).toBe(250); // 100 + 150
    expect(amsterdam.children).toHaveLength(2);

    const rotterdam = airbnb.children[1];
    expect(rotterdam.value).toBe('Rotterdam');
    expect(rotterdam.aggregates.SUM_Amount).toBe(80);
    expect(rotterdam.children).toHaveLength(1);
  });

  it('skips rollup rows (all group columns null)', () => {
    const rows = [
      { channel: 'Airbnb', SUM_Amount: 100 },
      { channel: 'Booking.com', SUM_Amount: 200 },
      { channel: null, SUM_Amount: 300 }, // Grand total rollup row
    ];

    const tree = buildHierarchicalTree(rows, ['channel'], ['SUM_Amount']);
    expect(tree).toHaveLength(2); // Rollup row excluded
  });

  it('skips null group values within levels', () => {
    const rows = [
      { channel: 'Airbnb', year: 2024, SUM_Amount: 100 },
      { channel: 'Airbnb', year: null, SUM_Amount: 100 }, // Subtotal rollup
      { channel: null, year: null, SUM_Amount: 100 }, // Grand total rollup
    ];

    const tree = buildHierarchicalTree(rows, ['channel', 'year'], ['SUM_Amount']);
    expect(tree).toHaveLength(1);
    expect(tree[0].children).toHaveLength(1); // Only year=2024, null skipped
  });

  it('uses SUM as default aggregation for rollup', () => {
    const rows = [
      { channel: 'Airbnb', year: 2024, SUM_Amount: 100 },
      { channel: 'Airbnb', year: 2025, SUM_Amount: 200 },
    ];

    const tree = buildHierarchicalTree(rows, ['channel', 'year'], ['SUM_Amount']);
    expect(tree[0].aggregates.SUM_Amount).toBe(300);
  });

  it('supports MIN aggregation function', () => {
    const rows = [
      { channel: 'Airbnb', year: 2024, MIN_Price: 50 },
      { channel: 'Airbnb', year: 2025, MIN_Price: 30 },
    ];

    const tree = buildHierarchicalTree(
      rows,
      ['channel', 'year'],
      ['MIN_Price'],
      { aggregateFunctions: { MIN_Price: 'MIN' } },
    );
    expect(tree[0].aggregates.MIN_Price).toBe(30);
  });

  it('supports MAX aggregation function', () => {
    const rows = [
      { channel: 'Airbnb', year: 2024, MAX_Price: 50 },
      { channel: 'Airbnb', year: 2025, MAX_Price: 80 },
    ];

    const tree = buildHierarchicalTree(
      rows,
      ['channel', 'year'],
      ['MAX_Price'],
      { aggregateFunctions: { MAX_Price: 'MAX' } },
    );
    expect(tree[0].aggregates.MAX_Price).toBe(80);
  });

  it('sets branch nodes as expanded by default', () => {
    const rows = [
      { channel: 'Airbnb', year: 2024, SUM_Amount: 100 },
    ];

    const tree = buildHierarchicalTree(rows, ['channel', 'year'], ['SUM_Amount']);
    expect(tree[0].isExpanded).toBe(true); // Branch node
    expect(tree[0].children[0].isExpanded).toBe(false); // Leaf node
  });

  it('preserves originalRow on leaf nodes with single row', () => {
    const rows = [
      { channel: 'Airbnb', SUM_Amount: 100, extra: 'data' },
    ];

    const tree = buildHierarchicalTree(rows, ['channel'], ['SUM_Amount']);
    expect(tree[0].originalRow).toEqual(rows[0]);
  });
});

describe('flattenTree', () => {
  it('returns empty array for empty tree', () => {
    expect(flattenTree([])).toEqual([]);
  });

  it('flattens single-level tree', () => {
    const nodes: PivotTreeNode[] = [
      { value: 'A', groupColumn: 'col', depth: 0, aggregates: {}, children: [], isExpanded: false },
      { value: 'B', groupColumn: 'col', depth: 0, aggregates: {}, children: [], isExpanded: false },
    ];

    const flat = flattenTree(nodes);
    expect(flat).toHaveLength(2);
    expect(flat[0].value).toBe('A');
    expect(flat[1].value).toBe('B');
  });

  it('includes children of expanded nodes', () => {
    const child: PivotTreeNode = {
      value: 2024, groupColumn: 'year', depth: 1,
      aggregates: { SUM: 100 }, children: [], isExpanded: false,
    };
    const parent: PivotTreeNode = {
      value: 'Airbnb', groupColumn: 'channel', depth: 0,
      aggregates: { SUM: 100 }, children: [child], isExpanded: true,
    };

    const flat = flattenTree([parent]);
    expect(flat).toHaveLength(2);
    expect(flat[0].value).toBe('Airbnb');
    expect(flat[1].value).toBe(2024);
  });

  it('excludes children of collapsed nodes', () => {
    const child: PivotTreeNode = {
      value: 2024, groupColumn: 'year', depth: 1,
      aggregates: { SUM: 100 }, children: [], isExpanded: false,
    };
    const parent: PivotTreeNode = {
      value: 'Airbnb', groupColumn: 'channel', depth: 0,
      aggregates: { SUM: 100 }, children: [child], isExpanded: false,
    };

    const flat = flattenTree([parent]);
    expect(flat).toHaveLength(1);
    expect(flat[0].value).toBe('Airbnb');
  });
});
