/**
 * Focused tests for useMemberSetLibrary.ts - the saved-set + preferred-list
 * derivations and mutations (the Members API is mocked).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({
  listAnalyticsSets: vi.fn(),
  getPreferredList: vi.fn(),
  savePreferredList: vi.fn(),
}));
vi.mock('../../../services/membersApiService', () => ({
  listAnalyticsSets: api.listAnalyticsSets,
  getPreferredList: api.getPreferredList,
  savePreferredList: api.savePreferredList,
}));

import { useMemberSetLibrary } from './useMemberSetLibrary';

const t = (key: string) => key;
type Summary = { id: string; name: string; kind: 'count' | 'list' };
const summary = (id: string, name: string): Summary => ({ id, name, kind: 'list' });

beforeEach(() => {
  api.listAnalyticsSets.mockReset().mockResolvedValue([]);
  api.getPreferredList.mockReset().mockResolvedValue({ refs: [] });
  api.savePreferredList
    .mockReset()
    .mockImplementation((refs: string[]) => Promise.resolve({ refs }));
});

const mount = (saved: Summary[] = [], refs: string[] = []) => {
  api.listAnalyticsSets.mockResolvedValue(saved);
  api.getPreferredList.mockResolvedValue({ refs });
  return renderHook(() => useMemberSetLibrary(t)).result;
};

describe('useMemberSetLibrary', () => {
  it('flattens saved sets into model: option values and keeps dropdownSets to preferred-only in saved order', async () => {
    const result = mount([summary('a', 'Alpha'), summary('b', 'Beta')], ['set:b']);
    await waitFor(() =>
      expect(result.current.dropdownSets.map((s) => s.optionValue)).toEqual(['model:b']),
    );
    expect(result.current.sets.map((s) => s.optionValue)).toEqual(['model:a', 'model:b']);
  });

  it('sorts the full library alphabetically and filters it by name (case-insensitive)', async () => {
    const result = mount([summary('b', 'Beta'), summary('a', 'Alpha')]);
    await waitFor(() =>
      expect(result.current.filteredLibraryItems.map((i) => i.label)).toEqual(['Alpha', 'Beta']),
    );
    act(() => result.current.setLibraryFilter('be'));
    expect(result.current.filteredLibraryItems.map((i) => i.label)).toEqual(['Beta']);
  });

  it('adds a ref to the preferred list and ignores null/duplicate adds', async () => {
    const result = mount([summary('a', 'Alpha')], []);
    await waitFor(() => expect(api.getPreferredList).toHaveBeenCalled());

    act(() => result.current.handleAddRef(null));
    expect(api.savePreferredList).not.toHaveBeenCalled();

    act(() => result.current.handleAddRef('set:a'));
    await waitFor(() => expect(api.savePreferredList).toHaveBeenCalledWith(['set:a']));
    await waitFor(() => expect(result.current.isSavingPreferred).toBe(false));

    api.savePreferredList.mockClear();
    act(() => result.current.handleAddRef('set:a'));
    expect(api.savePreferredList).not.toHaveBeenCalled();
  });

  it('removes a ref from the preferred list', async () => {
    const result = mount([summary('a', 'Alpha'), summary('b', 'Beta')], ['set:a', 'set:b']);
    await waitFor(() => expect(result.current.dropdownSets).toHaveLength(2));

    act(() => result.current.handleRemovePreferred('set:a'));
    await waitFor(() => expect(api.savePreferredList).toHaveBeenCalledWith(['set:b']));
  });

  it('reorders a preferred ref by one position and clamps at the bounds', async () => {
    const result = mount([summary('a', 'Alpha'), summary('b', 'Beta')], ['set:a', 'set:b']);
    await waitFor(() => expect(result.current.dropdownSets).toHaveLength(2));

    act(() => result.current.handleMovePreferred('set:a', -1));
    expect(api.savePreferredList).not.toHaveBeenCalled();

    act(() => result.current.handleMovePreferred('set:a', 1));
    await waitFor(() =>
      expect(api.savePreferredList).toHaveBeenCalledWith(['set:b', 'set:a']),
    );
  });

  it('refreshSavedModels refetches and degrades to [] on failure', async () => {
    const result = mount([]);
    await waitFor(() => expect(api.listAnalyticsSets).toHaveBeenCalled());

    api.listAnalyticsSets.mockResolvedValueOnce([summary('n', 'New')]);
    await act(async () => {
      await result.current.refreshSavedModels();
    });
    expect(result.current.sets.map((s) => s.optionValue)).toEqual(['model:n']);

    api.listAnalyticsSets.mockRejectedValueOnce(new Error('boom'));
    await act(async () => {
      await result.current.refreshSavedModels();
    });
    expect(result.current.savedModels).toEqual([]);
  });
});
