/**
 * Members config DELIVERED/LOADED status banner (impact-analysis Phase 0 step 3, risk #6).
 *
 * The `members.*` config is authored on the Flask/MySQL plane and projected one-directionally
 * into the SAM module's `config#*` rows. This small, presentation-only banner surfaces the
 * module's projected status (from `GET /members/field-config` → `config_status`) so a Tenant
 * Admin can see, per config, whether a saved edit has actually been projected (DELIVERED and
 * what the module LOADS) or has NEVER been delivered yet.
 *
 * It renders one row per authorable config:
 *   - a non-null version  → "delivered" (green), with the version shown as the loaded marker;
 *   - a null version      → "not yet delivered" (amber);
 *   - status unavailable  → an older module build omitted `config_status` entirely → nothing is
 *     claimed (the banner is hidden) rather than falsely reporting "not delivered".
 *
 * Enforcement lives server-side; this banner claims nothing beyond what the module reports.
 */
import React from 'react';
import { Badge, Box, HStack, Text, VStack } from '@chakra-ui/react';
import { MEMBERS_PARAM_TO_CONFIG_ID } from '../../../services/membersConfigService';

export interface MembersConfigStatusProps {
  /**
   * The module's projected `config_status` map `{config_id: version | null}` from
   * `getMembersConfigStatus()`. An empty / undefined map means "status unavailable" (older
   * module build) → the banner renders nothing.
   */
  status?: Record<string, string | number | null>;
  /** UI language for the inline labels (matches the editor's `lang` convention). */
  lang: 'nl' | 'en';
}

/** The per-config labels shown in the banner, in editor order. */
const CONFIG_LABELS: Record<string, { nl: string; en: string }> = {
  fields: { nl: 'Veldoverlay', en: 'Field overlay' },
  scope: { nl: 'Scope-dimensies', en: 'Scope dimensions' },
  views: { nl: 'Weergavecontexten', en: 'View contexts' },
  mail: { nl: 'E-mail', en: 'Mail' },
};

/** Render order: the three authorable params (by their config id) then the mail gate. */
const CONFIG_ORDER: string[] = [
  ...Object.values(MEMBERS_PARAM_TO_CONFIG_ID),
  'mail',
];

export const MembersConfigStatus: React.FC<MembersConfigStatusProps> = ({ status, lang }) => {
  // Status unavailable (older module build, or the fetch failed → empty map): claim nothing.
  if (!status || Object.keys(status).length === 0) {
    return null;
  }

  const title = lang === 'nl' ? 'Projectiestatus' : 'Projection status';
  const delivered = lang === 'nl' ? 'Geleverd' : 'Delivered';
  const notDelivered = lang === 'nl' ? 'Nog niet geleverd' : 'Not yet delivered';
  const loadedPrefix = lang === 'nl' ? 'geladen versie' : 'loaded version';

  return (
    <Box
      data-testid="members-config-status"
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
      <VStack align="stretch" spacing={1}>
        {CONFIG_ORDER.map((configId) => {
          // A config id the module did not report at all is skipped (nothing to claim).
          if (!(configId in status)) return null;
          const version = status[configId];
          const isDelivered = version !== null && version !== undefined;
          const label = CONFIG_LABELS[configId];
          const labelText = label ? label[lang] : configId;
          return (
            <HStack
              key={configId}
              justify="space-between"
              data-testid={`members-config-status-${configId}`}
            >
              <Text fontSize="sm" color="gray.200">
                {labelText}
              </Text>
              <HStack spacing={2}>
                {isDelivered && (
                  <Text fontSize="xs" color="gray.500">
                    {loadedPrefix}: {String(version)}
                  </Text>
                )}
                <Badge
                  colorScheme={isDelivered ? 'green' : 'yellow'}
                  data-testid={`members-config-status-${configId}-badge`}
                >
                  {isDelivered ? delivered : notDelivered}
                </Badge>
              </HStack>
            </HStack>
          );
        })}
      </VStack>
    </Box>
  );
};

export default MembersConfigStatus;
