/**
 * spec 12 (Application Form Serving Redesign) task 5.3 — the FRONTEND half of the CLIENT↔SERVER
 * filter-parity PIN.
 *
 * Task 5.2 deleted the server preview endpoint (`POST /members/application-preview`); the builder's
 * in-browser preview now reproduces the server's applicant-facing SELECTION entirely in the browser
 * via the pure `buildPreviewConfig` filter (task 5.1). This test is the frontend side of the pin
 * that stops the two filters silently drifting now the endpoint is gone (R3.2 / R9.1):
 *
 *   the SAME canonical fixture input, fed to the REAL client filter (`buildPreviewConfig`), must —
 *   after a plane-neutral normalization — produce the SAME `expected` applicant-facing selection the
 *   SAM parity test (`sam/tests/test_application_filter_parity.py`) asserts the server
 *   `get_public_field_config` produces.
 *
 * The ONE canonical fixture lives at `sam/tests/fixtures/application_form_filter_parity.json`; this
 * test root carries a byte-identical vendored copy. `the two fixture copies are byte-identical` is
 * the DRIFT GUARD: if either copy is edited without mirroring the other, it fails — so "both planes
 * compare against the SAME expected output" is enforced, not merely asserted by convention.
 *
 * The server filter is the AUTHORITY (R5.2); if the two ever diverge the CLIENT (`buildPreviewConfig`)
 * is reconciled to the server, never this assertion weakened.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { buildPreviewConfig } from '../applicationPreviewFilter';
import type { FieldConfig, FieldConfigField, MembershipType } from '../../../../types/members';
import type { PublicField, PublicFieldConfig } from '../../../public/application/applicationFieldConfig';

const _here = dirname(fileURLToPath(import.meta.url));
// The frontend vendored copy (this test root) and the canonical SAM copy (repo authority).
const FRONTEND_FIXTURE = resolve(_here, 'fixtures/application_form_filter_parity.json');
// _here = frontend/src/components/TenantAdmin/MembersConfig/__tests__ → up 6 to the repo root.
const REPO_ROOT = resolve(_here, '../../../../../..');
const SAM_FIXTURE = resolve(REPO_ROOT, 'sam/tests/fixtures/application_form_filter_parity.json');

const FIXTURE_RAW = readFileSync(FRONTEND_FIXTURE, 'utf-8');
const FIXTURE = JSON.parse(FIXTURE_RAW) as ParityFixture;

interface CanonicalOption {
  value: string;
  label: { nl: string; en: string };
}
interface CanonicalField {
  key: string;
  type: string;
  label: { nl: string; en: string };
  functional_group?: string;
  order: number;
  required: boolean;
  options: CanonicalOption[] | null;
  show_when?: Record<string, unknown>;
  format?: { checker: string; params: Record<string, unknown> };
}
interface ParityFixture {
  tenant_id: string;
  membership_type_catalog: Array<{
    type_code: string;
    label: { nl: string; en: string };
    active: boolean;
    order: number;
  }>;
  input: { resolved_fields: Array<Record<string, unknown>> };
  expected: { locales: string[]; fields: CanonicalField[] };
}

/** Build the RESOLVED `FieldConfig` the client filter consumes from the fixture's resolved fields. */
function fieldConfigFromFixture(): FieldConfig {
  const fields = FIXTURE.input.resolved_fields.map((rf) => ({ ...(rf as object) }) as FieldConfigField);
  return { fields } as FieldConfig;
}

/** Build the live membership-type catalog the client filter sources the reference field from. */
function catalogFromFixture(): MembershipType[] {
  return FIXTURE.membership_type_catalog.map(
    (c) => ({ type_code: c.type_code, label: c.label, active: c.active, order: c.order }) as MembershipType,
  );
}

// ── normalization: the CLIENT PublicFieldConfig → the plane-neutral `expected` shape ──

function normOptions(raw: PublicField['options']): CanonicalOption[] | null {
  // The client filter OMITS `options` on a non-choice field; the canonical shape is an explicit
  // `null` (matching the server's `options: None`), so an absent list normalizes to null.
  if (raw == null) return null;
  return raw.map((o) => {
    if (typeof o === 'string') return { value: o, label: { nl: o, en: o } };
    const label = o.label;
    if (label && typeof label === 'object') {
      return { value: o.value, label: { nl: label.nl ?? o.value, en: label.en ?? o.value } };
    }
    const s = typeof label === 'string' && label ? label : o.value;
    return { value: o.value, label: { nl: s, en: s } };
  });
}

function normalizeClientField(f: PublicField): CanonicalField {
  const out: CanonicalField = {
    key: f.key,
    type: f.type,
    label: { nl: f.label?.nl ?? '', en: f.label?.en ?? '' },
    functional_group: f.functional_group,
    order: typeof f.order === 'number' ? f.order : 0,
    required: !!f.required,
    options: normOptions(f.options),
  };
  if (f.show_when != null) out.show_when = f.show_when as Record<string, unknown>;
  if (f.format != null) {
    out.format = { checker: f.format.checker, params: (f.format.params ?? {}) as Record<string, unknown> };
  }
  return out;
}

function normalizeClientSchema(schema: PublicFieldConfig) {
  return {
    locales: [...(schema.locales ?? [])],
    fields: schema.fields.map(normalizeClientField),
  };
}

describe('application filter parity (frontend half of the client↔server pin, R3.2)', () => {
  it('the two fixture copies are byte-identical (drift guard)', () => {
    const samRaw = readFileSync(SAM_FIXTURE, 'utf-8');
    expect(samRaw).toBe(FIXTURE_RAW);
  });

  it('buildPreviewConfig matches the canonical expected applicant-facing selection', () => {
    const out = buildPreviewConfig(fieldConfigFromFixture(), {}, catalogFromFixture());
    expect(normalizeClientSchema(out)).toEqual(FIXTURE.expected);
  });

  it('exposes the same applicant locales the server (and the fixture) declare', () => {
    const out = buildPreviewConfig(fieldConfigFromFixture(), {}, catalogFromFixture());
    expect(out.locales).toEqual(FIXTURE.expected.locales);
  });
});
