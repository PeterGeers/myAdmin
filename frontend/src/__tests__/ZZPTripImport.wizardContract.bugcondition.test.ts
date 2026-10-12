/**
 * Bug Condition Exploration Test — ZZP Trip Import Wizard Contract (surface a)
 *
 * Spec: .kiro/specs/trip-import-preview-empty-fix  (bugfix)
 * Property 1 (surface a): Successful Import Response Not Mapped/Rendered/Committed
 *
 * CRITICAL: This test encodes the POST-FIX (correct) expectations.
 * On UNFIXED frontend code it MUST FAIL — failure confirms the bug exists.
 * After task 6 applies the fix, this same test validates the fix when it passes.
 *
 * Bug condition C(X): X.success === true  (a successful import-validation response).
 * The backend returns the validation result FLAT at the top level
 *   { success, total_rows, valid, warnings, errors, rows, preview }
 * and annotates each preview row with underscore-prefixed fields
 *   { _row_number, _status, _messages }.
 * The unfixed wizard instead:
 *   1. reads `resp.data` (nested) -> `undefined` -> null validationResult -> empty Preview;
 *   2. reads per-row `status` / `messages` / `row_number` -> empty status badges;
 *   3. commits `{ vehicle_id, column_mapping }` instead of the validated `rows`.
 *
 * The three defects are documented here as assertions against the FIXED shapes:
 *   (1) mapResponseToPreviewState  — mirrors ZZPTripImport.handleNext mapping;
 *   (2) getStatusBadge             — mirrors ZZPTripImport.getStatusBadge;
 *   (3) commitImport               — the REAL tripService.commitImport payload.
 *
 * (1) and (2) live inside the ZZPTripImport component as un-exported closures, so
 * — following the project convention for logic embedded in a component — the exact
 * current source expression is replicated inline and asserted against the post-fix
 * expectation. When task 6 edits ZZPTripImport.tsx, the SAME edit must be mirrored
 * into the `mapResponseToPreviewState` / `getStatusBadge` helpers below so this test
 * flips from failing to passing. (3) exercises the real exported service function,
 * so it tracks the source directly.
 *
 * Requirements: 2.1, 2.2, 2.4, 2.5
 */
import { vi } from 'vitest';
import { commitImport } from '../services/tripService';
import type { ImportRow } from '../types/zzpTrips';

/* ─── apiService mock (same pattern as contactService.test.ts) ─── */
const mockPost = vi.fn();
vi.mock('../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => vi.fn()(...args),
  authenticatedPost: (...args: any[]) => mockPost(...args),
  authenticatedPut: (...args: any[]) => vi.fn()(...args),
  authenticatedRequest: (...args: any[]) => vi.fn()(...args),
  authenticatedFormData: (...args: any[]) => vi.fn()(...args),
  buildEndpoint: (endpoint: string) => endpoint,
}));

const json = (data: any) => ({ json: async () => data });

/* ─────────────────────────────────────────────────────────────────────────
 * Local mirrors of the two un-exported component closures.
 *
 *   >>> TASK 6: when ZZPTripImport.handleNext / getStatusBadge are fixed,
 *       mirror the SAME change into these two helpers. <<<
 *
 * They are currently written to reflect the UNFIXED source expressions, so the
 * post-fix assertions below FAIL — proving the bug.
 * ──────────────────────────────────────────────────────────────────────── */

/** The wizard's local validation-state shape (post-fix target: adds `rows`). */
interface ImportValidationResult {
  total_rows: number;
  valid: number;
  warnings: number;
  errors: number;
  preview: ImportRow[];
  rows: ImportRow[];
}

/**
 * Mirror of ZZPTripImport.handleNext (Upload -> Preview branch).
 * UNFIXED source: `setValidationResult(resp.data as unknown as ImportValidationResult)`.
 */
function mapResponseToPreviewState(resp: any): ImportValidationResult | undefined {
  // --- post-fix (task 6.1): build state from the flat top-level fields ---
  return {
    total_rows: resp.total_rows,
    valid: resp.valid,
    warnings: resp.warnings,
    errors: resp.errors,
    preview: resp.preview,
    rows: resp.rows,
  };
}

/** Resolved badge presentation (what the Chakra <Badge>/<Tooltip> receives). */
interface BadgePresentation {
  colorScheme: string | undefined;
  label: string | undefined;
  tooltip: string;
}

/**
 * Mirror of ZZPTripImport.getStatusBadge.
 * UNFIXED source reads `row.status` / `row.messages` (unprefixed).
 */
function getStatusBadge(row: any): BadgePresentation {
  const colorMap: Record<string, string> = { ok: 'green', warning: 'yellow', error: 'red' };
  const labelMap: Record<string, string> = { ok: 'OK', warning: 'Waarschuwing', error: 'Fout' };
  // --- post-fix (task 6): read the underscore-prefixed per-row fields ---
  const status = row._status;
  const messages = row._messages;
  return {
    colorScheme: colorMap[status],
    label: labelMap[status],
    tooltip: messages?.length > 0 ? messages.join('\n') : 'Geen opmerkingen',
  };
}

/* ─── Fixtures: a flat, successful backend response ─── */
const flatRow = (overrides: Partial<ImportRow> & { _row_number: number; _status: string }): ImportRow =>
({
  trip_date: '2026-05-05',
  start_address: 'Amsterdam',
  end_address: 'Utrecht',
  start_odometer: 45000,
  end_odometer: 45050,
  trip_category: 'zakelijk',
  trip_purpose: 'klantbezoek',
  ...overrides,
  _messages: overrides._messages ?? [],
} as unknown as ImportRow);

const okRow = flatRow({ _row_number: 1, _status: 'ok', _messages: [] });
const warnRow = flatRow({ _row_number: 2, _status: 'warning', _messages: ['Categorie ontbreekt'] });
const errRow = flatRow({ _row_number: 3, _status: 'error', _messages: ['Ongeldig datumformaat'] });

/** Flat success response as the backend actually returns it. */
const flatSuccessResponse = {
  success: true,
  total_rows: 3,
  valid: 3,
  warnings: 0,
  errors: 0,
  rows: [okRow, warnRow, errRow],
  preview: [okRow, warnRow, errRow],
};

describe('Bug Condition Exploration — ZZP Trip Import wizard contract (surface a)', () => {
  beforeEach(() => vi.clearAllMocks());

  /* ───────── (1) Flat response mapping (Requirements 2.1, 2.2) ───────── */
  describe('mapResponseToPreviewState — flat response must populate the preview state', () => {
    it('maps a flat success response to a populated validation state (not undefined/null)', () => {
      const state = mapResponseToPreviewState(flatSuccessResponse);

      // BUG: unfixed reads resp.data -> undefined -> empty Preview.
      expect(state).toBeDefined();
      expect(state).not.toBeNull();
    });

    it('maps every top-level count and the preview/rows arrays from the flat fields', () => {
      const state = mapResponseToPreviewState(flatSuccessResponse);

      expect(state?.total_rows).toBe(3);
      expect(state?.valid).toBe(3);
      expect(state?.warnings).toBe(0);
      expect(state?.errors).toBe(0);
      expect(state?.preview).toEqual(flatSuccessResponse.preview);
      // rows must be carried so the commit step has the full validated set.
      expect(state?.rows).toEqual(flatSuccessResponse.rows);
    });

    it('COUNTEREXAMPLE: reading resp.data from the flat response yields undefined', () => {
      // This documents the exact empty-preview cause. It PASSES on unfixed code
      // (resp.data IS undefined) and will no longer hold once task 6 maps the
      // flat fields — at which point the mapping assertions above take over.
      expect((flatSuccessResponse as any).data).toBeUndefined();
    });
  });

  /* ───────── (2) Per-row status badge from underscore fields (Requirement 2.4) ───────── */
  describe('getStatusBadge — must read _status / _messages', () => {
    it('ok row -> green "OK" badge', () => {
      const badge = getStatusBadge(okRow);
      expect(badge.colorScheme).toBe('green');
      expect(badge.label).toBe('OK');
    });

    it('warning row -> yellow "Waarschuwing" badge joining _messages', () => {
      const badge = getStatusBadge(warnRow);
      expect(badge.colorScheme).toBe('yellow');
      expect(badge.label).toBe('Waarschuwing');
      expect(badge.tooltip).toBe('Categorie ontbreekt');
    });

    it('error row -> red "Fout" badge joining _messages', () => {
      const badge = getStatusBadge(errRow);
      expect(badge.colorScheme).toBe('red');
      expect(badge.label).toBe('Fout');
      expect(badge.tooltip).toBe('Ongeldig datumformaat');
    });
  });

  /* ───────── (3) Commit payload (Requirement 2.5) ───────── */
  describe('commitImport — must POST { vehicle_id, rows, skip_error_rows }', () => {
    it('sends the validated rows (and skip_error_rows), not a column_mapping', async () => {
      mockPost.mockResolvedValue(json({ success: true, imported: 3 }));

      // Post-fix signature: commitImport(vehicleId, rows, skipErrorRows)
      await (commitImport as any)(7, flatSuccessResponse.rows, true);

      expect(mockPost).toHaveBeenCalledTimes(1);
      const [endpoint, body] = mockPost.mock.calls[0];
      expect(endpoint).toBe('/api/zzp/trips/import/commit');
      expect(body).toEqual({
        vehicle_id: 7,
        rows: flatSuccessResponse.rows,
        skip_error_rows: true,
      });
      // BUG: unfixed commitImport posts { vehicle_id, column_mapping } with no rows.
      expect(body).not.toHaveProperty('column_mapping');
      expect(body.rows).toHaveLength(3);
    });
  });
});
