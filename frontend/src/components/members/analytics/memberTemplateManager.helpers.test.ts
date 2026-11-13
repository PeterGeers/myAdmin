/**
 * Focused unit tests for the MemberTemplateManager draft helpers
 * (memberTemplateManager.helpers.ts) - the pure DTO/draft/request-body transforms.
 * No React, no network, no mocks.
 */

import { describe, it, expect } from 'vitest';
import {
  LANGS,
  emptyDraft,
  templateKind,
  draftFromTemplate,
  draftToInput,
  type DraftState,
} from './memberTemplateManager.helpers';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';

const dto = (over: Partial<MemberTemplateDto> = {}): MemberTemplateDto => ({
  template_id: 't1',
  name: 'Welcome',
  languages: {},
  merge_fields: [],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'u1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...over,
});

describe('memberTemplateManager.helpers', () => {
  it('LANGS is exactly nl, en', () => {
    expect(LANGS).toEqual(['nl', 'en']);
  });

  describe('emptyDraft', () => {
    it('defaults to a blank mail draft with both language slots', () => {
      expect(emptyDraft()).toEqual({
        templateId: null,
        kind: 'mail',
        name: '',
        languages: {
          nl: { subject: '', body_html: '' },
          en: { subject: '', body_html: '' },
        },
        lines: [[]],
      });
    });

    it('carries the requested kind (label seeds one empty starter line)', () => {
      expect(emptyDraft('label').kind).toBe('label');
      expect(emptyDraft('label').lines).toEqual([[]]);
    });
  });

  describe('templateKind', () => {
    it('infers mail when kind is absent, label only for an explicit label kind', () => {
      expect(templateKind(dto())).toBe('mail');
      expect(templateKind(dto({ kind: 'mail' }))).toBe('mail');
      expect(templateKind(dto({ kind: 'label' }))).toBe('label');
    });
  });

  describe('draftFromTemplate', () => {
    it('maps a mail DTO into an editable draft', () => {
      const d = draftFromTemplate(
        dto({ languages: { nl: { subject: 'Hoi', body_html: '<p>NL</p>' } } }),
      );
      expect(d.templateId).toBe('t1');
      expect(d.kind).toBe('mail');
      expect(d.name).toBe('Welcome');
      expect(d.languages.nl).toEqual({ subject: 'Hoi', body_html: '<p>NL</p>' });
      expect(d.languages.en).toEqual({ subject: '', body_html: '' });
    });

    it('clones label lines so editing the draft never mutates the DTO', () => {
      const source = dto({ kind: 'label', lines: [['a']] });
      const d = draftFromTemplate(source);
      d.lines[0].push('b');
      expect(source.lines?.[0]).toEqual(['a']);
      expect(d.lines).toEqual([['a', 'b']]);
    });

    it('seeds exactly one empty line for a label template with no lines', () => {
      expect(draftFromTemplate(dto({ kind: 'label' })).lines).toEqual([[]]);
      expect(draftFromTemplate(dto({ kind: 'label', lines: [] })).lines).toEqual([[]]);
    });
  });

  describe('draftToInput', () => {
    it('sends only non-blank MAIL languages and trims the name', () => {
      const draft: DraftState = {
        ...emptyDraft(),
        name: '  Hello  ',
        languages: {
          nl: { subject: 'Hoi', body_html: '' },
          en: { subject: '', body_html: '   ' },
        },
      };
      expect(draftToInput(draft)).toEqual({
        name: 'Hello',
        languages: { nl: { subject: 'Hoi', body_html: '' } },
      });
    });

    it('omits every language when all are blank', () => {
      expect(draftToInput(emptyDraft())).toEqual({ name: '', languages: {} });
    });

    it('writes a LABEL draft as trimmed name + non-empty lines only (no languages)', () => {
      const draft: DraftState = {
        ...emptyDraft('label'),
        name: ' Labels ',
        lines: [['a'], [], ['b', 'c']],
      };
      expect(draftToInput(draft)).toEqual({
        name: 'Labels',
        kind: 'label',
        lines: [['a'], ['b', 'c']],
      });
    });
  });
});
