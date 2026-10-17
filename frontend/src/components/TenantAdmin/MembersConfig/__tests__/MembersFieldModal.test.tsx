/**
 * Tests for the field modal (Members config redesign Phase 3, task 4.6).
 *
 * The drill-down leaf: every editable field option authored AS AN ATTRIBUTE on the one field —
 * identity/flags/enum choices and the step-9 scope-binding attribute. It does NOT author the
 * catalog `alias` (a Phase-1 declared-only stub with no runtime consumer) nor any analytics role
 * (that layer was deleted). CONTROLLED — mutations flow out via `overlayModel`; the editor saves once.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within, fireEvent } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { MembersFieldModal } from '../MembersFieldModal';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import type { FieldConfig } from '../../../../types/members';

function overlay(): MembersConfigValue {
  return {
    functional_groups: [{ key: 'personal', order: 1 }],
    fields: {
      region: {
        // Single-vocabulary: the overlay field carries `scope = { enabled, required_for }` ONLY
        // (no `values` list) — the scope values ARE the enum vocabulary (served under `options`).
        type: 'enum',
        label_en: 'Region',
        functional_group: 'personal',
        order: 2,
        choices: [
          { value: 'Noord', label: { nl: 'Noord', en: 'Noord' } },
          { value: 'Zuid', label: { nl: 'Zuid', en: 'Zuid' } },
        ],
        scope: { enabled: true, required_for: ['Members_CRUD'] },
      },
    },
    fixed_overrides: {},
  };
}

/**
 * The RESOLVED FieldConfig the modal SEEDS from (remediation R2.1–R2.3): the server serves the full
 * field set with the correct `type`, enum values ALWAYS under `options` (rich OR bare — never a
 * `choices` key), and the bilingual `label{}`. `status` is a fixed enum with 6 options; `region` is
 * an enum whose values come from its scope vocabulary (10 region values); `name` is a plain string.
 */
const STATUS_OPTIONS = [
  { value: 'prospect', label: { en: 'Prospect', nl: 'Prospect' } },
  { value: 'active', label: { en: 'Active', nl: 'Actief' } },
  { value: 'lapsed', label: { en: 'Lapsed', nl: 'Verlopen' } },
  { value: 'suspended', label: { en: 'Suspended', nl: 'Geschorst' } },
  { value: 'resigned', label: { en: 'Resigned', nl: 'Opgezegd' } },
  { value: 'deceased', label: { en: 'Deceased', nl: 'Overleden' } },
];
const REGION_VALUES = [
  'Noord', 'Zuid', 'Oost', 'West', 'Midden',
  'Noordoost', 'Noordwest', 'Zuidoost', 'Zuidwest', 'Centraal',
];

function fieldConfig(): FieldConfig {
  return {
    fields: [
      {
        key: 'status',
        type: 'enum',
        label: { en: 'Status', nl: 'Status' },
        functional_group: 'personal',
        order: 1,
        options: STATUS_OPTIONS,
      },
      {
        key: 'region',
        type: 'enum',
        label: { en: 'Region', nl: 'Regio' },
        functional_group: 'personal',
        order: 2,
        // Scope-sourced values are served as a bare string list under `options` (the ONE
        // vocabulary). The served `scope` is `{ enabled, required_for }` ONLY — no `values` (R3.5/R3.6).
        options: REGION_VALUES,
        scope: { enabled: true, required_for: ['Members_CRUD'] },
      },
      {
        key: 'name',
        type: 'string',
        label: { en: 'Name', nl: 'Naam' },
        functional_group: 'personal',
        order: 3,
      },
    ],
    functional_groups: [{ key: 'personal', order: 1 }],
  };
}

function renderModal(props: Partial<React.ComponentProps<typeof MembersFieldModal>> = {}) {
  i18n.changeLanguage('en');
  const merged: React.ComponentProps<typeof MembersFieldModal> = {
    isOpen: true,
    onClose: vi.fn(),
    mode: 'create',
    groupKey: 'personal',
    overlay: overlay(),
    fieldConfig: fieldConfig(),
    onChange: vi.fn(),
    lang: 'en',
    ...props,
  };
  return {
    ...render(
      <I18nextProvider i18n={i18n}>
        <MembersFieldModal {...merged} />
      </I18nextProvider>,
    ),
    props: merged,
  };
}

describe('MembersFieldModal — create', () => {
  it('creates a field with its authored attributes (into the opened group)', () => {
    const onChange = vi.fn();
    renderModal({ mode: 'create', onChange });
    const modal = screen.getByTestId('members-field-modal');
    fireEvent.change(within(modal).getByLabelText('Field key'), { target: { value: 'nickname' } });
    fireEvent.change(within(modal).getByLabelText('Label (English)'), { target: { value: 'Nickname' } });
    fireEvent.click(within(modal).getByLabelText('Required'));
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.nickname).toMatchObject({
      type: 'string',
      label_en: 'Nickname',
      functional_group: 'personal',
      required: true,
    });
  });

  it('rejects a duplicate field key', () => {
    const onChange = vi.fn();
    renderModal({ mode: 'create', onChange });
    fireEvent.change(screen.getByLabelText('Field key'), { target: { value: 'region' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));
    expect(screen.getByText('This field key already exists')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows the enum choices editor only for the enum type', () => {
    renderModal({ mode: 'create' });
    // string type → no choices editor
    expect(screen.queryByText('Choices')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'enum' } });
    expect(screen.getByText('Choices')).toBeInTheDocument();
    // enum shows the inline values editor, NOT the reference catalog pointer (R3.3).
    expect(screen.queryByTestId('members-field-modal-reference-note')).not.toBeInTheDocument();
  });

  it('authors the scope-binding attribute (single-vocabulary, R3.2/R3.3) when the switch is on', () => {
    const onChange = vi.fn();
    renderModal({ mode: 'create', onChange });
    fireEvent.change(screen.getByLabelText('Field key'), { target: { value: 'area' } });
    fireEvent.click(screen.getByLabelText('Scope axis'));
    // There is NO separate "scope values" input — the single-vocabulary rule removed it (R3.2).
    expect(screen.queryByLabelText('Scope values')).not.toBeInTheDocument();
    // The scope section carries only `required_for` (a roles control).
    fireEvent.change(screen.getByLabelText('Required for roles'), { target: { value: 'Members_CRUD' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    const next = onChange.mock.calls[0][0] as Record<string, any>;
    // Stored scope is `{ enabled, required_for }` ONLY — no `values` list.
    expect(next.fields.area.scope).toEqual({ enabled: true, required_for: ['Members_CRUD'] });
  });

  it('does NOT author an alias / analytics-role attribute (neither control is present)', () => {
    const onChange = vi.fn();
    renderModal({ mode: 'create', onChange });
    // The analytics role was deleted (members-analytics-role-removal); the catalog `alias` is a
    // Phase-1 declared-only stub with no runtime consumer, so the modal exposes NEITHER control.
    expect(screen.queryByLabelText('Analytics role (alias)')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Alias (English)')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-field-modal-alias')).not.toBeInTheDocument();
    // A plain create authors no alias attribute on the field.
    fireEvent.change(screen.getByLabelText('Field key'), { target: { value: 'nickname' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.nickname.alias).toBeUndefined();
  });
});

describe('MembersFieldModal — reference vs enum branch (Property 4, R3.1/R3.2/R3.3)', () => {
  it('a REFERENCE field shows the catalog pointer, NOT an enum-values editor (R3.1/R3.3)', () => {
    renderModal({ mode: 'create' });
    // Drive the field type to `reference` the same way the enum test does (the Type select).
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'reference' } });
    const modal = screen.getByTestId('members-field-modal');
    // The read-only note + its pointer link to the membership-type catalog are shown (no dead end).
    expect(within(modal).getByTestId('members-field-modal-reference-note')).toBeInTheDocument();
    expect(within(modal).getByTestId('members-field-modal-reference-link')).toBeInTheDocument();
    // The inline enum choices editor is ABSENT for a reference field — values live in the catalog.
    expect(within(modal).queryByText('Choices')).not.toBeInTheDocument();
  });

  it('clicking the pointer invokes the onManageCatalog handler when wired (R3.1)', () => {
    const onManageCatalog = vi.fn();
    renderModal({ mode: 'create', onManageCatalog });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'reference' } });
    fireEvent.click(screen.getByTestId('members-field-modal-reference-link'));
    expect(onManageCatalog).toHaveBeenCalledTimes(1);
  });

  it('a REFERENCE field still exposes the presentation attributes (label / order) for editing (R3.2)', () => {
    renderModal({ mode: 'create' });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'reference' } });
    const modal = screen.getByTestId('members-field-modal');
    // Presentation attributes remain editable — only the VALUES are managed elsewhere.
    expect(within(modal).getByLabelText('Label (English)')).toBeInTheDocument();
    expect(within(modal).getByLabelText('Order')).toBeInTheDocument();
  });

  it('an ENUM field still shows the inline EnumOptionsEditor and NOT the reference note (R3.3)', () => {
    renderModal({ mode: 'create' });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'enum' } });
    const modal = screen.getByTestId('members-field-modal');
    // enum keeps its inline values editor (the "Choices" block) unchanged …
    expect(within(modal).getByText('Choices')).toBeInTheDocument();
    // … and does NOT render the reference catalog pointer.
    expect(within(modal).queryByTestId('members-field-modal-reference-note')).not.toBeInTheDocument();
  });
});

describe('MembersFieldModal — seeds from the resolved field (R2.1–R2.3)', () => {
  it('opens a fixed enum field (status) as enum with its 6 served options (R2.3)', () => {
    renderModal({ mode: 'edit', fieldKey: 'status' });
    const modal = screen.getByTestId('members-field-modal');
    // type seeded from the resolved `field.type` (NOT silently defaulted to string) — R2.2.
    expect((within(modal).getByLabelText('Type') as HTMLSelectElement).value).toBe('enum');
    // enum vocabulary seeded from the served `options` (rich) — the choices editor shows 6 options.
    expect(within(modal).getByText('Choices')).toBeInTheDocument();
    const optionRows = modal.querySelectorAll('[data-testid^="enum-option-"]');
    expect(optionRows.length).toBe(6);
    expect((within(modal).getByLabelText('Option 1 value') as HTMLInputElement).value).toBe('prospect');
    expect((within(modal).getByLabelText('Option 6 value') as HTMLInputElement).value).toBe('deceased');
    // label seeded from the resolved `label{}`.
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe('Status');
  });

  it('opens a scope-backed enum (region) as enum with its scope-sourced values (R2.3)', () => {
    renderModal({ mode: 'edit', fieldKey: 'region' });
    const modal = screen.getByTestId('members-field-modal');
    expect((within(modal).getByLabelText('Type') as HTMLSelectElement).value).toBe('enum');
    // region's values come from scope_vocab, served as a bare string list under `options` — 10 values.
    const optionRows = modal.querySelectorAll('[data-testid^="enum-option-"]');
    expect(optionRows.length).toBe(10);
    expect((within(modal).getByLabelText('Option 1 value') as HTMLInputElement).value).toBe('Noord');
    expect((within(modal).getByLabelText('Option 10 value') as HTMLInputElement).value).toBe('Centraal');
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe('Region');
  });

  it('opens a plain string field (name) as type string with no choices editor (R2.2)', () => {
    renderModal({ mode: 'edit', fieldKey: 'name' });
    const modal = screen.getByTestId('members-field-modal');
    expect((within(modal).getByLabelText('Type') as HTMLSelectElement).value).toBe('string');
    expect(within(modal).queryByText('Choices')).not.toBeInTheDocument();
    expect((within(modal).getByLabelText('Label (English)') as HTMLInputElement).value).toBe('Name');
  });

  it('seeds `type` from the resolved field — does NOT silently default to string (R2.2)', () => {
    // A resolved field that (defectively) carries no `type` seeds EMPTY, not a papered-over `string`.
    const cfg: FieldConfig = {
      fields: [{ key: 'mystery', label: { en: 'Mystery' }, functional_group: 'personal' }],
      functional_groups: [{ key: 'personal', order: 1 }],
    };
    renderModal({ mode: 'edit', fieldKey: 'mystery', fieldConfig: cfg });
    const modal = screen.getByTestId('members-field-modal');
    expect((within(modal).getByLabelText('Type') as HTMLSelectElement).value).toBe('');
  });
});

describe('MembersFieldModal — origin-aware write-back (remediation task 2.2, R1)', () => {
  /**
   * A resolved config with explicit origin/provenance so the modal can route the write by slice:
   *  - `last_name` is a BASE field (fixed, storage group `personal`) → `fixed_overrides` on edit;
   *  - `nickname` is a TENANT-ADDED overlay field → `fields` on edit;
   *  - `age` is a CALCULATED (derived) field → read-only, NO write.
   */
  function provenanceConfig(): FieldConfig {
    return {
      fields: [
        {
          key: 'last_name',
          type: 'string',
          label: { en: 'Last name', nl: 'Achternaam' },
          group: 'personal',
          origin: 'fixed',
          provenance: 'base',
          functional_group: 'personal',
          order: 1,
        },
        {
          key: 'nickname',
          type: 'string',
          label: { en: 'Nickname', nl: 'Bijnaam' },
          origin: 'variable',
          provenance: 'tenant_added',
          functional_group: 'personal',
          order: 2,
        },
        {
          key: 'age',
          type: 'number',
          label: { en: 'Age', nl: 'Leeftijd' },
          origin: 'calculated',
          read_only: true,
          functional_group: 'personal',
          order: 3,
        },
      ],
      functional_groups: [{ key: 'personal', order: 1 }],
    };
  }

  /** The working overlay carries only the tenant-added field; base/calculated have no entry yet. */
  function writeOverlay(): MembersConfigValue {
    return {
      functional_groups: [{ key: 'personal', order: 1 }],
      fields: {
        nickname: { type: 'string', label_en: 'Nickname', functional_group: 'personal', order: 2 },
      },
      fixed_overrides: {},
    };
  }

  it('editing a FIXED (base) field writes a `fixed_overrides` entry (dotted {group}.{key})', () => {
    const onChange = vi.fn();
    renderModal({
      mode: 'edit',
      fieldKey: 'last_name',
      fieldConfig: provenanceConfig(),
      overlay: writeOverlay(),
      onChange,
    });
    fireEvent.change(screen.getByLabelText('Label (English)'), { target: { value: 'Surname' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    // ONE save → ONE request (single-save contract unchanged).
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    // routed to fixed_overrides under the dotted key — NOT into the tenant `fields` map.
    expect(next.fixed_overrides['personal.last_name']).toMatchObject({ label_en: 'Surname' });
    expect(next.fields.last_name).toBeUndefined();
  });

  it('editing an ADDED (tenant) field writes a `fields` entry', () => {
    const onChange = vi.fn();
    renderModal({
      mode: 'edit',
      fieldKey: 'nickname',
      fieldConfig: provenanceConfig(),
      overlay: writeOverlay(),
      onChange,
    });
    fireEvent.change(screen.getByLabelText('Label (English)'), { target: { value: 'Alias name' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.nickname).toMatchObject({ label_en: 'Alias name' });
    // no stray fixed_overrides entry created for a tenant-added field
    expect(next.fixed_overrides['personal.nickname']).toBeUndefined();
  });

  it('a CALCULATED (read-only) field performs NO write on save', () => {
    const onChange = vi.fn();
    const onClose = vi.fn();
    renderModal({
      mode: 'edit',
      fieldKey: 'age',
      fieldConfig: provenanceConfig(),
      overlay: writeOverlay(),
      onChange,
      onClose,
    });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));
    // read-only → no overlay mutation, but the modal still closes cleanly.
    expect(onChange).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('create always writes a tenant VARIABLE field under `fields` (never fixed_overrides, R1.5)', () => {
    const onChange = vi.fn();
    renderModal({
      mode: 'create',
      groupKey: 'personal',
      fieldConfig: provenanceConfig(),
      overlay: writeOverlay(),
      onChange,
    });
    fireEvent.change(screen.getByLabelText('Field key'), { target: { value: 'hobby' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.hobby).toMatchObject({ type: 'string', functional_group: 'personal' });
    expect(next.fixed_overrides).toEqual({});
  });
});

describe('MembersFieldModal — edit', () => {
  it('seeds the form from the SERVED scope (single-vocabulary) and locks the key (R3.5/R3.6)', () => {
    renderModal({ mode: 'edit', fieldKey: 'region' });
    const keyInput = screen.getByLabelText('Field key') as HTMLInputElement;
    expect(keyInput.value).toBe('region');
    expect(keyInput).toBeDisabled();
    // scope `enabled` + `required_for` seeded from the RESOLVED field's served `scope`
    // (`{ enabled, required_for }` — no `values`, R3.5/R3.6).
    expect((screen.getByLabelText('Scope axis') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Required for roles') as HTMLInputElement).value).toBe('Members_CRUD');
    // There is NO separate scope-values list — the single vocabulary is the enum `Choices` editor.
    expect(screen.queryByLabelText('Scope values')).not.toBeInTheDocument();
  });

  it('turning scope OFF removes the scope attribute on save', () => {
    const onChange = vi.fn();
    renderModal({ mode: 'edit', fieldKey: 'region', onChange });
    fireEvent.click(screen.getByLabelText('Scope axis')); // true → false
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    expect(next.fields.region.scope).toBeUndefined();
    // other attributes preserved
    expect(next.fields.region.label_en).toBe('Region');
    expect(next.fields.region.functional_group).toBe('personal');
  });

  /**
   * Property P2 — Scope round-trip (R3.7), single-vocabulary. The scope values ARE the field's
   * enum values: there is ONE editor. Enabling scope, ADDING a value and REMOVING a value via the
   * enum (Choices) editor, then saving, yields a committed overlay whose enum vocabulary (`choices`)
   * reflects the edit AND whose `scope` is `{ enabled, required_for }` — the scope dimension's values
   * are DERIVED from that single vocabulary (server builder, task 3.2), never a divergent list.
   */
  it('round-trips a scope vocabulary edit through the ONE enum editor (P2, R3.7)', () => {
    const onChange = vi.fn();
    // A scope-backed enum field with a small, unambiguous served vocabulary (the ONE vocabulary):
    // two enum values, scope enabled, served `scope = { enabled, required_for }` (no `values`).
    const cfg: FieldConfig = {
      fields: [
        {
          key: 'region',
          type: 'enum',
          label: { en: 'Region', nl: 'Regio' },
          functional_group: 'personal',
          order: 2,
          options: [
            { value: 'Noord', label: { en: 'Noord', nl: 'Noord' } },
            { value: 'Zuid', label: { en: 'Zuid', nl: 'Zuid' } },
          ],
          scope: { enabled: true, required_for: ['Members_CRUD'] },
        },
      ],
      functional_groups: [{ key: 'personal', order: 1 }],
    };
    renderModal({ mode: 'edit', fieldKey: 'region', fieldConfig: cfg, onChange });
    const modal = screen.getByTestId('members-field-modal');

    // Scope is already enabled (served `{ enabled, required_for }`); the ONE vocabulary is the
    // enum Choices editor — there is NO separate scope-values input (single-vocabulary, R3.2).
    expect((within(modal).getByLabelText('Scope axis') as HTMLInputElement).checked).toBe(true);
    expect(within(modal).queryByLabelText('Scope values')).not.toBeInTheDocument();

    // The enum editor seeds the field's 2 served options (the scope vocabulary).
    expect(modal.querySelectorAll('[data-testid^="enum-option-"]').length).toBe(2);
    expect((within(modal).getByLabelText('Option 1 value') as HTMLInputElement).value).toBe('Noord');
    expect((within(modal).getByLabelText('Option 2 value') as HTMLInputElement).value).toBe('Zuid');

    // ADD a value through the single enum editor.
    fireEvent.click(within(modal).getByLabelText('Add option'));
    fireEvent.change(within(modal).getByLabelText('Option 3 value'), { target: { value: 'Oost' } });
    // REMOVE the first value (Noord) through the same editor.
    fireEvent.click(within(modal).getByLabelText('Remove option 1'));

    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    const region = next.fields.region;

    // The committed overlay reflects the vocabulary edit in the ENUM OPTIONS (`choices`): Noord
    // removed, Oost added → { Zuid, Oost }.
    const values = (region.choices as Array<{ value: string }>).map((o) => o.value);
    expect(values).toEqual(['Zuid', 'Oost']);

    // Scope remains `{ enabled, required_for }` ONLY — single-vocabulary, no separate `values` list.
    // The config#scope dimension values are DERIVED from the enum vocabulary above by the builder
    // on save (task 3.2) + the re-resolved field's options reflect it (task 3.1) — asserted there.
    expect(region.scope).toEqual({ enabled: true, required_for: ['Members_CRUD'] });
    expect(region.scope.values).toBeUndefined();
  });

  /**
   * Property P4 — Move persistence (R6.1–R6.3, I-8). The move action is the mutator: it reassigns a
   * field's stored `functional_group` to the TARGET group and leaves the modal open. A subsequent
   * editor Save must PERSIST that target group — the modal must NOT re-author `functional_group`
   * back to the stale group it was OPENED under (`groupKey`), which was the I-8 revert.
   *
   * This fixture reflects the state right after a move: the modal was opened from `personal`
   * (`groupKey='personal'`) but the field's working-overlay `functional_group` is already the
   * TARGET group `contact` (set by `moveFieldToGroup`). Saving an unrelated edit (a relabel) must
   * keep the field in `contact`.
   */
  it('persists a moved field in the TARGET group on save — no revert to the opened group (P4, R6.3)', () => {
    const onChange = vi.fn();
    const movedOverlay: MembersConfigValue = {
      functional_groups: [
        { key: 'personal', order: 1 },
        { key: 'contact', order: 2 },
      ],
      fields: {
        // The move action already reassigned `region` from `personal` → `contact` in the overlay.
        region: {
          type: 'enum',
          label_en: 'Region',
          functional_group: 'contact',
          order: 2,
          choices: [{ value: 'Noord', label: { nl: 'Noord', en: 'Noord' } }],
        },
      },
      fixed_overrides: {},
    };
    const cfg: FieldConfig = {
      fields: [
        {
          key: 'region',
          type: 'enum',
          label: { en: 'Region', nl: 'Regio' },
          origin: 'variable',
          provenance: 'tenant_added',
          // The resolved config also reflects the move (re-resolved after the overlay mutation).
          functional_group: 'contact',
          order: 2,
          options: [{ value: 'Noord', label: { en: 'Noord', nl: 'Noord' } }],
        },
      ],
      functional_groups: [
        { key: 'personal', order: 1 },
        { key: 'contact', order: 2 },
      ],
    };
    // Modal OPENED from `personal` (the stale group) — the pre-fix bug re-authored this on save.
    renderModal({
      mode: 'edit',
      fieldKey: 'region',
      groupKey: 'personal',
      overlay: movedOverlay,
      fieldConfig: cfg,
      onChange,
    });
    // Make an unrelated edit and save.
    fireEvent.change(screen.getByLabelText('Label (English)'), { target: { value: 'Area' } });
    fireEvent.click(screen.getByTestId('members-field-modal-save-btn'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Record<string, any>;
    // The field PERSISTS in the TARGET group `contact` — NOT reverted to the opened `personal`.
    expect(next.fields.region.functional_group).toBe('contact');
    // The unrelated edit still applied.
    expect(next.fields.region.label_en).toBe('Area');
  });

  it('renders an actions slot when provided (task 4.7 injection point)', () => {
    renderModal({
      mode: 'edit',
      fieldKey: 'region',
      actionsSlot: <button data-testid="injected-action">Delete</button>,
    });
    expect(screen.getByTestId('injected-action')).toBeInTheDocument();
  });
});
