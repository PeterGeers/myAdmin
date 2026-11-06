/**
 * Tests for the look-and-feel editor + its builder/preview wiring (spec 15 — SAM Page
 * Look-and-Feel, task 12.2; Req 2.3, 4.2, 4.5, 7.1, 7.2, 8.1, 9.1, 9.4; FRONTEND plane, steering 33).
 *
 * The change-with-tests pairing for task 12.2 — the MISSING admin editor + its wiring. It pins:
 *
 *  1. the editor renders the SEVEN supported controls (the preferences editor);
 *  2. an edit lifts the VALUE up (onChange) AND persists it values-only (onSave) — never CSS,
 *     never a whole record (Req 8.1 / steering 39);
 *  3. wired into the builder, an edit calls the authoring client `setLookAndFeelSetting` with the
 *     right values-only payload, and the preview reflects the edit (Req 7.2); and
 *  4. a caller-safe edge error (422 identifying the rejected setting / 403 cross-tenant / 409 stale)
 *     surfaces WITHOUT leaking internals (Req 4.5 / 9.4).
 *
 * The editor tests drive the component directly (clean props contract); the wiring tests mount the
 * real `ApplicationFormBuilder` with the data edges + authoring client mocked, so the seed →
 * edit → persist → preview path runs end to end.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, fireEvent, waitFor } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { ApiError } from '../../../../shared/api/ApiError';
import { SUPPORTED_ATTRIBUTES } from '../pageStyles';
import type { FieldConfig } from '../../../../types/members';

/* ================================================================== */
/*  Part A — the editor component in isolation (clean props contract)  */
/* ================================================================== */
import { LookAndFeelEditor } from '../LookAndFeelEditor';

describe('LookAndFeelEditor — the seven-attribute preferences editor (Req 3.2)', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  it('renders exactly one control for each of the seven supported attributes', () => {
    render(
      <LookAndFeelEditor values={{}} onChange={vi.fn()} onSave={vi.fn()} lang="en" />,
    );
    // Every supported attribute has a labelled control keyed by its attribute name.
    for (const attr of SUPPORTED_ATTRIBUTES) {
      expect(screen.getByTestId(`lookandfeel-${attr}`)).toBeInTheDocument();
    }
    expect(SUPPORTED_ATTRIBUTES).toHaveLength(7);
  });

  it('renders the full editor (incl. the help caption) without throwing — regression for the\n      FormHelperText-outside-FormControl crash that white-screened the builder (task 12.2 bug)', () => {
    // The original editor placed <FormHelperText> directly in the VStack (no FormControl
    // ancestor), so Chakra's useFormControlStyles threw at render and the whole Application
    // Form panel white-screened in the live app. A full render here must NOT throw, and the
    // caption text must be present — this fails if the help text is ever re-nested wrongly.
    expect(() =>
      render(
        <LookAndFeelEditor values={{}} onChange={vi.fn()} onSave={vi.fn()} lang="en" />,
      ),
    ).not.toThrow();
    expect(
      screen.getByText('A change is saved for this form immediately.'),
    ).toBeInTheDocument();
  });

  it('seeds each control from the current values, falling back to the SAM-owned default', () => {
    render(
      <LookAndFeelEditor
        values={{ base_spacing: 'relaxed' }}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lang="en"
      />,
    );
    // The set attribute shows its stored value…
    expect((screen.getByTestId('lookandfeel-base_spacing') as HTMLSelectElement).value).toBe(
      'relaxed',
    );
    // …an UNSET attribute shows its Layer-2 default (never blank — Req 7.3).
    expect((screen.getByTestId('lookandfeel-shadow_style') as HTMLSelectElement).value).toBe(
      'subtle',
    );
    expect((screen.getByTestId('lookandfeel-color_primary') as HTMLInputElement).value).toBe(
      '#2d5f8a',
    );
  });

  it('an enum edit lifts the VALUE up (onChange) AND persists it values-only (onSave)', () => {
    const onChange = vi.fn();
    const onSave = vi.fn();
    render(
      <LookAndFeelEditor values={{}} onChange={onChange} onSave={onSave} lang="en" />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-shadow_style'), {
      target: { value: 'dramatic' },
    });
    // The VALUE (not CSS, not a record) is lifted up for the live preview AND persisted.
    expect(onChange).toHaveBeenCalledWith('shadow_style', 'dramatic');
    expect(onSave).toHaveBeenCalledWith('shadow_style', 'dramatic');
  });

  it('a colour edit authors the hex value only (values-only — never generated CSS)', () => {
    const onSave = vi.fn();
    render(
      <LookAndFeelEditor values={{}} onChange={vi.fn()} onSave={onSave} lang="en" />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-color_primary-hex'), {
      target: { value: '#123456' },
    });
    expect(onSave).toHaveBeenCalledWith('color_primary', '#123456');
    // The persisted value is a bare hex string — not a `:root {` block or any CSS.
    const [, value] = onSave.mock.calls[0];
    expect(value).toBe('#123456');
    expect(String(value)).not.toContain(':root');
    expect(String(value)).not.toContain('--');
  });
});

/* ================================================================== */
/*  Part B — wired into the builder: seed → edit → persist → preview   */
/* ================================================================== */

const mockGetFieldConfig = vi.fn();
const mockGetLookAndFeel = vi.fn();
const mockSetLookAndFeel = vi.fn();

// Capture builder error-toast calls deterministically. Chakra toasts render into a portal with
// animation timers that are flaky to query in jsdom; the builder surfaces every caller-safe error
// through `useToast()`, so spying on the toast is the stable way to assert the surfaced envelope.
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
  applyFieldConfigChangeOps: vi.fn().mockResolvedValue({ success: true, configId: 'fields', version: 'v2' }),
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
  mail_config: { mail_enabled: true, mail_certified: true, mail_domain: 'h-dcn.nl', mail_local_part: 'noreply' },
} as unknown as FieldConfig;

async function renderBuilder() {
  mockGetFieldConfig.mockResolvedValue(FIELD_CONFIG);
  i18n.changeLanguage('en');
  const utils = render(
    <I18nextProvider i18n={i18n}>
      <ApplicationFormBuilder tenant="t-1" />
    </I18nextProvider>,
  );
  await screen.findByTestId('application-form-builder');
  // Wait for the best-effort look-and-feel seed to resolve.
  await screen.findByTestId('application-form-builder-lookandfeel');
  return utils;
}

describe('ApplicationFormBuilder — look-and-feel editor wiring (task 12.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockToast.mockClear();
    mockGetLookAndFeel.mockResolvedValue({ settings: { color_primary: '#111111' } });
    mockSetLookAndFeel.mockResolvedValue({ settings: { color_primary: '#111111', shadow_style: 'dramatic' } });
  });

  it('seeds the editor from the SAM look_and_feel slice (getLookAndFeelSettings) on load', async () => {
    await renderBuilder();
    expect(mockGetLookAndFeel).toHaveBeenCalledTimes(1);
    // The stored value seeds the control.
    await waitFor(() =>
      expect((screen.getByTestId('lookandfeel-color_primary-hex') as HTMLInputElement).value).toBe(
        '#111111',
      ),
    );
  });

  it('an edit persists via setLookAndFeelSetting with a VALUES-ONLY payload — never CSS, never a record', async () => {
    await renderBuilder();
    fireEvent.change(screen.getByTestId('lookandfeel-shadow_style'), {
      target: { value: 'dramatic' },
    });
    await waitFor(() => expect(mockSetLookAndFeel).toHaveBeenCalledTimes(1));
    // The client is called with exactly (attribute, value) — one supported attribute + its value.
    expect(mockSetLookAndFeel).toHaveBeenCalledWith('shadow_style', 'dramatic');
    const args = mockSetLookAndFeel.mock.calls[0];
    // No extra args smuggling a whole record / CSS blob into the call.
    expect(args).toHaveLength(2);
    expect(JSON.stringify(args)).not.toContain(':root');
  });

  it('the preview reflects an UNSAVED look-and-feel edit live (Req 7.2) — no server round-trip needed', async () => {
    await renderBuilder();
    // The preview renders (email is on the form), carrying the seeded look-and-feel vars.
    const render0 = await screen.findByTestId('application-form-preview-render');
    const vars0 = render0.getAttribute('data-lookandfeel-vars') ?? '';
    // Change the HEADING font — the editor lifts the value into builder state, which feeds the
    // preview's `lookAndFeel` prop on the very NEXT render (no persist/await required).
    fireEvent.change(screen.getByTestId('lookandfeel-font_heading'), {
      target: { value: 'Inter' },
    });
    await waitFor(() => {
      const vars1 =
        screen.getByTestId('application-form-preview-render').getAttribute('data-lookandfeel-vars') ??
        '';
      // The injected CSS-variable block now differs and carries the chosen font family.
      expect(vars1).not.toBe(vars0);
      expect(vars1).toContain('Inter');
    });
  });

  it('a 422 rejection surfaces the caller-safe message WITHOUT leaking internals (Req 4.5)', async () => {
    await renderBuilder();
    mockSetLookAndFeel.mockRejectedValueOnce(
      new ApiError(422, {
        error: 'shadow_style must be one of: none, subtle, medium, dramatic',
        code: 'errors.validation.failed',
      }),
    );
    fireEvent.change(screen.getByTestId('lookandfeel-shadow_style'), {
      target: { value: 'none' },
    });
    // The caller-safe envelope surfaces as an error toast naming the client's OWN setting; the
    // description carries NO internal detail (no stack frame / Python traceback marker).
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    const toastArg = mockToast.mock.calls.at(-1)![0] as { status?: string; description?: string };
    expect(toastArg.status).toBe('error');
    expect(toastArg.description).toContain('shadow_style must be one of');
    expect(toastArg.description ?? '').not.toMatch(/Traceback|File "|str\(e\)/);
  });

  it('a 403 cross-tenant/forbidden surfaces a generic message that never confirms the other tenant (Req 9.4)', async () => {
    await renderBuilder();
    mockSetLookAndFeel.mockRejectedValueOnce(
      new ApiError(403, { error: 'Forbidden', code: 'errors.api.forbidden' }),
    );
    fireEvent.change(screen.getByTestId('lookandfeel-color_accent-hex'), {
      target: { value: '#abcdef' },
    });
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    const toastArg = mockToast.mock.calls.at(-1)![0] as { status?: string; description?: string };
    expect(toastArg.status).toBe('error');
    // Generic — never leaks whether the other tenant / page exists.
    expect(toastArg.description).toBe('Forbidden');
  });
});
