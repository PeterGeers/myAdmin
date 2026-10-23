/**
 * Tests for the Application Form Builder ROOT scaffold (spec 11, task 2.1; R1.3, design §3/§3.1).
 *
 * This task scaffolds the sub-tab root + the four panel SLOTS and wires the ONE working
 * `field_overlay` object + its single commit (`saveMembersParameter('field_overlay', …)`). The
 * sub-components that fill the slots land in later tasks (2.3/3.1/3.2/4.1/4.2), so these assert the
 * scaffold contract only:
 *  - the root loads the resolved field config + the `field_overlay` row (best-effort; a failed
 *    field-config fetch NEVER blocks authoring);
 *  - the four panel slots render (fields, form-shell, readiness, preview);
 *  - the single save path: one Save → EXACTLY one `writeFieldConfig` (→ `PUT /members/config/fields`),
 *    with NO per-field Flask create/update — the real `saveMembersParameter` un-mocked (Property 8);
 *  - Save is disabled until there is an unsaved edit.
 *
 * Uses the project's real i18n + test-utils render so the bilingual `t(nl,en)` labels render.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, waitFor, fireEvent } from '../../../../test-utils';
import i18n from '../../../../i18n';
import type { Parameter } from '../../../../types/parameterTypes';
import type { FieldConfig } from '../../../../types/members';

/* ------------------------------------------------------------------ */
/*  Service mocks — the data edges; the real save-once primitive runs. */
/* ------------------------------------------------------------------ */
const mockGetParams = vi.fn();
const mockGetFieldConfig = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
// field_overlay is SAM-owned (`config#fields`): the save goes through the Members API write path,
// not parameterService. Capture it to COUNT and inspect the authored body.
const mockWriteFieldConfig = vi.fn();
// config#mail is SAM-owned too: the form-shell save goes through `writeMailConfig` →
// `PUT /members/config/mail`. Capture it to COUNT and inspect the committed body (task 3.4 / R5.5).
const mockWriteMailConfig = vi.fn();

vi.mock('../../../../services/membersConfigService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/membersConfigService')
  >('../../../../services/membersConfigService');
  return {
    ...actual,
    getMembersParameters: (...a: unknown[]) => mockGetParams(...a),
    getMembersFieldConfig: (...a: unknown[]) => mockGetFieldConfig(...a),
    // REAL save-once primitives — Property 8 (one save → one request) is asserted through them:
    // `saveMembersParameter` (field_overlay) and `saveMembersMailConfig` (config#mail) both run
    // un-mocked so the single-commit contract is proven end to end through the service, not a stub.
    saveMembersParameter: actual.saveMembersParameter,
    saveMembersMailConfig: actual.saveMembersMailConfig,
  };
});

// The field_overlay + config#mail saves delegate to the Members API SAM write path
// (`PUT /members/config/fields` / `PUT /members/config/mail`).
vi.mock('../../../../services/membersApiService', () => ({
  writeFieldConfig: (...a: unknown[]) => mockWriteFieldConfig(...a),
  writeMailConfig: (...a: unknown[]) => mockWriteMailConfig(...a),
  getFieldConfig: vi.fn(),
  // The live-preview panel (task 4.2) POSTs the working overlay to `POST /members/application-preview`
  // via the REAL `previewMembersApplicationConfig` (spread from importActual above), which delegates
  // here. Resolve a small schema so the preview slot renders without a real network call.
  previewApplicationFieldConfig: vi
    .fn()
    .mockResolvedValue({ fields: [], locales: ['nl', 'en'], notice: null }),
}));

// The scope_dimensions save (still Flask) delegates to parameterService; mock to COUNT requests.
vi.mock('../../../../services/parameterService', () => ({
  getParameters: vi.fn(),
  createParameter: (...a: unknown[]) => mockCreate(...a),
  updateParameter: (...a: unknown[]) => mockUpdate(...a),
  deleteParameter: vi.fn(),
  getParameterDefault: vi.fn(),
}));

// The form-shell panel (task 3.2) reads the landing-page slug to DERIVE + display the public URL.
// It is a best-effort read (a failure degrades to "no address yet"); mock it so the scaffold load
// is deterministic and makes no real network call.
const mockGetSlug = vi.fn();
vi.mock('../../../../services/landingPageApi', () => ({
  getSlug: (...a: unknown[]) => mockGetSlug(...a),
}));

// The membership-type field's subset picker (task 3.3 / R4) sources its vocabulary from the LIVE
// catalog; the builder loads it best-effort via `listMembershipTypes`. Mock it so the scaffold load
// is deterministic and makes no real network call (an un-mocked call rejects fail-closed → null).
const mockListMembershipTypes = vi.fn();
vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: (...a: unknown[]) => mockListMembershipTypes(...a),
}));

import { ApplicationFormBuilder } from '../ApplicationFormBuilder';

/* ------------------------------------------------------------------ */
/*  Fixtures — one field_overlay row + a resolved config.              */
/* ------------------------------------------------------------------ */
const overlayRow: Parameter = {
  id: 303,
  namespace: 'members',
  key: 'field_overlay',
  value: {
    functional_groups: [{ key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 }],
    fields: {
      email: { type: 'string', label_en: 'Email', functional_group: 'personal', visible: true },
    },
    fixed_overrides: {},
  },
  value_type: 'json',
  scope_origin: 'tenant',
  is_secret: false,
} as unknown as Parameter;

const FIELD_CONFIG: FieldConfig = {
  fields: [
    { key: 'email', functional_group: 'personal', provenance: 'tenant_added', type: 'string', label: { en: 'Email', nl: 'E-mail' } },
  ],
  functional_groups: [{ key: 'personal', order: 1 }],
  config_status: { fields: '2026-10-21T09:00:00', scope: 1, mail: null },
  // The Mail sub-tab owns these scalars on `config#mail` (spec 11 §0.3 / R5.4). The builder's
  // form-shell save must SEED from them and carry them through verbatim — it references (displays)
  // `application_scope_copy` / `mail_reply_to_default` but owns NO editor for them (task 3.4).
  mail_config: {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
    mail_reply_to_default: 'board@h-dcn.nl',
    application_scope_copy: true,
  },
  // The RAW stored config#fields overlay — the builder now SEEDS its one working object from THIS
  // (the same SAM row it writes back), not the retired Flask members.field_overlay param (spec 11
  // bugfix: GET/PUT symmetric so a save is loss-free).
  field_overlay: {
    functional_groups: [{ key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 }],
    fields: {
      email: { type: 'string', label_en: 'Email', functional_group: 'personal', visible: true },
    },
    fixed_overrides: {},
  },
};

function seed(rows: Record<string, Parameter> = { field_overlay: overlayRow }, cfg: FieldConfig | null = FIELD_CONFIG) {
  mockGetParams.mockResolvedValue(rows);
  mockGetFieldConfig.mockResolvedValue(cfg);
  mockCreate.mockResolvedValue({ success: true });
  mockUpdate.mockResolvedValue({ success: true });
  mockWriteFieldConfig.mockResolvedValue({ success: true, configId: 'fields', version: '2026-10-21T10:00:00+00:00' });
  mockWriteMailConfig.mockResolvedValue({ success: true, configId: 'mail', version: '2026-10-21T10:05:00+00:00' });
  mockGetSlug.mockResolvedValue({ success: true, data: { slug: 'h-dcn' } });
  mockListMembershipTypes.mockResolvedValue([
    { type_code: 'regular', label: { en: 'Regular', nl: 'Gewoon' }, active: true, order: 1 },
  ]);
}

async function renderBuilder(
  rows: Record<string, Parameter> = { field_overlay: overlayRow },
  cfg: FieldConfig | null = FIELD_CONFIG,
) {
  seed(rows, cfg);
  i18n.changeLanguage('en');
  const utils = render(
    <I18nextProvider i18n={i18n}>
      <ApplicationFormBuilder tenant="t-1" />
    </I18nextProvider>,
  );
  await screen.findByTestId('application-form-builder');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ApplicationFormBuilder — scaffold + four panel slots (R1.3, §3)', () => {
  it('loads and renders the four panel slots', async () => {
    await renderBuilder();
    expect(screen.getByTestId('application-form-builder-panel-fields')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-builder-panel-shell')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-builder-panel-readiness')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-builder-panel-preview')).toBeInTheDocument();
  });

  it('seeds the working overlay from the resolved field config (same SAM row it writes), not Flask', async () => {
    await renderBuilder();
    // GET/PUT symmetric on config#fields: the builder loads the field config (which carries the
    // raw `field_overlay`) and NEVER reads the retired Flask members.field_overlay param.
    expect(mockGetFieldConfig).toHaveBeenCalledTimes(1);
    expect(mockGetParams).not.toHaveBeenCalled();
  });

  it('still renders the panels when the field-config fetch fails (null) — never blocks authoring', async () => {
    await renderBuilder({ field_overlay: overlayRow }, null);
    expect(screen.getByTestId('application-form-builder-panel-fields')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-builder-panel-preview')).toBeInTheDocument();
  });
});

describe('ApplicationFormBuilder — single save path (Property 8 / §3.1)', () => {
  it('Save is disabled and shows no unsaved indicator until there is an edit (clean load)', async () => {
    await renderBuilder();
    expect(screen.getByTestId('application-form-builder-save')).toBeDisabled();
    expect(
      screen.queryByTestId('application-form-builder-unsaved-indicator'),
    ).not.toBeInTheDocument();
  });

  it('makes NO config write on a clean load — authoring is one-object/one-save, never per-field', async () => {
    await renderBuilder();
    // Loading the builder reads the resolved config (which carries the overlay to seed) but writes
    // nothing until a Save — and never touches the retired Flask param path.
    await waitFor(() => expect(mockGetFieldConfig).toHaveBeenCalledTimes(1));
    expect(mockGetParams).not.toHaveBeenCalled();
    expect(mockWriteFieldConfig).not.toHaveBeenCalled();
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('toggling a field on the form sets application_visible in the ONE overlay with NO per-field write (§3.1)', async () => {
    await renderBuilder();
    // Save starts disabled; a single field toggle is a pure overlay transform, not a network call.
    expect(screen.getByTestId('application-form-builder-save')).toBeDisabled();
    fireEvent.click(screen.getByTestId('application-field-toggle-email'));

    // The toggle mutated the in-memory overlay only — zero writes so far (no per-field request).
    expect(mockWriteFieldConfig).not.toHaveBeenCalled();
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
    // The edit is now unsaved → Save enables + the indicator shows.
    await waitFor(() =>
      expect(screen.getByTestId('application-form-builder-save')).toBeEnabled(),
    );
    expect(
      screen.getByTestId('application-form-builder-unsaved-indicator'),
    ).toBeInTheDocument();
  });

  it('one Save after a toggle → EXACTLY one writeFieldConfig carrying application_visible in the one object', async () => {
    await renderBuilder();
    fireEvent.click(screen.getByTestId('application-field-toggle-email'));
    fireEvent.click(screen.getByTestId('application-form-builder-save'));

    // The real saveMembersParameter routes the ONE overlay through the SAM write path exactly once.
    await waitFor(() => expect(mockWriteFieldConfig).toHaveBeenCalledTimes(1));
    // No Flask per-field path is touched (never a parallel write).
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();

    // The single committed body is the one overlay object, carrying the toggled attribute on the
    // field's entry — email is a tenant-added field, so it lands under fields[email].
    const body = mockWriteFieldConfig.mock.calls[0][0] as {
      fields?: Record<string, { application_visible?: boolean }>;
    };
    expect(body.fields?.email?.application_visible).toBe(true);
  });

  it('PRESERVES prior application selections on save — seeds from the SAM overlay, not an empty Flask copy (regression)', async () => {
    // The stored config#fields overlay (served as `field_overlay`) ALREADY has a field on the form
    // from a prior session. Toggling a DIFFERENT field and saving must keep the prior one — the bug
    // was seeding the working overlay empty (from Flask) so a save replaced the SAM row and wiped it.
    const cfgWithPrior: FieldConfig = {
      ...FIELD_CONFIG,
      fields: [
        ...(FIELD_CONFIG.fields ?? []),
        { key: 'notes', functional_group: 'personal', provenance: 'tenant_added', type: 'string', label: { en: 'Notes', nl: 'Notities' } },
      ],
      field_overlay: {
        functional_groups: [{ key: 'personal', order: 1 }],
        fields: {
          // a PRIOR-session selection already on the form
          notes: { type: 'string', functional_group: 'personal', application_visible: true },
          email: { type: 'string', functional_group: 'personal', visible: true },
        },
        fixed_overrides: {},
      },
    };
    await renderBuilder(undefined, cfgWithPrior);

    // Toggle a DIFFERENT field (email) on, then save.
    fireEvent.click(screen.getByTestId('application-field-toggle-email'));
    fireEvent.click(screen.getByTestId('application-form-builder-save'));

    await waitFor(() => expect(mockWriteFieldConfig).toHaveBeenCalledTimes(1));
    const body = mockWriteFieldConfig.mock.calls[0][0] as {
      fields?: Record<string, { application_visible?: boolean }>;
    };
    // BOTH survive: the just-toggled field AND the prior-session selection (not wiped).
    expect(body.fields?.email?.application_visible).toBe(true);
    expect(body.fields?.notes?.application_visible).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/*  Task 3.4 — the form-shell mail commit: ONE config#mail object,     */
/*  seeded-not-clobbered, scope_copy/reply_to referenced-not-authored. */
/* ------------------------------------------------------------------ */
describe('ApplicationFormBuilder — single form-shell mail commit (task 3.4 / R5.5 / §3.1)', () => {
  it('the form-shell save is disabled on a clean load (no form-shell edit yet)', async () => {
    await renderBuilder();
    expect(screen.getByTestId('application-form-shell-save-mail')).toBeDisabled();
    expect(
      screen.queryByTestId('application-form-shell-mail-unsaved'),
    ).not.toBeInTheDocument();
    // Loading never commits mail — authoring is one-object/one-save, never on load.
    expect(mockWriteMailConfig).not.toHaveBeenCalled();
  });

  it('references (displays) the Mail-owned scalars without rendering an editor for them (R5.4)', async () => {
    await renderBuilder();
    // The builder SURFACES that scope-copy/Reply-To live on the Mail sub-tab — a reference note,
    // not an authoring control. There is NO scope-copy toggle / Reply-To input in the builder.
    expect(screen.getByTestId('application-form-shell-mail-ref')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-shell-scope-copy')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-form-shell-reply-to')).not.toBeInTheDocument();
  });

  it('one form-shell Save → EXACTLY one writeMailConfig carrying the SEEDED-and-overlaid body (R5.5)', async () => {
    await renderBuilder();

    // Author a form-shell change (the consent notice text) so the mail body is dirty.
    fireEvent.change(screen.getByTestId('application-form-shell-consent-en'), {
      target: { value: 'I consent to the processing of my data.' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('application-form-shell-save-mail')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('application-form-shell-save-mail'));

    // The real saveMembersMailConfig routes the ONE config#mail body through the SAM write
    // path EXACTLY once — one mail save → one PUT /members/config/mail (R5.5 / Property 8).
    await waitFor(() => expect(mockWriteMailConfig).toHaveBeenCalledTimes(1));
    // The form-shell mail commit is a DISTINCT single write from the field_overlay commit — saving
    // the mail settings never touches the config#fields write path (one object, one save per row).
    expect(mockWriteFieldConfig).not.toHaveBeenCalled();
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();

    // The committed body is SEEDED from the loaded mail_config (never clobbered): every Mail
    // sub-tab scalar is carried through VERBATIM, and the REFERENCED-not-authored scalars
    // (application_scope_copy / mail_reply_to_default) are preserved exactly as loaded (R5.4/R5.5).
    const body = mockWriteMailConfig.mock.calls[0][0] as {
      mail_enabled?: boolean;
      mail_certified?: boolean;
      mail_domain?: string;
      mail_local_part?: string;
      mail_reply_to_default?: string;
      application_scope_copy?: boolean;
      consent_notice?: { version: string; text: Record<string, string> };
    };
    expect(body.mail_enabled).toBe(true);
    expect(body.mail_certified).toBe(true);
    expect(body.mail_domain).toBe('h-dcn.nl');
    expect(body.mail_local_part).toBe('noreply');
    // Referenced-not-authored: preserved verbatim, the builder owns no editor for these.
    expect(body.mail_reply_to_default).toBe('board@h-dcn.nl');
    expect(body.application_scope_copy).toBe(true);
    // The one attribute the form shell DID author is overlaid onto the same single body: a
    // well-formed consent notice with a freshly stamped (non-blank) version and the edited text.
    expect(body.consent_notice?.text.en).toBe('I consent to the processing of my data.');
    expect(typeof body.consent_notice?.version).toBe('string');
    expect(body.consent_notice?.version).toBeTruthy();
  });

  it('the ONE committed body carries BOTH new keys — application_embed_origins AND consent_notice — alongside the preserved Mail scalars (R5.5)', async () => {
    await renderBuilder();

    // Author BOTH form-shell attributes the builder owns on config#mail: switch to iframe embed +
    // declare an allowed origin (application_embed_origins), AND edit the consent notice text. Both
    // must ride on the SAME single committed body — one object, one save (R5.5 / Property 8).
    fireEvent.click(screen.getByTestId('application-form-shell-embed-iframe'));
    fireEvent.change(screen.getByTestId('application-form-shell-embed-origins'), {
      target: { value: 'https://sites.google.com\nhttps://portal.h-dcn.nl' },
    });
    fireEvent.change(screen.getByTestId('application-form-shell-consent-nl'), {
      target: { value: 'Ik ga akkoord met de verwerking van mijn gegevens.' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('application-form-shell-save-mail')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('application-form-shell-save-mail'));

    // Still EXACTLY one mail write — adding a second authored attribute does not add a request.
    await waitFor(() => expect(mockWriteMailConfig).toHaveBeenCalledTimes(1));
    expect(mockWriteFieldConfig).not.toHaveBeenCalled();

    const body = mockWriteMailConfig.mock.calls[0][0] as {
      mail_enabled?: boolean;
      mail_certified?: boolean;
      mail_domain?: string;
      mail_local_part?: string;
      mail_reply_to_default?: string;
      application_scope_copy?: boolean;
      application_embed_origins?: string[];
      consent_notice?: { version: string; text: Record<string, string> };
    };

    // BOTH new keys land on the one body.
    expect(body.application_embed_origins).toEqual([
      'https://sites.google.com',
      'https://portal.h-dcn.nl',
    ]);
    expect(body.consent_notice?.text.nl).toBe('Ik ga akkoord met de verwerking van mijn gegevens.');
    expect(body.consent_notice?.version).toBeTruthy();

    // The Mail sub-tab's scalars are still carried through VERBATIM on that same body (no clobber).
    expect(body.mail_enabled).toBe(true);
    expect(body.mail_certified).toBe(true);
    expect(body.mail_domain).toBe('h-dcn.nl');
    expect(body.mail_local_part).toBe('noreply');
    expect(body.mail_reply_to_default).toBe('board@h-dcn.nl');
    expect(body.application_scope_copy).toBe(true);
  });
});
