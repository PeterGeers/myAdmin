/**
 * Tests for the in-app help URL mapping (helpLinks.ts).
 * Covers nl/en language detection and the url builder branches.
 */

import { describe, it, expect, afterEach } from 'vitest';
import i18n from 'i18next';
import { helpLinks, getDocsLanguage, getHelpUrl } from './helpLinks';

const BASE = import.meta.env.VITE_DOCS_URL || '/docs';
const originalLanguage = i18n.language;
const setLang = (value?: string) => {
  (i18n as unknown as { language?: string }).language = value;
};

afterEach(() => {
  setLang(originalLanguage);
});

describe('helpLinks map', () => {
  it('maps known page types to doc sections (menu -> docs root)', () => {
    expect(helpLinks.banking).toBe('banking/');
    expect(helpLinks['fin-reports']).toBe('reports/');
    expect(helpLinks.menu).toBe('');
  });
});

describe('getDocsLanguage', () => {
  it('maps nl* to nl and everything else to en', () => {
    setLang('nl');
    expect(getDocsLanguage()).toBe('nl');
    setLang('nl-NL');
    expect(getDocsLanguage()).toBe('nl');
    setLang('en');
    expect(getDocsLanguage()).toBe('en');
    setLang('de');
    expect(getDocsLanguage()).toBe('en');
  });

  it('defaults to nl when the i18n language is unset', () => {
    setLang(undefined);
    expect(getDocsLanguage()).toBe('nl');
  });
});

describe('getHelpUrl', () => {
  it('builds a NL url with no language prefix', () => {
    setLang('nl');
    expect(getHelpUrl('banking')).toBe(`${BASE}/banking/`);
  });

  it('builds an EN url with the /en prefix', () => {
    setLang('en');
    expect(getHelpUrl('banking')).toBe(`${BASE}/en/banking/`);
  });

  it('falls back to the docs root for an unknown page', () => {
    setLang('nl');
    expect(getHelpUrl('nope')).toBe(`${BASE}/`);
    setLang('en');
    expect(getHelpUrl('nope')).toBe(`${BASE}/en/`);
  });
});
