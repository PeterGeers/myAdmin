/**
 * Unit tests for the pure Mail-function form helpers (`mailConfigForm.ts`).
 *
 * These moved OUT of the component file so the component exports only a React component (Vite/
 * React Fast Refresh requirement). This locks their behaviour directly, without rendering:
 *  - `toMailConfigBody` shapes the reader-shaped config#mail body (consent_notice omitted unless
 *    well-formed; domain/reply-to omitted when blank);
 *  - `mailConfigToFormValues` flattens the authoritative field-config `mail_config` back onto the
 *    form (incl. the consent_notice.{version,text} round-trip — the reported "consent not shown
 *    after save" symptom).
 */
import { describe, it, expect } from 'vitest';
import {
  INITIAL_VALUES,
  mailConfigToFormValues,
  toMailConfigBody,
  type MailFormValues,
} from '../mailConfigForm';
import type { FieldConfig } from '../../../../types/members';

const form = (over: Partial<MailFormValues> = {}): MailFormValues => ({
  ...INITIAL_VALUES,
  ...over,
});

describe('toMailConfigBody', () => {
  it('always carries mail_enabled / mail_local_part / mail_certified', () => {
    const body = toMailConfigBody(form());
    expect(body).toEqual({
      mail_enabled: false,
      mail_local_part: 'noreply',
      mail_certified: false,
    });
  });

  it('omits mail_domain / mail_reply_to_default when blank', () => {
    const body = toMailConfigBody(form({ mail_domain: '  ', mail_reply_to_default: '' }));
    expect(body).not.toHaveProperty('mail_domain');
    expect(body).not.toHaveProperty('mail_reply_to_default');
  });

  it('includes a well-formed consent_notice (version + >=1 body)', () => {
    const body = toMailConfigBody(
      form({ consent_version: '2026-01', consent_text_nl: 'Tekst', consent_text_en: 'Body' }),
    );
    expect(body.consent_notice).toEqual({
      version: '2026-01',
      text: { nl: 'Tekst', en: 'Body' },
    });
  });

  it('omits a half-authored consent_notice (version but no body)', () => {
    const body = toMailConfigBody(form({ consent_version: '2026-01' }));
    expect(body).not.toHaveProperty('consent_notice');
  });

  it('omits a consent_notice with bodies but no version', () => {
    const body = toMailConfigBody(form({ consent_text_nl: 'Tekst' }));
    expect(body).not.toHaveProperty('consent_notice');
  });
});

describe('mailConfigToFormValues', () => {
  it('yields fail-closed defaults when mail_config is absent', () => {
    expect(mailConfigToFormValues(null)).toEqual(INITIAL_VALUES);
    expect(mailConfigToFormValues({ fields: [] } as unknown as FieldConfig)).toEqual(
      INITIAL_VALUES,
    );
  });

  it('flattens a full mail_config onto the form (reply-to + consent round-trip)', () => {
    const cfg = {
      fields: [],
      mail_config: {
        mail_enabled: true,
        mail_local_part: 'info',
        mail_certified: true,
        mail_domain: 'h-dcn.nl',
        mail_reply_to_default: 'webmaster@h-dcn.nl',
        consent_notice: { version: '2026-01', text: { nl: 'Tekst', en: 'Body' } },
      },
    } as unknown as FieldConfig;
    expect(mailConfigToFormValues(cfg)).toEqual({
      mail_enabled: true,
      mail_local_part: 'info',
      mail_certified: true,
      mail_domain: 'h-dcn.nl',
      mail_reply_to_default: 'webmaster@h-dcn.nl',
      consent_version: '2026-01',
      consent_text_nl: 'Tekst',
      consent_text_en: 'Body',
    });
  });

  it('round-trips consent_notice back onto the flat consent fields (findings: not shown after save)', () => {
    const cfg = {
      fields: [],
      mail_config: {
        mail_enabled: true,
        mail_local_part: 'noreply',
        mail_certified: true,
        consent_notice: { version: '2026-02', text: { nl: 'Alleen NL' } },
      },
    } as unknown as FieldConfig;
    const values = mailConfigToFormValues(cfg);
    expect(values.consent_version).toBe('2026-02');
    expect(values.consent_text_nl).toBe('Alleen NL');
    expect(values.consent_text_en).toBe('');
    // And it survives a save round-trip back to the body shape.
    expect(toMailConfigBody(values).consent_notice).toEqual({
      version: '2026-02',
      text: { nl: 'Alleen NL' },
    });
  });
});
