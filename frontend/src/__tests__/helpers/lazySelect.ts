/**
 * Shared test helpers for driving the `LazySelect` combobox (building block at
 * `frontend/src/components/common/LazySelect.tsx`, spec `.kiro/specs/Common/Frameworks/lazy-select/`).
 *
 * The Members add/edit modals migrated every enum/reference/scope dropdown — including
 * `membership_type` and the `region` scope dimension — from a native `<select name="…">`/`<option>`
 * to the shared `LazySelect` combobox (see `MembersFieldFormBody.tsx`). A `LazySelect` renders a
 * `role="combobox"` trigger inside a `data-testid="${name}-lazyselect"` container; its
 * `role="option"` children exist only AFTER the combobox is opened, and — for an async source such
 * as `membership_type` (`optionsDepKey="membership_type"`, fed by `listMembershipTypes(true)`) —
 * only after that source resolves.
 *
 * These helpers centralize the "find trigger → open → (await async source) → read/pick option" flow
 * so the next control/LazySelect refactor is a one-line helper change rather than scattered query
 * updates across every consuming test (Lessons #1/#2 of the 2026-09-28 full-test-suite fixes).
 *
 * They are framework-agnostic over the specific field: pass the LazySelect `name` (e.g.
 * `membership_type`, `region`, `tier`) and they resolve the `${name}-lazyselect` trigger.
 */

import { expect } from 'vitest';
import { screen, fireEvent, within, waitFor } from '@/test-utils';

/** The combobox trigger element for the LazySelect registered under `name` (throws if absent). */
export function getLazySelectTrigger(name: string, container?: HTMLElement): HTMLElement {
  const scope = container ?? document.body;
  const root = within(scope).getByTestId(`${name}-lazyselect`);
  const trigger = root.querySelector('[role="combobox"]') as HTMLElement | null;
  if (!trigger) {
    throw new Error(`No LazySelect combobox trigger found for name="${name}"`);
  }
  return trigger;
}

/** The at-rest displayed value/label text shown on the LazySelect trigger (never the open list). */
export function getLazySelectDisplay(name: string, container?: HTMLElement): string {
  const scope = container ?? document.body;
  return within(scope).getByTestId(`${name}-lazyselect`).textContent ?? '';
}

/**
 * Open the LazySelect `name` and return its listbox. When the source is async (e.g.
 * `membership_type`), pass `awaitSource` to wait for the resolution before reading options.
 */
export async function openLazySelect(
  name: string,
  opts: { container?: HTMLElement; awaitSource?: () => void } = {},
): Promise<HTMLElement> {
  const trigger = getLazySelectTrigger(name, opts.container);
  fireEvent.click(trigger);
  if (opts.awaitSource) {
    await waitFor(() => opts.awaitSource!());
  }
  return screen.getByRole('listbox');
}

/**
 * Open the LazySelect `name` and pick the option whose accessible name is `optionName`, driving the
 * component's `onChange` (which the Members form wires to Formik `setFieldValue(name, …)`).
 * Selection uses `mouseDown` — the option handler fires on mousedown, before the trigger's
 * outside-click/blur close (see `LazySelect.tsx`). Returns after the option has been clicked.
 */
export async function pickLazySelectOption(
  name: string,
  optionName: string,
  opts: { container?: HTMLElement; awaitSource?: () => void } = {},
): Promise<void> {
  const listbox = await openLazySelect(name, opts);
  const option = await within(listbox).findByRole('option', { name: optionName });
  fireEvent.mouseDown(option);
}

/**
 * Convenience: open the `membership_type` LazySelect (async catalog source) and return its listbox
 * once `listMembershipTypes(true)` has run. Pass the mocked `listMembershipTypes` spy.
 */
export async function openMembershipType(
  listMembershipTypesSpy: { mock: { calls: unknown[][] } } | (() => void),
  container?: HTMLElement,
): Promise<HTMLElement> {
  const awaitSource =
    typeof listMembershipTypesSpy === 'function'
      ? (listMembershipTypesSpy as () => void)
      : () => {
        // Assert the async catalog feed has been requested with active_only=true.
        expect(
          (listMembershipTypesSpy as { mock: { calls: unknown[][] } }).mock.calls.some(
            (c) => c[0] === true,
          ),
        ).toBe(true);
      };
  return openLazySelect('membership_type', { container, awaitSource });
}

/** Pick a `membership_type` option once the async catalog has resolved. */
export async function pickMembershipType(
  optionName: string,
  listMembershipTypesSpy: { mock: { calls: unknown[][] } },
  container?: HTMLElement,
): Promise<void> {
  const listbox = await openMembershipType(listMembershipTypesSpy, container);
  const option = await within(listbox).findByRole('option', { name: optionName });
  fireEvent.mouseDown(option);
}
