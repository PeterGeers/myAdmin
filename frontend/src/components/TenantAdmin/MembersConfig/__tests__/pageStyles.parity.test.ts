/**
 * spec 15 (SAM Page Look-and-Feel) task 13.2 — the FRONTEND/REACT half of the Layer-2/3
 * PYTHON ↔ REACT parity PIN.
 *
 * Task 13.1 made `pageStyles.ts` (`renderPageStyles`) a byte-level mirror of the SAM-owned
 * AUTHORITATIVE Python Layer-2 generator `sam.shared.page_styles.render_page_styles`. This
 * test FORMALIZES that parity as a COMMITTED shared fixture both planes read (DD-3 / design
 * §C5, Req 7.1 / 7.3), mirroring the existing `buildPreviewConfig` ↔ `get_public_field_config`
 * pin (`applicationFilterParity.test.ts`):
 *
 *   the SAME canonical fixture cases, fed to the REAL client generator (`renderPageStyles`),
 *   must reproduce the SAME `expected` cssVariables / pageCss / fontLinks the SAM python
 *   parity test (`sam/tests/test_page_styles_parity.py`) asserts `render_page_styles` produces.
 *
 * The ONE canonical fixture lives at `sam/tests/fixtures/page_styles_parity.json`; this test
 * root carries a byte-identical vendored copy. The `expected` values were GENERATED FROM the
 * Python generator, so they are authoritative — a drift in EITHER the Python generator or this
 * TS mirror is caught on BOTH sides.
 *
 * `the two fixture copies are byte-identical` is the DRIFT GUARD: if either copy is edited
 * without mirroring the other, it fails — so "both planes compare against the SAME expected
 * output" is enforced, not merely asserted by convention.
 *
 * The Python generator is the AUTHORITY (design §C5): if the two ever diverge the CLIENT
 * (`renderPageStyles`) is reconciled to the Python output, never this assertion weakened.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { renderPageStyles, type LookAndFeelSettings } from '../pageStyles';

const _here = dirname(fileURLToPath(import.meta.url));
// The frontend vendored copy (this test root) and the canonical SAM copy (repo authority).
const FRONTEND_FIXTURE = resolve(_here, 'fixtures/page_styles_parity.json');
// _here = frontend/src/components/TenantAdmin/MembersConfig/__tests__ → up 6 to the repo root.
const REPO_ROOT = resolve(_here, '../../../../../..');
const SAM_FIXTURE = resolve(REPO_ROOT, 'sam/tests/fixtures/page_styles_parity.json');

interface ParityCase {
  name: string;
  description: string;
  input: LookAndFeelSettings;
  expected: {
    cssVariables: string;
    pageCss: string;
    fontLinks: string;
  };
}
interface ParityFixture {
  cases: ParityCase[];
}

const FIXTURE = JSON.parse(readFileSync(FRONTEND_FIXTURE, 'utf-8')) as ParityFixture;

describe('spec 15 task 13.2 — page-styles Python↔React parity fixture', () => {
  it('the two fixture copies are byte-identical (drift guard, Req 7.3)', () => {
    const frontendBytes = readFileSync(FRONTEND_FIXTURE);
    const samBytes = readFileSync(SAM_FIXTURE);
    expect(frontendBytes.equals(samBytes)).toBe(true);
  });

  it('covers the required case classes (defaults / full / partial / sanitiser)', () => {
    const names = new Set(FIXTURE.cases.map((c) => c.name));
    expect(names.has('all_defaults_empty')).toBe(true);
    expect(names.has('full_seven_custom')).toBe(true);
    expect([...names].filter((n) => n.startsWith('partial_')).length).toBeGreaterThanOrEqual(2);
    expect(names.has('sanitiser_dangerous_values')).toBe(true);
  });

  it.each(FIXTURE.cases.map((c) => [c.name, c] as const))(
    'renderPageStyles reproduces the canonical Python output for case %s (Req 7.1/7.3)',
    (_name, testCase) => {
      const styles = renderPageStyles(testCase.input);
      expect(styles.cssVariables).toBe(testCase.expected.cssVariables);
      expect(styles.pageCss).toBe(testCase.expected.pageCss);
      expect(styles.fontLinks).toBe(testCase.expected.fontLinks);
    },
  );
});
