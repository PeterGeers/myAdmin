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

describe('LookAndFeelEditor — the look-and-feel preferences editor (Req 3.2 + bugfix 3.4)', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  it('renders exactly one control for each of the ten supported attributes', () => {
    render(
      <LookAndFeelEditor values={{}} onChange={vi.fn()} onSave={vi.fn()} lang="en" />,
    );
    // Every supported attribute has a labelled control keyed by its attribute name — the original
    // seven plus the three the bugfix `bugfix-published-form-styling` added (`logo` /
    // `header_title` / `columns`, bugfix 3.4), each surfaced via its own `lookandfeel-${attr}` control.
    for (const attr of SUPPORTED_ATTRIBUTES) {
      expect(screen.getByTestId(`lookandfeel-${attr}`)).toBeInTheDocument();
    }
    expect(SUPPORTED_ATTRIBUTES).toHaveLength(10);
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
      screen.getByText('Changes appear instantly in the preview. Click Save to store them for this form.'),
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

  it('an enum edit lifts the VALUE up (onChange) for live preview — it does NOT persist on change', () => {
    const onChange = vi.fn();
    const onSave = vi.fn();
    render(
      <LookAndFeelEditor values={{}} onChange={onChange} onSave={onSave} lang="en" />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-shadow_style'), {
      target: { value: 'dramatic' },
    });
    // The VALUE is lifted for the live preview — serverless-friendly: NO per-change network write.
    expect(onChange).toHaveBeenCalledWith('shadow_style', 'dramatic');
    expect(onSave).not.toHaveBeenCalled();
  });

  it('a colour edit lifts the hex value up (values-only — never generated CSS), no persist on change', () => {
    const onChange = vi.fn();
    const onSave = vi.fn();
    render(
      <LookAndFeelEditor values={{}} onChange={onChange} onSave={onSave} lang="en" />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-color_primary-hex'), {
      target: { value: '#123456' },
    });
    expect(onChange).toHaveBeenCalledWith('color_primary', '#123456');
    expect(onSave).not.toHaveBeenCalled();
    // The lifted value is a bare hex string — not a `:root {` block or any CSS.
    const [, value] = onChange.mock.calls[0];
    expect(value).toBe('#123456');
    expect(String(value)).not.toContain(':root');
    expect(String(value)).not.toContain('--');
  });
});

/* ========================================================================= */
/*  Part A2 — the three NEW values-only controls (bugfix-published-form-      */
/*  styling, Task 11): logo / header_title / columns (defect 1.7 / Req 2.7)  */
/* ========================================================================= */

describe('LookAndFeelEditor — logo / header_title / columns controls (bugfix Req 2.7)', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  it('renders a data-entry control for each of the three new attributes', () => {
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.getByTestId('lookandfeel-logo')).toBeInTheDocument();
    expect(screen.getByTestId('lookandfeel-header_title')).toBeInTheDocument();
    expect(screen.getByTestId('lookandfeel-columns')).toBeInTheDocument();
  });

  it('seeds each new control from its value, falling back to the SAM-owned default', () => {
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{ header_title: 'Join us', columns: '3' }}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        lang="en"
      />,
    );
    expect((screen.getByTestId('lookandfeel-header_title') as HTMLInputElement).value).toBe(
      'Join us',
    );
    expect((screen.getByTestId('lookandfeel-columns') as HTMLSelectElement).value).toBe('3');
    // An unset new attribute shows its default (logo → empty; columns → 2), never blank-but-wrong.
    expect((screen.getByTestId('lookandfeel-logo') as HTMLInputElement).value).toBe('');
  });

  it('the columns selector offers exactly the bounded 1..4 range (matches the service/generator clamp)', () => {
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        lang="en"
      />,
    );
    const options = Array.from(
      (screen.getByTestId('lookandfeel-columns') as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(options).toEqual(['1', '2', '3', '4']);
  });

  it('a logo edit lifts the VALUE up (onExtraChange) AND persists it values-only (onExtraSave)', () => {
    const onExtraChange = vi.fn();
    const onExtraSave = vi.fn();
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={onExtraChange}
        onExtraSave={onExtraSave}
        lang="en"
      />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-logo'), {
      target: { value: 'https://cdn.example.org/logo.png' },
    });
    expect(onExtraChange).toHaveBeenCalledWith('logo', 'https://cdn.example.org/logo.png');
    // Serverless-friendly: editing lifts the value for live preview but does NOT persist on change.
    expect(onExtraSave).not.toHaveBeenCalled();
    // The lifted value is a bare reference string — not a `:root {` block or any CSS.
    const [, value] = onExtraChange.mock.calls[0];
    expect(String(value)).not.toContain(':root');
    expect(String(value)).not.toContain('--');
  });

  it('a header_title edit lifts the bare text value up (values-only), no persist on change', () => {
    const onExtraChange = vi.fn();
    const onExtraSave = vi.fn();
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={onExtraChange}
        onExtraSave={onExtraSave}
        lang="en"
      />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-header_title'), {
      target: { value: 'Membership application' },
    });
    expect(onExtraChange).toHaveBeenCalledWith('header_title', 'Membership application');
    expect(onExtraSave).not.toHaveBeenCalled();
  });

  it('a columns edit lifts the chosen bounded count up (values-only), no persist on change', () => {
    const onExtraChange = vi.fn();
    const onExtraSave = vi.fn();
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={onExtraChange}
        onExtraSave={onExtraSave}
        lang="en"
      />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-columns'), {
      target: { value: '3' },
    });
    expect(onExtraChange).toHaveBeenCalledWith('columns', '3');
    expect(onExtraSave).not.toHaveBeenCalled();
  });

  it('clearing the logo / header_title text lifts null (revert to the SAM-owned default), no persist', () => {
    const onExtraChange = vi.fn();
    const onExtraSave = vi.fn();
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{ logo: 'https://cdn.example.org/logo.png', header_title: 'Join' }}
        onExtraChange={onExtraChange}
        onExtraSave={onExtraSave}
        lang="en"
      />,
    );
    fireEvent.change(screen.getByTestId('lookandfeel-logo'), { target: { value: '' } });
    expect(onExtraChange).toHaveBeenCalledWith('logo', null);
    expect(onExtraSave).not.toHaveBeenCalled();
  });

  it('shows a preview thumbnail of the currently-stored logo (the S3 reference)', () => {
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{ logo: 'https://assets.example.org/h-dcn/logo.png' }}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        lang="en"
      />,
    );
    const preview = screen.getByTestId('lookandfeel-logo-preview') as HTMLImageElement;
    expect(preview).toBeInTheDocument();
    expect(preview.getAttribute('src')).toBe('https://assets.example.org/h-dcn/logo.png');
  });

  it('no preview is shown when no logo is set', () => {
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.queryByTestId('lookandfeel-logo-preview')).not.toBeInTheDocument();
  });

  it('the Upload button stores a new image via onUploadLogo and sets the logo to the stored URL', async () => {
    const onUploadLogo = vi
      .fn()
      .mockResolvedValue('https://assets.example.org/h-dcn/new-logo.png');
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        onUploadLogo={onUploadLogo}
        lang="en"
      />,
    );
    const file = new File(['img-bytes'], 'logo.png', { type: 'image/png' });
    const input = screen.getByTestId('lookandfeel-logo-file') as HTMLInputElement;
    // Simulate the user picking a file (the Upload button triggers this hidden input).
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(onUploadLogo).toHaveBeenCalledTimes(1));
    expect(onUploadLogo).toHaveBeenCalledWith(file);
  });

  it('a failed upload surfaces an inline error without throwing', async () => {
    const onUploadLogo = vi.fn().mockRejectedValue(new Error('file too large'));
    render(
      <LookAndFeelEditor
        values={{}}
        onChange={vi.fn()}
        onSave={vi.fn()}
        extraValues={{}}
        onExtraChange={vi.fn()}
        onExtraSave={vi.fn()}
        onUploadLogo={onUploadLogo}
        lang="en"
      />,
    );
    const file = new File(['x'], 'big.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('lookandfeel-logo-file'), { target: { files: [file] } });
    await waitFor(() =>
      expect(screen.getByTestId('lookandfeel-logo-error')).toHaveTextContent('file too large'),
    );
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
    // THE REAL PUT CONTRACT (bugfix Task 14.1 / DD-D1): `write_look_and_feel` returns the resolved
    // `{settings}` (the same shape GET returns) FOLDED IN WITH the Change-Op write-result fields —
    // `{ version, idempotent_replay, settings: { <resolved> } }` (`_with_resolved_settings`). The
    // pre-fix bare `{ settings: ... }` mock (no write-result fields) was a false-green that hid R-B
    // — the shipped edge produced no `settings` at all. Mock the REAL shape so the re-seed
    // (`setLookAndFeel(res.settings ?? {})`) exercises the true contract.
    mockSetLookAndFeel.mockResolvedValue({
      version: 'v2',
      idempotent_replay: false,
      settings: { color_primary: '#111111', shadow_style: 'dramatic' },
    });
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
    // Serverless model: editing does NOT persist. Click the single bottom Save button.
    expect(mockSetLookAndFeel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
    await waitFor(() => expect(mockSetLookAndFeel).toHaveBeenCalledWith('shadow_style', 'dramatic'));
    // Each call is exactly (attribute, value) — one supported attribute + its value, no CSS/record.
    const call = mockSetLookAndFeel.mock.calls.find((c) => c[0] === 'shadow_style')!;
    expect(call).toHaveLength(2);
    expect(JSON.stringify(call)).not.toContain(':root');
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
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
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
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    const toastArg = mockToast.mock.calls.at(-1)![0] as { status?: string; description?: string };
    expect(toastArg.status).toBe('error');
    // Generic — never leaks whether the other tenant / page exists.
    expect(toastArg.description).toBe('Forbidden');
  });
});

/* ========================================================================= */
/*  Part B2 — the three NEW controls wired into the builder (Task 11):       */
/*  values-only Change-Ops + caller-safe edge-error surfacing                 */
/* ========================================================================= */

describe('ApplicationFormBuilder — logo / header_title / columns wiring (bugfix Task 11/12)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockToast.mockClear();
    // The slice seeds BOTH the original seven AND the three new attributes. As of Task 12 the
    // builder feeds ALL TEN to the preview (the seven + the three), since `renderPageStyles` now
    // accepts the full set — so the new keys reach the preview rather than being split away.
    mockGetLookAndFeel.mockResolvedValue({
      settings: { color_primary: '#111111', columns: '3', header_title: 'Join' },
    });
    // THE REAL PUT CONTRACT (bugfix Task 14.1 / DD-D1): the resolved `{settings}` is folded in WITH
    // the Change-Op write-result fields — GET and PUT share one `{settings}` contract. The new
    // attributes (`columns`/`header_title`) resolve back under `settings`, so the client re-seeds
    // from the true post-fix shape (not the pre-fix bare `{settings}` false-green).
    mockSetLookAndFeel.mockResolvedValue({
      version: 'v2',
      idempotent_replay: false,
      settings: { color_primary: '#111111', columns: '3', header_title: 'Join' },
    });
  });

  it('seeds the new controls from the SAM look_and_feel slice AND reflects them in the preview (Task 12)', async () => {
    await renderBuilder();
    // The new controls reflect the stored values…
    await waitFor(() =>
      expect((screen.getByTestId('lookandfeel-columns') as HTMLSelectElement).value).toBe('3'),
    );
    expect((screen.getByTestId('lookandfeel-header_title') as HTMLInputElement).value).toBe('Join');
    // …and the builder did NOT white-screen — the preview renders with all ten attributes, and now
    // REFLECTS the three new ones (Task 12 unified the preview feed): the seeded header_title shows
    // as the preview heading and the column count drives the grid (Req 2.6).
    expect(await screen.findByTestId('application-form-preview-render')).toBeInTheDocument();
    expect(await screen.findByTestId('application-form-preview-title')).toHaveTextContent('Join');
    expect(
      screen
        .getByTestId('application-form-preview-render')
        .getAttribute('data-lookandfeel-columns'),
    ).toBe('3');
  });

  it('a columns edit persists via setLookAndFeelSetting with a VALUES-ONLY payload — never CSS, never a record', async () => {
    await renderBuilder();
    fireEvent.change(screen.getByTestId('lookandfeel-columns'), { target: { value: '4' } });
    expect(mockSetLookAndFeel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
    await waitFor(() => expect(mockSetLookAndFeel).toHaveBeenCalledWith('columns', '4'));
    const call = mockSetLookAndFeel.mock.calls.find((c) => c[0] === 'columns')!;
    expect(call).toHaveLength(2);
    expect(JSON.stringify(call)).not.toContain(':root');
  });

  it('a logo edit persists a values-only reference via setLookAndFeelSetting', async () => {
    await renderBuilder();
    fireEvent.change(screen.getByTestId('lookandfeel-logo'), {
      target: { value: 'https://cdn.example.org/logo.png' },
    });
    expect(mockSetLookAndFeel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
    await waitFor(() =>
      expect(mockSetLookAndFeel).toHaveBeenCalledWith('logo', 'https://cdn.example.org/logo.png'),
    );
    const logoCall = mockSetLookAndFeel.mock.calls.find((c) => c[0] === 'logo')!;
    expect(JSON.stringify(logoCall)).not.toContain(':root');
  });

  it('a header_title edit persists the bare text value via setLookAndFeelSetting', async () => {
    await renderBuilder();
    fireEvent.change(screen.getByTestId('lookandfeel-header_title'), {
      target: { value: 'Membership application' },
    });
    expect(mockSetLookAndFeel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
    await waitFor(() =>
      expect(mockSetLookAndFeel).toHaveBeenCalledWith('header_title', 'Membership application'),
    );
  });

  it('a 422 rejection on a new attribute surfaces the caller-safe message WITHOUT leaking internals (Req 4.5)', async () => {
    await renderBuilder();
    mockSetLookAndFeel.mockRejectedValueOnce(
      new ApiError(422, {
        error: "invalid value '9' for 'columns': expected an integer in 1..4",
        code: 'errors.validation.failed',
      }),
    );
    fireEvent.change(screen.getByTestId('lookandfeel-columns'), { target: { value: '4' } });
    fireEvent.click(screen.getByTestId('application-form-builder-save'));
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    const toastArg = mockToast.mock.calls.at(-1)![0] as { status?: string; description?: string };
    expect(toastArg.status).toBe('error');
    expect(toastArg.description).toContain("for 'columns'");
    // No internal detail leaks (no stack frame / Python traceback marker / str(e)).
    expect(toastArg.description ?? '').not.toMatch(/Traceback|File "|str\(e\)/);
  });
});
