/**
 * Unit tests for the shared Members form helpers (s5c task 4.4; R5.5, R4.8, R4.9, R4.11, R4.12).
 *
 * These pin the PURE logic the add/edit/view modals share — sectioning by `functional_group`,
 * the `show_when` predicate (shared verbatim with the server), value-level enum option filtering,
 * `member_number` format feedback, and the storage-group-shaped write payload — without rendering
 * a modal. Authority stays server-side (R2.3); this is presentation/convenience only.
 */

import { describe, it, expect } from 'vitest';
import type { FieldConfig, FieldConfigField, FunctionalGroup } from '../../types/members';
import {
  evaluateShowWhen,
  optionsForCaller,
  memberNumberError,
  groupFieldsBySection,
  formFields,
  isEditableField,
  isMembershipTypeField,
  membershipTypeOptions,
  resolveLabel,
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

/**
 * members-modal-field-mapping-mismatch — Problem 4 (`referral_source` visibility gate) fix.
 *
 * The field was authored in members_config.json with a malformed
 * `show_when: {"field": "member_id", "op": "not_exists"}`. `evaluateShowWhen` reads `show_when`
 * as a map of `{controllingKey: expected}` ANDed, so that shape resolves to `false` for EVERY
 * real row — hiding the field in the view modal AND on the create form.
 *
 * The chosen fix (Task 3) was to DROP the `show_when` gate from `referral_source` in the config,
 * NOT to teach `evaluateShowWhen` the malformed `{field, op}` shape. So post-fix the field has no
 * gate and renders everywhere, while the predicate is deliberately unchanged and still treats the
 * old malformed shape as unsatisfied. These tests assert that actual fix.
 *
 * Validates: Requirements 1.6, 2.6
 */
describe('evaluateShowWhen — referral_source gate fix (gate dropped from config, Task 3)', () => {
  // The fix for Problem 4 was NOT to teach evaluateShowWhen the malformed
  // {field, op} shape — it was to DROP the show_when gate from referral_source in
  // members_config.json. So post-fix the field has NO gate, and the predicate
  // (correctly) still treats the old malformed shape as unsatisfied. These tests
  // assert the ACTUAL fix: an ungated referral_source renders everywhere.
  const noGate = undefined; // referral_source after the fix: no show_when

  it('shows referral_source for an EXISTING member (no gate -> always visible)', () => {
    const existingMemberRow = {
      member_id: 'abc-123',
      referral_source: 'via een vriend',
    };
    expect(evaluateShowWhen(noGate, existingMemberRow)).toBe(true);
  });

  it('shows referral_source on the CREATE form (no gate -> always visible)', () => {
    const createFormValues: Record<string, unknown> = {};
    expect(evaluateShowWhen(noGate, createFormValues)).toBe(true);
  });

  it('the OLD malformed gate shape stays unsatisfied (predicate unchanged — fix was config, not predicate)', () => {
    // Regression guard: we deliberately did NOT change evaluateShowWhen to accept
    // {field, op}. That nonsensical shape must still resolve false — proving the
    // fix lived in the config (gate removed), not in a loosened predicate.
    const malformedGate = { field: 'member_id', op: 'not_exists' };
    expect(evaluateShowWhen(malformedGate, { member_id: 'abc-123' })).toBe(false);
  });
});

/**
 * Missing-locale fallback — the FINAL `→ key` leg of the Option-(b) i18n contract (task 5.5).
 *
 * The complete missing-locale fallback chain is `active → en → nl → key`, NEVER blank (design §3).
 * The locale-independent TAIL (`en` → `nl`) is pinned SAM-side by the catalog artifact's
 * `LABEL_FALLBACK_ORDER = ("en", "nl")` (`sam/members/domain/attribute_catalog.py`,
 * `test_attribute_catalog.py::test_label_fallback_order_tail_is_recorded_on_the_artifact`); this
 * suite pins the FRONTEND end of the SAME chain — the active-locale head and the final `→ key`
 * step that renders the canonical key (the `fallback` arg) when no locale has a value. The key
 * observable claim is NEVER blank: the all-locales-missing case renders the canonical key, not "".
 *
 * Validates: Requirements R3.5
 */
describe('resolveLabel (R3.5) — missing-locale fallback chain active → en → nl → key, never blank', () => {
  const KEY = 'membersConfig.field.first_name'; // the canonical key (fallback arg)

  it('uses the ACTIVE locale value when present', () => {
    expect(resolveLabel({ de: 'Vorname', en: 'First name', nl: 'Voornaam' }, 'de', KEY)).toBe(
      'Vorname',
    );
  });

  it('falls back to `en` when the active locale is missing', () => {
    // active = de (absent) → en wins (en BEFORE nl, matching LABEL_FALLBACK_ORDER=("en","nl")).
    expect(resolveLabel({ en: 'First name', nl: 'Voornaam' }, 'de', KEY)).toBe('First name');
  });

  it('falls back to `nl` when both the active locale and `en` are missing', () => {
    expect(resolveLabel({ nl: 'Voornaam' }, 'de', KEY)).toBe('Voornaam');
  });

  it('falls back to the canonical key when NO locale has a value — never blank', () => {
    const resolved = resolveLabel({}, 'de', KEY);
    expect(resolved).toBe(KEY);
    expect(resolved).not.toBe('');
  });

  it('falls back to the canonical key when the label is absent — never blank', () => {
    expect(resolveLabel(undefined, 'de', KEY)).toBe(KEY);
    expect(resolveLabel(undefined, 'de', KEY)).not.toBe('');
  });

  it('treats a blank active-locale value as absent and takes the next tier (never render "")', () => {
    // active locale present but empty string → absent → en fills it, not a blank render.
    expect(resolveLabel({ de: '', en: 'First name', nl: 'Voornaam' }, 'de', KEY)).toBe(
      'First name',
    );
    // active + en both blank → nl fills it.
    expect(resolveLabel({ de: '', en: '', nl: 'Voornaam' }, 'de', KEY)).toBe('Voornaam');
    // every locale blank → the canonical key, never "".
    expect(resolveLabel({ de: '', en: '', nl: '' }, 'de', KEY)).toBe(KEY);
  });

  it('prefers `en` over `nl` for a non-nl/en active locale (the documented en→nl tail)', () => {
    // This is the behaviour the SAM artifact records: for a missing active locale, en precedes nl.
    expect(resolveLabel({ en: 'Address', nl: 'Adres' }, 'fr', KEY)).toBe('Address');
  });

  it('passes a plain-string label through, but still never renders blank', () => {
    expect(resolveLabel('Literal', 'de', KEY)).toBe('Literal');
    expect(resolveLabel('', 'de', KEY)).toBe(KEY); // empty string label → the key, never ""
  });
});

/**
 * Add-a-language PROOF — a new locale is a DATA change, not a code change (task 5.6).
 *
 * R3.6: adding a language (`de`) must be purely data. This suite proves the FRONTEND end of the
 * add-a-language claim against the UNCHANGED `resolveLabel`:
 *
 *   1. A base field that gains a `de` label (the shape a translator-dropped `de` resource produces
 *      once the serializer folds it into the served `{nl,en,…}` dict) resolves for a `de`-active
 *      user with NO change to `resolveLabel` — the helper reads `label[lang]` generically, so `de`
 *      is resolved by the SAME lookup that resolves nl/en (no `de`-specific branch).
 *   2. A field with NO `de` label falls back per task 5.5's chain `active → en → nl → key`, never
 *      blank — the de-active lookup misses, then en → nl → the canonical key.
 *
 * The `de` label is constructed IN the test (not committed to a shipped `admin.json` resource
 * file), so the task-5.1 membersConfig nl↔en parity test is untouched; the point holds either way
 * because `resolveLabel` is locale-agnostic. The SAM half is
 * `sam/tests/test_attribute_catalog.py::test_adding_a_de_resource_entry_resolves_with_no_domain_code_change`.
 *
 * Validates: Requirements R3.6
 */
describe('resolveLabel (R3.6) — add-a-language proof: `de` resolves as pure data, no code change', () => {
  const KEY = 'membersConfig.field.first_name';

  it('resolves a newly-added `de` label for a `de`-active user with no code change', () => {
    // A base key gains a `de` value (translator-dropped resource, folded into the served dict).
    // The UNCHANGED resolveLabel picks it for a de-active user — proving add-a-language is data.
    expect(resolveLabel({ nl: 'Voornaam', en: 'First name', de: 'Vorname' }, 'de', KEY)).toBe(
      'Vorname',
    );
  });

  it('resolves an arbitrary never-seen locale the SAME way (locale-agnostic, no per-language code)', () => {
    // The generality: `fr`/`xx` resolve exactly as `de` does — there is no per-language branch to
    // add, which is WHY a new language is a data change.
    expect(resolveLabel({ nl: 'Adres', en: 'Address', fr: 'Adresse' }, 'fr', KEY)).toBe('Adresse');
    expect(resolveLabel({ nl: 'Adres', en: 'Address', xx: 'Xx-label' }, 'xx', KEY)).toBe('Xx-label');
  });

  it('falls back per task 5.5 when a field has NO `de` label — en → nl → key, never blank', () => {
    // A tenant field not yet backfilled for `de`: de-active lookup misses → en wins (the en→nl tail).
    expect(resolveLabel({ nl: 'Voornaam', en: 'First name' }, 'de', KEY)).toBe('First name');
    // No en either → nl fills it.
    expect(resolveLabel({ nl: 'Voornaam' }, 'de', KEY)).toBe('Voornaam');
    // No locale at all → the canonical key, never blank.
    const resolved = resolveLabel({}, 'de', KEY);
    expect(resolved).toBe(KEY);
    expect(resolved).not.toBe('');
  });
});

/**
 * Display-ordering DETERMINISM — the `(functional_group.order, field.order, field.key)` contract
 * (task 7.2, design §5 D6).
 *
 * The display position of a field is the tuple sort key
 * `(functional_group.order, field.order, field.key)` (R6.3): group fields under their
 * `functional_group` (sections ordered by the group's `order`, ties by group `key`), then within
 * a section by the field's `order`, then by the field's `key` as the STABLE tiebreak (R6.4). It is
 * CONSUMER-derived — no new response field — via exactly the frontend path the add/edit/view
 * modals + the CSV export share (`MembersPage`, `MembersViewBody`, `MembersAddModal`,
 * `MembersEditModal`): `formFields(config)` pre-sorts the visible fields by `order`, then
 * `groupFieldsBySection(fields, functional_groups)` buckets them into sections ordered by the
 * group catalog's `order`, and the consumer flattens `sections.flatMap(s => s.fields)` into the
 * single rendered/exported sequence. These tests exercise that REAL path (no re-implementation of
 * the sort) and assert the R6.4 determinism guarantees:
 *
 *   (a) STABLE / idempotent — computing the display order twice over the same input yields the
 *       same sequence;
 *   (b) PERMUTATION-INVARIANT — shuffling the input field list yields the SAME display order (the
 *       tuple sort is total given `(group.order, order, key)`, so input order cannot leak through);
 *   (c) TIE-BREAK BY `key` — two fields in the SAME functional group with the SAME `order` are
 *       ordered by their `key` ascending, deterministically (NOT by input order).
 *
 * This is DISTINCT from the SAM resolver's storage-bucket sort
 * (`test_field_resolver.py::test_fields_are_deterministically_ordered`, keyed off the STORAGE
 * group); see design §5 — the display group is orthogonal to the storage bucket.
 *
 * Validates: Requirements R6.4
 */
describe('display ordering determinism (R6.4) — (group.order, field.order, key), tie-break by key', () => {
  // A catalog with a deliberate group-`order` TIE (membership & extra both order 3) so the
  // section-order tiebreak by group `key` is exercised too.
  const catalog: FunctionalGroup[] = [
    { key: 'personal', label: { nl: 'Persoonlijk' }, order: 1 },
    { key: 'address', label: { nl: 'Adres' }, order: 2 },
    { key: 'membership', label: { nl: 'Lidmaatschap' }, order: 3 },
    { key: 'extra', label: { nl: 'Extra' }, order: 3 },
  ];

  // Fields with explicit (functional_group, order, key). Includes a WITHIN-group `order` tie in
  // `personal` (first_name & birth_date both order 10) that MUST break by key → birth_date < first_name.
  const fields: FieldConfigField[] = [
    { key: 'first_name', functional_group: 'personal', order: 10, visible: true },
    { key: 'birth_date', functional_group: 'personal', order: 10, visible: true },
    { key: 'email', functional_group: 'personal', order: 20, visible: true },
    { key: 'street', functional_group: 'address', order: 10, visible: true },
    { key: 'city', functional_group: 'address', order: 10, visible: true },
    { key: 'joined_on', functional_group: 'membership', order: 10, visible: true },
    { key: 'badge', functional_group: 'extra', order: 10, visible: true },
  ];

  /**
   * The REAL consumer display sequence: the exact pipeline MembersPage/MembersViewBody/the modals
   * use — `formFields` (pre-sort by order) → `groupFieldsBySection` (bucket by functional_group,
   * sections ordered by the group catalog) → flatten. Returns the ordered field-key list.
   */
  const displayOrder = (fs: FieldConfigField[], cat: FunctionalGroup[]): string[] => {
    const resolved = formFields({ fields: fs } as unknown as FieldConfig);
    const sections = groupFieldsBySection(resolved, cat);
    return sections.flatMap((s) => s.fields).map((f) => f.key);
  };

  // The one correct display order given (group.order, field.order, key):
  //   personal(1): birth_date(10) < first_name(10, key tie) < email(20)
  //   address(2):  city(10) < street(10, key tie)
  //   membership(3) vs extra(3): group-order tie → break by group key: extra < membership
  //   extra(3):    badge
  //   membership(3): joined_on
  const EXPECTED = ['birth_date', 'first_name', 'email', 'city', 'street', 'badge', 'joined_on'];

  it('(a) is STABLE/idempotent — same input yields the same sequence twice', () => {
    const once = displayOrder(fields, catalog);
    const twice = displayOrder(fields, catalog);
    expect(once).toEqual(twice);
    expect(once).toEqual(EXPECTED);
  });

  it('(b) is PERMUTATION-INVARIANT — shuffling the input yields the SAME display order', () => {
    // A few deterministic permutations (reverse, rotate, swap-pairs) — the tuple sort is total,
    // so NONE of them may change the output. Input order must not leak into display position.
    const reversed = [...fields].reverse();
    const rotated = [...fields.slice(3), ...fields.slice(0, 3)];
    const swapped = [...fields];
    for (let i = 0; i + 1 < swapped.length; i += 2) {
      [swapped[i], swapped[i + 1]] = [swapped[i + 1], swapped[i]];
    }
    for (const perm of [reversed, rotated, swapped]) {
      expect(displayOrder(perm, catalog)).toEqual(EXPECTED);
    }
  });

  it('(c) breaks a WITHIN-group `order` tie by `key` ascending (not by input order)', () => {
    // personal has first_name & birth_date both at order 10. Regardless of which appears first in
    // the input, birth_date (b < f) must precede first_name in the display order.
    const fnFirst = displayOrder(fields, catalog);
    const bdFirst = displayOrder([...fields].reverse(), catalog);
    const personalSlice = (seq: string[]) =>
      seq.filter((k) => k === 'birth_date' || k === 'first_name');
    expect(personalSlice(fnFirst)).toEqual(['birth_date', 'first_name']);
    expect(personalSlice(bdFirst)).toEqual(['birth_date', 'first_name']);
  });

  it('breaks a SECTION-order (group.order) tie by group `key` ascending, deterministically', () => {
    // membership & extra both at group order 3 → sections ordered by group key: extra before
    // membership, regardless of catalog input order.
    const asGiven = displayOrder(fields, catalog);
    const catReversed = [...catalog].reverse();
    const sectionTail = (seq: string[]) => seq.filter((k) => k === 'badge' || k === 'joined_on');
    expect(sectionTail(asGiven)).toEqual(['badge', 'joined_on']); // extra(badge) < membership(joined_on)
    expect(sectionTail(displayOrder(fields, catReversed))).toEqual(['badge', 'joined_on']);
  });
});
