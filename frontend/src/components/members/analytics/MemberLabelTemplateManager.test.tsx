/**
 * Component tests for MemberLabelTemplateManager (analytics/MemberLabelTemplateManager.tsx).
 *
 * Verifies labels sub-spec task 2.1 (R-L1, pivot-output-actions/labels): the stored LABEL-template
 * management surface —
 *   - lists ONLY `kind === "label"` templates (a mail template in the fake list is excluded);
 *   - builds a draft (name + ordered lines of field keys) and saving CREATES a
 *     `{ name, kind: "label", lines }` record with NO `languages`;
 *   - editing an existing label template seeds its lines; saving UPDATES it with
 *     `{ kind: "label", lines }`;
 *   - Save is gated until a name + ≥1 line-carrying-a-field exist;
 *   - a load / save failure surfaces the bilingual error-toast KEY;
 *   - no hardcoded English (labels resolve from the `members` namespace, echoed by the i18n mock).
 *
 * The service functions are injected via props (no network); Chakra's useToast is spied while
 * the rest of the library stays real.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// --- Spy on Chakra's useToast, keep the rest of the library real. -------------
const toastSpy = vi.fn();
vi.mock('@chakra-ui/react', async () => {
  const actual = await vi.importActual<typeof import('@chakra-ui/react')>(
    '@chakra-ui/react',
  );
  return { ...actual, useToast: () => toastSpy };
});

// Echo i18n keys so assertions are locale-independent (prove no hardcoded English).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberLabelTemplateManager from './MemberLabelTemplateManager';
import { MemberLabelTemplateManager as FromBarrel } from './index';
import type { MemberLabelTemplateManagerProps } from './MemberLabelTemplateManager';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';
import type { FieldConfigField } from '../../../types/members';

const AVAILABLE_FIELDS: FieldConfigField[] = [
  { key: 'display_name' },
  { key: 'street' },
  { key: 'postal_code' },
  { key: 'city' },
  { key: 'country' },
];

const LABEL_TPL: MemberTemplateDto = {
  template_id: 'lbl-1',
  name: 'Address labels',
  kind: 'label',
  lines: [['display_name'], ['street'], ['postal_code', 'city']],
  languages: {},
  merge_fields: [],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'sub-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

// A MAIL template (absent kind defaults to mail) — must NOT appear in the label list.
const MAIL_TPL: MemberTemplateDto = {
  template_id: 'mail-1',
  name: 'Welcome mail',
  languages: { en: { subject: 'Hi', body_html: 'Body' } },
  merge_fields: [],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'sub-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

// Injected service spies (fresh per test).
let listTemplates: ReturnType<typeof vi.fn>;
let getTemplate: ReturnType<typeof vi.fn>;
let createTemplate: ReturnType<typeof vi.fn>;
let updateTemplate: ReturnType<typeof vi.fn>;
let deleteTemplate: ReturnType<typeof vi.fn>;

function makeProps(
  overrides: Partial<MemberLabelTemplateManagerProps> = {},
): MemberLabelTemplateManagerProps {
  return {
    isOpen: true,
    onClose: vi.fn(),
    language: 'en',
    availableFields: AVAILABLE_FIELDS,
    onTemplatesChanged: vi.fn(),
    listTemplates: listTemplates as unknown as MemberLabelTemplateManagerProps['listTemplates'],
    getTemplate: getTemplate as unknown as MemberLabelTemplateManagerProps['getTemplate'],
    createTemplate: createTemplate as unknown as MemberLabelTemplateManagerProps['createTemplate'],
    updateTemplate: updateTemplate as unknown as MemberLabelTemplateManagerProps['updateTemplate'],
    deleteTemplate: deleteTemplate as unknown as MemberLabelTemplateManagerProps['deleteTemplate'],
    ...overrides,
  };
}

beforeEach(() => {
  toastSpy.mockReset();
  listTemplates = vi.fn().mockResolvedValue({ ok: true, data: [] });
  getTemplate = vi.fn().mockResolvedValue({ ok: true, data: LABEL_TPL });
  createTemplate = vi
    .fn()
    .mockResolvedValue({ ok: true, data: { ...LABEL_TPL, template_id: 'new-1' } });
  updateTemplate = vi.fn().mockResolvedValue({ ok: true, data: LABEL_TPL });
  deleteTemplate = vi.fn().mockResolvedValue({ ok: true, data: LABEL_TPL });
});

describe('MemberLabelTemplateManager', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberLabelTemplateManager);
  });

  it('shows the empty state when the tenant has no label templates', async () => {
    render(<MemberLabelTemplateManager {...makeProps()} />);
    expect(await screen.findByTestId('member-label-template-empty')).toBeInTheDocument();
    expect(listTemplates).toHaveBeenCalledTimes(1);
  });

  it('lists only kind="label" templates (a mail template is excluded)', async () => {
    listTemplates.mockResolvedValue({ ok: true, data: [MAIL_TPL, LABEL_TPL] });
    render(<MemberLabelTemplateManager {...makeProps()} />);
    expect(await screen.findByTestId('member-label-template-list')).toBeInTheDocument();
    // The label template is shown...
    expect(screen.getByText('Address labels')).toBeInTheDocument();
    expect(screen.getByTestId('member-label-template-edit-lbl-1')).toBeInTheDocument();
    // ...the mail template is NOT.
    expect(screen.queryByText('Welcome mail')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-label-template-edit-mail-1')).not.toBeInTheDocument();
  });

  it('gates Save until a name + a line-with-a-field exist, then creates a label record', async () => {
    render(<MemberLabelTemplateManager {...makeProps()} />);
    await screen.findByTestId('member-label-template-editor');

    const save = screen.getByTestId('member-label-template-save');
    expect(save).toBeDisabled();

    // Name alone is not enough — a line needs a field.
    fireEvent.change(screen.getByTestId('member-label-template-name'), {
      target: { value: 'My labels' },
    });
    expect(save).toBeDisabled();

    // Build lines: ["display_name"], ["street"], ["postal_code","city"].
    // Line 0 starts present; add fields to it, then add two more lines.
    fireEvent.change(screen.getByTestId('member-label-template-add-field-0'), {
      target: { value: 'display_name' },
    });
    // After the first field the Save should enable.
    expect(save).not.toBeDisabled();

    fireEvent.click(screen.getByTestId('member-label-template-add-line'));
    fireEvent.change(screen.getByTestId('member-label-template-add-field-1'), {
      target: { value: 'street' },
    });

    fireEvent.click(screen.getByTestId('member-label-template-add-line'));
    fireEvent.change(screen.getByTestId('member-label-template-add-field-2'), {
      target: { value: 'postal_code' },
    });
    fireEvent.change(screen.getByTestId('member-label-template-add-field-2'), {
      target: { value: 'city' },
    });

    fireEvent.click(save);
    await waitFor(() => expect(createTemplate).toHaveBeenCalledTimes(1));
    const input = createTemplate.mock.calls[0][0];
    expect(input.name).toBe('My labels');
    expect(input.kind).toBe('label');
    expect(input.lines).toEqual([['display_name'], ['street'], ['postal_code', 'city']]);
    // A label template carries NO languages.
    expect(input.languages).toBeUndefined();
  });

  it('seeds an existing label template on edit and updates it with kind="label" lines', async () => {
    listTemplates.mockResolvedValue({ ok: true, data: [LABEL_TPL] });
    render(<MemberLabelTemplateManager {...makeProps()} />);
    fireEvent.click(await screen.findByTestId('member-label-template-edit-lbl-1'));

    await waitFor(() => expect(getTemplate).toHaveBeenCalledWith('lbl-1'));
    const name = screen.getByTestId('member-label-template-name') as HTMLInputElement;
    await waitFor(() => expect(name.value).toBe('Address labels'));

    // The three seeded lines are rendered.
    expect(screen.getByTestId('member-label-template-line-0')).toBeInTheDocument();
    expect(screen.getByTestId('member-label-template-line-1')).toBeInTheDocument();
    expect(screen.getByTestId('member-label-template-line-2')).toBeInTheDocument();
    // Line 2 holds both of its seeded field chips.
    expect(screen.getByTestId('member-label-template-field-2-0')).toBeInTheDocument();
    expect(screen.getByTestId('member-label-template-field-2-1')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('member-label-template-save'));
    await waitFor(() => expect(updateTemplate).toHaveBeenCalledTimes(1));
    expect(updateTemplate.mock.calls[0][0]).toBe('lbl-1');
    const input = updateTemplate.mock.calls[0][1];
    expect(input.kind).toBe('label');
    expect(input.lines).toEqual([['display_name'], ['street'], ['postal_code', 'city']]);
    expect(input.languages).toBeUndefined();
  });

  it('removes a field from a line', async () => {
    listTemplates.mockResolvedValue({ ok: true, data: [LABEL_TPL] });
    render(<MemberLabelTemplateManager {...makeProps()} />);
    fireEvent.click(await screen.findByTestId('member-label-template-edit-lbl-1'));
    await waitFor(() => expect(getTemplate).toHaveBeenCalledWith('lbl-1'));

    // Drop "city" (line 2, field 1); line 2 should now be just ["postal_code"].
    fireEvent.click(screen.getByTestId('member-label-template-remove-field-2-1'));
    fireEvent.click(screen.getByTestId('member-label-template-save'));
    await waitFor(() => expect(updateTemplate).toHaveBeenCalledTimes(1));
    expect(updateTemplate.mock.calls[0][1].lines).toEqual([
      ['display_name'],
      ['street'],
      ['postal_code'],
    ]);
  });

  it('surfaces the error-toast key on a load failure', async () => {
    listTemplates.mockResolvedValue({ ok: false, status: 500, error: 'boom' });
    render(<MemberLabelTemplateManager {...makeProps()} />);
    await waitFor(() =>
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'analytics.labelTemplates.loadError' }),
      ),
    );
  });

  it('surfaces the error-toast key on a save failure', async () => {
    createTemplate.mockResolvedValue({ ok: false, status: 400, error: 'bad' });
    render(<MemberLabelTemplateManager {...makeProps()} />);
    await screen.findByTestId('member-label-template-editor');

    fireEvent.change(screen.getByTestId('member-label-template-name'), {
      target: { value: 'My labels' },
    });
    fireEvent.change(screen.getByTestId('member-label-template-add-field-0'), {
      target: { value: 'display_name' },
    });
    fireEvent.click(screen.getByTestId('member-label-template-save'));

    await waitFor(() => expect(createTemplate).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'analytics.labelTemplates.saveError' }),
      ),
    );
  });
});
