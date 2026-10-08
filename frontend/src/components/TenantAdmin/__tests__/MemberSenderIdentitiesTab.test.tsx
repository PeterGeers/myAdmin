/**
 * MemberSenderIdentitiesTab Component - Unit Tests (R0, design §6.2).
 *
 * Covers the three behaviours in task 0.3:
 *   - add a sender address (POST /members/sender-identities),
 *   - show each address with its SES status (pending / verified / ...),
 *   - resend verification for a not-yet-verified address.
 */
import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '../../../test-utils';
import MemberSenderIdentitiesTab from '../MemberSenderIdentitiesTab';
import type { MemberSenderIdentity } from '../../../types/memberSenderIdentityTypes';

vi.mock('../../../services/memberSenderIdentityService', () => ({
  getSenderIdentities: vi.fn(),
  addSenderIdentity: vi.fn(),
  resendSenderIdentity: vi.fn(),
}));

// Translation stub: return the fallback (2nd arg) so assertions read human text.
const mockT = (_key: string, fallback?: string) => fallback ?? _key;
const mockI18n = { language: 'en', changeLanguage: vi.fn() };
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: mockT, i18n: mockI18n }),
}));

import {
  getSenderIdentities,
  addSenderIdentity,
  resendSenderIdentity,
} from '../../../services/memberSenderIdentityService';

const identities: MemberSenderIdentity[] = [
  { email: 'news@club.nl', status: 'verified', lastChecked: '2026-01-01T00:00:00Z' },
  { email: 'board@club.nl', status: 'pending', lastChecked: null },
];

function okList(list: MemberSenderIdentity[]) {
  return { success: true, data: { identities: list } };
}

describe('MemberSenderIdentitiesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getSenderIdentities).mockResolvedValue(okList(identities));
    vi.mocked(addSenderIdentity).mockResolvedValue({
      success: true,
      data: { email: 'new@club.nl', status: 'pending', lastChecked: null },
    });
    vi.mocked(resendSenderIdentity).mockResolvedValue({ success: true });
  });

  describe('Rendering + status', () => {
    test('shows a loading spinner initially', () => {
      // Use `...Once` so the never-resolving promise cannot leak into later tests.
      vi.mocked(getSenderIdentities).mockReturnValueOnce(new Promise(() => { }));
      render(<MemberSenderIdentitiesTab tenant="club" />);
      expect(screen.getByText(/Loading sender addresses/i)).toBeInTheDocument();
    });

    test('lists each sender address with its SES status', async () => {
      render(<MemberSenderIdentitiesTab tenant="club" />);
      await waitFor(() => {
        expect(screen.getByText('news@club.nl')).toBeInTheDocument();
        expect(screen.getByText('board@club.nl')).toBeInTheDocument();
      });
      // Each row renders its status via `t('status.<status>', <status>)`; the
      // translation stub returns the fallback (the raw status key value), so the
      // verified/pending states are both present and distinct.
      expect(screen.getByText('verified')).toBeInTheDocument();
      expect(screen.getByText('pending')).toBeInTheDocument();
    });

    test('shows an empty state when no addresses exist', async () => {
      vi.mocked(getSenderIdentities).mockResolvedValue(okList([]));
      render(<MemberSenderIdentitiesTab tenant="club" />);
      await waitFor(() =>
        expect(screen.getByText(/No sender addresses yet/i)).toBeInTheDocument()
      );
    });
  });

  describe('Add a sender address', () => {
    test('submits a valid address and reloads the list', async () => {
      render(<MemberSenderIdentitiesTab tenant="club" />);
      await waitFor(() => expect(screen.getByText('news@club.nl')).toBeInTheDocument());

      const callsBeforeAdd = vi.mocked(getSenderIdentities).mock.calls.length;

      const input = screen.getByPlaceholderText('sender@example.com');
      fireEvent.change(input, { target: { value: 'new@club.nl' } });
      fireEvent.click(screen.getByRole('button', { name: /Add Address/i }));

      await waitFor(() =>
        expect(addSenderIdentity).toHaveBeenCalledWith('new@club.nl')
      );
      // A successful add reloads the list (at least one extra fetch after add).
      await waitFor(() =>
        expect(vi.mocked(getSenderIdentities).mock.calls.length).toBeGreaterThan(
          callsBeforeAdd
        )
      );
    });

    test('rejects an invalid address client-side (no API call)', async () => {
      render(<MemberSenderIdentitiesTab tenant="club" />);
      await waitFor(() => expect(screen.getByText('news@club.nl')).toBeInTheDocument());

      const input = screen.getByPlaceholderText('sender@example.com');
      fireEvent.change(input, { target: { value: 'not-an-email' } });
      fireEvent.click(screen.getByRole('button', { name: /Add Address/i }));

      await waitFor(() =>
        expect(screen.getByText(/valid email address/i)).toBeInTheDocument()
      );
      expect(addSenderIdentity).not.toHaveBeenCalled();
    });
  });

  describe('Resend verification', () => {
    test('offers resend only for a not-yet-verified address and calls the API', async () => {
      render(<MemberSenderIdentitiesTab tenant="club" />);
      await waitFor(() => expect(screen.getByText('board@club.nl')).toBeInTheDocument());

      // One resend button — only the pending address (board@club.nl) gets one.
      const resendButtons = screen.getAllByRole('button', { name: /Resend/i });
      expect(resendButtons).toHaveLength(1);

      fireEvent.click(resendButtons[0]);
      await waitFor(() =>
        expect(resendSenderIdentity).toHaveBeenCalledWith('board@club.nl')
      );
    });
  });
});
