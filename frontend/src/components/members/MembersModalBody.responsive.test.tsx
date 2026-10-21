/**
 * Responsive two-column modal layout — interaction tests (members-overview-tweaks task 3.2).
 *
 * Task 3.1 wrapped BOTH member-modal bodies' section containers in
 * `<SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>`:
 *   - EDIT body: `MembersFieldFormBody` (top-level container mapping over `sections`),
 *   - VIEW body: `MembersViewBody` (top-level container mapping over `sections`).
 *
 * These tests assert the responsive contract (Req 4.1–4.4):
 *   - WIDE viewport (≥ Chakra `md`) → the container arranges fields in TWO columns,
 *   - NARROW viewport (< `md`)      → the container arranges fields in a SINGLE column.
 *
 * HOW THE VIEWPORT / BREAKPOINT IS CONTROLLED
 * -------------------------------------------
 * In this repo the whole of `@chakra-ui/react` is replaced by a lightweight mock
 * (`src/__mocks__/chakra-ui-react.tsx`, wired via `resolve.alias` in `vite.config.ts`), so the
 * REAL `SimpleGrid` — and therefore Chakra's real media-query breakpoint resolution — never runs
 * under jsdom. Mocking `window.matchMedia` alone would change nothing, because the mock
 * `SimpleGrid` is a plain `<div>` that drops the `columns` prop. The established repo pattern for
 * asserting Chakra behaviour (see `TenantAdmin/__tests__/ParameterManagement.property.test.tsx`
 * and `TemplateManagement/__tests__/TemplateUpload.test.tsx`) is to `vi.mock('@chakra-ui/react')`
 * off the central mock and override only the component under test.
 *
 * So here we override ONLY `SimpleGrid` with a version that does what the real one does
 * conceptually: it RESOLVES the responsive `columns={{ base, md }}` object against the active
 * breakpoint and renders the resolved track count on the container as `data-columns`. The active
 * breakpoint is driven by a `window.matchMedia` mock keyed on the `md` min-width query — exactly
 * the signal Chakra uses — so a test sets the viewport by toggling whether the `md` query matches
 * (WIDE = matches → `md` value = 2; NARROW = no match → `base` value = 1) BEFORE rendering.
 *
 * The assertion target (`data-columns` === "2" vs "1") is a faithful stand-in for "two-column vs
 * single-column container": it is the exact value the real `SimpleGrid` would resolve its
 * `gridTemplateColumns` track count to at that breakpoint.
 */

import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

/* ------------------------------------------------------------------------ */
/*  Viewport control: a matchMedia-backed breakpoint the mock SimpleGrid     */
/*  resolves `columns={{ base, md }}` against.                               */
/* ------------------------------------------------------------------------ */

/** Whether the viewport is at/above the Chakra `md` breakpoint (WIDE). Toggled per test. */
let mdMatches = false;

/** The `md` min-width media query Chakra uses for the `md` breakpoint (Chakra default 48em). */
const MD_QUERY = '(min-width: 48em)';

function installMatchMedia(): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    // Only the `md` breakpoint query tracks the WIDE/NARROW flag; everything else is NARROW.
    matches: query.includes('48em') ? mdMatches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

/* ------------------------------------------------------------------------ */
/*  Chakra mock: keep the central mock, override SimpleGrid to resolve the   */
/*  responsive `columns` object against the active breakpoint.               */
/* ------------------------------------------------------------------------ */

vi.mock('@chakra-ui/react', async () => {
  const mocks = await vi.importActual<typeof import('@/__mocks__/chakra-ui-react')>(
    '@/__mocks__/chakra-ui-react',
  );
  const React = await import('react');

  /**
   * Resolve `columns={{ base: 1, md: 2 }}` (or a plain number) to the track count for the active
   * breakpoint — WIDE (`md` query matches) picks the `md` value, NARROW falls back to `base`.
   * This mirrors how the real SimpleGrid resolves a responsive value via the `md` media query.
   */
  function resolveColumns(columns: unknown): number {
    if (typeof columns === 'number') return columns;
    if (columns && typeof columns === 'object') {
      const c = columns as Record<string, number>;
      const wide = window.matchMedia(MD_QUERY).matches;
      if (wide && typeof c.md === 'number') return c.md;
      if (typeof c.base === 'number') return c.base;
    }
    return 1;
  }

  const SimpleGrid = ({ children, columns, ...rest }: any) => {
    const resolved = resolveColumns(columns);
    return (
      <div
        data-testid="members-modal-grid"
        data-columns={String(resolved)}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${resolved}, 1fr)`,
        }}
      >
        {children}
      </div>
    );
  };

  return { ...mocks, SimpleGrid };
});

/* ------------------------------------------------------------------------ */
/*  Imports AFTER the mock so the bodies pick up the overridden SimpleGrid.   */
/* ------------------------------------------------------------------------ */

import { render, screen, cleanup } from '@/test-utils';
import '../../i18n';
import { Formik, Form } from 'formik';
import type { FieldConfig, FieldConfigField, Member } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import { MembersViewBody } from './MembersViewBody';
import { groupFieldsBySection, formFields } from './fieldForm';

const t = (k: string) => k;

/** A small resolved field config spanning two functional groups (so there are multiple sections). */
const FIELDS: FieldConfigField[] = [
  { key: 'first_name', group: 'personal', type: 'string', order: 10, functional_group: 'personal' },
  { key: 'last_name', group: 'personal', type: 'string', order: 20, functional_group: 'personal' },
  { key: 'city', group: 'overlay', type: 'string', order: 30, functional_group: 'address' },
  { key: 'country', group: 'overlay', type: 'string', order: 40, functional_group: 'address' },
];

const MEMBER: Member = {
  member_id: 'm-1',
  personal: { first_name: 'Ada', last_name: 'Lovelace' },
  overlay: { city: 'London', country: 'UK' },
} as unknown as Member;

function renderEditBody() {
  const fieldConfig: FieldConfig = { fields: FIELDS };
  const resolved = formFields(fieldConfig);
  const sections = groupFieldsBySection(resolved, fieldConfig.functional_groups);
  return render(
    <Formik initialValues={{}} onSubmit={() => {}}>
      <Form>
        <MembersFieldFormBody
          sections={sections}
          fieldConfig={fieldConfig}
          values={{}}
          callerRoles={[]}
          lang="nl"
          t={t}
          dimensionKey="region"
          regionValues={[]}
          membershipTypes={null}
        />
      </Form>
    </Formik>,
  );
}

function renderViewBody() {
  const fieldConfig: FieldConfig = { fields: FIELDS };
  return render(<MembersViewBody fieldConfig={fieldConfig} member={MEMBER} lang="nl" />);
}

beforeEach(() => {
  installMatchMedia();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Member modal bodies — responsive two-column layout (Req 4.1–4.4)', () => {
  describe('EDIT modal body (MembersFieldFormBody)', () => {
    it('arranges fields in TWO columns on a WIDE viewport (≥ md) — Req 4.1', () => {
      mdMatches = true; // WIDE
      renderEditBody();
      const grid = screen.getByTestId('members-modal-grid');
      expect(grid).toHaveAttribute('data-columns', '2');
      expect(grid).toHaveStyle({ gridTemplateColumns: 'repeat(2, 1fr)' });
    });

    it('arranges fields in a SINGLE column on a NARROW viewport (< md) — Req 4.3', () => {
      mdMatches = false; // NARROW
      renderEditBody();
      const grid = screen.getByTestId('members-modal-grid');
      expect(grid).toHaveAttribute('data-columns', '1');
      expect(grid).toHaveStyle({ gridTemplateColumns: 'repeat(1, 1fr)' });
    });
  });

  describe('VIEW modal body (MembersViewBody)', () => {
    it('arranges fields in TWO columns on a WIDE viewport (≥ md) — Req 4.2', () => {
      mdMatches = true; // WIDE
      renderViewBody();
      const grid = screen.getByTestId('members-modal-grid');
      expect(grid).toHaveAttribute('data-columns', '2');
      expect(grid).toHaveStyle({ gridTemplateColumns: 'repeat(2, 1fr)' });
    });

    it('arranges fields in a SINGLE column on a NARROW viewport (< md) — Req 4.4', () => {
      mdMatches = false; // NARROW
      renderViewBody();
      const grid = screen.getByTestId('members-modal-grid');
      expect(grid).toHaveAttribute('data-columns', '1');
      expect(grid).toHaveStyle({ gridTemplateColumns: 'repeat(1, 1fr)' });
    });
  });
});
