/**
 * Tests for the group modal's label seeding — the fold round-trip regression (group-label bug).
 *
 * The bug: a tenant edits a functional group's Dutch label, the whole-overlay save succeeds, but on
 * reopening the modal the edit appears GONE. Root cause was a read/write asymmetry — the server save
 * path FOLDS the editor's flat per-locale `label_nl`/`label_en` inputs into an inline `label{nl,en}`
 * dict and DROPS the flat keys (members_config_validation `_fold_entry_labels`), while the modal's
 * `formFromGroup` only ever read the flat `label_nl`/`label_en`. So a reloaded group (which now
 * carries `label{}` and no flat keys) re-seeded to blank.
 *
 * These assert the fold-aware seed: the modal reads a group's label from the flat input when present
 * (a fresh, unsaved edit) and otherwise from the folded `label{}` dict (the reloaded, post-save
 * shape) — so a saved label survives reopen.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { MembersGroupModal } from '../MembersGroupModal';
import type { MembersConfigValue } from '../../../../types/membersConfig';

/** An overlay whose `address` group carries ONLY the server-FOLDED `label{nl,en}` dict (the shape a
 *  reload returns after a save — no flat `label_nl`/`label_en`). This is the exact bug scenario. */
function foldedOverlay(): MembersConfigValue {
  return {
    functional_groups: [
      { key: 'address', label: { nl: 'Adres bewerkt', en: 'Address edited' }, order: 2 },
    ],
    fields: {},
    fixed_overrides: {},
  };
}

/** An overlay whose `address` group carries the FLAT per-locale inputs (a fresh, pre-save edit). */
function flatOverlay(): MembersConfigValue {
  return {
    functional_groups: [
      { key: 'address', label_nl: 'Adres vers', label_en: 'Address fresh', order: 2 },
    ],
    fields: {},
    fixed_overrides: {},
  };
}

function renderModal(
  overlay: MembersConfigValue,
  onChange: (next: MembersConfigValue) => void = vi.fn(),
) {
  i18n.changeLanguage('en');
  return render(
    <I18nextProvider i18n={i18n}>
      <MembersGroupModal
        isOpen
        onClose={vi.fn()}
        mode="edit"
        groupKey="address"
        overlay={overlay}
        onChange={onChange}
        lang="en"
      />
    </I18nextProvider>,
  );
}

describe('MembersGroupModal — fold-aware label seeding (group-label round-trip)', () => {
  it('seeds the Dutch + English inputs from the FOLDED label{} dict on reopen (regression)', () => {
    renderModal(foldedOverlay());
    const modal = screen.getByTestId('members-group-modal');
    // The saved labels survive reopen — read from `label{}`, not the (now-absent) flat keys.
    expect((within(modal).getByLabelText('Label (Dutch)') as HTMLInputElement).value).toBe(
      'Adres bewerkt',
    );
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe(
      'Address edited',
    );
  });

  it('still seeds from the FLAT per-locale inputs for a fresh (unsaved) group edit', () => {
    renderModal(flatOverlay());
    const modal = screen.getByTestId('members-group-modal');
    expect((within(modal).getByLabelText('Label (Dutch)') as HTMLInputElement).value).toBe(
      'Adres vers',
    );
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe(
      'Address fresh',
    );
  });

  it('prefers the flat input over the folded dict when BOTH are present (flat wins)', () => {
    const mixed: MembersConfigValue = {
      functional_groups: [
        {
          key: 'address',
          label_nl: 'Flat NL',
          label: { nl: 'Folded NL', en: 'Folded EN' },
          order: 2,
        },
      ],
      fields: {},
      fixed_overrides: {},
    };
    renderModal(mixed);
    const modal = screen.getByTestId('members-group-modal');
    // Flat input wins for its own locale; the other locale falls through to the folded dict.
    expect((within(modal).getByLabelText('Label (Dutch)') as HTMLInputElement).value).toBe('Flat NL');
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe(
      'Folded EN',
    );
  });
});
