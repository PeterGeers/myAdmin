/**
 * Tests for the Application field modal (spec 12 — Application Form Serving Redesign, task 4.1;
 * R1.1/R1.2, design §C1 / redesign A).
 *
 * This is the change-with-tests pairing for the NEW modal that replaces spec 11's toggle-list +
 * buried attributes panel (the full dedicated modal suite + axe is task 4.4). It asserts the task
 * 4.1 scaffold contract the modal owns:
 *  - the modal reuses `MembersFieldModal`'s ENGINE — the origin-aware `resolveWriteTarget` +
 *    `overlayModel.upsertField` — so a tenant field authors `application_visible` under
 *    `fields[key]` and a base field under `fixed_overrides[{group}.{key}]`, no network call (R1.1);
 *  - toggling OFF persists an EXPLICIT `false` (03b BU-5 / Req 2.1 — the toggle root-cause fix: a
 *    dropped `undefined` was treated as "unchanged" and silently reverted on reload);
 *  - a calculated / read-only field is NOT offerable — a note, no toggle (R2.5);
 *  - the application-form attributes section renders ONLY when a form is in scope (R1.2).
 *
 * Task 4.3 completes the four-attribute write-through: the remaining `application_required`
 * (NO-RELAX for a platform-required field) and `format` (KNOWN tokens only) attributes are authored
 * onto the SAME single `field_overlay` via the SAME origin-aware `upsertField` engine. The cases
 * here pair those behaviours:
 *  - `application_required` writes true / persists an explicit false on OFF (03b BU-5), origin-aware;
 *  - the NO-RELAX lock holds for a platform-required field (the toggle is disabled + forced on with
 *    an explanatory note — it cannot be authored optional);
 *  - `format` writes only a KNOWN token and clears to null; an unknown token is never offerable.
 *
 * Fixtures use the bare `key` + `group` server shape (R2.3) — never a pre-dotted key.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import { ApplicationFieldModal, resolveWriteTarget } from '../ApplicationFieldModal';
import { findField } from '../overlayModel';

/* ------------------------------------------------------------------ */
/*  Fixture — bare `key` + `group` server shape (R2.3): a tenant field, */
/*  a base field, and a calculated (non-offerable) field.              */
/* ------------------------------------------------------------------ */
const FIELD_CONFIG: FieldConfig = {
  // The platform's KNOWN format-validator tokens (R3.3) — the ONLY tokens the format picker offers.
  field_format_tokens: ['EMAIL', 'IBAN'],
  functional_groups: [
    { key: 'contact', label: { en: 'Contact', nl: 'Contact' }, order: 1 },
    { key: 'membership', label: { en: 'Membership', nl: 'Lidmaatschap' }, order: 2 },
  ],
  fields: [
    // tenant-added field → writes under fields[email]
    { key: 'email', functional_group: 'contact', order: 1, type: 'string', provenance: 'tenant_added', label: { en: 'Email', nl: 'E-mail' } },
    // base/fixed field with a storage `group` → writes under fixed_overrides['membership.member_number']
    { key: 'member_number', group: 'membership', functional_group: 'membership', order: 1, type: 'string', origin: 'fixed', provenance: 'base', label: { en: 'Member number', nl: 'Lidnummer' } },
    // calculated/read-only → NOT offerable
    { key: 'age', functional_group: 'contact', order: 2, type: 'number', origin: 'calculated', read_only: true, label: { en: 'Age', nl: 'Leeftijd' } },
    // reference field (membership_type) → subset sources from the field's OWN options (03b 9b.2)
    { key: 'membership_type', group: 'membership', functional_group: 'membership', order: 2, type: 'reference', provenance: 'base', origin: 'fixed', options: [{ value: 'regular', label: { en: 'Regular', nl: 'Regulier' } }, { value: 'student', label: { en: 'Student', nl: 'Student' } }], label: { en: 'Membership type', nl: 'Lidmaatschapstype' } },
    // scope axis → subset sources from the scope DIMENSION values (= its own options)
    { key: 'region', functional_group: 'contact', order: 3, type: 'enum', provenance: 'tenant_added', scope: { enabled: true, required_for: ['Member'] }, options: [{ value: 'north', label: { en: 'North', nl: 'Noord' } }, { value: 'south', label: { en: 'South', nl: 'Zuid' } }], label: { en: 'Region', nl: 'Regio' } },
    // enum field → subset sources from its OWN options
    { key: 'salutation', functional_group: 'contact', order: 4, type: 'enum', provenance: 'tenant_added', options: ['mr', 'mrs', 'mx'], label: { en: 'Salutation', nl: 'Aanhef' } },
    // plain string field → NOT choice-bearing, NO picker
    { key: 'first_name', functional_group: 'contact', order: 5, type: 'string', provenance: 'tenant_added', label: { en: 'First name', nl: 'Voornaam' } },
    // platform-required base field (appended LAST to keep the earlier index-based assertions stable)
    // → the required toggle is FORCED ON + disabled (NO-RELAX, R2).
    { key: 'last_name', group: 'contact', functional_group: 'contact', order: 6, type: 'string', origin: 'fixed', provenance: 'base', required: true, label: { en: 'Last name', nl: 'Achternaam' } },
  ],
};

function renderModal(
  fieldKey: string | null,
  overlay: MembersConfigValue = {},
  opts: { formInScope?: boolean } = {},
  onChange = vi.fn(),
) {
  const utils = render(
    <ApplicationFieldModal
      isOpen={fieldKey !== null}
      onClose={vi.fn()}
      fieldKey={fieldKey}
      fieldConfig={FIELD_CONFIG}
      overlay={overlay}
      onChange={onChange}
      formInScope={opts.formInScope ?? true}
      lang="en"
    />,
  );
  return { ...utils, onChange };
}

describe('ApplicationFieldModal — reuses MembersFieldModal engine: resolveWriteTarget (R1.1)', () => {
  it('routes a tenant-added field to fields[key]', () => {
    const target = resolveWriteTarget(FIELD_CONFIG.fields[0]); // email
    expect(target).toEqual({ writable: true, origin: 'fields', overlayKey: 'email' });
  });

  it('routes a base field to fixed_overrides[{group}.{key}] (R2.3 bare key + group)', () => {
    const target = resolveWriteTarget(FIELD_CONFIG.fields[1]); // member_number
    expect(target).toEqual({
      writable: true,
      origin: 'fixed_overrides',
      overlayKey: 'membership.member_number',
    });
  });

  it('marks a calculated field as read-only (never written)', () => {
    const target = resolveWriteTarget(FIELD_CONFIG.fields[2]); // age
    expect(target.writable).toBe(false);
  });
});

describe('ApplicationFieldModal — on-the-form toggle writes application_visible via the shared engine (R1.1 / §3.1)', () => {
  it('toggling a tenant field ON sets application_visible=true under fields[key] in the ONE overlay', () => {
    const { onChange } = renderModal('email', {});
    fireEvent.click(screen.getByTestId('application-field-modal-on-form-toggle'));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'email')?.field.application_visible).toBe(true);
    expect(findField(next, 'email')?.origin).toBe('fields');
  });

  it('toggling a base field ON writes under fixed_overrides keyed {group}.{key}', () => {
    const { onChange } = renderModal('member_number', {});
    fireEvent.click(screen.getByTestId('application-field-modal-on-form-toggle'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'membership.member_number')?.field.application_visible).toBe(true);
    expect(findField(next, 'membership.member_number')?.origin).toBe('fixed_overrides');
  });

  it('toggling OFF persists application_visible as an EXPLICIT false, not a dropped undefined (03b BU-5 / Req 2.1)', () => {
    const seeded: MembersConfigValue = {
      fields: { email: { type: 'string', application_visible: true } },
    };
    const { onChange } = renderModal('email', seeded);
    // The seeded "on" state is reflected on the toggle.
    expect(screen.getByTestId('application-field-modal-on-form-toggle')).toBeChecked();
    fireEvent.click(screen.getByTestId('application-field-modal-on-form-toggle'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    // 03b root-cause fix: OFF is an explicit `false` so the change-op diff emits it (a reload shows
    // OFF), never a dropped `undefined` the diff would treat as "unchanged".
    expect(findField(next, 'email')?.field.application_visible).toBe(false);
  });
});

describe('ApplicationFieldModal — offerability (R2.5)', () => {
  it('a calculated/read-only field shows a note and NO toggle', () => {
    renderModal('age', {});
    expect(screen.queryByTestId('application-field-modal-on-form-toggle')).not.toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-not-offerable')).toBeInTheDocument();
  });
});

describe('ApplicationFieldModal — application-form attributes section is gated on form-in-scope (R1.2)', () => {
  it('renders the application-form attributes section when a form is in scope', () => {
    renderModal('email', {}, { formInScope: true });
    expect(screen.getByTestId('application-field-modal-app-attrs')).toBeInTheDocument();
    expect(screen.queryByTestId('application-field-modal-no-form')).not.toBeInTheDocument();
  });

  it('does NOT render the application-form attributes section when no form is in scope', () => {
    renderModal('email', {}, { formInScope: false });
    expect(screen.queryByTestId('application-field-modal-app-attrs')).not.toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-no-form')).toBeInTheDocument();
  });

  it('renders the required + format controls (no scaffold placeholder) for an offerable field (task 4.3)', () => {
    renderModal('email', {}, { formInScope: true });
    expect(screen.queryByTestId('application-field-modal-attrs-placeholder')).not.toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-required')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-format')).toBeInTheDocument();
  });
});

describe('ApplicationFieldModal — application_required writes onto the ONE overlay (task 4.3 / R1.4)', () => {
  it('toggling required ON sets application_required=true under fields[key] (origin-aware)', () => {
    const seeded: MembersConfigValue = {
      fields: { email: { type: 'string', application_visible: true } },
    };
    const { onChange } = renderModal('email', seeded, { formInScope: true });
    fireEvent.click(screen.getByTestId('application-field-modal-required-toggle'));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'email')?.field.application_required).toBe(true);
    expect(findField(next, 'email')?.origin).toBe('fields');
  });

  it('toggling required OFF persists application_required as an EXPLICIT false, not a dropped undefined (03b BU-5 / Req 2.1)', () => {
    const seeded: MembersConfigValue = {
      fields: { email: { type: 'string', application_visible: true, application_required: true } },
    };
    const { onChange } = renderModal('email', seeded, { formInScope: true });
    // Chakra <Switch> places the data-testid on the underlying <input>, so assert on it directly.
    const toggle = screen.getByTestId('application-field-modal-required-toggle');
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    // 03b root-cause fix: OFF is an explicit `false` so the change-op diff emits it (a reload shows
    // OFF), never a dropped `undefined` the diff would treat as "unchanged".
    expect(findField(next, 'email')?.field.application_required).toBe(false);
  });

  it('a BASE field writes application_required under fixed_overrides keyed {group}.{key}', () => {
    const { onChange } = renderModal('member_number', {}, { formInScope: true });
    fireEvent.click(screen.getByTestId('application-field-modal-required-toggle'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'membership.member_number')?.field.application_required).toBe(true);
    expect(findField(next, 'membership.member_number')?.origin).toBe('fixed_overrides');
  });
});

describe('ApplicationFieldModal — application_required NO-RELAX for a platform-required field (task 4.3 / R2)', () => {
  it('the required toggle is forced ON (locked) with an explanatory note (cannot author optional)', () => {
    renderModal('last_name', {}, { formInScope: true });
    // Forced ON — a platform-required field is always required on the form (R2, no-relax).
    expect(screen.getByTestId('application-field-modal-required-toggle')).toBeChecked();
    // The platform-required provenance + the locked note surface WHY it cannot be relaxed.
    expect(screen.getByText('platform-required')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-required-locked-note')).toBeInTheDocument();
  });

  it('clicking the locked toggle does NOT write a relax onto the overlay', () => {
    const { onChange } = renderModal('last_name', {}, { formInScope: true });
    // The no-relax guard holds: a click can NEVER write a relax to the overlay (R2 / R8.1c).
    fireEvent.click(screen.getByTestId('application-field-modal-required-toggle'));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('the membership-type reference field is likewise forced required (locked) when on the form', () => {
    const { onChange } = renderModal('membership_type', {}, { formInScope: true });
    // Forced ON even though it is NOT platform-required — an exposed membership-type field is
    // always application-required (spec 10 D21) — and the lock holds (no relax written).
    expect(screen.getByTestId('application-field-modal-required-toggle')).toBeChecked();
    fireEvent.click(screen.getByTestId('application-field-modal-required-toggle'));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('ApplicationFieldModal — format writes only a KNOWN token (task 4.3 / R3.3)', () => {
  it('offers ONLY the platform-known tokens (+ the "none" choice) and no unknown token', () => {
    renderModal('email', {}, { formInScope: true });
    const select = screen.getByTestId('application-field-modal-format-select') as HTMLSelectElement;
    const optionValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(optionValues).toEqual(['', 'EMAIL', 'IBAN']); // none + the two known tokens only
    // An unknown token is structurally not offerable — it is not among the options.
    expect(optionValues).not.toContain('PHONE');
  });

  it('selecting a known token writes format={checker} onto the ONE overlay (origin-aware)', () => {
    const seeded: MembersConfigValue = {
      fields: { email: { type: 'string', application_visible: true } },
    };
    const { onChange } = renderModal('email', seeded, { formInScope: true });
    fireEvent.change(screen.getByTestId('application-field-modal-format-select'), {
      target: { value: 'EMAIL' },
    });
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'email')?.field.format).toEqual({ checker: 'EMAIL' });
    expect(findField(next, 'email')?.origin).toBe('fields');
  });

  it('selecting "— none —" clears format to null', () => {
    const seeded: MembersConfigValue = {
      fields: {
        email: { type: 'string', application_visible: true, format: { checker: 'EMAIL' } },
      },
    };
    const { onChange } = renderModal('email', seeded, { formInScope: true });
    fireEvent.change(screen.getByTestId('application-field-modal-format-select'), {
      target: { value: '' },
    });
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'email')?.field.format).toBeNull();
  });

  it('degrades to "no format checks" when the platform serves no known tokens', () => {
    const { container } = render(
      <ApplicationFieldModal
        isOpen
        onClose={vi.fn()}
        fieldKey="email"
        fieldConfig={{ ...FIELD_CONFIG, field_format_tokens: [] }}
        overlay={{}}
        onChange={vi.fn()}
        formInScope
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-field-modal-format-empty')).toBeInTheDocument();
    // Only the "none" option is offered.
    const select = container.querySelector(
      '[data-testid="application-field-modal-format-select"]',
    ) as HTMLSelectElement;
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.value)).toEqual(['']);
  });
});

describe('ApplicationFieldModal — enum-subset picker SOURCE adapts to field kind (task 4.2 / R1.3)', () => {
  it('renders the picker for a REFERENCE field sourced from the field\u2019s own options (03b 9b.2)', () => {
    renderModal('membership_type', {}, { formInScope: true });
    const source = screen.getByTestId('application-field-modal-subset-source');
    expect(source).toHaveAttribute('data-source-kind', 'reference');
    // The options are the field's OWN option values (the live catalog is retired, 03b).
    expect(screen.getByTestId('application-field-modal-subset-option-regular')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-subset-option-student')).toBeInTheDocument();
  });

  it('renders the picker for a SCOPE field sourced from the scope dimension values', () => {
    renderModal('region', {}, { formInScope: true });
    const source = screen.getByTestId('application-field-modal-subset-source');
    expect(source).toHaveAttribute('data-source-kind', 'scope');
    expect(screen.getByTestId('application-field-modal-subset-option-north')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-subset-option-south')).toBeInTheDocument();
  });

  it('renders the picker for an ENUM field sourced from its own options', () => {
    renderModal('salutation', {}, { formInScope: true });
    const source = screen.getByTestId('application-field-modal-subset-source');
    expect(source).toHaveAttribute('data-source-kind', 'enum');
    expect(screen.getByTestId('application-field-modal-subset-option-mr')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-subset-option-mrs')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-subset-option-mx')).toBeInTheDocument();
  });

  it('does NOT render the picker for a plain string field (the spec 11 choice-on-string fix)', () => {
    renderModal('first_name', {}, { formInScope: true });
    expect(screen.queryByTestId('application-field-modal-subset')).not.toBeInTheDocument();
  });

  it('surfaces an empty-source note for a reference field with NO options yet (03b 9b.2)', () => {
    // membership_type is choice-bearing by kind, but with an empty option set the picker shows
    // the "no options yet" note and offers nothing (the field has no authored vocabulary).
    const emptyCfg = {
      ...FIELD_CONFIG,
      fields: FIELD_CONFIG.fields.map((f) =>
        f.key === 'membership_type' ? { ...f, options: [] } : f,
      ),
    } as typeof FIELD_CONFIG;
    render(
      <ApplicationFieldModal
        isOpen
        onClose={vi.fn()}
        fieldKey="membership_type"
        fieldConfig={emptyCfg}
        overlay={{}}
        onChange={vi.fn()}
        formInScope
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-field-modal-subset')).toBeInTheDocument();
    expect(screen.getByTestId('application-field-modal-subset-empty-source')).toBeInTheDocument();
  });
});

describe('ApplicationFieldModal — selecting a subset writes application_choices onto the overlay (task 4.2 / R1.4)', () => {
  it('unchecking one enum option persists the remaining proper subset as a list', () => {
    // Default: all selected = the full set. Unchecking "mx" leaves a proper subset [mr, mrs].
    const { onChange } = renderModal('salutation', {}, { formInScope: true });
    fireEvent.click(screen.getByTestId('application-field-modal-subset-option-mx'));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'salutation')?.field.application_choices).toEqual(['mr', 'mrs']);
    expect(findField(next, 'salutation')?.origin).toBe('fields');
  });

  it('seeded proper subset reflects the checkbox state (only the subset is checked)', () => {
    const seeded: MembersConfigValue = {
      fields: { salutation: { type: 'enum', application_visible: true, application_choices: ['mr'] } },
    };
    renderModal('salutation', seeded, { formInScope: true });
    // The Chakra Checkbox `data-testid` lands on the wrapping label; the checked state lives on the
    // nested <input>, so assert against that.
    const checkbox = (testid: string) =>
      screen.getByTestId(testid).querySelector('input') as HTMLInputElement;
    expect(checkbox('application-field-modal-subset-option-mr')).toBeChecked();
    expect(checkbox('application-field-modal-subset-option-mrs')).not.toBeChecked();
    expect(checkbox('application-field-modal-subset-option-mx')).not.toBeChecked();
  });

  it('checking the last option back in restores the full set stored as null (R3.2)', () => {
    // Seed [mr, mrs] (a proper subset of 3); checking "mx" completes the full set → null.
    const seeded: MembersConfigValue = {
      fields: { salutation: { type: 'enum', application_visible: true, application_choices: ['mr', 'mrs'] } },
    };
    const { onChange } = renderModal('salutation', seeded, { formInScope: true });
    fireEvent.click(screen.getByTestId('application-field-modal-subset-option-mx'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'salutation')?.field.application_choices).toBeNull();
  });

  it('a REFERENCE subset writes under fixed_overrides keyed {group}.{key} (origin-aware)', () => {
    // Unchecking "student" from the catalog leaves the proper subset [regular] on membership_type.
    const { onChange } = renderModal('membership_type', {}, { formInScope: true });
    fireEvent.click(screen.getByTestId('application-field-modal-subset-option-student'));
    const next = onChange.mock.calls[0][0] as MembersConfigValue;
    expect(findField(next, 'membership.membership_type')?.field.application_choices).toEqual(['regular']);
    expect(findField(next, 'membership.membership_type')?.origin).toBe('fixed_overrides');
  });
});

describe('ApplicationFieldModal — unresolved field degrades, never crashes', () => {
  it('renders a neutral "unavailable" body for an unknown key', () => {
    renderModal('does_not_exist', {});
    expect(screen.getByTestId('application-field-modal-unavailable')).toBeInTheDocument();
  });
});
