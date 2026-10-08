/**
 * Component tests for MemberDeliveryEditor (analytics/MemberDeliveryEditor.tsx).
 *
 * Verifies task 3.4 (R3, pivot-output-actions): the stored-delivery editor on a
 * saved member set —
 *   - switches mode (per_recipient ⇄ to_fixed), showing the template picker for
 *     per_recipient and the recipients field for to_fixed;
 *   - mirrors the SAM entity's validate() rules client-side: to_fixed requires at
 *     least one valid recipient (Save blocked until then); per_recipient needs none;
 *   - shows the shared label-options sub-UI only when the attachment is pdf_labels;
 *   - Save calls the injected onSave (→ PUT the dedicated delivery route) with the
 *     built MemberDelivery; Clear calls onClear (→ DELETE the delivery route);
 *   - no hardcoded English (labels resolve from the `members` namespace, echoed by
 *     the i18n mock).
 *
 * The persistence + template-list functions are injected via props (no network);
 * Chakra's useToast is not used by this component (the parent toasts), so only the
 * i18n hook is mocked. The real `labelOptions` + `MemberMailCompose` helpers are
 * used (no mocking) so the shared model + the shared recipient parser are exercised.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// Echo i18n keys so assertions are locale-independent (prove no hardcoded English).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
  }),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberDeliveryEditor, {
  hasValidFixedRecipients,
  type MemberDeliveryEditorProps,
} from './MemberDeliveryEditor';
import { MemberDeliveryEditor as FromBarrel } from './index';
import type { MemberDelivery } from '../../../types/members';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';

const TPL: MemberTemplateDto = {
  template_id: 'tpl-1',
  name: 'Welcome',
  languages: { en: { subject: 'Hi', body_html: 'Dear {{first_name}}' } },
  merge_fields: ['first_name'],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'sub-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

let onSave: ReturnType<typeof vi.fn>;
let onClear: ReturnType<typeof vi.fn>;
let onClose: ReturnType<typeof vi.fn>;
let listTemplates: ReturnType<typeof vi.fn>;

function makeProps(
  overrides: Partial<MemberDeliveryEditorProps> = {},
): MemberDeliveryEditorProps {
  return {
    isOpen: true,
    onClose: onClose as unknown as MemberDeliveryEditorProps['onClose'],
    setId: 'set-1',
    setName: 'Jubilees',
    language: 'en',
    onSave: onSave as unknown as MemberDeliveryEditorProps['onSave'],
    onClear: onClear as unknown as MemberDeliveryEditorProps['onClear'],
    listTemplates: listTemplates as unknown as MemberDeliveryEditorProps['listTemplates'],
    ...overrides,
  };
}

beforeEach(() => {
  onSave = vi.fn().mockResolvedValue(undefined);
  onClear = vi.fn().mockResolvedValue(undefined);
  onClose = vi.fn();
  listTemplates = vi.fn().mockResolvedValue({ ok: true, data: [TPL] });
});

describe('hasValidFixedRecipients', () => {
  it('is true only when at least one address is valid', () => {
    expect(hasValidFixedRecipients([])).toBe(false);
    expect(hasValidFixedRecipients(['not-an-email'])).toBe(false);
    expect(hasValidFixedRecipients(['a@b.com'])).toBe(true);
    expect(hasValidFixedRecipients(['bad', 'a@b.com'])).toBe(true);
  });
});

describe('MemberDeliveryEditor', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberDeliveryEditor);
  });

  it('defaults a set with no existing delivery to per_recipient + the template picker', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);

    const modeSelect = (await screen.findByTestId('delivery-mode-select')) as HTMLSelectElement;
    expect(modeSelect.value).toBe('per_recipient');
    // per_recipient shows the template picker, not the recipients field.
    expect(await screen.findByTestId('delivery-template-select')).toBeInTheDocument();
    expect(screen.queryByTestId('delivery-recipients-input')).not.toBeInTheDocument();
    // The template list loaded into the picker.
    await waitFor(() => expect(listTemplates).toHaveBeenCalledTimes(1));
  });

  it('switches mode to to_fixed, revealing the recipients field (and hiding the template picker)', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);

    const modeSelect = (await screen.findByTestId('delivery-mode-select')) as HTMLSelectElement;
    fireEvent.change(modeSelect, { target: { value: 'to_fixed' } });

    expect(await screen.findByTestId('delivery-recipients-input')).toBeInTheDocument();
    expect(screen.queryByTestId('delivery-template-select')).not.toBeInTheDocument();
  });

  it('blocks Save for to_fixed until a valid recipient is entered (recipients required rule)', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);

    fireEvent.change(await screen.findByTestId('delivery-mode-select'), {
      target: { value: 'to_fixed' },
    });

    const save = (await screen.findByTestId('member-delivery-save')) as HTMLButtonElement;
    // No recipients yet → Save disabled, the "required" reason is shown.
    expect(save).toBeDisabled();
    expect(screen.getByTestId('delivery-recipients-required')).toBeInTheDocument();

    // A valid address enables Save.
    fireEvent.change(screen.getByTestId('delivery-recipients-input'), {
      target: { value: 'agent@example.com' },
    });
    await waitFor(() => expect(save).not.toBeDisabled());
    expect(screen.queryByTestId('delivery-recipients-required')).not.toBeInTheDocument();
  });

  it('shows the shared label-options sub-UI only when the attachment is pdf_labels', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);

    await screen.findByTestId('delivery-attachment-select');
    // none (default) → no label options.
    expect(screen.queryByTestId('delivery-label-options')).not.toBeInTheDocument();

    // csv → still no label options.
    fireEvent.change(screen.getByTestId('delivery-attachment-select'), {
      target: { value: 'csv' },
    });
    expect(screen.queryByTestId('delivery-label-options')).not.toBeInTheDocument();

    // pdf_labels → the shared label-options block appears, with the shared keys.
    fireEvent.change(screen.getByTestId('delivery-attachment-select'), {
      target: { value: 'pdf_labels' },
    });
    expect(await screen.findByTestId('delivery-label-options')).toBeInTheDocument();
    expect(screen.getByTestId('delivery-label-format-select')).toBeInTheDocument();
  });

  it('Save calls onSave (PUT) with per_recipient storing no recipients + the picked template', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);

    // Pick a template for per_recipient.
    fireEvent.change(await screen.findByTestId('delivery-template-select'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.click(await screen.findByTestId('member-delivery-save'));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const sent = onSave.mock.calls[0][0] as MemberDelivery;
    expect(sent.mode).toBe('per_recipient');
    expect(sent.templateId).toBe('tpl-1');
    expect(sent.recipients).toEqual([]); // per_recipient stores NO recipients
    expect(sent.labelOptions).toBeNull();
    // A successful save closes the modal.
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('Save calls onSave (PUT) with to_fixed storing the entered recipients + pdf_labels options', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);

    fireEvent.change(await screen.findByTestId('delivery-mode-select'), {
      target: { value: 'to_fixed' },
    });
    fireEvent.change(await screen.findByTestId('delivery-recipients-input'), {
      target: { value: 'agent@example.com, office@example.org' },
    });
    fireEvent.change(screen.getByTestId('delivery-attachment-select'), {
      target: { value: 'pdf_labels' },
    });

    fireEvent.click(await screen.findByTestId('member-delivery-save'));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const sent = onSave.mock.calls[0][0] as MemberDelivery;
    expect(sent.mode).toBe('to_fixed');
    expect(sent.recipients).toEqual(['agent@example.com', 'office@example.org']);
    expect(sent.templateId).toBeNull(); // to_fixed stores no template
    expect(sent.attachment).toBe('pdf_labels');
    expect(sent.labelOptions).not.toBeNull();
    expect(sent.labelOptions?.format).toBeTruthy();
  });

  it('seeds the form from an existing delivery and Clear calls onClear (DELETE)', async () => {
    const existing: MemberDelivery = {
      mode: 'to_fixed',
      templateId: null,
      attachment: 'csv',
      recipients: ['agent@example.com'],
      labelOptions: null,
    };
    render(<MemberDeliveryEditor {...makeProps({ initialDelivery: existing })} />);

    // Seeded to to_fixed with the stored recipient.
    const modeSelect = (await screen.findByTestId('delivery-mode-select')) as HTMLSelectElement;
    expect(modeSelect.value).toBe('to_fixed');
    const recipients = (await screen.findByTestId(
      'delivery-recipients-input',
    )) as HTMLTextAreaElement;
    expect(recipients.value).toContain('agent@example.com');

    // Clear is offered (there is an existing delivery) and calls onClear.
    fireEvent.click(await screen.findByTestId('member-delivery-clear'));
    await waitFor(() => expect(onClear).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('does not offer Clear for a set with no existing delivery', async () => {
    render(<MemberDeliveryEditor {...makeProps()} />);
    await screen.findByTestId('member-delivery-save');
    expect(screen.queryByTestId('member-delivery-clear')).not.toBeInTheDocument();
  });
});
