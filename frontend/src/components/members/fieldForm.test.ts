/**
 * Unit tests for the shared Members form helpers (s5c task 4.4; R5.5, R4.8, R4.9, R4.11, R4.12).
 *
 * These pin the PURE logic the add/edit/view modals share — sectioning by `functional_group`,
 * the `show_when` predicate (shared verbatim with the server), value-level enum option filtering,
 * `member_number` format feedback, and the storage-group-shaped write payload — without rendering
 * a modal. Authority stays server-side (R2.3); this is presentation/convenience only.
 */

import { describe, it, expect } from 'vitest';
import type { FieldConfigField, FunctionalGroup } from '../../types/members';
import {
  evaluateShowWhen,
  optionsForCaller,
  memberNumberError,
  groupFieldsBySection,
  formFields,
  isEditableField,
  isMembershipTypeField,
  membershipTypeOptions,
  DEFAULT_SECTION_KEY,
} from './fieldForm';
import { buildInitialValues, buildValidationSchema, shapeWritePayload } from './fieldFormModel';

const t = (k: string) => k;

describe('evaluateShowWhen (R4.12) — shared verbatim with the server', () => {
  it('always shows a field with no condition', () => {
    expect(evaluateShowWhen(null, {})).toBe(true);
    expect(evaluateShowWhen({}, { x: 1 })).toBe(true);
  });

  it('matches a scalar condition', () => {
    expect(evaluateShowWhen({ membership_type: 'motor' }, { membership_type: 'motor' })).toBe(true);
    expect(evaluateShowWhen({ membership_type: 'motor' }, { membership_type: 'family' })).toBe(false);
  });

  it('matches a list condition (one-of)', () => {
    expect(evaluateShowWhen({ membership_type: ['motor', 'sport'] }, { membership_type: 'sport' })).toBe(true);
    expect(evaluateShowWhen({ membership_type: ['motor'] }, { membership_type: 'family' })).toBe(false);
  });

  it('requires ALL conditions to hold (implicit AND)', () => {
    const values = { membership_type: 'motor', active: 'yes' };
    expect(evaluateShowWhen({ membership_type: 'motor', active: 'yes' }, values)).toBe(true);
    expect(evaluateShowWhen({ membership_type: 'motor', active: 'no' }, values)).toBe(false);
  });

  it('resolves a dotted controlling key to its bare tail', () => {
    expect(evaluateShowWhen({ 'membership.membership_type': 'motor' }, { membership_type: 'motor' })).toBe(true);
  });
});

describe('optionsForCaller (R4.12) — value-level role filtering', () => {
  const options = [
    { value: 'standard', label: { nl: 'Standaard' } },
    { value: 'premium', label: { nl: 'Premium' }, roles: ['Members_CRUD'] },
  ];

  it('keeps open (unrestricted) options for any caller', () => {
    expect(optionsForCaller(options, []).map((o) => o.value)).toContain('standard');
  });

  it('drops a role-restricted option for a caller lacking the role', () => {
    expect(optionsForCaller(options, ['Members_Read']).map((o) => o.value)).toEqual(['standard']);
  });

  it('keeps a role-restricted option for a caller holding the role', () => {
    expect(optionsForCaller(options, ['Members_CRUD']).map((o) => o.value)).toEqual([
      'standard',
      'premium',
    ]);
  });
});

describe('memberNumberError (R4.8) — immediate tenant-format feedback', () => {
  const field: FieldConfigField = {
    key: 'member_number',
    member_number_format: { prefix: 'Nr-', width: 4, regex: '^Nr\\-\\d{4}$', example: 'Nr-0001' },
  };

  it('returns null for a value matching the format', () => {
    expect(memberNumberError(field, 'Nr-0042', 'bad')).toBeNull();
  });

  it('returns the hint for a malformed value', () => {
    expect(memberNumberError(field, 'BAD1', 'bad')).toBe('bad');
  });

  it('does not complain about a blank value (required-ness handles emptiness)', () => {
    expect(memberNumberError(field, '', 'bad')).toBeNull();
  });

  it('is a no-op when the field has no format', () => {
    expect(memberNumberError({ key: 'member_number' }, 'anything', 'bad')).toBeNull();
  });
});

describe('groupFieldsBySection (R4.9) — sectioning by functional_group', () => {
  const catalog: FunctionalGroup[] = [
    { key: 'personal', label: { nl: 'Persoonlijk' }, order: 1 },
    { key: 'address', label: { nl: 'Adres' }, order: 2 },
  ];
  const fields: FieldConfigField[] = [
    { key: 'first_name', functional_group: 'personal', order: 10 },
    { key: 'street', functional_group: 'address', order: 20 },
    { key: 'orphan', functional_group: 'nonexistent', order: 30 },
    { key: 'ungrouped', order: 40 },
  ];

  it('buckets fields into catalog sections in catalog order', () => {
    const sections = groupFieldsBySection(fields, catalog);
    expect(sections[0].key).toBe('personal');
    expect(sections[1].key).toBe('address');
  });

  it('falls back a dangling/absent group into a single default section, appended last', () => {
    const sections = groupFieldsBySection(fields, catalog);
    const fallback = sections[sections.length - 1];
    expect(fallback.key).toBe(DEFAULT_SECTION_KEY);
    expect(fallback.fields.map((f) => f.key).sort()).toEqual(['orphan', 'ungrouped']);
  });
});

describe('formFields — visibility + read-only + system-field rules', () => {
  const fields: FieldConfigField[] = [
    { key: 'first_name', group: 'personal', visible: true, order: 10 },
    { key: 'hidden', group: 'personal', visible: false, order: 20 },
    { key: 'display_name', group: 'personal', origin: 'calculated', read_only: true, order: 30 },
    { key: 'member_id', group: 'membership', order: 40 },
  ];

  it('excludes not-visible + system fields, but KEEPS read-only fields (rendered disabled)', () => {
    const keys = formFields({ fields } as never).map((f) => f.key);
    expect(keys).toContain('first_name');
    expect(keys).toContain('display_name'); // read-only: rendered (disabled), schema/payload skip it
    expect(keys).not.toContain('hidden');    // visible:false → excluded
    expect(keys).not.toContain('member_id'); // system field → handled separately
  });

  it('isEditableField flags calculated/read-only as not editable', () => {
    expect(isEditableField({ key: 'x', origin: 'calculated' })).toBe(false);
    expect(isEditableField({ key: 'y', read_only: true })).toBe(false);
    expect(isEditableField({ key: 'z' })).toBe(true);
  });
});

describe('shapeWritePayload — nested body by storage group (Property 2, R4.12)', () => {
  const fields: FieldConfigField[] = [
    { key: 'first_name', group: 'personal', order: 10 },
    { key: 'email', group: 'personal', order: 20 },
    { key: 'membership_type', group: 'membership', order: 30 },
    { key: 'tier', group: 'overlay', order: 40 },
    { key: 'motor_brand', group: 'overlay', show_when: { membership_type: ['motor'] }, order: 50 },
    { key: 'region', group: 'membership', order: 60 },
  ];

  it('shapes fields into personal/membership/overlay + scope_values, dropping blanks + tenant', () => {
    const values = {
      first_name: 'Sam', email: 'sam@x.nl', membership_type: 'gewoon', tier: 'standard',
      motor_brand: '', region: 'Noord',
    };
    const body = shapeWritePayload(fields, values, { dimensionKey: 'region' });
    expect(body).toEqual({
      personal: { first_name: 'Sam', email: 'sam@x.nl' },
      membership: { membership_type: 'gewoon' },
      overlay: { tier: 'standard' },
      scope_values: { region: ['Noord'] },
    });
    expect(body).not.toHaveProperty('tenant_id');
  });

  it('does NOT send a field hidden by an unmet show_when (hidden-not-sent, R4.12)', () => {
    const values = {
      first_name: 'Sam', email: 'sam@x.nl', membership_type: 'gewoon',
      motor_brand: 'Honda', region: 'Noord', tier: '',
    };
    const body = shapeWritePayload(fields, values, { dimensionKey: 'region' }) as {
      overlay?: Record<string, unknown>;
    };
    // membership_type is "gewoon" → motor_brand is hidden → not sent even though it has a value.
    expect(body.overlay).toBeUndefined();
  });

  it('sends a show_when field when its condition holds', () => {
    const values = {
      first_name: 'Sam', email: 'sam@x.nl', membership_type: 'motor',
      motor_brand: 'Honda', region: 'Noord', tier: '',
    };
    const body = shapeWritePayload(fields, values, { dimensionKey: 'region' }) as {
      overlay?: Record<string, unknown>;
    };
    expect(body.overlay).toEqual({ motor_brand: 'Honda' });
  });
});

describe('buildInitialValues + buildValidationSchema — show_when-aware required', () => {
  const fields: FieldConfigField[] = [
    { key: 'first_name', group: 'personal', required: true, order: 10 },
    { key: 'motor_brand', group: 'overlay', required: true, show_when: { membership_type: ['motor'] }, order: 20 },
    { key: 'membership_type', group: 'membership', required: true, order: 30 },
  ];

  it('initial values are blank for a create', () => {
    const init = buildInitialValues(fields, null);
    expect(init.first_name).toBe('');
    expect(init.region).toBe('');
  });

  it('does not require a hidden show_when field, but requires it when shown', async () => {
    const schema = buildValidationSchema(fields, { t, memberNumberError });
    // membership_type "gewoon" → motor_brand hidden → not required.
    await expect(
      schema.validate({ first_name: 'A', membership_type: 'gewoon', motor_brand: '', region: '' }),
    ).resolves.toBeTruthy();
    // membership_type "motor" → motor_brand shown → required (empty fails).
    await expect(
      schema.validate({ first_name: 'A', membership_type: 'motor', motor_brand: '', region: '' }),
    ).rejects.toBeTruthy();
  });
});

describe('membership_type catalog dropdown (R5.8) — active-only, bilingual, domain-validated', () => {
  it('isMembershipTypeField identifies the catalog-backed reference field', () => {
    expect(isMembershipTypeField({ key: 'membership_type', type: 'reference' })).toBe(true);
    expect(isMembershipTypeField({ key: 'status', type: 'enum' })).toBe(false);
  });

  it('membershipTypeOptions maps active catalog entries to {value,label} options', () => {
    const opts = membershipTypeOptions([
      { key: 'erelid', label: { nl: 'Erelid', en: 'Honorary' }, active: true },
      { key: 'donateur', label: { nl: 'Donateur', en: 'Donor' }, active: true },
    ]);
    expect(opts).toEqual([
      { value: 'erelid', label: { nl: 'Erelid', en: 'Honorary' } },
      { value: 'donateur', label: { nl: 'Donateur', en: 'Donor' } },
    ]);
  });

  it('coerces a plain-string label into a {nl,en} bilingual label', () => {
    const opts = membershipTypeOptions([{ key: 'member', label: 'Lid' }]);
    expect(opts).toEqual([{ value: 'member', label: { nl: 'Lid', en: 'Lid' } }]);
  });

  it('drops entries with no usable key and tolerates null/undefined feeds', () => {
    expect(membershipTypeOptions(null)).toEqual([]);
    expect(membershipTypeOptions(undefined)).toEqual([]);
    expect(
      membershipTypeOptions([{ key: '', label: { nl: 'x' } }, { key: 'ok', label: { nl: 'OK' } }]),
    ).toEqual([{ value: 'ok', label: { nl: 'OK' } }]);
  });
});
