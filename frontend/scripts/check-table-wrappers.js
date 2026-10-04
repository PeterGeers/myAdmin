#!/usr/bin/env node

/**
 * Responsive <Table> Wrapper Checker  (recurring-issue gate #2)
 *
 * Flags any Chakra `<Table>` that is NOT made horizontally scrollable on
 * mobile, i.e. not wrapped in a `<TableContainer>` and not inside an element
 * that sets `overflowX` (e.g. `<Box overflowX="auto">`), and without a
 * `useBreakpointValue` card fallback nearby. Tasks M6 / L1 wrapped the known
 * offenders; this gate stops the mobile-table debt from regressing.
 *
 * Why a script and not an ESLint rule: a precise JSX-ancestor check (walk up
 * the parent chain of each <Table> looking for a scroll container) is a custom
 * ESLint rule's worth of work. A bounded, well-scoped text scan is reliable and
 * precise for this codebase and far cheaper to maintain. If false positives
 * ever appear, prefer promoting this to a real custom rule over loosening it.
 *
 * Heuristic: for each `<Table` (capital T = the Chakra component; lowercase
 * `<table>` is raw HTML in test fixtures and is ignored), look at a small
 * window of preceding lines plus the opening tag itself for a responsive
 * signal. In this codebase the wrapper always sits 1-3 lines above the
 * `<Table`, so a 6-line look-back is comfortably sufficient with zero false
 * positives on the current (post-fix) tree.
 *
 * Exit code: 0 = clean, 1 = offender(s) found (so it can gate CI / pre-commit).
 */

const fs = require('fs');
const path = require('path');

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
};

const SRC_DIR = path.join(__dirname, '..', 'src');

// Files/dirs where a bare <Table> is fine: tests, mocks, examples. These never
// ship to users, so mobile responsiveness is irrelevant there.
const EXCLUDE_PATTERNS = [
  /\.test\.tsx?$/,
  /\.spec\.tsx?$/,
  /[\\/]__tests__[\\/]/,
  /[\\/]__mocks__[\\/]/,
  /[\\/]examples[\\/]/,
];

// How many lines above a <Table to scan for a responsive wrapper.
const LOOKBACK = 6;

// Signals that a <Table> is responsive (any one is enough).
const RESPONSIVE_SIGNALS = [
  /<TableContainer\b/,
  /\boverflowX\b/,
  /\buseBreakpointValue\b/,
];

/** Recursively collect .tsx files under dir. */
function collectTsx(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collectTsx(full, out);
    } else if (entry.isFile() && entry.name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

function isExcluded(file) {
  return EXCLUDE_PATTERNS.some((re) => re.test(file));
}

function hasResponsiveSignal(lines, tableLineIdx) {
  const start = Math.max(0, tableLineIdx - LOOKBACK);
  // Include the <Table opening line itself (a Table can carry overflow props,
  // though rare) plus the look-back window.
  const window = lines.slice(start, tableLineIdx + 1).join('\n');
  return RESPONSIVE_SIGNALS.some((re) => re.test(window));
}

function checkFile(file) {
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  const offenders = [];
  lines.forEach((line, idx) => {
    // Skip single-line `//` comments so a `<Table` mentioned in a comment is
    // not treated as a real JSX element.
    if (/^\s*\/\//.test(line)) return;
    // Chakra component only: `<Table` followed by whitespace or `>`.
    // (Excludes `<TableContainer`, `<Tbody>`, and lowercase `<table>`.)
    if (/<Table[\s>]/.test(line)) {
      if (!hasResponsiveSignal(lines, idx)) {
        offenders.push({ line: idx + 1, text: line.trim() });
      }
    }
  });
  return offenders;
}

function main() {
  const files = collectTsx(SRC_DIR).filter((f) => !isExcluded(f));
  let total = 0;
  const problems = [];

  for (const file of files) {
    const offenders = checkFile(file);
    if (offenders.length) {
      problems.push({ file, offenders });
      total += offenders.length;
    }
  }

  if (total === 0) {
    console.log(
      `${colors.green}✓ check-table-wrappers: all <Table> components are inside a responsive wrapper.${colors.reset}`
    );
    process.exit(0);
  }

  console.error(
    `${colors.red}✗ check-table-wrappers: ${total} <Table> without a responsive wrapper (TableContainer / overflowX / card fallback):${colors.reset}`
  );
  for (const { file, offenders } of problems) {
    const rel = path.relative(path.join(__dirname, '..'), file);
    for (const o of offenders) {
      console.error(
        `  ${colors.cyan}${rel}:${o.line}${colors.reset}  ${colors.yellow}${o.text}${colors.reset}`
      );
    }
  }
  console.error(
    `\n${colors.red}Wrap each <Table> in <TableContainer> or <Box overflowX="auto">, or add a useBreakpointValue card fallback.${colors.reset}`
  );
  process.exit(1);
}

main();
