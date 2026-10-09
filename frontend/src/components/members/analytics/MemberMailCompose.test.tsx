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
 *   - when no email field resolves, the send is blocked with a bilingual reason.
 *
 * Plane repoint (mail-spec tasks 2.3 + 4.1, R1.1/R1.2): the compose POSTs to the
 * SAM Members route `POST /members/mail/send` via `sendAdHocMail`. The old Flask
 * `POST /api/members/mail-set` route (`mailMembersSet`) has since been RETIRED and
 * deleted (task 4.1), so there is no longer a Flask seam to mock or guard against.
 * These tests verify:
 *   - Send is a CONFIRMED action (first press confirms, second sends) and calls
 *     `sendAdHocMail` with the ad-hoc body (mode + result rows + template /
 *     recipients / attachment);
 *   - the 202 queued receipt surfaces as the "queued, N" acknowledgment;
 *   - a not-certified / invalid-body 422 is surfaced via `applyApiError` and the
 *     composed set is kept (the modal stays open).
 *
 * The Mail button's `canExport` gating lives with the Pivot Views slot
 * (MemberPivotViews.test.tsx) where the button is mounted; this file verifies the
 * compose modal itself.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import type { FieldConfig, MemberRow } from '../../../types/members';

// --- Mock the SAM Members API service (no network). --------------------------
// The compose POSTs the ad-hoc body to `POST /members/mail/send` via `sendAdHocMail`
// (mail-spec task 2.3). The old Flask `memberMailService` seam is gone (task 4.1).
const sendAdHocMail = vi.fn();
vi.mock('../../../services/membersApiService', () => ({
  sendAdHocMail: (...args: unknown[]) => sendAdHocMail(...args),
}));

// --- Mock the template service so the R2 picker + manager run with no network. ---
// The picker lists templates (async) and seeds subject/body on a pick via get-by-id;
// the manager (mounted inside the compose modal) also lists on open. Default both to
// an empty library; individual tests override via the per-test spies below.
const listMemberTemplates = vi.fn();
const getMemberTemplate = vi.fn();
vi.mock('../../../services/memberTemplateService', () => ({
  listMemberTemplates: (...args: unknown[]) => listMemberTemplates(...args),
  getMemberTemplate: (...args: unknown[]) => getMemberTemplate(...args),
  createMemberTemplate: vi.fn(),
  updateMemberTemplate: vi.fn(),
  deleteMemberTemplate: vi.fn(),
  aiImproveMemberTemplate: vi.fn(),
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
    // recipient-count assertions can see the number; echo the `addresses`
    // interpolation for the external-recipients validation message.
    t: (key: string, opts?: { count?: number; addresses?: string }) => {
      if (opts && typeof opts.count === 'number') {
        return `${key}:${opts.count}`;
      }
      if (opts && typeof opts.addresses === 'string') {
        return `${key}:${opts.addresses}`;
      }
      return key;
    },
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
  sendAdHocMail.mockReset();
  // The 202 accepted receipt (DeliveryRunResult) the SAM route returns.
  sendAdHocMail.mockResolvedValue({
    runId: 'run-1',
    mode: 'per_recipient',
    enqueued: 3,
    skippedNoAddress: 0,
    jobIds: ['job-1', 'job-2', 'job-3'],
  });
  toastSpy.mockReset();
  // Default: an empty template library (the picker renders, lists nothing).
  listMemberTemplates.mockReset();
  listMemberTemplates.mockResolvedValue({ ok: true, data: [] });
  getMemberTemplate.mockReset();
  getMemberTemplate.mockResolvedValue({ ok: false, status: 404, error: 'not found' });
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

  it('confirms before sending, then POSTs the ad-hoc body to the SAM route — NOT Flask (R1/R8.4)', async () => {
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
    expect(sendAdHocMail).not.toHaveBeenCalled();

    // Second press → the actual send, via the SAM `POST /members/mail/send` seam.
    fireEvent.click(screen.getByTestId('member-mail-send'));
    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));

    const body = sendAdHocMail.mock.calls[0][0];
    // No external recipients + no attachment → a per_recipient fan-out carrying
    // the current result rows (the member-list mailing).
    expect(body.mode).toBe('per_recipient');
    expect(body.result_rows).toEqual(recipients);
    // The per-recipient address column is the field resolved from fieldConfig
    // (R4.12), carried as the recipient_field override — not hardcoded.
    expect(body.recipient_field).toBe('email');
    // The audit label rides along as set_id (metadata only, R8.1).
    expect(body.set_id).toBe('members-per-type');

    // The 202 queued receipt surfaces as the "queued, N" acknowledgment.
    await waitFor(() =>
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'analytics.mail.toast.queued:3' }),
      ),
    );
  });

  it('sends to_fixed with the attachment KIND when CSV/PDF is toggled (worker builds the bytes)', async () => {
    render(<MemberMailCompose {...makeProps()} />);

    // Toggling an attachment makes this a to_fixed send; the frontend ships only
    // the attachment KIND + the result rows — the SAM worker renders the bytes
    // on-plane (steering 35: the frontend never produces/sends the payload).
    fireEvent.click(screen.getByTestId('member-mail-attach-pdf'));

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));
    const body = sendAdHocMail.mock.calls[0][0];
    expect(body.mode).toBe('to_fixed');
    // The Avery-labels toggle maps to the SAM `pdf_labels` attachment kind.
    expect(body.attachment).toBe('pdf_labels');
    expect(body.result_rows).toEqual(recipients);
    // No base64 payload is ever shipped on the ad-hoc body.
    expect(body).not.toHaveProperty('content_base64');
    expect(body).not.toHaveProperty('attachments');
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

  // --- R1 (pivot-output-actions): external recipients ------------------------
  describe('external recipients (R1)', () => {
    it('renders the external-recipients field', () => {
      render(<MemberMailCompose {...makeProps()} />);
      expect(screen.getByTestId('member-mail-external')).toBeInTheDocument();
    });

    it('adds valid external addresses to the confirmed count (3 members + 2 external = 5)', () => {
      render(<MemberMailCompose {...makeProps()} />);
      fireEvent.change(screen.getByTestId('member-mail-external'), {
        target: { value: 'agent@example.com, office@example.org' },
      });
      expect(screen.getByTestId('member-mail-recipient-count')).toHaveTextContent(
        'analytics.mail.recipientCount:5',
      );
      // No validation error for well-formed addresses.
      expect(
        screen.queryByTestId('member-mail-external-invalid'),
      ).not.toBeInTheDocument();
    });

    it('splits on comma, semicolon, newline, and whitespace', () => {
      render(<MemberMailCompose {...makeProps()} />);
      fireEvent.change(screen.getByTestId('member-mail-external'), {
        target: { value: 'a@x.com, b@x.com; c@x.com\nd@x.com e@x.com' },
      });
      // 3 members + 5 external = 8.
      expect(screen.getByTestId('member-mail-recipient-count')).toHaveTextContent(
        'analytics.mail.recipientCount:8',
      );
    });

    it('de-duplicates external addresses against each other and the member emails', () => {
      render(<MemberMailCompose {...makeProps()} />);
      fireEvent.change(screen.getByTestId('member-mail-external'), {
        // bob@ already appears in the member rows; AGENT@ listed twice (case-insensitive).
        target: { value: 'BOB@example.com, AGENT@example.com, agent@example.com' },
      });
      // 3 members + only 1 new unique external (agent@) = 4.
      expect(screen.getByTestId('member-mail-recipient-count')).toHaveTextContent(
        'analytics.mail.recipientCount:4',
      );
    });

    it('surfaces a validation reason and disables Send on an invalid address', () => {
      render(<MemberMailCompose {...makeProps()} />);
      fireEvent.change(screen.getByTestId('member-mail-external'), {
        target: { value: 'good@example.com, not-an-email, also@bad@x' },
      });
      const invalid = screen.getByTestId('member-mail-external-invalid');
      expect(invalid).toHaveTextContent('analytics.mail.externalRecipientsInvalid');
      expect(invalid).toHaveTextContent('not-an-email');
      expect(invalid).toHaveTextContent('also@bad@x');
      // An invalid token blocks the send even though valid members exist.
      expect(screen.getByTestId('member-mail-send')).toBeDisabled();
    });

    it('sends typed external addresses as a to_fixed recipient list (R1), on the SAM plane', async () => {
      render(<MemberMailCompose {...makeProps()} />);
      fireEvent.change(screen.getByTestId('member-mail-subject'), {
        target: { value: 'Hi' },
      });
      fireEvent.change(screen.getByTestId('member-mail-body'), {
        target: { value: 'Body' },
      });
      fireEvent.change(screen.getByTestId('member-mail-external'), {
        target: { value: 'agent@example.com' },
      });

      fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
      fireEvent.click(screen.getByTestId('member-mail-send')); // send
      await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));

      const body = sendAdHocMail.mock.calls[0][0];
      // Typed fixed recipients → a to_fixed send: the typed list is the fixed
      // recipients; the member rows ride along as the result_rows source.
      expect(body.mode).toBe('to_fixed');
      expect(body.recipients).toEqual(['agent@example.com']);
      expect(body.result_rows).toEqual(recipients);
    });

    it('allows an external-only send when no email field is configured', async () => {
      const noEmail = {
        fields: [{ key: 'display_name', origin: 'calculated', label: { en: 'Name' } }],
      } as unknown as FieldConfig;
      render(<MemberMailCompose {...makeProps({ fieldConfig: noEmail })} />);

      fireEvent.change(screen.getByTestId('member-mail-subject'), {
        target: { value: 'Hi' },
      });
      fireEvent.change(screen.getByTestId('member-mail-body'), {
        target: { value: 'Body' },
      });
      fireEvent.change(screen.getByTestId('member-mail-external'), {
        target: { value: 'agent@example.com' },
      });

      // Send is now enabled on the strength of the external address alone.
      expect(screen.getByTestId('member-mail-send')).not.toBeDisabled();

      fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
      fireEvent.click(screen.getByTestId('member-mail-send')); // send
      await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));

      const body = sendAdHocMail.mock.calls[0][0];
      // Only the external address is the fixed recipient list.
      expect(body.mode).toBe('to_fixed');
      expect(body.recipients).toEqual(['agent@example.com']);
    });
  });

  // --- R2 (pivot-output-actions): stored-template picker ---------------------
  describe('template picker (R2)', () => {
    it('renders the template picker and a Manage templates button by default', () => {
      render(<MemberMailCompose {...makeProps()} />);
      expect(
        screen.getByTestId('member-mail-template-control'),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('member-mail-manage-templates'),
      ).toBeInTheDocument();
    });

    it('hides the picker when templates are disabled', () => {
      render(<MemberMailCompose {...makeProps({ enableTemplates: false })} />);
      expect(
        screen.queryByTestId('member-mail-template-control'),
      ).not.toBeInTheDocument();
    });

    it('seeds the (still-editable) subject + body from a picked template for the active language', async () => {
      listMemberTemplates.mockResolvedValue({
        ok: true,
        data: [{ template_id: 'tpl-1', name: 'Welcome' }],
      });
      getMemberTemplate.mockResolvedValue({
        ok: true,
        data: {
          template_id: 'tpl-1',
          name: 'Welcome',
          languages: {
            nl: { subject: 'NL onderwerp', body_html: 'NL body' },
            en: { subject: 'EN subject', body_html: 'EN body' },
          },
          merge_fields: [],
          logo_asset_ref: null,
          origin: 'user',
          created_by: '',
          created_at: '',
          updated_at: '',
        },
      });

      render(<MemberMailCompose {...makeProps({ language: 'en' })} />);

      // Open the picker (LazySelect combobox) and pick the template.
      fireEvent.click(screen.getByRole('combobox'));
      const option = await screen.findByText('Welcome');
      fireEvent.mouseDown(option);

      // The active language (en) seeds the subject + body, and they remain editable.
      const subject = screen.getByTestId('member-mail-subject') as HTMLInputElement;
      const body = screen.getByTestId('member-mail-body') as HTMLTextAreaElement;
      await waitFor(() => expect(subject.value).toBe('EN subject'));
      expect(body.value).toBe('EN body');

      // Still editable after seeding.
      fireEvent.change(subject, { target: { value: 'Edited' } });
      expect(subject.value).toBe('Edited');
      expect(getMemberTemplate).toHaveBeenCalledWith('tpl-1');
    });

    it('opens the template-management surface from the Manage templates button', async () => {
      render(<MemberMailCompose {...makeProps()} />);
      fireEvent.click(screen.getByTestId('member-mail-manage-templates'));
      expect(
        await screen.findByTestId('member-template-manager'),
      ).toBeInTheDocument();
    });
  });

  it('keeps the modal open on a failed send (set result not lost)', async () => {
    sendAdHocMail.mockRejectedValue(new Error('network boom'));
    const onClose = vi.fn();
    render(<MemberMailCompose {...makeProps({ onClose })} />);

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));
    expect(onClose).not.toHaveBeenCalled();
    // The composed set is NOT lost — the send control is still mounted.
    expect(screen.getByTestId('member-mail-send')).toBeInTheDocument();
  });

  it('surfaces the not-certified 422 via applyApiError and keeps the set (R4.2/R5.2)', async () => {
    // The SAM route refuses BEFORE enqueue (pre-send certification gate): a typed
    // ApiError the compose surfaces via applyApiError, never a silent drop.
    const { ApiError } = await import('../../../shared/api/ApiError');
    sendAdHocMail.mockRejectedValue(
      new ApiError(422, {
        error: 'The tenant mail sender is not certified',
        code: 'errors.mail.notCertified',
      }),
    );
    const onClose = vi.fn();
    render(<MemberMailCompose {...makeProps({ onClose })} />);

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));

    // applyApiError surfaces an error toast carrying the refusal reason (the
    // key-echo i18n env falls back to the backend English `error`), and the
    // generic success/queued toast is NOT shown.
    await waitFor(() =>
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'The tenant mail sender is not certified',
          status: 'error',
        }),
      ),
    );
    expect(toastSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'analytics.mail.toast.queued:3' }),
    );
    // The composed set is NOT lost — the modal stays open to act on the reason.
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByTestId('member-mail-send')).toBeInTheDocument();
  });

  it('surfaces an invalid-body 422 via applyApiError and keeps the set', async () => {
    const { ApiError } = await import('../../../shared/api/ApiError');
    sendAdHocMail.mockRejectedValue(
      new ApiError(422, { error: 'per_recipient send carries no result rows to mail' }),
    );
    const onClose = vi.fn();
    render(<MemberMailCompose {...makeProps({ onClose })} />);

    fireEvent.click(screen.getByTestId('member-mail-send')); // confirm
    fireEvent.click(screen.getByTestId('member-mail-send')); // send

    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'error' }),
      ),
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});
