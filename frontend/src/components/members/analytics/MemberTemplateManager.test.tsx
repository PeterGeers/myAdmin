/**
 * Component tests for MemberTemplateManager (analytics/MemberTemplateManager.tsx).
 *
 * Verifies task 2.5 (R2, pivot-output-actions): the stored-template management surface —
 *   - lists the tenant's templates (CRUD list), with an empty state;
 *   - creates a template from a name + a usable NL/EN language (Save gated on a usable language);
 *   - edits an existing template (fetched by id so the body loads), and deletes one;
 *   - uploads a local file into the active language's body textarea (no server round-trip);
 *   - improves the active language with AI — only for a SAVED template, replacing the editor's
 *     subject/body on success and keeping the text on a fail-closed/degraded result;
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
import MemberTemplateManager from './MemberTemplateManager';
import { MemberTemplateManager as FromBarrel } from './index';
import type { MemberTemplateManagerProps } from './MemberTemplateManager';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';

const TPL: MemberTemplateDto = {
  template_id: 'tpl-1',
  name: 'Welcome',
  languages: {
    nl: { subject: 'NL onderwerp', body_html: 'NL body {{first_name}}' },
    en: { subject: 'EN subject', body_html: 'EN body {{first_name}}' },
  },
  merge_fields: ['first_name'],
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
let aiImprove: ReturnType<typeof vi.fn>;

function makeProps(
  overrides: Partial<MemberTemplateManagerProps> = {},
): MemberTemplateManagerProps {
  return {
    isOpen: true,
    onClose: vi.fn(),
    language: 'en',
    onTemplatesChanged: vi.fn(),
    listTemplates: listTemplates as unknown as MemberTemplateManagerProps['listTemplates'],
    getTemplate: getTemplate as unknown as MemberTemplateManagerProps['getTemplate'],
    createTemplate: createTemplate as unknown as MemberTemplateManagerProps['createTemplate'],
    updateTemplate: updateTemplate as unknown as MemberTemplateManagerProps['updateTemplate'],
    deleteTemplate: deleteTemplate as unknown as MemberTemplateManagerProps['deleteTemplate'],
    aiImprove: aiImprove as unknown as MemberTemplateManagerProps['aiImprove'],
    ...overrides,
  };
}

beforeEach(() => {
  toastSpy.mockReset();
  listTemplates = vi.fn().mockResolvedValue({ ok: true, data: [] });
  getTemplate = vi.fn().mockResolvedValue({ ok: true, data: TPL });
  createTemplate = vi.fn().mockResolvedValue({ ok: true, data: { ...TPL, template_id: 'new-1' } });
  updateTemplate = vi.fn().mockResolvedValue({ ok: true, data: TPL });
  deleteTemplate = vi.fn().mockResolvedValue({ ok: true, data: TPL });
  aiImprove = vi.fn().mockResolvedValue({
    ok: true,
    data: { lang: 'en', subject: 'Improved subject', body_html: 'Improved body', model_used: 'x:free' },
  });
});

describe('MemberTemplateManager', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberTemplateManager);
  });

  it('shows the empty state when the tenant has no templates', async () => {
    render(<MemberTemplateManager {...makeProps()} />);
    expect(await screen.findByTestId('member-template-empty')).toBeInTheDocument();
    expect(listTemplates).toHaveBeenCalledTimes(1);
  });

  it('lists stored templates with edit + delete actions', async () => {
    listTemplates.mockResolvedValue({ ok: true, data: [TPL] });
    render(<MemberTemplateManager {...makeProps()} />);
    expect(await screen.findByTestId('member-template-list')).toBeInTheDocument();
    expect(screen.getByText('Welcome')).toBeInTheDocument();
    expect(screen.getByTestId('member-template-edit-tpl-1')).toBeInTheDocument();
    expect(screen.getByTestId('member-template-delete-tpl-1')).toBeInTheDocument();
  });

  it('gates Save until a name + a usable language are present, then creates', async () => {
    render(<MemberTemplateManager {...makeProps()} />);
    await screen.findByTestId('member-template-editor');

    const save = screen.getByTestId('member-template-save');
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByTestId('member-template-name'), {
      target: { value: 'Monthly' },
    });
    // A name alone is not enough — a language needs subject + body.
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByTestId('member-template-subject'), {
      target: { value: 'Hi' },
    });
    fireEvent.change(screen.getByTestId('member-template-body'), {
      target: { value: 'Body {{first_name}}' },
    });
    expect(save).not.toBeDisabled();

    fireEvent.click(save);
    await waitFor(() => expect(createTemplate).toHaveBeenCalledTimes(1));
    const input = createTemplate.mock.calls[0][0];
    expect(input.name).toBe('Monthly');
    // The active language is 'en' (prop), so the body lands under en.
    expect(input.languages.en).toEqual({ subject: 'Hi', body_html: 'Body {{first_name}}' });
  });

  it('fetches a template by id when editing (so the body loads) and updates it', async () => {
    listTemplates.mockResolvedValue({ ok: true, data: [TPL] });
    render(<MemberTemplateManager {...makeProps()} />);
    fireEvent.click(await screen.findByTestId('member-template-edit-tpl-1'));

    await waitFor(() => expect(getTemplate).toHaveBeenCalledWith('tpl-1'));
    const name = screen.getByTestId('member-template-name') as HTMLInputElement;
    await waitFor(() => expect(name.value).toBe('Welcome'));
    // Active language en → en subject/body shown.
    expect((screen.getByTestId('member-template-subject') as HTMLInputElement).value).toBe(
      'EN subject',
    );

    fireEvent.change(name, { target: { value: 'Welcome v2' } });
    fireEvent.click(screen.getByTestId('member-template-save'));
    await waitFor(() => expect(updateTemplate).toHaveBeenCalledTimes(1));
    expect(updateTemplate.mock.calls[0][0]).toBe('tpl-1');
    expect(updateTemplate.mock.calls[0][1].name).toBe('Welcome v2');
  });

  it('deletes a template', async () => {
    listTemplates.mockResolvedValue({ ok: true, data: [TPL] });
    render(<MemberTemplateManager {...makeProps()} />);
    fireEvent.click(await screen.findByTestId('member-template-delete-tpl-1'));
    await waitFor(() => expect(deleteTemplate).toHaveBeenCalledWith('tpl-1'));
  });

  it('uploads a local file into the active language body textarea', async () => {
    render(<MemberTemplateManager {...makeProps()} />);
    await screen.findByTestId('member-template-editor');

    const file = new File(['<p>Uploaded {{first_name}}</p>'], 'body.html', {
      type: 'text/html',
    });
    // jsdom File#text() resolves the content.
    const input = screen.getByTestId('member-template-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    const body = screen.getByTestId('member-template-body') as HTMLTextAreaElement;
    await waitFor(() => expect(body.value).toBe('<p>Uploaded {{first_name}}</p>'));
  });

  describe('improve with AI (R2)', () => {
    it('is disabled with a hint for an unsaved draft', async () => {
      render(<MemberTemplateManager {...makeProps()} />);
      await screen.findByTestId('member-template-editor');
      expect(screen.getByTestId('member-template-improve')).toBeDisabled();
      expect(screen.getByTestId('member-template-improve-hint')).toBeInTheDocument();
    });

    it('improves the active language of a saved template and replaces the editor fields', async () => {
      listTemplates.mockResolvedValue({ ok: true, data: [TPL] });
      render(<MemberTemplateManager {...makeProps()} />);
      // Edit (so there is a saved template id) → improve becomes available with an instruction.
      fireEvent.click(await screen.findByTestId('member-template-edit-tpl-1'));
      await waitFor(() => expect(getTemplate).toHaveBeenCalledWith('tpl-1'));

      fireEvent.change(screen.getByTestId('member-template-instruction'), {
        target: { value: 'make it warmer' },
      });
      const improve = screen.getByTestId('member-template-improve');
      expect(improve).not.toBeDisabled();

      fireEvent.click(improve);
      await waitFor(() => expect(aiImprove).toHaveBeenCalledTimes(1));
      expect(aiImprove.mock.calls[0][0]).toBe('tpl-1');
      expect(aiImprove.mock.calls[0][1]).toEqual({ lang: 'en', instruction: 'make it warmer' });

      // The improved subject/body replace the editor fields.
      await waitFor(() =>
        expect((screen.getByTestId('member-template-subject') as HTMLInputElement).value).toBe(
          'Improved subject',
        ),
      );
      expect((screen.getByTestId('member-template-body') as HTMLTextAreaElement).value).toBe(
        'Improved body',
      );
    });

    it('keeps the text on a fail-closed/degraded AI result (no crash)', async () => {
      listTemplates.mockResolvedValue({ ok: true, data: [TPL] });
      aiImprove.mockResolvedValue({
        ok: false,
        status: 422,
        error: 'model not allowed',
        code: 'errors.template.aiModelDisallowed',
      });
      render(<MemberTemplateManager {...makeProps()} />);
      fireEvent.click(await screen.findByTestId('member-template-edit-tpl-1'));
      await waitFor(() => expect(getTemplate).toHaveBeenCalledWith('tpl-1'));

      const subjectBefore = (screen.getByTestId('member-template-subject') as HTMLInputElement)
        .value;
      fireEvent.change(screen.getByTestId('member-template-instruction'), {
        target: { value: 'rewrite' },
      });
      fireEvent.click(screen.getByTestId('member-template-improve'));

      await waitFor(() => expect(aiImprove).toHaveBeenCalledTimes(1));
      // The subject is unchanged — the user keeps the un-improved template (design §9).
      expect((screen.getByTestId('member-template-subject') as HTMLInputElement).value).toBe(
        subjectBefore,
      );
      await waitFor(() =>
        expect(toastSpy).toHaveBeenCalledWith(
          expect.objectContaining({ title: 'analytics.mail.templates.improveError' }),
        ),
      );
    });
  });
});
