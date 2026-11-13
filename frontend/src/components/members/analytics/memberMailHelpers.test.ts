/**
 * Focused unit tests for memberMailHelpers.ts - the pure recipient / template-seed /
 * merge-preview / sanitize transforms behind MemberMailCompose. No React, no network.
 */

import { describe, it, expect } from 'vitest';
import {
  isValidEmail,
  parseExternalRecipients,
  resolveTemplateSeed,
  flattenRowMergeValues,
  renderMergePreview,
  sanitizeMailHtml,
} from './memberMailHelpers';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';

const AT = String.fromCharCode(64);
const mail = (local: string, domain: string) => `${local}${AT}${domain}`;

const dto = (languages: MemberTemplateDto['languages']): MemberTemplateDto => ({
  template_id: 't',
  name: 'T',
  languages,
  merge_fields: [],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'u',
  created_at: '',
  updated_at: '',
});

describe('isValidEmail', () => {
  it('accepts a simple dotted-domain address, trimming whitespace', () => {
    expect(isValidEmail(mail('a', 'b.com'))).toBe(true);
    expect(isValidEmail(`  ${mail('a', 'b.com')}  `)).toBe(true);
  });

  it('rejects addresses without @, without a dotted domain, or with whitespace', () => {
    expect(isValidEmail('nodomain')).toBe(false);
    expect(isValidEmail(mail('a', 'localhost'))).toBe(false);
    expect(isValidEmail('a b' + AT + 'c.com')).toBe(false);
    expect(isValidEmail('')).toBe(false);
  });
});

describe('parseExternalRecipients', () => {
  it('splits on comma, semicolon and whitespace, dropping blanks', () => {
    const raw = ` a${AT}b.com , c${AT}d.com;  e${AT}f.com
`;
    expect(parseExternalRecipients(raw)).toEqual([
      mail('a', 'b.com'),
      mail('c', 'd.com'),
      mail('e', 'f.com'),
    ]);
  });

  it('returns [] for blank input and preserves order without de-duping', () => {
    expect(parseExternalRecipients('   ')).toEqual([]);
    expect(parseExternalRecipients('x x')).toEqual(['x', 'x']);
  });
});

describe('resolveTemplateSeed', () => {
  it('prefers the active language', () => {
    const t = dto({ nl: { subject: 'NL' }, en: { subject: 'EN' } });
    expect(resolveTemplateSeed(t, 'en')).toEqual({ subject: 'EN', body: '' });
  });

  it('falls back nl then en then any other language', () => {
    const both = dto({ nl: { subject: 'NL' }, en: { subject: 'EN' } });
    expect(resolveTemplateSeed(both, 'de')).toEqual({ subject: 'NL', body: '' });
    expect(resolveTemplateSeed(dto({ en: { subject: 'EN' } }), 'nl')).toEqual({
      subject: 'EN',
      body: '',
    });
    expect(resolveTemplateSeed(dto({ fr: { subject: 'FR' } }), 'de')).toEqual({
      subject: 'FR',
      body: '',
    });
  });

  it('carries the resolved body_html when present', () => {
    const t = dto({ nl: { subject: 'NL', body_html: '<p>hoi</p>' } });
    expect(resolveTemplateSeed(t, 'nl')).toEqual({ subject: 'NL', body: '<p>hoi</p>' });
  });

  it('skips blank variants and returns null when nothing usable exists', () => {
    expect(resolveTemplateSeed(dto({ nl: { subject: '   ', body_html: '  ' } }), 'nl')).toBeNull();
    expect(resolveTemplateSeed(dto({}), 'nl')).toBeNull();
  });
});

describe('flattenRowMergeValues', () => {
  it('returns {} for null/undefined rows', () => {
    expect(flattenRowMergeValues(null)).toEqual({});
    expect(flattenRowMergeValues(undefined)).toEqual({});
  });

  it('keeps flat scalars and stringifies them', () => {
    expect(flattenRowMergeValues({ a: 'x', n: 3, b: true })).toEqual({
      a: 'x',
      n: '3',
      b: 'true',
    });
  });

  it('adds dotted AND bare leaves for one level of nested mapping', () => {
    expect(flattenRowMergeValues({ personal: { last_name: 'Jansen', age: 30 } })).toEqual({
      'personal.last_name': 'Jansen',
      last_name: 'Jansen',
      'personal.age': '30',
      age: '30',
    });
  });

  it('stringifies a top-level array and skips nested non-leaf objects', () => {
    expect(flattenRowMergeValues({ tags: ['a'], deep: { inner: { x: 1 } } })).toEqual({
      tags: 'a',
    });
  });

  it('skips a null leaf inside a nested mapping', () => {
    expect(flattenRowMergeValues({ g: { x: null } })).toEqual({});
  });
});

describe('renderMergePreview', () => {
  it('substitutes placeholders (optional inner spaces) and blanks missing keys', () => {
    expect(renderMergePreview('Hi {{name}}!', { name: 'Ada' })).toBe('Hi Ada!');
    expect(renderMergePreview('{{  name  }}', { name: 'Ada' })).toBe('Ada');
    expect(renderMergePreview('Hi {{missing}}!', {})).toBe('Hi !');
  });

  it('handles null/undefined text safely', () => {
    expect(renderMergePreview(null as unknown as string, {})).toBe('');
    expect(renderMergePreview(undefined as unknown as string, {})).toBe('');
  });
});

describe('sanitizeMailHtml', () => {
  it('strips script content while preserving harmless markup', () => {
    const out = sanitizeMailHtml('<b>hi</b><script>alert(1)</script>');
    expect(out).toContain('<b>hi</b>');
    expect(out.toLowerCase()).not.toContain('<script');
  });

  it('collapses null/undefined to an empty string', () => {
    expect(sanitizeMailHtml(null)).toBe('');
    expect(sanitizeMailHtml(undefined)).toBe('');
  });
});
