/**
 * Tests for the config-driven Yup schema generator of the public member-application form
 * (spec `Members/application-app`, task 9.2; R10a.2 / R4a / R4b / R6.3 / R7).
 *
 * These pin the GENERATED-FROM-CONFIG contract (the server-validation mirror, R2.3) so the schema
 * cannot drift from the renderer:
 *   - application-required → .required(), but a field hidden by show_when is NOT required (R4b.5);
 *   - enum → membership restricted to the exposed application SUBSET (mirrors server R4a.3);
 *   - format EMAIL → email-shape (reuses the canonical regex); format IBAN → mod-97 (valid+invalid);
 *   - show_when → conditional gating matching the server.
 *
 * ## Key shape (task-9.3 consolidation)
 *
 * The schema keys each field — and the flat values it validates — by the field's FULL DOTTED key
 * (e.g. `personal.name`, `membership.membership_type`). This is the canonical Formik key the
 * renderer holds, the submit shape (`{ dotted_key: value }`, design §3.2), and the key the server's
 * 422 `errors[].field` carries (R10a.3). Task 9.3 consolidated the field-config contract onto ONE
 * shared type (`components/public/application/applicationFieldConfig`) keyed by the dotted key, so
 * renderer + schema + submit share one key shape. These tests therefore drive dotted-keyed values.
 */

import { describe, it, expect } from 'vitest';
import * as Yup from 'yup';

import type { ApplicationField } from '../components/public/application/applicationFieldConfig';
import {
  buildApplicationValidationSchema,
  isFieldShown,
  cleanErrorPath,
  validateApplication,
} from '../components/members/application/applicationFormSchema';

/** Assert a Yup object schema accepts the given flat values (no error keys produced). */
async function expectValid(
  schema: Yup.ObjectSchema<Record<string, unknown>>,
  values: Record<string, unknown>,
): Promise<void> {
  const errors = await validateApplication(schema, values);
  expect(errors).toEqual({});
}

/**
 * Assert a schema REJECTS the values, returning the failing DOTTED field keys. Uses
 * `validateApplication` so the returned keys are the PLAIN dotted keys (R10a.3) — the same keys the
 * renderer + server 422 use — not Yup's escaped `["a.b"]` path form.
 */
async function expectInvalid(
  schema: Yup.ObjectSchema<Record<string, unknown>>,
  values: Record<string, unknown>,
): Promise<string[]> {
  const errors = await validateApplication(schema, values);
  const keys = Object.keys(errors);
  if (keys.length === 0) throw new Error('expected validation to fail, but it passed');
  return keys;
}

describe('buildApplicationValidationSchema — required (R4b)', () => {
  it('requires an application-required field and accepts it when present', async () => {
    const fields: ApplicationField[] = [
      { key: 'personal.name', type: 'text', required: true },
    ];
    const schema = buildApplicationValidationSchema(fields);

    expect(await expectInvalid(schema, { 'personal.name': '' })).toContain('personal.name');
    // blank-only is absent
    expect(await expectInvalid(schema, { 'personal.name': '   ' })).toContain('personal.name');
    await expectValid(schema, { 'personal.name': 'Ada Lovelace' });
  });

  it('treats a non-required field as optional (blank accepted)', async () => {
    const fields: ApplicationField[] = [
      { key: 'personal.tussenvoegsel', type: 'text', required: false },
    ];
    const schema = buildApplicationValidationSchema(fields);
    await expectValid(schema, { 'personal.tussenvoegsel': '' });
    await expectValid(schema, { 'personal.tussenvoegsel': 'van der' });
  });

  it('does NOT require an application-required field hidden by show_when (R4b.5)', async () => {
    // iban is required ONLY when payment_method === 'incasso'; hidden otherwise.
    const fields: ApplicationField[] = [
      {
        key: 'financial.iban',
        type: 'text',
        required: true,
        show_when: { 'financial.payment_method': 'incasso' },
      },
    ];
    const schema = buildApplicationValidationSchema(fields);

    // Hidden (payment_method is not incasso) → blank iban is fine.
    await expectValid(schema, { 'financial.payment_method': 'invoice', 'financial.iban': '' });
    // Shown (incasso) → blank iban is rejected.
    expect(
      await expectInvalid(schema, { 'financial.payment_method': 'incasso', 'financial.iban': '' }),
    ).toContain('financial.iban');
  });
});

describe('buildApplicationValidationSchema — enum subset (R4a → membership)', () => {
  const fields: ApplicationField[] = [
    {
      key: 'membership.membership_type',
      type: 'enum',
      required: true,
      // Exposed public-safe SUBSET only (server already filtered staff-only types out, R4a.2).
      options: ['regular', 'student'],
    },
  ];
  const schema = buildApplicationValidationSchema(fields);

  it('accepts a value within the application subset', async () => {
    await expectValid(schema, { 'membership.membership_type': 'regular' });
    await expectValid(schema, { 'membership.membership_type': 'student' });
  });

  it('rejects a value outside the subset even if it would be a staff-valid choice (R4a.3)', async () => {
    expect(await expectInvalid(schema, { 'membership.membership_type': 'honorary' })).toContain(
      'membership.membership_type',
    );
  });

  it('supports rich { value, label } choice entries', async () => {
    const richSchema = buildApplicationValidationSchema([
      {
        key: 'membership.membership_type',
        type: 'enum',
        options: [
          { value: 'regular', label: { nl: 'Gewoon', en: 'Regular' } },
          { value: 'student', label: { nl: 'Student', en: 'Student' } },
        ],
      },
    ]);
    await expectValid(richSchema, { 'membership.membership_type': 'regular' });
    expect(await expectInvalid(richSchema, { 'membership.membership_type': 'honorary' })).toContain(
      'membership.membership_type',
    );
  });
});

describe('buildApplicationValidationSchema — format EMAIL (R7.6)', () => {
  const schema = buildApplicationValidationSchema([
    { key: 'personal.email', type: 'email', required: true, format: { checker: 'EMAIL' } },
  ]);

  it('accepts a well-formed email', async () => {
    await expectValid(schema, { 'personal.email': 'applicant@example.com' });
  });

  it('rejects a malformed email', async () => {
    expect(await expectInvalid(schema, { 'personal.email': 'not-an-email' })).toContain(
      'personal.email',
    );
    expect(await expectInvalid(schema, { 'personal.email': 'user@domain' })).toContain(
      'personal.email',
    );
  });
});

describe('buildApplicationValidationSchema — format IBAN (R6.2 mod-97)', () => {
  // IBAN is required only when incasso is chosen (conditional, R6.3).
  const schema = buildApplicationValidationSchema([
    {
      key: 'financial.iban',
      type: 'text',
      required: true,
      format: { checker: 'IBAN' },
      show_when: { 'financial.payment_method': 'incasso' },
    },
  ]);

  it('accepts a checksum-valid IBAN when incasso is shown', async () => {
    await expectValid(schema, {
      'financial.payment_method': 'incasso',
      'financial.iban': 'NL91 ABNA 0417 1643 00',
    });
    await expectValid(schema, {
      'financial.payment_method': 'incasso',
      'financial.iban': 'GB82WEST12345698765432',
    });
  });

  it('rejects a checksum-invalid IBAN', async () => {
    expect(
      await expectInvalid(schema, {
        'financial.payment_method': 'incasso',
        'financial.iban': 'NL00 ABNA 0417 1643 00',
      }),
    ).toContain('financial.iban');
    expect(
      await expectInvalid(schema, {
        'financial.payment_method': 'incasso',
        'financial.iban': 'ZZ00NOTANIBAN',
      }),
    ).toContain('financial.iban');
  });

  it('neither requires nor format-checks IBAN when incasso is NOT shown (R6.3)', async () => {
    // Hidden → an absent/garbage iban is tolerated (the field is not shown).
    await expectValid(schema, { 'financial.payment_method': 'invoice', 'financial.iban': '' });
    await expectValid(schema, { 'financial.payment_method': 'invoice' });
  });
});

describe('isFieldShown — show_when predicate parity (R6.3)', () => {
  it('is always shown when show_when is absent/empty', () => {
    expect(isFieldShown(undefined, {})).toBe(true);
    expect(isFieldShown(null, {})).toBe(true);
    expect(isFieldShown({}, {})).toBe(true);
  });

  it('matches a scalar equality condition', () => {
    expect(isFieldShown({ payment_method: 'incasso' }, { payment_method: 'incasso' })).toBe(true);
    expect(isFieldShown({ payment_method: 'incasso' }, { payment_method: 'invoice' })).toBe(false);
  });

  it('matches an array (membership) condition', () => {
    const cond = { payment_method: ['incasso', 'sepa'] };
    expect(isFieldShown(cond, { payment_method: 'sepa' })).toBe(true);
    expect(isFieldShown(cond, { payment_method: 'cash' })).toBe(false);
  });

  it('ANDs multiple conditions', () => {
    const cond = { payment_method: 'incasso', country: 'NL' };
    expect(isFieldShown(cond, { payment_method: 'incasso', country: 'NL' })).toBe(true);
    expect(isFieldShown(cond, { payment_method: 'incasso', country: 'BE' })).toBe(false);
  });

  it('resolves a dotted controlling key by its bare tail', () => {
    expect(
      isFieldShown({ 'financial.payment_method': 'incasso' }, { payment_method: 'incasso' }),
    ).toBe(true);
  });

  it('resolves a dotted controlling key against a dotted value (renderer/submit shape)', () => {
    expect(
      isFieldShown(
        { 'financial.payment_method': 'incasso' },
        { 'financial.payment_method': 'incasso' },
      ),
    ).toBe(true);
  });

  it('resolves a bare controlling key against a dotted value by its tail', () => {
    expect(
      isFieldShown({ payment_method: 'incasso' }, { 'financial.payment_method': 'incasso' }),
    ).toBe(true);
  });
});

describe('buildApplicationValidationSchema — generated-from-config, not hand-maintained (R10a.2)', () => {
  it('produces schema keys that exactly track the config fields by DOTTED key (zero per-tenant code)', () => {
    const schema = buildApplicationValidationSchema([
      { key: 'personal.email', type: 'email', format: { checker: 'EMAIL' } },
      { key: 'membership.membership_type', type: 'enum', options: ['regular'] },
    ]);
    expect(Object.keys(schema.fields).sort()).toEqual([
      'membership.membership_type',
      'personal.email',
    ]);
  });

  it('ignores an unknown/malformed format token (degrades to no extra checker, R7.3)', async () => {
    const schema = buildApplicationValidationSchema([
      { key: 'personal.nickname', type: 'text', format: { checker: 'WAT' } },
    ]);
    // No checker applied → any non-blank string is accepted.
    await expect(
      schema.validate({ 'personal.nickname': 'anything at all' }),
    ).resolves.toBeDefined();
  });
});

describe('validateApplication — clean dotted error keys (R10a.3)', () => {
  it('cleanErrorPath unwraps Yup\'s escaped dotted path and passes a plain key through', () => {
    expect(cleanErrorPath('["personal.name"]')).toBe('personal.name');
    expect(cleanErrorPath('plainkey')).toBe('plainkey');
    expect(cleanErrorPath(undefined)).toBe('');
  });

  it('returns errors keyed by the PLAIN dotted key (not Yup\'s bracket form)', async () => {
    const schema = buildApplicationValidationSchema([
      { key: 'personal.email', type: 'email', required: true, format: { checker: 'EMAIL' } },
    ]);
    const errors = await validateApplication(schema, { 'personal.email': 'not-an-email' });
    // The key is exactly the dotted field key the server 422 + renderer use.
    expect(Object.keys(errors)).toEqual(['personal.email']);
  });

  it('collects every failing field at once (R6.5)', async () => {
    const schema = buildApplicationValidationSchema([
      { key: 'personal.first_name', type: 'text', required: true },
      { key: 'personal.email', type: 'email', required: true, format: { checker: 'EMAIL' } },
    ]);
    const errors = await validateApplication(schema, {
      'personal.first_name': '',
      'personal.email': 'bad',
    });
    expect(Object.keys(errors).sort()).toEqual(['personal.email', 'personal.first_name']);
  });

  it('returns an empty map when everything is valid', async () => {
    const schema = buildApplicationValidationSchema([
      { key: 'personal.first_name', type: 'text', required: true },
    ]);
    expect(await validateApplication(schema, { 'personal.first_name': 'Ada' })).toEqual({});
  });
});
