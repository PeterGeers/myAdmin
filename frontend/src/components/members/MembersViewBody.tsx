/**
 * Sectioned READ-ONLY view body for a member (s5c task 4.4, design C-SURFACE; R5.5, R4.9, R4.12).
 *
 * The read-only counterpart of `MembersFieldFormBody`: it renders the RESOLVED field set (fixed
 * base ⊕ tenant overlay ⊕ calculated) for a single member as label/value rows, SECTIONED by each
 * field's parameter-driven `functional_group` (R4.9), honoring:
 *
 * - field-level VIEW permissions — a `visible === false` field is not shown (R5.1);
 * - `show_when` CONDITIONAL VISIBILITY (R4.12) — a field is shown only when its condition holds
 *   for THIS member (the same predicate the form + server use);
 * - value presentation via the shared `renderFieldValue` (dates localized, enums as their value,
 *   calculated read-only values surfaced like any other, absent → dash).
 *
 * It reuses `groupFieldsBySection` so the view sections match the add/edit modal sections exactly.
 * Pure presentation — no writes, no authority (R2.3).
 */

import React from 'react';
import { VStack, Heading, Divider, Box, Flex, Text } from '@chakra-ui/react';
import type { FieldConfig, Member } from '../../types/members';
import { renderFieldValue, valueFor } from './fieldValue';
import {
  groupFieldsBySection, evaluateShowWhen, resolveLabel, formFields,
} from './fieldForm';

interface MembersViewBodyProps {
  /** The resolved field config (fixed base ⊕ overlay + functional groups). */
  fieldConfig: FieldConfig | null;
  /** The member being viewed. */
  member: Member;
  /** Current UI language (2-letter). */
  lang: string;
}

export const MembersViewBody: React.FC<MembersViewBodyProps> = ({
  fieldConfig, member, lang,
}) => {
  // All VISIBLE fields (member_id + system timestamps are handled/omitted separately).
  const fields = formFields(fieldConfig);
  const sections = groupFieldsBySection(fields, fieldConfig?.functional_groups);

  if (sections.length === 0) return null;

  // The flat value map `show_when` reads (mirror the row shape: bare keys + region + status).
  const flat = flatten(member);

  return (
    <VStack spacing={4} align="stretch">
      {sections.map((section) => {
        const shown = section.fields.filter((f) => evaluateShowWhen(f.show_when, flat));
        if (shown.length === 0) return null;
        return (
          <Box key={section.key}>
            {section.label && (
              <>
                <Heading size="xs" color="orange.300" mb={2} textTransform="uppercase">
                  {resolveLabel(section.label, lang, section.key)}
                </Heading>
                <Divider borderColor="gray.600" mb={2} />
              </>
            )}
            <VStack spacing={1} align="stretch">
              {shown.map((f) => (
                <Flex key={`${f.group ?? ''}.${f.key}`} justify="space-between" gap={4}>
                  <Text color="gray.400" fontSize="sm">
                    {resolveLabel(f.label, lang, f.key)}
                  </Text>
                  <Text fontSize="sm" textAlign="right">
                    {renderFieldValue(f, valueFor(member, f.group, f.key), lang)}
                  </Text>
                </Flex>
              ))}
            </VStack>
          </Box>
        );
      })}
    </VStack>
  );
};

/** Flatten a member's nested buckets + top-level scalars into one map for `show_when`. */
function flatten(member: Member): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const group of ['personal', 'membership', 'overlay']) {
    const bucket = (member as Record<string, unknown>)[group];
    if (bucket && typeof bucket === 'object') {
      Object.assign(out, bucket as Record<string, unknown>);
    }
  }
  // Top-level scalars (region/status/membership_type on the flattened row) win.
  for (const [k, v] of Object.entries(member)) {
    if (typeof v !== 'object' || v === null) out[k] = v;
  }
  return out;
}

export default MembersViewBody;
