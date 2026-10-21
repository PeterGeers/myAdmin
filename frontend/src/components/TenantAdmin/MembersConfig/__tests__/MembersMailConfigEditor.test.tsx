/**
 * Tests for the typed Members MAIL function — the single authoring door for the SAM-owned
 * `config#mail` scalars (Members config SAM-owned write path, task 7.1; Requirements 20.1/20.2/
 * 9.1/14.4/15.2).
 *
 * Asserts the task-7.1 contract:
 *  (a) the typed fields render with bilingual labels (no raw JSON grid);
 *  (b) client-side Yup validation REJECTS a malformed `mail_reply_to_default` with NO API call;
 *  (c) ONE Save issues EXACTLY one `saveMembersMailConfig` (→ `PUT /members/config/mail`) with the
 *      full reader-shaped body (single authoring door, Property 8);
 *  (d) `consent_notice` is OMITTED when not well-formed and INCLUDED when well-formed;
 *  (e) a failed save surfaces the error toast and does NOT claim success.
 *
 * Uses the project's real i18n + test-utils render so the bilingual `t(nl,en)` labels render.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, fireEvent, waitFor } from '../../../../test-utils';
import i18n from '../../../../i18n';
/* ------------------------------------------------------------------ */
/*  Toast spy — Chakra renders toasts in a portal via a manager, so   */
/*  spying on useToast is the reliable way to assert the error toast. */
/* ------------------------------------------------------------------ */
const mockToast = vi.fn();
vi.mock('@chakra-ui/react', async () => {
  const actual = await vi.importActual<typeof import('@chakra-ui/react')>('@chakra-ui/react');
  return { ...actual, useToast: () => mockToast };
});

/* ------------------------------------------------------------------ */
/*  Service mocks — the save door + the best-effort loads.            */
/* ------------------------------------------------------------------ */
const mockSaveMail = vi.fn();
const mockGetFieldConfig = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    saveMembersMailConfig: (...a: unknown[]) => mockSaveMail(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
  };
});

import { MembersMailConfigEditor } from '../MembersMailConfigEditor';

const renderEditor = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <MembersMailConfigEditor tenant="h-dcn" />
    </I18nextProvider>,
  );

describe('MembersMailConfigEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The form now loads the mail scalars from the AUTHORITATIVE field-config `mail_config`
    // (the SAM config#mail body), NOT from the legacy members.* params. An empty/fail-closed
    // mail_config → the fail-closed defaults; never blocks authoring.
    mockGetFieldConfig.mockResolvedValue({
      fields: [],
      mail_config: { mail_enabled: false, mail_local_part: 'noreply', mail_certified: false },
    });
    mockSaveMail.mockResolvedValue({ success: true, version: '2026-10-20T10:00:00+00:00' });
  });

  it('renders the typed fields with bilingual labels (English active)', async () => {
    await i18n.changeLanguage('en');
    renderEditor();

    // The editor renders (best-effort load completes).
    expect(await screen.findByTestId('members-mail-config-editor')).toBeInTheDocument();
    // Typed controls, not a raw JSON grid.
    expect(screen.getByTestId('members-mail-config-enabled')).toBeInTheDocument();
    expect(screen.getByTestId('members-mail-config-domain')).toBeInTheDocument();
    expect(screen.getByTestId('members-mail-config-local-part')).toBeInTheDocument();
    expect(screen.getByTestId('members-mail-config-certified')).toBeInTheDocument();
    expect(screen.getByTestId('members-mail-config-reply-to')).toBeInTheDocument();
    // English labels.
    expect(screen.getByText('Mail enabled')).toBeInTheDocument();
    expect(screen.getByText('Mail domain')).toBeInTheDocument();
  });

  it('shows Dutch labels when the active language is nl', async () => {
    await i18n.changeLanguage('nl');
    renderEditor();

    expect(await screen.findByTestId('members-mail-config-editor')).toBeInTheDocument();
    expect(screen.getByText('Mail inschakelen')).toBeInTheDocument();
    expect(screen.getByText('Maildomein')).toBeInTheDocument();
  });

  it('renders the From preview from local-part + domain', async () => {
    await i18n.changeLanguage('en');
    renderEditor();

    const preview = await screen.findByTestId('members-mail-config-from-preview');
    // Default local-part noreply + unset domain placeholder.
    expect(preview).toHaveTextContent('noreply@<domain>');

    fireEvent.change(screen.getByTestId('members-mail-config-domain'), {
      target: { value: 'h-dcn.nl' },
    });
    fireEvent.change(screen.getByTestId('members-mail-config-local-part'), {
      target: { value: 'info' },
    });
    await waitFor(() => expect(preview).toHaveTextContent('info@h-dcn.nl'));
  });

  it('rejects a malformed mail_reply_to_default client-side with NO save call (b)', async () => {
    await i18n.changeLanguage('en');
    renderEditor();

    await screen.findByTestId('members-mail-config-editor');
    fireEvent.change(screen.getByTestId('members-mail-config-reply-to'), {
      target: { value: 'not-an-email' },
    });
    fireEvent.click(screen.getByTestId('members-mail-config-save'));

    // The Yup error surfaces and the save door is NEVER reached.
    await screen.findByTestId('members-mail-config-reply-to-error');
    expect(mockSaveMail).not.toHaveBeenCalled();
  });

  it('issues EXACTLY one save with the full body and OMITS a half-authored consent_notice (c/d)', async () => {
    await i18n.changeLanguage('en');
    renderEditor();

    await screen.findByTestId('members-mail-config-editor');
    fireEvent.click(screen.getByTestId('members-mail-config-enabled'));
    fireEvent.change(screen.getByTestId('members-mail-config-domain'), {
      target: { value: 'h-dcn.nl' },
    });
    fireEvent.change(screen.getByTestId('members-mail-config-local-part'), {
      target: { value: 'info' },
    });
    fireEvent.click(screen.getByTestId('members-mail-config-certified'));
    fireEvent.change(screen.getByTestId('members-mail-config-reply-to'), {
      target: { value: 'noreply@h-dcn.nl' },
    });
    // Author ONLY a consent version (no locale body) — NOT well-formed → must be omitted.
    fireEvent.change(screen.getByTestId('members-mail-config-consent-version'), {
      target: { value: '2026-01' },
    });

    fireEvent.click(screen.getByTestId('members-mail-config-save'));

    await waitFor(() => expect(mockSaveMail).toHaveBeenCalledTimes(1));
    const body = mockSaveMail.mock.calls[0][0];
    expect(body).toEqual({
      mail_enabled: true,
      mail_certified: true,
      mail_local_part: 'info',
      mail_domain: 'h-dcn.nl',
      mail_reply_to_default: 'noreply@h-dcn.nl',
    });
    // Half-authored notice (version but no body) is OMITTED.
    expect(body).not.toHaveProperty('consent_notice');
  });

  it('INCLUDES a well-formed consent_notice (version + >=1 locale body) (d)', async () => {
    await i18n.changeLanguage('en');
    renderEditor();

    await screen.findByTestId('members-mail-config-editor');
    fireEvent.change(screen.getByTestId('members-mail-config-consent-version'), {
      target: { value: '2026-01' },
    });
    fireEvent.change(screen.getByTestId('members-mail-config-consent-nl'), {
      target: { value: 'Toestemmingstekst' },
    });

    fireEvent.click(screen.getByTestId('members-mail-config-save'));

    await waitFor(() => expect(mockSaveMail).toHaveBeenCalledTimes(1));
    const body = mockSaveMail.mock.calls[0][0];
    expect(body.consent_notice).toEqual({
      version: '2026-01',
      text: { nl: 'Toestemmingstekst' },
    });
  });

  it('surfaces an error toast and does not claim success on a failed save (e)', async () => {
    await i18n.changeLanguage('en');
    mockSaveMail.mockResolvedValue({ success: false, error: 'Access denied' });
    renderEditor();

    await screen.findByTestId('members-mail-config-editor');
    fireEvent.click(screen.getByTestId('members-mail-config-save'));

    await waitFor(() => expect(mockSaveMail).toHaveBeenCalledTimes(1));
    // The error toast surfaces with the caller-safe description; success is NEVER claimed.
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'error', description: 'Access denied' }),
      ),
    );
    expect(mockToast).not.toHaveBeenCalledWith(
      expect.objectContaining({ status: 'success' }),
    );
  });

  it('round-trips a saved reply-to through the authoritative field-config read (findings fix)', async () => {
    // Regression for the reported bug: Default Reply-To saved (server 200) then appeared blank
    // because the form reloaded the mail scalars from MySQL (which never holds the SAM-only
    // mail_reply_to_default). The form now loads from field-config `mail_config` and RE-FETCHES
    // after save, so the saved value round-trips through the real authoritative read path.
    await i18n.changeLanguage('en');
    // Initial load: no reply-to yet.
    mockGetFieldConfig.mockResolvedValueOnce({
      fields: [],
      mail_config: { mail_enabled: true, mail_local_part: 'noreply', mail_certified: true },
    });
    // Post-save re-fetch: the authoritative config#mail now carries the saved reply-to.
    mockGetFieldConfig.mockResolvedValueOnce({
      fields: [],
      mail_config: {
        mail_enabled: true,
        mail_local_part: 'noreply',
        mail_certified: true,
        mail_reply_to_default: 'webmaster@h-dcn.nl',
      },
    });
    mockSaveMail.mockResolvedValue({ success: true, version: '2026-10-21T08:29:24+00:00' });
    renderEditor();

    await screen.findByTestId('members-mail-config-editor');
    const replyTo = screen.getByTestId('members-mail-config-reply-to') as HTMLInputElement;
    // Loaded blank from the first (no reply-to) mail_config.
    expect(replyTo.value).toBe('');
    fireEvent.change(replyTo, { target: { value: 'webmaster@h-dcn.nl' } });
    fireEvent.click(screen.getByTestId('members-mail-config-save'));

    await waitFor(() => expect(mockSaveMail).toHaveBeenCalledTimes(1));
    expect(mockSaveMail.mock.calls[0][0]).toMatchObject({
      mail_reply_to_default: 'webmaster@h-dcn.nl',
    });
    // The re-fetch re-seeds from the AUTHORITATIVE read, so the value sticks (did not reset).
    await waitFor(() =>
      expect(
        (screen.getByTestId('members-mail-config-reply-to') as HTMLInputElement).value,
      ).toBe('webmaster@h-dcn.nl'),
    );
    // getMembersFieldConfig was called twice: initial load + post-save re-fetch (round-trip).
    expect(mockGetFieldConfig).toHaveBeenCalledTimes(2);
  });
});
