/**
 * Application field list — the "which fields appear on the public form" picker (spec 11, R2.1–R2.5,
 * design §3 table / §3.1 / §10).
 *
 * The R2 panel of the Application Form Builder: it renders the tenant's RESOLVED field list
 * (`GET /members/field-config`) grouped by `functional_group` and ordered by the catalog rule
 * `(group.order, field.order, key)`, and offers a per-row **on-the-form** toggle writing
 * `application_visible` onto the ONE working `field_overlay` object.
 *
 * ## One object, one save (design §3.1 / steering 38 rule 5)
 *
 * This component NEVER makes a network call. Exactly like `MembersFieldModal`, every toggle is a
 * pure `overlayModel.upsertField` transform of the one working overlay, bubbled up via `onChange`;
 * the builder root (`ApplicationFormBuilder`) commits that one object once via
 * `saveMembersParameter('field_overlay', …)` → `PUT /members/config/fields`. The write target per
 * field is provenance/origin-aware (mirrors the modal's `resolveWriteTarget`): a tenant-added field
 * is authored under `fields[key]`; a platform base field under `fixed_overrides[{group}.{key}]`.
 *
 * ## Offerability (R2.4 / R2.5)
 *
 *  - **Calculated / read-only fields are NOT offerable (R2.5).** A derived field (`origin:
 *    'calculated'`) or a platform read-only field is never put on the form; instead of a toggle the
 *    row shows a clear "not available" note, rather than silently accepting a toggle.
 *  - **Membership-admin fields default OFF but stay toggleable (R2.4).** A back-office storage-group
 *    field (`group: 'membership'`, e.g. `member_number` / `status`) defaults to NOT on the form, but
 *    the admin MAY still toggle a specific one on — inclusion is per field, never all-or-nothing.
 *
 * The current on-the-form state is read from the WORKING overlay first (so an unsaved toggle shows
 * immediately), falling back to the resolved field's served `application_visible`, then the
 * storage-group default. The resolved config is the DISPLAY source; the overlay is the WRITE model.
 */
import React, { useMemo } from 'react';
import {
  Badge,
  Box,
  Heading,
  HStack,
  Switch,
  Text,
  VStack,
} from '@chakra-ui/react';
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import {
  groupResolvedFields,
  resolveFieldConfigLabel,
} from '../../../services/membersConfigService';
import { findField, upsertField, type FieldOrigin } from './overlayModel';

export interface ApplicationFieldListProps {
  /** The resolved `FieldConfig` the list DISPLAYS from (null/absent → nothing to offer yet). */
  fieldConfig?: FieldConfig | null;
  /** The ONE working `field_overlay` object (the WRITE model + the current on-the-form state). */
  overlay: MembersConfigValue | undefined;
  /** Apply a mutated overlay — the list never saves; the builder commits once (Property 8). */
  onChange: (next: MembersConfigValue) => void;
  lang: 'nl' | 'en';
  /**
   * The key of the field currently SELECTED (drives the per-field attributes panel, spec 11 task
   * 3.1). Optional — when unwired the list is a pure on-the-form picker (task 2.3 behaviour).
   */
  selectedKey?: string | null;
  /**
   * Select a field (by key) to author its application attributes. Clicking an OFFERABLE row (away
   * from its toggle) selects it; a non-offerable row is never selectable. Optional — see above.
   */
  onSelect?: (key: string) => void;
}

/** The back-office STORAGE group whose fields default OFF the public form (R2.4). */
const MEMBERSHIP_STORAGE_GROUP = 'membership';

/**
 * Is this resolved field OFFERABLE on the public form (R2.5)? Calculated/derived fields and
 * platform read-only fields are never authorable onto the form — the row shows a note, not a toggle.
 */
function isOfferable(field: FieldConfigField): boolean {
  if (field.origin === 'calculated') return false;
  if (field.read_only === true) return false;
  return true;
}

/**
 * The origin-aware overlay write target for a field's application attribute (mirrors
 * `MembersFieldModal.resolveWriteTarget`): a base / base_overridden field authors a presentation
 * override under `fixed_overrides[{group}.{key}]`; a tenant-added (or unknown-provenance) field
 * authors under `fields[key]`. A field already living in a slice keeps being edited there
 * (`upsertField` never moves a field across maps), so the storage-group key only matters on the
 * FIRST write of a base field.
 */
function writeTarget(field: FieldConfigField): { origin: FieldOrigin; overlayKey: string } {
  const isBase =
    field.origin === 'fixed' ||
    field.provenance === 'base' ||
    field.provenance === 'base_overridden';
  if (isBase) {
    const group = typeof field.group === 'string' && field.group ? field.group : '';
    return { origin: 'fixed_overrides', overlayKey: group ? `${group}.${field.key}` : field.key };
  }
  return { origin: 'fields', overlayKey: field.key };
}

/**
 * The effective on-the-form state for a field (R2.2/R2.3/R2.4). Precedence:
 *  1. the WORKING overlay's authored `application_visible` (an unsaved toggle wins, by either the
 *     bare key or the `{group}.{key}` override key the toggle writes under);
 *  2. the resolved field's served `application_visible`;
 *  3. the storage-group default — membership-admin fields default OFF (R2.4), everything else OFF
 *     until the admin opts it in (R2.3 "toggling off clears to the default").
 */
function isOnForm(overlay: MembersConfigValue | undefined, field: FieldConfigField): boolean {
  const target = writeTarget(field);
  const authored =
    findField(overlay, target.overlayKey)?.field.application_visible ??
    findField(overlay, field.key)?.field.application_visible;
  if (typeof authored === 'boolean') return authored;
  const served = (field as { application_visible?: boolean }).application_visible;
  if (typeof served === 'boolean') return served;
  // Default: off (membership-admin fields and everything else start off; R2.4/R2.3).
  return false;
}

export const ApplicationFieldList: React.FC<ApplicationFieldListProps> = ({
  fieldConfig,
  overlay,
  onChange,
  lang,
  selectedKey = null,
  onSelect,
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);

  // Grouped by `functional_group`, ordered `(group.order, field.order, key)` — the catalog rule,
  // reusing the shared hierarchy builder (R2.1). A trailing bucket surfaces any field whose group
  // is not catalog-resolvable, never silently dropping it.
  const sections = useMemo(() => groupResolvedFields(fieldConfig), [fieldConfig]);

  const toggle = (field: FieldConfigField, on: boolean) => {
    const target = writeTarget(field);
    // Toggling OFF clears the attribute to its default (R2.3); toggling ON writes true.
    const patch = { application_visible: on ? true : undefined };
    onChange(upsertField(overlay, target.overlayKey, patch, target.origin));
  };

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
                return (
                  <HStack
                    key={field.key}
                    justify="space-between"
                    bg={selectedKey === field.key ? 'gray.700' : 'gray.750'}
                    borderWidth="1px"
                    borderColor={selectedKey === field.key ? 'orange.400' : 'gray.700'}
                    borderRadius="md"
                    px={3}
                    py={2}
                    cursor={offerable ? 'pointer' : undefined}
                    onClick={() => offerable && onSelect?.(field.key)}
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
                      <Switch
                        isChecked={on}
                        onChange={(e) => toggle(field, e.target.checked)}
                        colorScheme="orange"
                        data-testid={`application-field-toggle-${field.key}`}
                        aria-label={t(
                          `${label} op het formulier`,
                          `${label} on the form`,
                        )}
                      />
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

export default ApplicationFieldList;
