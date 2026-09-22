/**
 * Members typed-field renderer (s5c task 2.5, C-EDITOR).
 *
 * REUSES + EXTENDS the `AccountModal.tsx` typed-editor renderer. AccountModal maps a
 * ledger def `type` (boolean / string / string[] + options / depends_on / bilingual
 * labels) to a control; this renderer keeps those scalar mappings and adds the two
 * composite types Members needs:
 *
 *  - `object`         → a bordered group of typed sub-fields (`object_fields`)
 *  - `list<object>`   → an ordered, add/remove list of records (each a set of sub-fields)
 *  - `map<field_def>` → a keyed map of records (add/remove keyed entries; the value shape
 *                       is `field_def`, or a nested composite via `object_fields`)
 *
 * Two authoring-time reference helps (Property 7 — the backend still validates on Save):
 *  - a **functional-group picker** offers only groups defined in the catalog, and
 *  - a **field-key picker** offers only field keys resolvable in the current field set.
 * A picker is selected by convention on the definition key (`functional_group`, or the
 * `columns` / `filterable_columns` / `default_sort.field` view-context keys).
 *
 * Enum options are authored as `{ value, label{nl,en}, roles? }` (R4.11/R4.12) via the
 * dedicated `EnumOptionsEditor`; the plain `string[]` control remains for bare value
 * lists.
 */
import React from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Input,
  Select,
  Switch,
  Text,
  VStack,
} from '@chakra-ui/react';
import type {
  MembersParamDefinition,
  MembersConfigValue,
} from '../../../types/membersConfig';
import { EnumOptionsEditor, looksLikeEnumOptions } from './EnumOptionsEditor';

/** Reference-help data the pickers draw from (authoring-time only). */
export interface MembersEditorContext {
  /** Keys of the defined functional groups (for the functional_group picker). */
  functionalGroupKeys: string[];
  /** Field keys resolvable in the current field set (for view-context column pickers). */
  resolvableFieldKeys: string[];
  /** Known role names (for enum-option `roles` and permission_roles multi-selects). */
  availableRoles: string[];
  /** Active language for rendering bilingual `label[language]`. */
  lang: 'nl' | 'en';
}

interface Props {
  def: MembersParamDefinition;
  value: MembersConfigValue;
  onChange: (next: MembersConfigValue) => void;
  ctx: MembersEditorContext;
  /** Sibling values in the same object, used to evaluate `depends_on`. */
  siblings?: Record<string, MembersConfigValue>;
  /** Set to hide the field's own label (e.g. when the parent renders it). */
  hideLabel?: boolean;
}

const label = (def: MembersParamDefinition, lang: 'nl' | 'en') =>
  lang === 'nl' ? def.label_nl : def.label_en;

const description = (def: MembersParamDefinition, lang: 'nl' | 'en') =>
  lang === 'nl' ? def.description_nl : def.description_en;

/** Keys whose `string[]` control should be a field-key picker rather than free text. */
const FIELD_KEY_PICKER_KEYS = new Set(['columns', 'filterable_columns']);

/**
 * The recursive renderer. Renders a single definition node against its current value.
 */
export const MembersTypedField: React.FC<Props> = ({
  def,
  value,
  onChange,
  ctx,
  siblings,
  hideLabel,
}) => {
  const { lang } = ctx;

  // depends_on: hide unless the named sibling is truthy (mirrors AccountModal).
  if (def.depends_on && siblings) {
    const parent = siblings[def.depends_on];
    if (!parent) return null;
  }

  const fieldLabel = label(def, lang);
  const desc = description(def, lang);

  const wrap = (control: React.ReactNode) => (
    <FormControl>
      {!hideLabel && (
        <FormLabel color="gray.300" fontSize="sm" mb={1}>
          {fieldLabel}
        </FormLabel>
      )}
      {control}
      {desc && (
        <Text fontSize="xs" color="gray.500" mt={1}>
          {desc}
        </Text>
      )}
    </FormControl>
  );

  // ---- boolean ----
  if (def.type === 'boolean') {
    return wrap(
      <Switch
        isChecked={value === true}
        onChange={(e) => onChange(e.target.checked)}
        colorScheme="orange"
      />,
    );
  }

  // ---- number ----
  if (def.type === 'number') {
    return wrap(
      <Input
        type="number"
        bg="gray.700"
        color="white"
        borderColor="gray.600"
        value={value == null ? '' : String(value)}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === '') return onChange(null);
          const n = Number(raw);
          onChange(Number.isNaN(n) ? null : n);
        }}
        aria-label={fieldLabel}
      />,
    );
  }

  // ---- string (with a picker when the key/options ask for one) ----
  if (def.type === 'string') {
    // functional_group → offer only defined groups (Property 7 reference help)
    if (def.key === 'functional_group') {
      return wrap(
        <Select
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          aria-label={fieldLabel}
        >
          <option value="">—</option>
          {ctx.functionalGroupKeys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </Select>,
      );
    }
    // default_sort.field → offer only resolvable field keys
    if (def.key === 'field') {
      return wrap(
        <Select
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          aria-label={fieldLabel}
        >
          <option value="">—</option>
          {ctx.resolvableFieldKeys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </Select>,
      );
    }
    // options → fixed enum dropdown (bare, e.g. sort direction)
    if (def.options && def.options.length > 0) {
      return wrap(
        <Select
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          aria-label={fieldLabel}
        >
          <option value="">—</option>
          {def.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </Select>,
      );
    }
    return wrap(
      <Input
        bg="gray.700"
        color="white"
        borderColor="gray.600"
        value={(value as string) ?? ''}
        onChange={(e) => onChange(e.target.value)}
        aria-label={fieldLabel}
      />,
    );
  }

  // ---- string[] ----
  if (def.type === 'string[]') {
    const arr: string[] = Array.isArray(value) ? (value as string[]) : [];

    // `choices` on a field_def → author rich enum options {value,label,roles} (R4.11/12)
    if (def.key === 'choices') {
      return wrap(
        <EnumOptionsEditor
          value={value}
          onChange={onChange}
          availableRoles={ctx.availableRoles}
          lang={lang}
        />,
      );
    }

    // permission_roles / required_for / all_wildcard-style role lists → role multi-select
    if (def.key === 'permission_roles' || def.key === 'required_for') {
      return wrap(
        <RoleMultiSelect
          selected={arr}
          available={ctx.availableRoles}
          onChange={onChange}
          label={fieldLabel}
        />,
      );
    }

    // columns / filterable_columns → field-key picker list (offer only resolvable keys)
    if (FIELD_KEY_PICKER_KEYS.has(def.key)) {
      return wrap(
        <FieldKeyListEditor
          selected={arr}
          available={ctx.resolvableFieldKeys}
          onChange={onChange}
          label={fieldLabel}
        />,
      );
    }

    // plain editable value list (e.g. scope-dimension `values`)
    return wrap(
      <StringListEditor selected={arr} onChange={onChange} label={fieldLabel} />,
    );
  }

  // ---- object (fixed set of typed sub-fields) ----
  if (def.type === 'object') {
    const obj = (value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, MembersConfigValue>)
      : {}) as Record<string, MembersConfigValue>;
    const children = def.object_fields ?? [];
    return wrap(
      <Box
        border="1px"
        borderColor="gray.600"
        borderRadius="md"
        p={3}
        bg="gray.750"
      >
        <VStack align="stretch" spacing={3}>
          {children.map((child) => (
            <MembersTypedField
              key={child.key}
              def={child}
              value={obj[child.key] ?? null}
              onChange={(next) => onChange({ ...obj, [child.key]: next })}
              ctx={ctx}
              siblings={obj}
            />
          ))}
        </VStack>
      </Box>,
    );
  }

  // ---- list<object> (ordered add/remove list of records) ----
  if (def.type === 'list<object>') {
    const rows: Record<string, MembersConfigValue>[] = Array.isArray(value)
      ? (value as Record<string, MembersConfigValue>[])
      : [];
    // Each row's shape comes from object_fields (preferred) or field_def.
    const rowFields = def.object_fields ?? def.field_def ?? [];

    const updateRow = (idx: number, next: Record<string, MembersConfigValue>) => {
      const copy = rows.slice();
      copy[idx] = next;
      onChange(copy);
    };
    const removeRow = (idx: number) => onChange(rows.filter((_, i) => i !== idx));
    const addRow = () => onChange([...rows, {}]);

    return (
      <FormControl>
        {!hideLabel && (
          <FormLabel color="gray.300" fontSize="sm" mb={1}>
            {fieldLabel}
          </FormLabel>
        )}
        {desc && (
          <Text fontSize="xs" color="gray.500" mb={2}>
            {desc}
          </Text>
        )}
        <VStack align="stretch" spacing={3}>
          {rows.map((row, idx) => (
            <Box
              key={idx}
              border="1px"
              borderColor="gray.600"
              borderRadius="md"
              p={3}
              bg="gray.750"
              data-testid={`${def.key}-row-${idx}`}
            >
              <HStack justify="space-between" mb={2}>
                <Text fontSize="xs" color="gray.400">
                  #{idx + 1}
                </Text>
                <IconButton
                  aria-label={`Remove ${fieldLabel} row ${idx + 1}`}
                  icon={<Text>✕</Text>}
                  size="xs"
                  variant="ghost"
                  colorScheme="red"
                  onClick={() => removeRow(idx)}
                />
              </HStack>
              <VStack align="stretch" spacing={3}>
                {rowFields.map((child) => (
                  <MembersTypedField
                    key={child.key}
                    def={child}
                    value={row[child.key] ?? null}
                    onChange={(next) => updateRow(idx, { ...row, [child.key]: next })}
                    ctx={ctx}
                    siblings={row}
                  />
                ))}
              </VStack>
            </Box>
          ))}
          <Button
            size="sm"
            variant="outline"
            colorScheme="orange"
            onClick={addRow}
            aria-label={`Add ${fieldLabel}`}
          >
            + {fieldLabel}
          </Button>
        </VStack>
      </FormControl>
    );
  }

  // ---- map<field_def> (keyed map of records) ----
  if (def.type === 'map<field_def>') {
    // A map<field_def> may itself contain nested composite object_fields (e.g. the
    // field_overlay param bundles functional_groups + fields + fixed_overrides). When
    // object_fields is present, render those as a fixed object rather than a free map.
    if (def.object_fields && def.object_fields.length > 0) {
      const obj = (value && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, MembersConfigValue>)
        : {}) as Record<string, MembersConfigValue>;
      return (
        <VStack align="stretch" spacing={4}>
          {def.object_fields.map((child) => (
            <MembersTypedField
              key={child.key}
              def={child}
              value={obj[child.key] ?? null}
              onChange={(next) => onChange({ ...obj, [child.key]: next })}
              ctx={ctx}
              siblings={obj}
            />
          ))}
        </VStack>
      );
    }

    // A true keyed map: entries keyed by a tenant-authored snake_case key, each value
    // shaped by field_def.
    const map = (value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, Record<string, MembersConfigValue>>)
      : {}) as Record<string, Record<string, MembersConfigValue>>;
    const entryFields = def.field_def ?? [];
    const entryKeys = Object.keys(map);

    const renameKey = (oldKey: string, newKey: string) => {
      if (!newKey || newKey === oldKey || map[newKey] !== undefined) return;
      const next: typeof map = {};
      for (const k of Object.keys(map)) {
        next[k === oldKey ? newKey : k] = map[k];
      }
      onChange(next);
    };
    const updateEntry = (key: string, next: Record<string, MembersConfigValue>) =>
      onChange({ ...map, [key]: next });
    const removeEntry = (key: string) => {
      const next = { ...map };
      delete next[key];
      onChange(next);
    };
    const addEntry = () => {
      let base = 'new_field';
      let candidate = base;
      let n = 1;
      while (map[candidate] !== undefined) candidate = `${base}_${n++}`;
      onChange({ ...map, [candidate]: {} });
    };

    return (
      <FormControl>
        {!hideLabel && (
          <FormLabel color="gray.300" fontSize="sm" mb={1}>
            {fieldLabel}
          </FormLabel>
        )}
        {desc && (
          <Text fontSize="xs" color="gray.500" mb={2}>
            {desc}
          </Text>
        )}
        <VStack align="stretch" spacing={3}>
          {entryKeys.map((entryKey) => (
            <Box
              key={entryKey}
              border="1px"
              borderColor="gray.600"
              borderRadius="md"
              p={3}
              bg="gray.750"
              data-testid={`${def.key}-entry-${entryKey}`}
            >
              <HStack mb={2}>
                <Input
                  size="sm"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  defaultValue={entryKey}
                  onBlur={(e) => renameKey(entryKey, e.target.value.trim())}
                  aria-label={`${fieldLabel} key`}
                  placeholder="field_key"
                />
                <IconButton
                  aria-label={`Remove ${entryKey}`}
                  icon={<Text>✕</Text>}
                  size="sm"
                  variant="ghost"
                  colorScheme="red"
                  onClick={() => removeEntry(entryKey)}
                />
              </HStack>
              <VStack align="stretch" spacing={3}>
                {entryFields.map((child) => (
                  <MembersTypedField
                    key={child.key}
                    def={child}
                    value={map[entryKey][child.key] ?? null}
                    onChange={(next) =>
                      updateEntry(entryKey, { ...map[entryKey], [child.key]: next })
                    }
                    ctx={ctx}
                    siblings={map[entryKey]}
                  />
                ))}
              </VStack>
            </Box>
          ))}
          <Button
            size="sm"
            variant="outline"
            colorScheme="orange"
            onClick={addEntry}
            aria-label={`Add ${fieldLabel}`}
          >
            + {fieldLabel}
          </Button>
        </VStack>
      </FormControl>
    );
  }

  return null;
};

/* ------------------------------------------------------------------ */
/*  Small sub-controls                                                 */
/* ------------------------------------------------------------------ */

/** A plain editable list of free-text strings (add / edit / remove). */
const StringListEditor: React.FC<{
  selected: string[];
  onChange: (next: string[]) => void;
  label: string;
}> = ({ selected, onChange, label }) => (
  <VStack align="stretch" spacing={2}>
    {selected.map((v, idx) => (
      <HStack key={idx}>
        <Input
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={v}
          onChange={(e) => {
            const copy = selected.slice();
            copy[idx] = e.target.value;
            onChange(copy);
          }}
          aria-label={`${label} value ${idx + 1}`}
        />
        <IconButton
          aria-label={`Remove ${label} value ${idx + 1}`}
          icon={<Text>✕</Text>}
          size="sm"
          variant="ghost"
          colorScheme="red"
          onClick={() => onChange(selected.filter((_, i) => i !== idx))}
        />
      </HStack>
    ))}
    <Button
      size="xs"
      variant="outline"
      colorScheme="orange"
      onClick={() => onChange([...selected, ''])}
      aria-label={`Add ${label} value`}
    >
      + Add value
    </Button>
  </VStack>
);

/**
 * A field-key picker list: each row is a Select offering ONLY resolvable field keys
 * (Property 7 authoring-time reference help). Free typing is not allowed — the backend
 * still validates on Save, but the picker prevents most dangling references up front.
 */
const FieldKeyListEditor: React.FC<{
  selected: string[];
  available: string[];
  onChange: (next: string[]) => void;
  label: string;
}> = ({ selected, available, onChange, label }) => (
  <VStack align="stretch" spacing={2}>
    {selected.map((v, idx) => (
      <HStack key={idx}>
        <Select
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={v}
          onChange={(e) => {
            const copy = selected.slice();
            copy[idx] = e.target.value;
            onChange(copy);
          }}
          aria-label={`${label} ${idx + 1}`}
        >
          <option value="">Select field…</option>
          {available.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
          {/* keep an already-authored key selectable even if it no longer resolves */}
          {v && !available.includes(v) && (
            <option value={v}>{v} (unresolved)</option>
          )}
        </Select>
        <IconButton
          aria-label={`Remove ${label} ${idx + 1}`}
          icon={<Text>✕</Text>}
          size="sm"
          variant="ghost"
          colorScheme="red"
          onClick={() => onChange(selected.filter((_, i) => i !== idx))}
        />
      </HStack>
    ))}
    <Button
      size="xs"
      variant="outline"
      colorScheme="orange"
      onClick={() => onChange([...selected, ''])}
      aria-label={`Add ${label}`}
    >
      + Add column
    </Button>
  </VStack>
);

/** A role multi-select rendered as toggle switches over the known role names. */
const RoleMultiSelect: React.FC<{
  selected: string[];
  available: string[];
  onChange: (next: string[]) => void;
  label: string;
}> = ({ selected, available, onChange, label }) => {
  const toggle = (role: string, on: boolean) =>
    onChange(on ? [...selected, role] : selected.filter((r) => r !== role));
  if (available.length === 0) {
    // No known roles — fall back to a plain editable list so authoring still works.
    return <StringListEditor selected={selected} onChange={onChange} label={label} />;
  }
  return (
    <VStack align="stretch" spacing={1}>
      {available.map((role) => (
        <HStack key={role} justify="space-between">
          <Text fontSize="sm" color="gray.300">
            {role}
          </Text>
          <Switch
            size="sm"
            colorScheme="orange"
            isChecked={selected.includes(role)}
            onChange={(e) => toggle(role, e.target.checked)}
            aria-label={`${label}: ${role}`}
          />
        </HStack>
      ))}
    </VStack>
  );
};

export { looksLikeEnumOptions };
export default MembersTypedField;
