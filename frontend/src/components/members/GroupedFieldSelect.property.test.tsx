/**
 * Property-based test for GroupedFieldSelect
 * (member-analytics-pivot-filter-operators, task 5.3).
 *
 * Feature: member-analytics-pivot-filter-operators
 * Property 12: GroupedFieldSelect grouping mirrors the checklist
 * Validates: Requirements 1.1, 1.2, 2.4
 *
 * For any field set, functional-group catalog, and language, the option groups
 * and in-group ordering `GroupedFieldSelect` RENDERS equal the sections
 * `sectionFields()` produces for the same inputs — same catalog (group) order,
 * same alphabetical-within-group order, same ungrouped-last fallback (rendered
 * WITHOUT an enclosing <optgroup>), and no field omitted. This is the SAME
 * `sectionFields()` the checklist consumes (R2.4), so the DOM structure is
 * exactly the checklist's grouping, projected into native <optgroup>/<option>s.
 *
 * Uses fast-check 4.4.0 with 100 sampled inputs per property (DOM render +
 * unmount per input, so we sample-and-loop rather than nest render in an async
 * fc.assert predicate — the established convention for render-based property
 * tests in this repo).
 */
import fc from 'fast-check';
import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@/test-utils';
import { GroupedFieldSelect } from './GroupedFieldSelect';
import { sectionFields, resolveLabel, DEFAULT_FG_SECTION_KEY } from './FieldChecklist';
import type { FieldConfigField, FunctionalGroup } from '../../types/members';

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Generators
//
// We constrain to the input space the control actually sees: a candidate field
// set (key + optional bilingual label + optional functional_group) and a
// functional-group catalog (key + optional bilingual label + order). We keep
// the universes of keys and group-keys small so collisions, dangling groups,
// and tie-breaking on equal labels all occur frequently.
// ---------------------------------------------------------------------------

/** A short label fragment — kept small so equal/near-equal labels recur. */
const labelFrag = fc.constantFrom('a', 'b', 'c', 'Z', 'alpha', 'Beta', 'gamma', '');

/** An optional bilingual label (sometimes absent → resolveLabel falls back to key). */
const localizedLabelArb = fc.option(
  fc.record({
    nl: fc.option(labelFrag, { nil: undefined }),
    en: fc.option(labelFrag, { nil: undefined }),
  }),
  { nil: undefined },
);

/** Group keys: a small universe, some of which may be dangling (not in catalog). */
const groupKeyArb = fc.constantFrom('g1', 'g2', 'g3', 'ghost', undefined);

/** A candidate field. Keys drawn from a small pool so ordering/collisions recur. */
const fieldArb: fc.Arbitrary<FieldConfigField> = fc.record({
  key: fc.constantFrom('k1', 'k2', 'k3', 'k4', 'k5', 'k6'),
  label: localizedLabelArb,
  functional_group: groupKeyArb,
}) as fc.Arbitrary<FieldConfigField>;

/** A unique-by-key field list (dedupe so React option keys stay stable). */
const fieldsArb: fc.Arbitrary<FieldConfigField[]> = fc
  .array(fieldArb, { minLength: 0, maxLength: 6 })
  .map((fields) => {
    const seen = new Set<string>();
    return fields.filter((f) => (seen.has(f.key) ? false : (seen.add(f.key), true)));
  });

/** One catalog entry. */
const catalogEntryArb: fc.Arbitrary<FunctionalGroup> = fc.record({
  key: fc.constantFrom('g1', 'g2', 'g3'),
  label: localizedLabelArb,
  order: fc.option(fc.integer({ min: -3, max: 3 }), { nil: undefined }),
}) as fc.Arbitrary<FunctionalGroup>;

/** A unique-by-key catalog (sometimes undefined → ungrouped-only rendering). */
const catalogArb: fc.Arbitrary<FunctionalGroup[] | undefined> = fc.option(
  fc.array(catalogEntryArb, { minLength: 0, maxLength: 3 }).map((cat) => {
    const seen = new Set<string>();
    return cat.filter((g) => (seen.has(g.key) ? false : (seen.add(g.key), true)));
  }),
  { nil: undefined },
);

const langArb = fc.constantFrom('nl', 'en', 'de');

// ---------------------------------------------------------------------------
// DOM extraction: read the rendered <select> back into the same section shape
// `sectionFields()` produces — a list of { groupLabel|null, fieldKeys[] }.
//
// A grouped section is an <optgroup> (groupLabel = its label attribute, in DOM
// order); the ungrouped fallback is a run of bare <option>s that are DIRECT
// children of the <select> (no enclosing <optgroup>). The leading placeholder
// option (value='') is skipped — it is not a field.
// ---------------------------------------------------------------------------

interface RenderedSection {
  groupLabel: string | null; // null = ungrouped (no <optgroup>)
  fieldKeys: string[];
}

function extractRenderedSections(select: HTMLSelectElement): RenderedSection[] {
  const out: RenderedSection[] = [];
  let ungroupedRun: string[] | null = null;

  for (const child of Array.from(select.children)) {
    if (child.tagName === 'OPTION') {
      const value = (child as HTMLOptionElement).value;
      if (value === '') continue; // placeholder — not a field
      if (ungroupedRun === null) ungroupedRun = [];
      ungroupedRun.push(value);
    } else if (child.tagName === 'OPTGROUP') {
      // Flush any pending ungrouped run before the group (should not normally
      // interleave, but keep extraction faithful to DOM order).
      if (ungroupedRun !== null) {
        out.push({ groupLabel: null, fieldKeys: ungroupedRun });
        ungroupedRun = null;
      }
      const optgroup = child as HTMLOptGroupElement;
      const keys = Array.from(optgroup.children)
        .filter((c) => c.tagName === 'OPTION')
        .map((c) => (c as HTMLOptionElement).value);
      out.push({ groupLabel: optgroup.label, fieldKeys: keys });
    }
  }
  if (ungroupedRun !== null) out.push({ groupLabel: null, fieldKeys: ungroupedRun });
  return out;
}

/** The EXPECTED rendered shape, derived directly from `sectionFields()`. */
function expectedSections(
  fields: FieldConfigField[],
  catalog: FunctionalGroup[] | undefined,
  lang: string,
): RenderedSection[] {
  return sectionFields(fields, catalog, lang).map((section) => ({
    // The ungrouped fallback renders WITHOUT an <optgroup> (groupLabel null);
    // a grouped section renders an <optgroup> whose label is the resolved
    // (bilingual) heading, exactly as the component does.
    groupLabel:
      section.key === DEFAULT_FG_SECTION_KEY
        ? null
        : resolveLabel(section.label, lang, section.key),
    fieldKeys: section.fields.map((f) => f.key),
  }));
}

describe('GroupedFieldSelect — Property 12: grouping mirrors the checklist', () => {
  it('renders optgroup/option structure equal to sectionFields() for any inputs', () => {
    const inputs = fc.sample(
      fc.tuple(fieldsArb, catalogArb, langArb),
      100,
    );

    for (const [fields, catalog, lang] of inputs) {
      const { container } = render(
        <GroupedFieldSelect
          fields={fields}
          value=""
          onChange={() => {}}
          functionalGroups={catalog}
          lang={lang}
          ariaLabel="field"
          placeholder="pick a field"
          testId="gfs"
        />,
      );

      const select = container.querySelector('select') as HTMLSelectElement;
      expect(select).not.toBeNull();

      const rendered = extractRenderedSections(select);
      const expected = expectedSections(fields, catalog, lang);

      // Same group order, same group labels, same in-group field order, same
      // ungrouped-last fallback (groupLabel null), and no field omitted.
      expect(rendered).toEqual(expected);

      // Belt-and-suspenders: no field is dropped (every candidate key appears
      // exactly once across the rendered sections).
      const renderedKeys = rendered.flatMap((s) => s.fieldKeys).sort();
      const candidateKeys = fields.map((f) => f.key).sort();
      expect(renderedKeys).toEqual(candidateKeys);

      cleanup();
    }
  });
});
