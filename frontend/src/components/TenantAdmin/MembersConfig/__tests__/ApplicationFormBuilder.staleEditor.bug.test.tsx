/**
 * R-B stale-editor exploration test (bugfix-published-form-styling, Task 2 → re-aligned in Task
 * 14.2; design.md Property 3 — "Editor reflects a change with no reload" / root cause 4 / DD-D1).
 *
 * ──────────────────────────────────────────────────────────────────────────────────────────
 *  This started life as a BUG-CONDITION exploration test: on the UNFIXED code it FAILED (the PUT
 *  edge returned no `settings`, so `res.settings ?? {}` blanked the edit), which is how it proved
 *  R-B (defect 1.8 / expected 2.8) existed. The fix has now landed — Task 14.1 made the
 *  `PUT /members/look-and-feel` edge return the resolved `{settings}` (DD-D1) — so this test is
 *  re-aligned to the REAL post-fix PUT contract and now PASSES. No assertion is weakened: it still
 *  pins the EXACT fixed behaviour — the editor reflects the authored value with NO reload.
 * ──────────────────────────────────────────────────────────────────────────────────────────
 *
 * ## What the bug was (confirmed by reading the shipped code)
 *
 * `ApplicationFormBuilder.handleSetLookAndFeel` does, after a successful save:
 *
 *     const res = await setLookAndFeelSetting(attribute, value);
 *     setLookAndFeel(res.settings ?? {});     // ← re-seeds from `res.settings`
 *
 * Pre-fix, the `PUT /members/look-and-feel` edge (`sam/members/handler/_dispatch_config.py`
 * `write_look_and_feel`) returned only the Change-Op WRITE RESULT from
 * `LookAndFeelSettingsService.set_setting` — `{ version, idempotent_replay }`, NOT a `{ settings }`
 * map (the GET dispatch returned `{ settings }`; the PUT did NOT). So `res.settings` was
 * `undefined`, `?? {}` BLANKED the optimistic edit, and the editor snapped the control back to the
 * Layer-2 DEFAULT until a fresh `getLookAndFeelSettings` GET repopulated it.
 *
 * ## The fix (Task 14.1 / DD-D1) and why this test exercises the REAL contract
 *
 * The edge now re-resolves the tenant's current values after the Change-Op and returns
 * `{ ...write-result, settings: { <resolved> } }` — GET and PUT share ONE contract. So
 * `res.settings` carries the authored value and the re-seed shows it with no reload. This test
 * drives the real builder success handler against that REAL post-fix PUT shape — the write result
 * (`{ version, idempotent_replay }`) PLUS the resolved `settings` — and asserts the control
 * reflects the AUTHORED value with NO reload (no second `getLookAndFeelSettings` GET).
 *
 * The EXISTING wiring test (`LookAndFeelEditor.test.tsx`) once mocked the set result as a bare
 * `{ settings: { ... } }` (no write-result fields) — a shape the real edge never produced; that
 * false-green is what HID R-B (design root cause 4, tasks.md Task 14.2). Both tests now mock the
 * REAL contract: the write-result fields AND the resolved `settings`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, fireEvent, waitFor } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { FieldConfig } from '../../../../types/members';

const mockGetFieldConfig = vi.fn();
const mockGetLookAndFeel = vi.fn();
const mockSetLookAndFeel = vi.fn();

// The builder surfaces errors through useToast(); stub it so a stray toast never interferes and
// so the test asserts on state, not portal timers.
const mockToast = vi.fn();
vi.mock('@chakra-ui/react', async () => {
  const actual = await vi.importActual<typeof import('@chakra-ui/react')>('@chakra-ui/react');
  return { ...actual, useToast: () => mockToast };
});

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
  };
});

vi.mock('../../../../services/membersApiService', () => ({
  applyFieldConfigChangeOps: vi
    .fn()
    .mockResolvedValue({ success: true, configId: 'fields', version: 'v2' }),
  writeMailConfig: vi.fn().mockResolvedValue({ success: true }),
  getFieldConfig: vi.fn(),
}));

vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: vi.fn().mockResolvedValue([]),
  publishApplicationForm: vi.fn().mockResolvedValue({ success: true }),
  setApplicationFormSlug: vi.fn().mockResolvedValue({ success: true, slug: 'h-dcn' }),
  setApplicationFormPrefix: vi.fn().mockResolvedValue({ success: true, prefix: 'h-dcn' }),
  getLookAndFeelSettings: (...a: unknown[]) => mockGetLookAndFeel(...a),
  setLookAndFeelSetting: (...a: unknown[]) => mockSetLookAndFeel(...a),
  copyLookAndFeelSettings: vi.fn(),
}));

import { ApplicationFormBuilder } from '../ApplicationFormBuilder';

const FIELD_CONFIG: FieldConfig = {
  slug: 'h-dcn',
  fields: [
    {
      key: 'email',
      functional_group: 'personal',
      provenance: 'tenant_added',
      type: 'string',
      label: { en: 'Email', nl: 'E-mail' },
      application_visible: true,
    },
  ],
  functional_groups: [{ key: 'personal', order: 1 }],
  field_format_tokens: ['EMAIL'],
  config_status: { fields: '2026-10-21T09:00:00', scope: 1, mail: null },
  mail_config: {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
  },
} as unknown as FieldConfig;

async function renderBuilder() {
  mockGetFieldConfig.mockResolvedValue(FIELD_CONFIG);
  i18n.changeLanguage('en');
  const utils = render(
    <I18nextProvider i18n={i18n}>
      <ApplicationFormBuilder tenant="t-1" />
    </I18nextProvider>,
  );
  await screen.findByTestId('application-form-builder-accordion');
  await screen.findByTestId('application-form-builder-group-lookandfeel');
  return utils;
}

describe('ApplicationFormBuilder — R-B stale editor (reflects the authored value after the bottom Save persists + reloads)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockToast.mockClear();
    // The slice starts empty, so `shadow_style` seeds to its Layer-2 default ('subtle') on the
    // load-time GET. In the grouped per-group-save redesign the Look & feel group's Save persists
    // each changed attribute via `setLookAndFeelSetting` and keeps the OPTIMISTIC in-memory value
    // as the authoritative draft (no re-seed from the PUT response, no `load()` reload) — removing
    // the overlapping-response race the old re-seed had. So the control reflects the authored value
    // straight through the save with NO additional GET.
    mockGetLookAndFeel.mockResolvedValue({ settings: {} });
    mockSetLookAndFeel.mockResolvedValue({
      version: 'v3',
      idempotent_replay: false,
      settings: { shadow_style: 'dramatic' },
    });
  });

  it('the Look & feel group Save persists the authored value and the editor keeps it (no stale snap-back)', async () => {
    await renderBuilder();

    // Baseline: one seed GET on load; the control shows the default 'subtle'.
    expect(mockGetLookAndFeel).toHaveBeenCalledTimes(1);
    const control = () =>
      screen.getByTestId('lookandfeel-shadow_style') as HTMLSelectElement;
    expect(control().value).toBe('subtle');

    // Author a distinct value. The change lifts the value in-memory for the live preview but does
    // NOT persist yet (deferred per-group save) — so no network write fires on change.
    fireEvent.change(control(), { target: { value: 'dramatic' } });
    expect(control().value).toBe('dramatic');
    expect(mockSetLookAndFeel).not.toHaveBeenCalled();

    // The Look & feel group's own Save persists the authored value via one Change-Op.
    fireEvent.click(screen.getByTestId('application-form-builder-lookandfeel-savebar-save'));
    await waitFor(() => expect(mockSetLookAndFeel).toHaveBeenCalledTimes(1));
    expect(mockSetLookAndFeel).toHaveBeenCalledWith('shadow_style', 'dramatic');

    // The control MUST still show the authored value — the optimistic in-memory draft is the
    // source of truth, so there is no stale default snap-back (the R-B symptom).
    await waitFor(() => {
      expect(control().value).toBe('dramatic');
    });

    // The group Save does NOT reload — no second GET fires (race-free, serverless-friendly).
    expect(mockGetLookAndFeel).toHaveBeenCalledTimes(1);
  });
});
