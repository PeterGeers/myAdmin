/**
 * Members unified field list + provenance badge (Members config redesign Phase 3 step 8, R1).
 *
 * Phase 3 collapses the former two-section fixed/overlay authoring split into ONE ordered field
 * list where every resolved field — platform base ⊕ tenant overlay — shows a PROVENANCE badge
 * indicating where it came from (R1.1, R1.2):
 *
 *   - base            → a platform base field with no tenant override (gray badge);
 *   - tenant_added    → a tenant-authored overlay field (green badge);
 *   - base_overridden → a base field the tenant re-presents via `fixed_overrides` (orange badge) —
 *                       it stays a base field and remains immovable (R1.5).
 *
 * The list is ordered by the catalog rule `(group.order, field.order, key)` (R1.3,
 * `38-sam-module-field-config.md` rule 2) — NO new position field is introduced; the order is
 * DERIVED from the facts the module already serves (`orderResolvedFields`). This is a PRESENTATION
 * view over the module's resolved field-config; authoring still writes the single `field_overlay`
 * object through the sub-editor below it (one save → one re-projection, R1.4).
 *
 * Presentation-only: the badge reflects what the module reports; nothing here enforces anything.
 */
import React from 'react';
import { Badge, Box, HStack, Text, VStack } from '@chakra-ui/react';
import type { FieldConfigField, FieldProvenance, LocalizedLabel } from '../../../types/members';

export interface MembersFieldProvenanceListProps {
  /**
   * The field list ALREADY ordered by `(group.order, field.order, key)` (via
   * `orderResolvedFields`). Empty/absent → the list renders a "no resolved fields" note (an
   * unconfigured tenant or an unavailable module build) rather than an error.
   */
  fields: FieldConfigField[];
  /** UI language for the inline labels (matches the editor's `lang` convention, steering 32). */
  lang: 'nl' | 'en';
}

/** The three single-list provenance badges (R1.2): color + bilingual label. */
const PROVENANCE_BADGE: Record<
  FieldProvenance,
  { colorScheme: string; nl: string; en: string }
> = {
  base: { colorScheme: 'gray', nl: 'Basis', en: 'Base' },
  tenant_added: { colorScheme: 'green', nl: 'Toegevoegd', en: 'Tenant-added' },
  base_overridden: { colorScheme: 'orange', nl: 'Basis (overschreven)', en: 'Base (overridden)' },
};

/** Resolve a field's display label from the localized/plain `label`, falling back to its key. */
function fieldLabel(field: FieldConfigField, lang: 'nl' | 'en'): string {
  const label = field.label;
  if (label && typeof label === 'object') {
    const loc = label as LocalizedLabel;
    return loc[lang] || loc.en || loc.nl || field.key;
  }
  if (typeof label === 'string' && label) return label;
  return field.key;
}

export const MembersFieldProvenanceList: React.FC<MembersFieldProvenanceListProps> = ({
  fields,
  lang,
}) => {
  const title = lang === 'nl' ? 'Alle velden (herkomst)' : 'All fields (provenance)';
  const empty =
    lang === 'nl'
      ? 'Geen opgeloste velden beschikbaar.'
      : 'No resolved fields available.';

  return (
    <Box
      data-testid="members-field-provenance-list"
      mb={4}
      p={3}
      borderWidth="1px"
      borderColor="gray.700"
      borderRadius="md"
      bg="gray.900"
    >
      <Text fontSize="sm" color="gray.400" mb={2}>
        {title}
      </Text>
      {fields.length === 0 ? (
        <Text fontSize="sm" color="gray.500" data-testid="members-field-provenance-empty">
          {empty}
        </Text>
      ) : (
        <VStack align="stretch" spacing={1}>
          {fields.map((field) => {
            const prov: FieldProvenance = field.provenance ?? 'base';
            const badge = PROVENANCE_BADGE[prov] ?? PROVENANCE_BADGE.base;
            return (
              <HStack
                key={field.key}
                justify="space-between"
                data-testid={`members-field-row-${field.key}`}
              >
                <HStack spacing={2} minW={0}>
                  <Text fontSize="sm" color="gray.200" isTruncated>
                    {fieldLabel(field, lang)}
                  </Text>
                  <Text fontSize="xs" color="gray.500">
                    {field.key}
                  </Text>
                </HStack>
                <Badge
                  colorScheme={badge.colorScheme}
                  data-testid={`members-field-provenance-${field.key}`}
                >
                  {badge[lang]}
                </Badge>
              </HStack>
            );
          })}
        </VStack>
      )}
    </Box>
  );
};

export default MembersFieldProvenanceList;
