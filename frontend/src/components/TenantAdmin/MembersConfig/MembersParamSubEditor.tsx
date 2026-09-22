/**
 * Members param sub-editor (s5c tasks 2.5/2.6, C-EDITOR).
 *
 * Drives ONE `members.*` param object. It renders the param's composite definition via
 * the extended `MembersTypedField` renderer, tracks whether there are uncommitted edits,
 * and on Save commits the WHOLE object in exactly ONE request (save-once, Property 8) via
 * `saveMembersParameter`. An unsaved-changes guard warns on navigate-away (task 2.6).
 *
 * A sub-editor may render only a SLICE of a composite param (e.g. just the
 * `functional_groups` catalog, or just `fields` + `fixed_overrides`) while still holding
 * and committing the entire param object — so several sub-editors can share one param and
 * each Save is still one whole-object PUT.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Button, HStack, Text, useToast, VStack } from '@chakra-ui/react';
import {
  saveMembersParameter,
  type MembersParamKey,
} from '../../../services/membersConfigService';
import type { Parameter } from '../../../types/parameterTypes';
import type {
  MembersParamDefinition,
  MembersConfigValue,
} from '../../../types/membersConfig';
import { MembersTypedField, type MembersEditorContext } from './MembersTypedField';
import { useUnsavedChangesGuard } from '../../../hooks/useUnsavedChangesGuard';

interface Props {
  paramKey: MembersParamKey;
  def: MembersParamDefinition;
  existing?: Parameter | null;
  ctx: MembersEditorContext;
  onSaved: () => void;
  /** Lift the working value up (so sibling pickers see live edits). */
  onValueChange?: (value: MembersConfigValue) => void;
  /** Render only this top-level object child of the param (e.g. `functional_groups`). */
  sliceKey?: string;
  /** Render only these top-level object children (e.g. `fields`, `fixed_overrides`). */
  sliceKeys?: string[];
}

/** Default empty value for a param type. */
function emptyValue(def: MembersParamDefinition): MembersConfigValue {
  if (def.type === 'list<object>') return [];
  return {};
}

export const MembersParamSubEditor: React.FC<Props> = ({
  paramKey,
  def,
  existing,
  ctx,
  onSaved,
  onValueChange,
  sliceKey,
  sliceKeys,
}) => {
  const lang = ctx.lang;
  const toast = useToast();

  const initial = useMemo<MembersConfigValue>(
    () => (existing?.value as MembersConfigValue) ?? emptyValue(def),
    [existing, def],
  );

  const [value, setValue] = useState<MembersConfigValue>(initial);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const baseline = useRef(JSON.stringify(initial));

  // Re-seed when the underlying row changes (e.g. after a reload following Save).
  useEffect(() => {
    setValue(initial);
    baseline.current = JSON.stringify(initial);
    setDirty(false);
  }, [initial]);

  const { confirmDiscard } = useUnsavedChangesGuard(
    dirty,
    lang === 'nl'
      ? 'Je hebt niet-opgeslagen wijzigingen. Weggaan zonder opslaan?'
      : 'You have unsaved changes. Leave without saving?',
  );

  const setWorking = (next: MembersConfigValue) => {
    setValue(next);
    setDirty(JSON.stringify(next) !== baseline.current);
    onValueChange?.(next);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save-once: the WHOLE param object in a single request (Property 8).
      const res = await saveMembersParameter(paramKey, value, existing);
      if (res.success) {
        toast({
          title: lang === 'nl' ? 'Opgeslagen' : 'Saved',
          status: 'success',
          duration: 3000,
        });
        setDirty(false);
        baseline.current = JSON.stringify(value);
        onSaved();
      } else {
        toast({
          title: 'Error',
          description: res.error,
          status: 'error',
          duration: 6000,
        });
      }
    } catch (e) {
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : String(e),
        status: 'error',
        duration: 6000,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!dirty || confirmDiscard()) {
      setValue(initial);
      baseline.current = JSON.stringify(initial);
      setDirty(false);
      onValueChange?.(initial);
    }
  };

  // Which child definitions to render (whole param, or the requested slice(s)).
  const slice = sliceKeys ?? (sliceKey ? [sliceKey] : null);
  const childDefs = def.object_fields ?? [];

  const renderBody = () => {
    if (slice && def.object_fields) {
      const obj = (value && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, MembersConfigValue>)
        : {}) as Record<string, MembersConfigValue>;
      const selected = childDefs.filter((c) => slice.includes(c.key));
      return (
        <VStack align="stretch" spacing={4}>
          {selected.map((child) => (
            <MembersTypedField
              key={child.key}
              def={child}
              value={obj[child.key] ?? null}
              onChange={(next) => setWorking({ ...obj, [child.key]: next })}
              ctx={ctx}
              siblings={obj}
            />
          ))}
        </VStack>
      );
    }
    // Whole param object.
    return (
      <MembersTypedField
        def={def}
        value={value}
        onChange={setWorking}
        ctx={ctx}
        hideLabel
      />
    );
  };

  return (
    <Box data-testid={`sub-editor-${paramKey}${slice ? `-${slice.join('-')}` : ''}`}>
      <VStack align="stretch" spacing={4}>
        {renderBody()}

        <HStack justify="flex-end" pt={2}>
          {dirty && (
            <Text
              fontSize="sm"
              color="yellow.300"
              mr="auto"
              data-testid="unsaved-indicator"
            >
              {lang === 'nl' ? 'Niet-opgeslagen wijzigingen' : 'Unsaved changes'}
            </Text>
          )}
          <Button
            variant="ghost"
            colorScheme="gray"
            onClick={handleReset}
            isDisabled={!dirty || saving}
          >
            {lang === 'nl' ? 'Herstellen' : 'Reset'}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isLoading={saving}
            isDisabled={!dirty}
            loadingText={lang === 'nl' ? 'Opslaan…' : 'Saving…'}
          >
            {lang === 'nl' ? 'Opslaan' : 'Save'}
          </Button>
        </HStack>
      </VStack>
    </Box>
  );
};

export default MembersParamSubEditor;
