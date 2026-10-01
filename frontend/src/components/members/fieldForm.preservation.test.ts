/**
 * Members modal field-mapping mismatch bugfix — Task 2 PRESERVATION tests (frontend plane).
 *
 * Feature: members-modal-field-mapping-mismatch
 * Property 6: Preservation — any OTHER field carrying a `show_when` gate still toggles correctly
 * via `evaluateShowWhen`. The fix only changes `referral_source`'s gate (it is dropped in the
 * config, tasks 3/5); every other conditional-visibility gate must behave EXACTLY as before.
 *
 * Observation-first: these assertions were recorded against the UNFIXED `evaluateShowWhen`
 * predicate (the shared `{ controllingKey: expected }`-ANDed convention). They are EXPECTED TO
 * PASS on unfixed code and must CONTINUE to pass after the fix — the config edit does not touch
 * `evaluateShowWhen` itself, only which fields carry a gate.
 *
 * Validates: Requirements 3.4, 3.6
 */

import { describe, it, expect } from 'vitest';
import { evaluateShowWhen } from './fieldForm';

describe('evaluateShowWhen preservation — other show_when gates unchanged (R3.4, R3.6)', () => {
  it('a scalar gate on ANOTHER field still toggles on an exact match', () => {
    // A legitimately-conditional field (e.g. a motor field gated on membership_type) keeps
    // toggling: shown when the controlling value matches, hidden otherwise.
    const gate = { membership_type: 'motor' };
    expect(evaluateShowWhen(gate, { membership_type: 'motor' })).toBe(true);
    expect(evaluateShowWhen(gate, { membership_type: 'family' })).toBe(false);
    expect(evaluateShowWhen(gate, {})).toBe(false); // controlling value absent → hidden
  });

  it('a list (one-of) gate on another field still toggles', () => {
    const gate = { membership_type: ['motor', 'sport'] };
    expect(evaluateShowWhen(gate, { membership_type: 'sport' })).toBe(true);
    expect(evaluateShowWhen(gate, { membership_type: 'motor' })).toBe(true);
    expect(evaluateShowWhen(gate, { membership_type: 'family' })).toBe(false);
  });

  it('a multi-key gate still requires ALL conditions (implicit AND)', () => {
    const gate = { membership_type: 'motor', active: 'yes' };
    expect(evaluateShowWhen(gate, { membership_type: 'motor', active: 'yes' })).toBe(true);
    expect(evaluateShowWhen(gate, { membership_type: 'motor', active: 'no' })).toBe(false);
  });

  it('a dotted controlling key still resolves to its bare tail', () => {
    expect(
      evaluateShowWhen({ 'membership.membership_type': 'motor' }, { membership_type: 'motor' }),
    ).toBe(true);
  });

  it('a field with no gate is always shown (absent/empty show_when)', () => {
    expect(evaluateShowWhen(null, { member_id: 'abc' })).toBe(true);
    expect(evaluateShowWhen(undefined, { member_id: 'abc' })).toBe(true);
    expect(evaluateShowWhen({}, { member_id: 'abc' })).toBe(true);
  });

  it('BASELINE: the malformed referral_source gate resolves false everywhere (pre-fix)', () => {
    // Observed UNFIXED behavior — recorded here so the fix (dropping this gate) is a visible,
    // intentional change and this preservation suite documents the pre-fix baseline. The
    // `{ field, op }` shape is read as TWO controlling keys ANDed, which no real row satisfies.
    const referralGate = { field: 'member_id', op: 'not_exists' };
    // An existing member's flat row (carries a member_id, not a literal `field`/`op` key):
    expect(evaluateShowWhen(referralGate, { member_id: 'm-123', referral_source: 'x' })).toBe(false);
    // An empty create-form value map:
    expect(evaluateShowWhen(referralGate, {})).toBe(false);
  });
});
