/**
 * Shared test helpers for driving the `LazySelect` combobox (building block at
 * `frontend/src/components/common/LazySelect.tsx`, spec `.kiro/specs/Common/Frameworks/lazy-select/`).
 *
 * The Members add/edit modals migrated every enum/reference/scope dropdown — including
 * `membership_type` and the `region` scope dimension — from a native `<select name="…">`/`<option>`
 * to the shared `LazySelect` combobox (see `MembersFieldFormBody.tsx`). A `LazySelect` renders a
 * `role="combobox"` trigger inside a `data-testid="${name}-lazyselect"` container; its
 * `role="option"` children exist only AFTER the combobox is opened (and, for any async-sourced
 * LazySelect, only after that source resolves). Spec 03b: `membership_type` is now an EAGER
 * field-options source like every other enum — no async catalog feed.
 *
 * These helpers centralize the "find trigger → open → (await async source) → read/pick option" flow
 * so the next control/LazySelect refactor is a one-line helper change rather than scattered query
 * updates across every consuming test (Lessons #1/#2 of the 2026-09-28 full-test-suite fixes).
 *
 * They are framework-agnostic over the specific field: pass the LazySelect `name` (e.g.
 * `membership_type`, `region`, `tier`) and they resolve the `${name}-lazyselect` trigger.
 */

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
 * Open the `membership_type` LazySelect and return its listbox. Spec 03b: membership_type is now a
 * normal enum field fed EAGERLY from the field config's own `options` (the live catalog is retired),
 * so there is no async source to await — this just opens the combobox. The optional second argument
 * is retained for call-site compatibility with the old async-catalog signature and is ignored.
 */
export async function openMembershipType(
  _ignored?: unknown,
  container?: HTMLElement,
): Promise<HTMLElement> {
  return openLazySelect('membership_type', { container });
}

/**
 * Pick a `membership_type` option from the eager field-options dropdown. The optional `_ignored`
 * middle argument preserves the old `(optionName, spy, container)` call shape and is unused.
 */
export async function pickMembershipType(
  optionName: string,
  _ignored?: unknown,
  container?: HTMLElement,
): Promise<void> {
  const listbox = await openMembershipType(_ignored, container);
  const option = await within(listbox).findByRole('option', { name: optionName });
  fireEvent.mouseDown(option);
}
