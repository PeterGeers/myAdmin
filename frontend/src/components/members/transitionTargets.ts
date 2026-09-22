/**
 * Allowed lifecycle-transition targets — sourced FROM THE MODULE (design C2),
 * never hardcoded in the SPA (R8.5).
 *
 * The membership lifecycle is a declarative state machine the MODULE owns
 * (`sam/members/domain/lifecycle_config.py`). The SPA must not embed a status
 * vocabulary or a transition graph: the set of states a member may move to is a
 * function of (1) the member's CURRENT state and (2) the tenant's lifecycle as
 * described by the module response (the resolved field config's optional
 * `lifecycle` block, `GET /members/field-config`).
 *
 * This helper reads the allowed target states for a given current state out of
 * that module-provided lifecycle. It accepts either shape the module may
 * project:
 *   - `allowed_transitions`: `{ <fromState>: [<toState>, ...] }` (preferred);
 *   - `transitions`: a flat edge list `[{ from, to }, ...]`.
 *
 * When the module describes no lifecycle (or no edges from the current state) it
 * returns an EMPTY list — no targets are offered (deny-by-default at the UI).
 * The module stays authoritative: it re-validates every requested transition and
 * answers 409 with reasons on a denial, so the UI candidate list is only a
 * convenience, never the authority.
 *
 * _Requirements: R8.5, R8.6_
 */

import type { LifecycleConfigShape } from '../../types/members';

/**
 * The allowed target states reachable from `currentState`, per the module's
 * lifecycle description. Returns `[]` when there is no lifecycle, no current
 * state, or no declared edge from it — never a hardcoded fallback.
 *
 * @param lifecycle    - the module-provided lifecycle (field-config `lifecycle`).
 * @param currentState - the member's current lifecycle state (e.g. "active").
 */
export function allowedTargetsFor(
  lifecycle: LifecycleConfigShape | null | undefined,
  currentState: string | null | undefined,
): string[] {
  if (!lifecycle || !currentState) return [];

  // Preferred: an explicit `fromState -> [toState, ...]` map.
  const map = lifecycle.allowed_transitions;
  if (map && Array.isArray(map[currentState])) {
    return dedupe(map[currentState]);
  }

  // Alternative: a flat edge list `[{ from, to }]`.
  const edges = lifecycle.transitions;
  if (Array.isArray(edges)) {
    return dedupe(
      edges.filter((e) => e && e.from === currentState).map((e) => e.to),
    );
  }

  return [];
}

/**
 * The full set of target states across ALL current states, per the module's
 * lifecycle — used by the BULK transition modal, which acts over a heterogeneous
 * selection whose members may sit in different current states. Returns `[]` when
 * the module describes no lifecycle. The module still re-validates each member's
 * transition individually (a target not reachable for a given member is simply
 * denied for that member).
 *
 * @param lifecycle - the module-provided lifecycle (field-config `lifecycle`).
 */
export function allTargetStates(
  lifecycle: LifecycleConfigShape | null | undefined,
): string[] {
  if (!lifecycle) return [];

  const collected: string[] = [];

  const map = lifecycle.allowed_transitions;
  if (map) {
    Object.values(map).forEach((tos) => {
      if (Array.isArray(tos)) collected.push(...tos);
    });
  }

  const edges = lifecycle.transitions;
  if (Array.isArray(edges)) {
    edges.forEach((e) => {
      if (e && typeof e.to === 'string') collected.push(e.to);
    });
  }

  // Fall back to the declared state vocabulary only when the module gave one and
  // no edges were described — still module-sourced, never a hardcoded list.
  if (collected.length === 0 && Array.isArray(lifecycle.allowed_states)) {
    collected.push(...lifecycle.allowed_states);
  }

  return dedupe(collected);
}

/**
 * Whether moving to `targetState` requires the guard-context approval flag
 * (h-dcn's `context.approved`), per the module's lifecycle. The module lists the
 * states/edges that need it in `requires_approval`; absent means no approval
 * fact is required. Never hardcoded.
 */
export function targetRequiresApproval(
  lifecycle: LifecycleConfigShape | null | undefined,
  targetState: string | null | undefined,
  fromState?: string | null,
): boolean {
  if (!lifecycle || !targetState) return false;
  const requires = lifecycle.requires_approval;
  if (!Array.isArray(requires)) return false;
  if (requires.includes(targetState)) return true;
  // Also match an explicit `<from>-><to>` edge form.
  if (fromState && requires.includes(`${fromState}->${targetState}`)) return true;
  return false;
}

/** De-duplicate while preserving first-seen order; drops empties/non-strings. */
function dedupe(values: unknown[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  values.forEach((v) => {
    if (typeof v === 'string' && v && !seen.has(v)) {
      seen.add(v);
      out.push(v);
    }
  });
  return out;
}
