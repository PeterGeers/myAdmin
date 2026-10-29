/**
 * Spec 03b Task 9b.3 - frontend parity guard: membership_type is a NORMAL enum field that owns
 * its vocabulary on EVERY admin surface, and the application-form AUTHORING path makes NO runtime
 * membership-type CATALOG read (`GET /membership-types` / `listMembershipTypes` / a
 * `membershipTypeCatalog` prop). The per-surface behavioural assertions live in the paired suites
 * converted in 9b.1/9b.2 (MembersFieldModal, ApplicationFieldModal, ApplicationFieldAttributes,
 * applicationChoiceSource, applicationPreviewFilter, applicationFilterParity). This file pins the
 * cross-surface INVARIANT by static-reading the authoring sources, so a future re-introduction of
 * the retired catalog dependency fails here rather than silently regressing the all-planes fix.
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4a (membership_type = a regular enum field everywhere).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, '..');

// The application-form AUTHORING surfaces + their pure source helpers. None may read the retired
// membership-type catalog at author time - membership_type sources from the field's own options.
const AUTHORING_SOURCES = [
  'ApplicationFieldModal.tsx',
  'ApplicationFieldAttributes.tsx',
  'ApplicationFormPreview.tsx',
  'ApplicationFormBuilder.tsx',
  'applicationChoiceSource.ts',
  'applicationPreviewFilter.ts',
  'MembersFieldModal.tsx',
];

function read(name: string): string {
  return readFileSync(resolve(SRC, name), 'utf-8');
}

describe('03b 9b.3 - no authoring-path membership-type catalog read', () => {
  it.each(AUTHORING_SOURCES)('%s does not read the retired catalog', (name) => {
    const src = read(name);
    expect(src).not.toMatch(/\blistMembershipTypes\b/);
    expect(src).not.toMatch(/\/membership-types\b/);
    expect(src).not.toMatch(/\bmembershipTypeCatalog\b/);
  });

  it('the field-config modal no longer points at the catalog ("managed elsewhere" is gone)', () => {
    const src = read('MembersFieldModal.tsx');
    expect(src).not.toMatch(/onManageCatalog/);
    expect(src).not.toMatch(/catalogus met lidmaatschapstypes/);
    expect(src).not.toMatch(/managed in the membership-type catalog/);
    // NOTE: the modal's EnumOptionsEditor still binds to the in-memory form field historically
    // named `choices` (`set('choices', ...)`) while SAVING it as the canonical `options` — that is
    // form state, not a wire write. The no-`choices`-on-the-config#fields-WRITE-PATH invariant is
    // enforced authoritatively by the SAM CRUD guard (scripts/check_sam_config_crud.py), so this
    // frontend guard does not assert on the form-state name.
  });
});
