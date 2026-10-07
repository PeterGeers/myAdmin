/**
 * Component tests for MemberMailCompose (analytics/MemberMailCompose.tsx).
 *
 * Verifies task 9.2 (R4.12, R8.4):
 *   - the compose modal renders with an editable, template-seeded subject + body
 *     (no hardcoded English — labels resolve from the `members` namespace);
 *   - the RECIPIENT COUNT is shown for confirmation (R8.4), resolved from the
 *     result rows via the email field resolved from `fieldConfig`
 *     (`resolveEmailField`, R4.12) — not hardcoded;
 *   - the optional attach-CSV / attach-PDF toggles appear per the supplied
 *     builders + the tenant's address mapping, and flow into the send;
 *   - Send is a CONFIRMED action (first press confirms, second sends) and calls
 *     the authenticated `mailMembersSet` service with the subject/body/recipients/
 *     attachments (R8.4); the service is mocked (no network);
 *   - when no email field resolves, the send is blocked with a bilingual reason.
 *
 * The Mail button's `canExport` gating lives with the Pivot Views slot
 * (MemberPivotViews.test.tsx) where the button is mounted; this file verifies the
 * compose modal itself.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import type { FieldConfig, MemberRow } from '../../../types/members';

// --- Mock the authenticated mail service (no network). -----------------------
const mailMembersSet = vi.fn();
vi.mock('../../../services/memberMailService', () => ({
  mailMembersSet: (...args: unknown[]) => mailMembersSet(...args),
}));

// --- Spy on Chakra's useToast while keeping the rest of the library real. -----
// Lets the rate-limit test assert the DEDICATED toast title fires (task 9.3).
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
    // Echo the key, appending a count when the caller interpolates one so the
    // recipient-count assertions can see the number.
    t: (key: string, opts?: { count?: number }) =>
      opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key,
  }),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberMailCompose from './MemberMailCompose';
import { MemberMailCompose as FromBarrel } from './index';
import type { MemberMailComposeProps } from './MemberMailCompose';

/** A field config exposing an `email`-typed recipient field + an address mapping. */
const fieldConfig = {
  fields: [
    { key: 'display_name', origin: 'calculated', label: { en: 'Name' } },
    { key: 'email', origin: 'fixed', type: 'email', label: { en: 'Email' } },
    { key: 'street', origin: 'fixed', label: { en: 'Street' } },
    { key: 'postcode', origin: 'fixed', label: { en: 'Postcode' } },
    { key: 'city', origin: 'fixed', label: { en: 'City' } },
  ],
  analytics: {
    address_mapping: {
      name: 'display_name',
      street: 'street',
      postcode: 'postcode',
      city: 'city',
    },
  },
} as unknown as FieldConfig;

/** Four result rows; two share an email so de-dup drops one → 3 recipients. */
const recipients = [
  { member_id: 'a', email: 'alice@example.com' },
  { member_id: 'b', email: 'bob@example.com' },
  { member_id: 'c', email: 'ALICE@example.com' }, // dup of alice (case-insensitive)
  { member_id: 'd', email: 'dora@example.com' },
] as unknown as MemberRow[];

function makeProps(overrides: Partial<MemberMailComposeProps> = {}): MemberMailComposeProps {
  return {
    isOpen: true,
    onClose: vi.fn(),
    fieldConfig,
    recipients,
    language: 'en',
    buildCsvBase64: () => 'Y3N2', // "csv"
    buildPdfBase64: () => 'cGRm', // "pdf"
    setKey: 'members-per-type',
    ...overrides,
  };
}

beforeEach(() => {
  mailMembersSet.mockReset();
  mailMembersSet.mockResolvedValue({ success: true, status: 200, recipientCount: 3 });
  toastSpy.mockReset();
});

describe('MemberMailCompose', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberMailCompose);
  });

  it('renders a template-seeded, editable subject + body (no hardcoded English)', () => {
    render(<MemberMailCompose {...makeProps()} />);

    const subject = screen.getByTestId('member-mail-subject') as HTMLInputElement;
    const body = screen.getByTestId('member-mail-body') as HTMLTextAreaElement;
    // Seeded from the bilingual template keys (echoed by the i18n mock).
    expect(subject.value).toBe('analytics.mail.subjectTemplate');
    expect(body.value).toBe('analytics.mail.bodyTemplate');

    // Editable.
    fireEvent.change(subject, { target: { value: 'Hello members' } });
    expect(subject.value).toBe('Hello members');
  });

  it('shows the de-duplicated recipient COUNT for confirmation (R8.4/R4.12)', () => {
    render(<MemberMailCompose {...makeProps()} />);
    // 4 rows, one duplicate email → 3 recipients, resolved via the email field.
    expect(screen.getByTestId('member-mail-recipient-count')).toHaveTextContent(
      'analytics.mail.recipientCount:3',
    );
  });

  it('renders both attach toggles when builders + address mapping are present', () => {
    render(<MemberMailCompose {...makeProps()} />);
    expect(screen.getByTestId('member-mail-attach-csv')).toBeInTheDocument();
    expect(screen.getByTestId('member-mail-attach-pdf')).toBeInTheDocument();
  });

  it('hides the PDF toggle when the tenant has no resolvable address mapping (R4.10)', () => {
    const noMapping = { ...fieldConfig, analytics: {} } as unknown as FieldConfig;
    render(<MemberMailCompose {...makeProps({ fieldConfig: noMapping })} />);
    expect(screen.getByTestId('member-mail-attach-csv')).toBeInTheDocument();
    expect(screen.queryByTestId('member-mail-attach-pdf')).not.toBeInTheDocument();
  });

  it('hides the CSV toggle when no CSV builder is supplied', () => {
    render(<MemberMailCompose {...makeProps({ buildCsvBase64: undefined })} />);
    expect(screen.queryByTestId('member-mail-attach-csv')).not.toBeInTheDocument();
  });

  it('confirms before sending, then calls the service with subject/body/recipients (R8.4)', async () => {
    render(<MemberMailCompose {...makeProps()} />);

    fireEvent.change(screen.getByTestId('member-mail-subject'), {
      target: { value: 'Hello members' },
    });
    fireEvent.change(screen.getByTestId('member-mail-body'), {
      target: { value: 'The body' },
    });

    // First press → confirmation prompt, no send yet.
    fireEvent.click(screen.getByTestId('member-mail-send'));
    expect(screen.getByTestId('member-mail-confirm')).toHaveTextContent(
      'analytics.mail.confirm:3',
    );
    expect(mailMembersSet).not.toHaveBeenCalled();

    // Second press → the actual send.
    fireEvent.click(screen.getByTestId('member-mail-send'));
    await waitFor(() => expect(mailMembersSet).toHaveBeenCalledTimes(1));

    const req = mailMembersSet.mock.calls[0][0];
    expect(req.subject).toBe('Hello members');
    expect(req.body).toBe('The body');
    expect(req.recipients).toBe(recipients);
    // The recipient email field is resolved from fieldConfig (R4.12), not hardcoded.
    expect(req.email_field).toBe('email');
    expect(req.set_key).toBe('members-per-type');
    // No attachments were toggled.
    expect(req.attachments).toEqual([]);
  });

  it('includes toggled CSV + PDF attachments in the send', async () => {
    // Snapshot the attachments AT CALL TIME: the component releases the base64
    // buffers after the send (R8.5, task 9.3) by clearing the same descriptors it
    // forwarded, so inspecting the recorded call afterwards would see them empty.
    let sentAttachments: unknown;
    mailMembersSet.mockImplementation((req: { attachments?: unknown[] }) => {
      sentAttachments = (req.attachments ?? []).map((a) => ({ ...(a as object) }));
      return Promise.resolve({ success: true, status: 200, recipientCount: 3 });
    });

    render(<MemberMailCompose {...makeProps()} />);

    fireEvent.click(screen.getByTestId('member-mail-attach-csv'));
    fireEvent.click(screen.getByTestId('member-mail-attach-pdf'));

    // Confirm + send.
    fireEvent.click(screen.getByTestId('member-mail-send'));
    fireEvent.click(screen.getByTestId('member-mail-send'));

    await waitFor(() => expect(mailMembersSet).toHaveBeenCalledTimes(1));
    expect(sentAttachments).toEqual([
      { kind: 'csv', content_base64: 'Y3N2', filename: 'members.csv' },
      { kind: 'pdf', content_base64: 'cGRm', filename: 'labels.pdf' },
    ]);
  });

  it('blocks the send and shows a reason when no email field resolves (R4.12)', () => {
    const noEmail = {
      fields: [{ key: 'display_name', origin: 'calculated', label: { en: 'Name' } }],
    } as unknown as FieldConfig;
    render(<MemberMailCompose {...makeProps({ fieldConfig: noEmail })} />);

    expect(screen.getByTestId('member-mail-no-email-field')).toHaveTextContent(
      'analytics.mail.noEmailField',
    );
    expect(screen.getByTestId('member-mail-send')).toBeDisabled();
  });

  it('keeps the modal open on a failed send (set result not lost)', async () => {
    mailMembersSet.mockResolvedValue({ success: false, status: 502, error: 'boom' });
    const onClose = vi.fn();
    render(<MemberMailCompose {...makeProps({ onClose })} />);

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(mailMembersSet).toHaveBeenCalledTimes(1));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('shows the dedicated rate-limited message and keeps the set (R4.12, task 9.3)', async () => {
    // SES rate-limited the send: the service flags `rateLimited`.
    mailMembersSet.mockResolvedValue({
      success: false,
      status: 429,
      rateLimited: true,
      error: 'Email send rate limit reached',
    });
    const onClose = vi.fn();
    render(<MemberMailCompose {...makeProps({ onClose })} />);

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(mailMembersSet).toHaveBeenCalledTimes(1));

    // The DEDICATED bilingual rate-limited toast fires, not the generic error.
    await waitFor(() =>
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'analytics.mail.toast.rateLimited' }),
      ),
    );
    expect(toastSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'analytics.mail.toast.error' }),
    );
    // The composed set is NOT lost — the modal stays open to retry.
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByTestId('member-mail-send')).toBeInTheDocument();
  });

  it('clears the in-memory attachment buffers after a send completes (R8.5)', async () => {
    // Capture the exact attachments array the component forwards to the service,
    // so we can assert the component released its base64 buffers afterwards.
    let forwarded: Array<{ content_base64: string }> | undefined;
    mailMembersSet.mockImplementation((req: { attachments?: Array<{ content_base64: string }> }) => {
      forwarded = req.attachments;
      // The content is present at the moment of send.
      expect(forwarded?.every((a) => a.content_base64 !== '')).toBe(true);
      return Promise.resolve({ success: true, status: 200, recipientCount: 3 });
    });

    render(<MemberMailCompose {...makeProps()} />);
    fireEvent.click(screen.getByTestId('member-mail-attach-csv'));
    fireEvent.click(screen.getByTestId('member-mail-attach-pdf'));

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(mailMembersSet).toHaveBeenCalledTimes(1));

    // After the send, every forwarded descriptor's buffer is released (R8.5).
    await waitFor(() =>
      expect(forwarded?.every((a) => a.content_base64 === '')).toBe(true),
    );
  });
});
