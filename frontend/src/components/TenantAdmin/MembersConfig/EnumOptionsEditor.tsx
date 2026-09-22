/**
 * Enum-options editor (s5c task 2.5, R4.11/R4.12, C-EDITOR).
 *
 * Authors an enum field's option list as rich `{ value, label{nl,en}, roles? }` objects
 * — used for BOTH fixed-field enum values and overlay-field `choices`. Each option
 * carries an optional per-option `roles` restriction (R4.12): a user sees/assigns only
 * the options their role permits. An option with no `roles` is open to any editor. The
 * domain layer is the authoritative gate; this editor only authors the restriction.
 *
 * The underlying param value tolerates a bare `string[]` (legacy / simple authoring);
 * this editor upgrades those to rich options and always emits rich options.
 */
import React from 'react';
import {
  Box,
  Button,
  HStack,
  IconButton,
  Input,
  Switch,
  Text,
  VStack,
} from '@chakra-ui/react';
import type { EnumOption, MembersConfigValue } from '../../../types/membersConfig';

/** True when the value is already an array of rich `{value,label}` option objects. */
export function looksLikeEnumOptions(value: unknown): value is EnumOption[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    typeof value[0] === 'object' &&
    value[0] !== null &&
    'value' in (value[0] as object)
  );
}

/** Normalize any stored value (bare string[] or rich options) to rich options. */
function toOptions(value: MembersConfigValue): EnumOption[] {
  if (looksLikeEnumOptions(value)) {
    return (value as unknown as EnumOption[]).map((o) => ({
      value: o.value ?? '',
      label: { nl: o.label?.nl ?? '', en: o.label?.en ?? '' },
      ...(o.roles && o.roles.length ? { roles: o.roles } : {}),
    }));
  }
  if (Array.isArray(value)) {
    return (value as string[]).map((v) => ({
      value: String(v),
      label: { nl: String(v), en: String(v) },
    }));
  }
  return [];
}

interface Props {
  value: MembersConfigValue;
  onChange: (next: MembersConfigValue) => void;
  availableRoles: string[];
  lang: 'nl' | 'en';
}

export const EnumOptionsEditor: React.FC<Props> = ({
  value,
  onChange,
  availableRoles,
  lang,
}) => {
  const options = toOptions(value);

  const update = (idx: number, next: EnumOption) => {
    const copy = options.slice();
    copy[idx] = next;
    onChange(copy as unknown as MembersConfigValue);
  };
  const remove = (idx: number) =>
    onChange(options.filter((_, i) => i !== idx) as unknown as MembersConfigValue);
  const add = () =>
    onChange([
      ...options,
      { value: '', label: { nl: '', en: '' } },
    ] as unknown as MembersConfigValue);

  const toggleRole = (idx: number, role: string, on: boolean) => {
    const opt = options[idx];
    const roles = new Set(opt.roles ?? []);
    if (on) roles.add(role);
    else roles.delete(role);
    const nextRoles = Array.from(roles);
    update(idx, {
      value: opt.value,
      label: opt.label,
      ...(nextRoles.length ? { roles: nextRoles } : {}),
    });
  };

  return (
    <VStack align="stretch" spacing={2}>
      {options.map((opt, idx) => (
        <Box
          key={idx}
          border="1px"
          borderColor="gray.600"
          borderRadius="md"
          p={2}
          bg="gray.750"
          data-testid={`enum-option-${idx}`}
        >
          <HStack mb={1}>
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={opt.value}
              onChange={(e) => update(idx, { ...opt, value: e.target.value })}
              placeholder="value"
              aria-label={`Option ${idx + 1} value`}
            />
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={opt.label.nl}
              onChange={(e) =>
                update(idx, { ...opt, label: { ...opt.label, nl: e.target.value } })
              }
              placeholder="label (nl)"
              aria-label={`Option ${idx + 1} label nl`}
            />
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={opt.label.en}
              onChange={(e) =>
                update(idx, { ...opt, label: { ...opt.label, en: e.target.value } })
              }
              placeholder="label (en)"
              aria-label={`Option ${idx + 1} label en`}
            />
            <IconButton
              aria-label={`Remove option ${idx + 1}`}
              icon={<Text>✕</Text>}
              size="sm"
              variant="ghost"
              colorScheme="red"
              onClick={() => remove(idx)}
            />
          </HStack>
          {/* Per-option role restriction (R4.12) */}
          <Box pl={1}>
            <Text fontSize="xs" color="gray.500" mb={1}>
              {lang === 'nl' ? 'Rollen (optioneel)' : 'Roles (optional)'}
            </Text>
            {availableRoles.length === 0 ? (
              <Input
                size="xs"
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                value={(opt.roles ?? []).join(', ')}
                onChange={(e) =>
                  update(idx, {
                    ...opt,
                    roles: e.target.value
                      .split(',')
                      .map((r) => r.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="Role_A, Role_B"
                aria-label={`Option ${idx + 1} roles`}
              />
            ) : (
              <HStack spacing={3} wrap="wrap">
                {availableRoles.map((role) => (
                  <HStack key={role} spacing={1}>
                    <Switch
                      size="sm"
                      colorScheme="orange"
                      isChecked={(opt.roles ?? []).includes(role)}
                      onChange={(e) => toggleRole(idx, role, e.target.checked)}
                      aria-label={`Option ${idx + 1} role ${role}`}
                    />
                    <Text fontSize="xs" color="gray.400">
                      {role}
                    </Text>
                  </HStack>
                ))}
              </HStack>
            )}
          </Box>
        </Box>
      ))}
      <Button
        size="xs"
        variant="outline"
        colorScheme="orange"
        onClick={add}
        aria-label="Add option"
      >
        + Add option
      </Button>
    </VStack>
  );
};

export default EnumOptionsEditor;
