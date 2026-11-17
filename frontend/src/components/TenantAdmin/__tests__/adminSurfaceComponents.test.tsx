/**
 * adminSurfaceComponents — component-map totality (Property 7).
 *
 * Feature: admin-surface-registry
 * The map MUST be total over every id the backend registry can emit: a missing
 * component must fail a test, never silently drop a surface at runtime. The
 * checked-in mirror below is the contract shared with
 * backend/src/services/admin_surface_registry.py.
 *
 * Children are stubbed so this test asserts the MAP (keys), not the trees.
 *
 * Validates: Requirements 5.2
 */

import { describe, it, expect, vi } from 'vitest';
import fc from 'fast-check';
import enAdmin from '../../../locales/en/admin.json';
import nlAdmin from '../../../locales/nl/admin.json';

vi.mock('../UserManagement', () => ({ default: () => null }));
vi.mock('../FunctionsTab', () => ({ default: () => null }));
vi.mock('../FinancialTab', () => ({ default: () => null }));
vi.mock('../MembersAdminPanel', () => ({ default: () => null }));
vi.mock('../StorageTab', () => ({ default: () => null }));
vi.mock('../../../pages/MediaAssetAdminPage', () => ({ default: () => null }));
vi.mock('../TemplateManagement/TemplateManagement', () => ({ default: () => null }));
vi.mock('../TenantInfoTab', () => ({ default: () => null }));
vi.mock('../SenderSettingsTab', () => ({ default: () => null }));
vi.mock('../LandingPage', () => ({ LandingPageEditor: () => null }));
vi.mock('../AdvancedTab', () => ({ default: () => null }));
vi.mock('../../pivot/PivotBuilderWithPreview', () => ({
  PivotBuilderWithPreview: () => null,
}));
vi.mock('@chakra-ui/react', () => ({
  Box: ({ children }: { children?: React.ReactNode }) => children ?? null,
  Text: ({ children }: { children?: React.ReactNode }) => children ?? null,
}));

/**
 * Checked-in mirror of ADMIN_SURFACE_REGISTRY ids, in registry declaration order
 * (backend/src/services/admin_surface_registry.py).
 */
const REGISTRY_IDS = [
  'users',
  'tenant-info',
  'sender',
  'landing',
  'financial',
  'members',
  'functions',
  'pivot',
  'storage',
  'media',
  'templates',
  'advanced',
];

import { adminSurfaceComponents } from '../adminSurfaceComponents';

describe('adminSurfaceComponents — totality (Property 7)', () => {
  it('defines a component for every id in the registry mirror', () => {
    for (const id of REGISTRY_IDS) {
      expect(
        typeof adminSurfaceComponents[id],
        `missing component for surface id "${id}"`,
      ).toBe('function');
    }
  });

  it('exposes exactly the registry ids and nothing else', () => {
    expect(Object.keys(adminSurfaceComponents).sort()).toEqual(
      [...REGISTRY_IDS].sort(),
    );
  });

  it('is total for every subset the backend can emit (fast-check, 100 runs)', () => {
    fc.assert(
      fc.property(fc.subarray(REGISTRY_IDS), (ids) => {
        // Every surface the backend can derive must resolve to a component.
        for (const id of ids) {
          if (typeof adminSurfaceComponents[id] !== 'function') {
            return false;
          }
        }
        return true;
      }),
      { numRuns: 100 },
    );
  });

  it('has no id outside the mirror for any generated unknown id (fast-check)', () => {
    fc.assert(
      fc.property(
        fc.stringMatching(/^[a-z][a-z0-9-]{0,20}$/),
        (candidate) => {
          const known = REGISTRY_IDS.includes(candidate);
          const mapped = adminSurfaceComponents[candidate] !== undefined;
          // A generated id is mapped if and only if it is a known registry id.
          return known === mapped;
        },
      ),
      { numRuns: 100 },
    );
  });
});

/**
 * Checked-in mirror of each surface's label_key (backend admin_surface_registry.py).
 * The dashboard renders `t(label_key)` with NO fallback, so a missing translation
 * shows the raw key in the tab bar — every key must exist in every locale.
 */
const SURFACE_LABEL_KEYS: Record<string, string> = {
  users: 'tenantAdmin.tabs.users',
  'tenant-info': 'tenantAdmin.tabs.tenantInfo',
  sender: 'tenantAdmin.tabs.senderSettings',
  landing: 'tenantAdmin.tabs.landingPage',
  financial: 'tenantAdmin.tabs.financial',
  members: 'tenantAdmin.tabs.membersConfig',
  functions: 'tenantAdmin.tabs.functions',
  pivot: 'tenantAdmin.tabs.pivotViews',
  storage: 'tenantAdmin.tabs.storage',
  media: 'tenantAdmin.tabs.mediaAssets',
  templates: 'tenantAdmin.tabs.templates',
  advanced: 'tenantAdmin.tabs.advanced',
};

function resolveDotted(source: unknown, dotted: string): unknown {
  return dotted.split('.').reduce<unknown>((acc, part) => {
    if (acc && typeof acc === 'object' && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, source);
}

describe('adminSurfaceComponents — every surface label resolves in every locale', () => {
  it.each([
    ['en', enAdmin],
    ['nl', nlAdmin],
  ])('has a non-empty tab label for all twelve surfaces (%s)', (_locale, locale) => {
    for (const [id, key] of Object.entries(SURFACE_LABEL_KEYS)) {
      const value = resolveDotted(locale, key);
      expect(typeof value, `surface "${id}" is missing translation "${key}"`).toBe(
        'string',
      );
      expect((value as string).trim().length).toBeGreaterThan(0);
    }
  });

  it('covers every surface in the component map (no surface without a label)', () => {
    for (const id of Object.keys(adminSurfaceComponents)) {
      expect(
        typeof SURFACE_LABEL_KEYS[id],
        `no label_key mirror for surface "${id}"`,
      ).toBe('string');
    }
  });
});
