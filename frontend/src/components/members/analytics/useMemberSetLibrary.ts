/**
 * useMemberSetLibrary — the saved-set + preferred-list LIBRARY concerns of the
 * Pivot Views panel, extracted from `MemberPivotViews.tsx` (code-quality split
 * 2026-10-28, task 5).
 *
 * This hook carries ZERO behaviour change: it is the verbatim saved-set /
 * preferred-list logic the panel held inline — the saved member sets fetched
 * from the Members API (`savedModels`, loaded on mount + re-fetchable via
 * `refreshSavedModels`), the per-user preferred ref list (loaded on mount,
 * persisted as a full replace), and every derivation built on them: the flat
 * `sets`, the `dropdownSets` (preferred only, in saved order), and the full
 * `filteredLibraryItems` (alphabetical, name-filtered). It also owns the
 * preferred-list mutations (`handleAddRef`, `handleRemovePreferred`,
 * `handleMovePreferred`).
 *
 * All of it stays driven by the same inputs the component already had, so the
 * public component API and every rendered testid / i18n key are unchanged.
 *
 * @module components/members/analytics/useMemberSetLibrary
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useToast } from '@chakra-ui/react';
import type { MemberAnalyticsSetSummary } from '../../../types/members';
import {
  listAnalyticsSets,
  getPreferredList,
  savePreferredList,
} from '../../../services/membersApiService';
import {
  type SelectableSet,
  MODEL_PREFIX,
  SET_PREFIX,
  optionValueToRef,
} from './memberPivotViewsHelpers';

/** The members-namespace translator (key + optional interpolation bag → string). */
type TFunction = (key: string, options?: Record<string, unknown>) => string;

/** A resolved library row (as the library modal consumes it). */
export interface LibraryItem {
  optionValue: string;
  label: string;
  ref: string | null;
  alreadyPreferred: boolean;
  savedSetId: string | null;
}

export interface UseMemberSetLibrary {
  savedModels: MemberAnalyticsSetSummary[];
  refreshSavedModels: () => Promise<MemberAnalyticsSetSummary[]>;
  sets: SelectableSet[];
  dropdownSets: SelectableSet[];
  libraryFilter: string;
  setLibraryFilter: (value: string) => void;
  filteredLibraryItems: LibraryItem[];
  isSavingPreferred: boolean;
  handleAddRef: (ref: string | null) => void;
  handleRemovePreferred: (ref: string) => void;
  handleMovePreferred: (ref: string, delta: -1 | 1) => void;
}

/**
 * The saved-set + preferred-list library bundle for the Pivot Views panel. Keeps
 * all the library state + derivations + mutations cohesive and out of the (very
 * large) component body, without changing any observable behaviour.
 */
export function useMemberSetLibrary(t: TFunction): UseMemberSetLibrary {
  const toast = useToast();

  // Saved member sets (R4.6/R5.2) — fetched from the Members API, which returns
  // ONLY this tenant's member sets (member-owned DynamoDB store, F-012). No
  // client-side data-source filter is needed: the Members Lambda never returns
  // another module's sets.
  const [savedModels, setSavedModels] = useState<MemberAnalyticsSetSummary[]>([]);

  // --- Preferred list state (R11.2 layer 2). ---------------------------------
  // One ordered list of TAGGED references per USER (keyed server-side on the
  // authenticated Cognito `sub` — user ≠ member, R11.1; the client never sends a
  // sub). `preset:<key>` references a predefined preset (code), `set:<id>` a
  // tenant-shared saved set. Loaded on mount; a load failure degrades to an empty
  // list (never a crash). Saving is a FULL replace (one list per user).
  const [preferredRefs, setPreferredRefs] = useState<string[]>([]);
  const [isSavingPreferred, setIsSavingPreferred] = useState(false);

  // Name-filter input for the "All sets" library list (find-by-name). Substring,
  // case-insensitive; the alphabetical order is preserved.
  const [libraryFilter, setLibraryFilter] = useState('');

  // Refresh the saved member sets from the Members API (the module-owned
  // DynamoDB store, F-012). The Lambda returns ONLY this tenant's member sets, so
  // no client-side data-source filter is needed (R5.2 — tenant-safe by
  // construction). A fetch failure degrades to presets-only (the predefined sets
  // stay usable) — never a crash (design C4 "Error handling": saved-set CRUD
  // failure → presets still usable). Called on mount AND after every
  // save/update/delete so lifecycle changes appear in the dropdown immediately
  // (task 7.5).
  const refreshSavedModels = useCallback(async (): Promise<MemberAnalyticsSetSummary[]> => {
    try {
      const sets = await listAnalyticsSets();
      setSavedModels(sets);
      return sets;
    } catch {
      setSavedModels([]);
      return [];
    }
  }, []);

  useEffect(() => {
    let active = true;
    listAnalyticsSets()
      .then((sets) => {
        if (!active) {
          return;
        }
        setSavedModels(sets);
      })
      .catch(() => {
        if (active) {
          setSavedModels([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // Load the user's preferred list on mount (R11.2). Keyed server-side on the
  // authenticated sub; an unset list returns empty refs. A load failure degrades
  // to an empty list — the preferred panel just shows the empty state, never a
  // crash (design C9 "Error handling": preferred-list read failure → empty).
  useEffect(() => {
    let active = true;
    getPreferredList()
      .then((pref) => {
        if (active) {
          setPreferredRefs(pref.refs);
        }
      })
      .catch(() => {
        if (active) {
          setPreferredRefs([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // The flat list of selectable sets, keyed by a collision-free option value.
  // Saved-member-sets only (the preset subsystem was removed): every view the
  // user runs is one they built in the generic Dynamic Pivot Views mechanism and
  // saved (group/filter on field names directly).
  const sets: SelectableSet[] = useMemo(() => {
    return savedModels.map((model) => ({
      optionValue: `${MODEL_PREFIX}${model.id}`,
      // A saved model's name is user-authored tenant data, shown as-is.
      label: model.name,
      source: 'model' as const,
      modelId: model.id,
    }));
  }, [savedModels]);

  // --- Preferred list resolution + actions (R11.2). --------------------------

  // Resolve the ordered preferred refs into displayable rows, resolving
  // `preset:<key>` against the materialized presets and `set:<id>` against this
  // tenant's saved sets. A DANGLING ref (a set another user deleted, or a preset
  // no longer available for the tenant) is SKIPPED silently (R11.6) — never an
  // error. The resolved `optionValue` is the dropdown's own scheme so Run can
  // reuse the existing select + execute path.
  const preferredItems = useMemo(() => {
    const items: { ref: string; optionValue: string; label: string }[] = [];
    for (const ref of preferredRefs) {
      if (ref.startsWith(SET_PREFIX)) {
        const id = ref.slice(SET_PREFIX.length);
        const model = savedModels.find((m) => m.id === id);
        if (model) {
          items.push({
            ref,
            optionValue: `${MODEL_PREFIX}${id}`,
            label: model.name,
          });
        }
        continue; // dangling set ref → skip (R11.6)
      }
      // A legacy `preset:<key>` ref (the removed preset subsystem) resolves to
      // nothing and is skipped silently (R11.6) — never an error.
    }
    return items;
  }, [preferredRefs, savedModels]);

  // The sets offered in the "Select a set" DROPDOWN: ONLY the user's preferred
  // list (in their saved order) — the everyday launcher. NO prefab/predefined
  // sets appear here unless the user has explicitly added them to the preferred
  // list. The full library (every prefab + custom set) lives behind the "All
  // sets" modal, where any set — including the jubilee/new-members selector
  // presets — can be Run directly or added to the preferred list. Each entry
  // resolves back to its full `SelectableSet` so the existing selection logic
  // (year selectors, Save-as / Update / Delete) is unchanged for a preferred set.
  const dropdownSets: SelectableSet[] = useMemo(() => {
    const byOption = new Map(sets.map((s) => [s.optionValue, s]));
    const result: SelectableSet[] = [];
    const seen = new Set<string>();
    // Preferred sets only, in the user's saved order.
    for (const item of preferredItems) {
      const set = byOption.get(item.optionValue);
      if (set && !seen.has(set.optionValue)) {
        result.push(set);
        seen.add(set.optionValue);
      }
    }
    return result;
  }, [sets, preferredItems]);

  // The FULL LIBRARY (issue 2): every preset + every saved set, ALPHABETICALLY
  // sorted by display label (localeCompare, case-insensitive), each tagged with
  // whether it is already in the preferred list (so Add can disable + show
  // "already added"). The library reuses the dropdown's `sets` (which already
  // flattens presets + saved models to {optionValue,label,source}) so a Run/Add
  // from the library speaks the same option-value scheme as everything else.
  const libraryItems = useMemo<LibraryItem[]>(() => {
    const items = sets.map((s) => {
      const ref = optionValueToRef(s.optionValue);
      return {
        optionValue: s.optionValue,
        label: s.label,
        ref,
        alreadyPreferred: ref !== null && preferredRefs.includes(ref),
        // A custom saved set can be permanently DELETED from the library.
        // `savedSetId` is the backend set_id for the saved set.
        savedSetId: typeof s.modelId === 'string' ? s.modelId : null,
      };
    });
    return items.sort((a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }),
    );
  }, [sets, preferredRefs]);

  // The library narrowed by its own name filter (substring, case-insensitive);
  // the alphabetical order is preserved.
  const filteredLibraryItems = useMemo<LibraryItem[]>(() => {
    const needle = libraryFilter.trim().toLowerCase();
    if (needle === '') {
      return libraryItems;
    }
    return libraryItems.filter((item) => item.label.toLowerCase().includes(needle));
  }, [libraryItems, libraryFilter]);

  // Persist a new ordered ref list (a FULL replace — one list per user, R11.2).
  // Optimistically updates local state, then saves; on failure it reloads the
  // server copy and toasts, so the UI never drifts from the stored list.
  const persistPreferred = useCallback(
    async (nextRefs: string[]) => {
      setIsSavingPreferred(true);
      const previous = preferredRefs;
      setPreferredRefs(nextRefs);
      try {
        const saved = await savePreferredList(nextRefs);
        setPreferredRefs(saved.refs);
        toast({ title: t('analytics.pivotViews.preferred.saved'), status: 'success' });
      } catch {
        setPreferredRefs(previous);
        toast({
          title: t('analytics.pivotViews.preferred.saveError'),
          status: 'error',
        });
      } finally {
        setIsSavingPreferred(false);
      }
    },
    [preferredRefs, toast, t],
  );

  // Add a tagged ref to the preferred list (append, no duplicates). The single
  // mutation both the dropdown's Add button and a library row's "Add to my list"
  // call (issue 2).
  const handleAddRef = useCallback(
    (ref: string | null) => {
      if (!ref || preferredRefs.includes(ref)) {
        return;
      }
      void persistPreferred([...preferredRefs, ref]);
    },
    [preferredRefs, persistPreferred],
  );

  // Remove a ref from the preferred list.
  const handleRemovePreferred = useCallback(
    (ref: string) => {
      void persistPreferred(preferredRefs.filter((r) => r !== ref));
    },
    [preferredRefs, persistPreferred],
  );

  // Reorder a ref one position up (-1) or down (+1) in the preferred list.
  const handleMovePreferred = useCallback(
    (ref: string, delta: -1 | 1) => {
      const index = preferredRefs.indexOf(ref);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= preferredRefs.length) {
        return;
      }
      const next = [...preferredRefs];
      [next[index], next[target]] = [next[target], next[index]];
      void persistPreferred(next);
    },
    [preferredRefs, persistPreferred],
  );

  return {
    savedModels,
    refreshSavedModels,
    sets,
    dropdownSets,
    libraryFilter,
    setLibraryFilter,
    filteredLibraryItems,
    isSavingPreferred,
    handleAddRef,
    handleRemovePreferred,
    handleMovePreferred,
  };
}
