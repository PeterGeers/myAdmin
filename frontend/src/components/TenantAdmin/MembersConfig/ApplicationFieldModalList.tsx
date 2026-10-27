/**
 * Application field list (modal-open) — the group ▸ field surface of the Application Form Builder
 * (spec 12 — Application Form Serving Redesign, task 4.1; R1.1, design §C1 / redesign A).
 *
 * ## What this replaces (redesign A)
 *
 * This REPLACES spec 11's `ApplicationFieldList`, whose every row carried an inline on-the-form
 * toggle and whose attributes lived in a cramped panel buried under the ~100-field list. The
 * builder keeps the SAME grouped/ordered group ▸ field surface, but a row-click now OPENS the
 * per-field modal (`ApplicationFieldModal`) — the proven `MembersFieldModal` row-click-opens-modal
 * convention (steering 32) reused for the application form (R1.1). There is no inline toggle and no
 * buried panel on this surface anymore; all per-field authoring happens in the modal.
 *
 * ## Pure DISPLAY, no write (design §3.1)
 *
 * This component NEVER mutates the overlay and NEVER makes a network call — it is a pure DISPLAY of
 * the tenant's RESOLVED field list (`GET /members/field-config`), grouped by `functional_group` and
 * ordered by the catalog rule `(group.order, field.order, key)` (reusing the shared
 * `groupResolvedFields` hierarchy builder). A row-click raises `onOpenField(key)`; the builder owns
 * the modal, the one working overlay, and the single save (one object, one save — steering 38
 * rule 5 / Property 8).
 *
 * ## On-the-form state is a read-only BADGE here (authored in the modal)
 *
 * Each row shows whether the field is currently on the form as a read-only badge (so the admin can
 * scan the surface at a glance), computed with the SAME precedence the modal authors with (working
 * overlay ⊕ served ⊕ default-off). A calculated / read-only field is not offerable (R2.5) and shows
 * a "not available" note; it is still clickable to open the modal (which explains why it can't go on
 * the form) — nothing on this surface is a dead end.
 */
import React, { useMemo } from 'react';
import {
  Badge,
  Box,
  Heading,
  HStack,
  Text,
  VStack,
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import {
  groupResolvedFields,
  resolveFieldConfigLabel,
} from '../../../services/membersConfigService';
import { findField } from './overlayModel';
import { resolveWriteTarget } from './ApplicationFieldModal';

/** The back-office STORAGE group whose fields default OFF the public form (R2.4). */
const MEMBERSHIP_STORAGE_GROUP = 'membership';

export interface ApplicationFieldModalListProps {
  /** The resolved `FieldConfig` the list DISPLAYS from (null/absent → nothing to offer yet). */
  fieldConfig?: FieldConfig | null;
  /** The ONE working `field_overlay` object (read-only here — the on-the-form badge source). */
  overlay: MembersConfigValue | undefined;
  /** Open the per-field modal for this field (the builder owns the modal). */
  onOpenField: (key: string) => void;
  lang: 'nl' | 'en';
}

/** Is this resolved field OFFERABLE on the public form (R2.5)? */
function isOfferable(field: FieldConfigField): boolean {
  if (field.origin === 'calculated') return false;
  if (field.read_only === true) return false;
  return true;
}

/**
 * The effective on-the-form state for a field (R2.2/R2.3/R2.4) — the SAME precedence the modal
 * authors with (via the shared `resolveWriteTarget`), so the badge can never disagree with the
 * modal's toggle: working overlay ⊕ the served value ⊕ default-off.
 */
function isOnForm(overlay: MembersConfigValue | undefined, field: FieldConfigField): boolean {
  const target = resolveWriteTarget(field);
  const authored =
    findField(overlay, target.overlayKey)?.field.application_visible ??
    findField(overlay, field.key)?.field.application_visible;
  if (typeof authored === 'boolean') return authored;
  const served = (field as { application_visible?: boolean }).application_visible;
  if (typeof served === 'boolean') return served;
  return false;
}

export const ApplicationFieldModalList: React.FC<ApplicationFieldModalListProps> = ({
  fieldConfig,
  overlay,
  onOpenField,
  lang,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // Grouped by `functional_group`, ordered `(group.order, field.order, key)` — the catalog rule,
  // reusing the shared hierarchy builder. A trailing bucket surfaces any field whose group is not
  // catalog-resolvable, never silently dropping it.
  const sections = useMemo(() => groupResolvedFields(fieldConfig), [fieldConfig]);

  if (sections.length === 0) {
    return (
      <Box data-testid="application-field-list-empty">
        <Text fontSize="sm" color="gray.500">
          {t(
            'Geen velden beschikbaar. Configureer eerst velden onder Veldconfiguratie.',
            'No fields available. Configure fields first under Field configuration.',
          )}
        </Text>
      </Box>
    );
  }

  return (
    <VStack align="stretch" spacing={4} data-testid="application-field-list">
      {sections.map((section) => {
        const groupLabel = section.resolved
          ? resolveFieldConfigLabel(section.group?.label, lang, section.key)
          : t('Overige velden', 'Other fields');
        return (
          <Box
            key={section.resolved ? section.key : '__ungrouped__'}
            data-testid={`application-field-group-${section.resolved ? section.key : '__ungrouped__'}`}
          >
            <Heading size="xs" color="gray.400" mb={2} textTransform="uppercase">
              {groupLabel}
            </Heading>
            <VStack align="stretch" spacing={1}>
              {section.fields.map((field) => {
                const label = resolveFieldConfigLabel(field.label, lang, field.key);
                const offerable = isOfferable(field);
                const on = isOnForm(overlay, field);
                const isMembershipAdmin = field.group === MEMBERSHIP_STORAGE_GROUP;
                // The WHOLE row is the open-modal control (steering 32 row-click convention). It
                // carries NO interactive descendants (plain Text/Badge), so it is a single focusable
                // button — no nested-interactive axe concern (the retired list split the row to host
                // its inline Switch; without the Switch the row itself is the control).
                const onRowKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
                  if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                    e.preventDefault();
                    onOpenField(field.key);
                  }
                };
                return (
                  <HStack
                    key={field.key}
                    justify="space-between"
                    bg="gray.750"
                    borderWidth="1px"
                    borderColor="gray.700"
                    borderRadius="md"
                    px={3}
                    py={2}
                    cursor="pointer"
                    _hover={{ bg: 'gray.700' }}
                    role="button"
                    tabIndex={0}
                    aria-label={t(
                      `Veldinstellingen voor ${label}`,
                      `Field attributes for ${label}`,
                    )}
                    onClick={() => onOpenField(field.key)}
                    onKeyDown={onRowKeyDown}
                    data-testid={`application-field-row-${field.key}`}
                  >
                    <Box minW={0}>
                      <HStack spacing={2}>
                        <Text fontSize="sm" color="gray.200" noOfLines={1}>
                          {label}
                        </Text>
                        {field.type && (
                          <Badge fontSize="0.6rem" colorScheme="purple">
                            {field.type}
                          </Badge>
                        )}
                        {isMembershipAdmin && (
                          <Badge fontSize="0.6rem" colorScheme="gray">
                            {t('beheer', 'admin')}
                          </Badge>
                        )}
                      </HStack>
                      <Text fontSize="xs" color="gray.500">
                        {field.key}
                      </Text>
                    </Box>

                    {offerable ? (
                      // Read-only on-the-form badge — a scan-at-a-glance view of the state the modal
                      // authors (never an inline control here).
                      <Badge
                        colorScheme={on ? 'orange' : 'gray'}
                        data-testid={`application-field-status-${field.key}`}
                      >
                        {on
                          ? t('op formulier', 'on form')
                          : t('niet op formulier', 'off form')}
                      </Badge>
                    ) : (
                      <Text
                        fontSize="xs"
                        color="gray.500"
                        fontStyle="italic"
                        data-testid={`application-field-not-offerable-${field.key}`}
                      >
                        {t('niet beschikbaar', 'not available')}
                      </Text>
                    )}
                  </HStack>
                );
              })}
              {section.fields.length === 0 && (
                <Text fontSize="xs" color="gray.600">
                  {t('Geen velden in deze groep.', 'No fields in this group.')}
                </Text>
              )}
            </VStack>
          </Box>
        );
      })}
    </VStack>
  );
};

export default ApplicationFieldModalList;
