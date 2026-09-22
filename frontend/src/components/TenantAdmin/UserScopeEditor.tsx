/**
 * UserScopeEditor Component (s5d task 6.2)
 *
 * Per-user MEMBER scope editor, rendered inside the user-details view for any
 * user who holds a Members capability role (R4.6). For each ENABLED scope
 * dimension (from `getScopeDimensions('members')`) it renders:
 *   - a MULTI-SELECT of the dimension's PLAIN values (label where available,
 *     value otherwise — NEVER a `Regio_` role name — R4.3), and
 *   - an explicit **All** toggle that maps the dimension to `["*"]` and visually
 *     supersedes the individual value selection for that dimension.
 *
 * Save issues `setUserScope(username, 'members', scopes)` — an ATOMIC OVERWRITE
 * (the save reflects exactly the selection); clearing ALL selections removes the
 * grant (deny) by sending an empty grant. The current grant is loaded via
 * `getUserScope(username, 'members')`. A 400 validation error thrown by the
 * service is surfaced to the user.
 *
 * The value picker is structured around a pluggable `filterValues` function.
 * Task 6.3 slots the diacritic/spacing-tolerant FUZZY filter
 * (`fuzzyFilterValues`) in as the DEFAULT, so the shipped picker is fuzzy — a
 * typeahead that FINDS canonical values regardless of accents/spacing but never
 * changes what is stored (fuzzy narrows the list; selection yields the canonical
 * value unchanged, R5.3/R5.4). The prop stays injectable so tests can pass a
 * custom filter (e.g. `plainFilterValues`).
 *
 * _Requirements: R4.1, R4.3, R4.4, R4.6, R5.3, R5.4, D2_
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Box, VStack, HStack, Text, Button, Checkbox, Switch, FormControl,
  FormLabel, Input, Spinner, Alert, AlertIcon, Wrap, WrapItem, useToast,
} from '@chakra-ui/react';
import { resolveLabel } from '../members/fieldForm';
import { getScopeDimensions, getUserScope, setUserScope } from '../../services/tenantAdminApi';
import { fuzzyFilterValues } from './scopeFuzzyFilter';
import type { ScopeGrant, ScopeDimensionOption } from '../../types/members';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The module this editor authors scope for (s5d ships the MEMBERS slice). */
export const SCOPE_MODULE = 'members';

/** The all-access sentinel a dimension maps to when "All" is toggled on. */
const ALL_SENTINEL = '*';

/**
 * Does this user hold a Members CAPABILITY role (R4.6)?
 *
 * Capability roles are `Members_*` (e.g. `Members_CRUD` / `Members_Read` /
 * `Members_Export`). `Tenant_Admin` (governance) and the retired `Regio_*`
 * (scope-in-role-name) encoding are NOT capability roles.
 */
export function holdsMembersCapabilityRole(groups: string[] | undefined): boolean {
  return (groups ?? []).some((g) => /^Members_/.test(g));
}

/**
 * A plain, case-insensitive substring value filter. Superseded as the editor's
 * default by the diacritic/spacing-tolerant `fuzzyFilterValues` (task 6.3), but
 * kept exported and injectable via the `filterValues` prop (e.g. for tests that
 * want a plain match).
 */
export function plainFilterValues(values: string[], query: string): string[] {
  const q = query.trim().toLowerCase();
  if (!q) return values;
  return values.filter((v) => v.toLowerCase().includes(q));
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserScopeEditorProps {
  /** The Cognito username whose scope is being authored. */
  username: string;
  /** The user's capability roles (used only to render context, gating is done by the caller). */
  t: (key: string, params?: Record<string, unknown>) => string;
  /** Current UI language (for localized dimension labels). */
  lang: string;
  /**
   * The value filter the picker uses. Defaults to the diacritic/spacing-tolerant
   * fuzzy typeahead (`fuzzyFilterValues`); injectable so tests can override it.
   */
  filterValues?: (values: string[], query: string) => string[];
}

// ---------------------------------------------------------------------------
// Per-dimension selector
// ---------------------------------------------------------------------------

interface DimensionSelectorProps {
  dimension: ScopeDimensionOption;
  /** Selected values for this dimension (`["*"]` when All is on). */
  selected: string[];
  onChange: (values: string[]) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
  lang: string;
  filterValues: (values: string[], query: string) => string[];
}

const DimensionSelector: React.FC<DimensionSelectorProps> = ({
  dimension, selected, onChange, t, lang, filterValues,
}) => {
  const [query, setQuery] = useState('');
  const isAll = selected.length === 1 && selected[0] === ALL_SENTINEL;
  const label = resolveLabel(dimension.label, lang, dimension.key);

  const visibleValues = useMemo(
    () => filterValues(dimension.values ?? [], query),
    [dimension.values, query, filterValues],
  );

  const toggleAll = (checked: boolean) => {
    onChange(checked ? [ALL_SENTINEL] : []);
  };

  const toggleValue = (value: string, checked: boolean) => {
    // Editing individual values implicitly leaves "All" mode.
    const base = isAll ? [] : selected;
    onChange(checked ? [...base, value] : base.filter((v) => v !== value));
  };

  return (
    <Box bg="gray.700" p={3} borderRadius="md">
      <HStack justify="space-between" mb={2}>
        <Text color="white" fontWeight="bold">{label}</Text>
        <FormControl display="flex" alignItems="center" width="auto">
          <FormLabel htmlFor={`scope-all-${dimension.key}`} mb={0} mr={2} color="gray.300" fontSize="sm">
            {t('userManagement.scope.all')}
          </FormLabel>
          <Switch
            id={`scope-all-${dimension.key}`}
            isChecked={isAll}
            onChange={(e) => toggleAll(e.target.checked)}
            colorScheme="orange"
          />
        </FormControl>
      </HStack>

      {isAll ? (
        <Text color="gray.400" fontSize="sm" fontStyle="italic">
          {t('userManagement.scope.allSelected')}
        </Text>
      ) : (
        <VStack align="stretch" spacing={2}>
          <Input
            size="sm"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('userManagement.scope.filterPlaceholder')}
            aria-label={t('userManagement.scope.filterValues', { dimension: label })}
            bg="gray.600"
            color="white"
            borderColor="gray.500"
          />
          <Wrap spacing={3} role="group" aria-label={label}>
            {visibleValues.map((value) => (
              <WrapItem key={value}>
                <Checkbox
                  isChecked={selected.includes(value)}
                  onChange={(e) => toggleValue(value, e.target.checked)}
                  colorScheme="orange"
                  color="white"
                >
                  {value}
                </Checkbox>
              </WrapItem>
            ))}
            {visibleValues.length === 0 && (
              <Text color="gray.400" fontSize="sm">
                {t('userManagement.scope.noValues')}
              </Text>
            )}
          </Wrap>
        </VStack>
      )}
    </Box>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const UserScopeEditor: React.FC<UserScopeEditorProps> = ({
  username,
  t,
  lang,
  filterValues = fuzzyFilterValues,
}) => {
  const toast = useToast();
  const [dimensions, setDimensions] = useState<ScopeDimensionOption[]>([]);
  const [grant, setGrant] = useState<ScopeGrant>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const [dims, current] = await Promise.all([
          getScopeDimensions(SCOPE_MODULE),
          getUserScope(username, SCOPE_MODULE),
        ]);
        if (cancelled) return;
        setDimensions(dims);
        setGrant(current);
      } catch (err) {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : t('userManagement.messages.unknownError'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]);

  const setDimensionValues = (key: string, values: string[]) => {
    setGrant((prev) => {
      const next = { ...prev };
      if (values.length === 0) {
        delete next[key];
      } else {
        next[key] = values;
      }
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      // Atomic overwrite: send exactly the current selection. Dropping empty
      // dimensions here means clearing all selections sends `{}` → the backend
      // removes the grant (deny).
      const payload: ScopeGrant = {};
      for (const [key, values] of Object.entries(grant)) {
        if (values && values.length > 0) payload[key] = values;
      }
      const normalized = await setUserScope(username, SCOPE_MODULE, payload);
      setGrant(normalized);
      toast({
        title: t('userManagement.scope.saved'),
        status: 'success',
        duration: 3000,
      });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : t('userManagement.messages.unknownError'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" py={4}>
        <Spinner color="orange.400" />
      </Box>
    );
  }

  return (
    <Box bg="gray.700" p={4} borderRadius="md" borderWidth="1px" borderColor="orange.500">
      <Text color="orange.400" fontWeight="bold" mb={3}>
        {t('userManagement.scope.title')}
      </Text>

      {loadError && (
        <Alert status="error" mb={3} borderRadius="md">
          <AlertIcon />
          {loadError}
        </Alert>
      )}

      {!loadError && dimensions.length === 0 && (
        <Text color="gray.400" fontSize="sm">
          {t('userManagement.scope.noDimensions')}
        </Text>
      )}

      {!loadError && dimensions.length > 0 && (
        <VStack align="stretch" spacing={3}>
          {dimensions.map((dimension) => (
            <DimensionSelector
              key={dimension.key}
              dimension={dimension}
              selected={grant[dimension.key] ?? []}
              onChange={(values) => setDimensionValues(dimension.key, values)}
              t={t}
              lang={lang}
              filterValues={filterValues}
            />
          ))}

          {saveError && (
            <Alert status="error" borderRadius="md">
              <AlertIcon />
              {saveError}
            </Alert>
          )}

          <HStack justify="flex-end">
            <Button
              colorScheme="orange"
              onClick={handleSave}
              isLoading={saving}
            >
              {t('userManagement.scope.save')}
            </Button>
          </HStack>
        </VStack>
      )}
    </Box>
  );
};
