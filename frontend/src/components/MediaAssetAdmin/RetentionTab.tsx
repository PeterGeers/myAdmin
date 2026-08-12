/**
 * Retention Tab — Retention Settings Management
 *
 * Displays current retention period per asset category with source indicator
 * (system default vs tenant override). Allows inline editing and saving
 * changed values via PUT /api/assets/retention-settings.
 *
 * @module components/MediaAssetAdmin/RetentionTab
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Text,
  Badge,
  Button,
  NumberInput,
  NumberInputField,
  Spinner,
  Alert,
  AlertIcon,
  useToast,
} from '@chakra-ui/react';
import { fetchRetentionSettings, updateRetentionSettings } from '@/services/mediaAssetService';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import type { RetentionSettingsData } from '@/types/mediaAsset';

// ─── Constants ────────────────────────────────────────────────────────────────

/** Human-readable labels for retention category keys */
const CATEGORY_LABELS: Record<string, string> = {
  invoices_days: 'Invoices',
  branding_days: 'Branding',
  templates_days: 'Templates',
  landing_pages_days: 'Landing Pages',
  landing_pages_media_days: 'Landing Pages Media',
};

/** System default values for reference display */
const SYSTEM_DEFAULTS: Record<string, number> = {
  invoices_days: 2555,
  branding_days: 30,
  templates_days: 90,
  landing_pages_days: 7,
  landing_pages_media_days: 30,
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function RetentionTab() {
  const { t } = useTypedTranslation('admin');
  const [settings, setSettings] = useState<RetentionSettingsData | null>(null);
  const [editValues, setEditValues] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  // ── Data fetching ───────────────────────────────────────────────────────────

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRetentionSettings();
      setSettings(data);
      // Initialize edit values from current settings
      const initial: Record<string, number> = {};
      Object.entries(data).forEach(([key, setting]) => {
        initial[key] = setting.value;
      });
      setEditValues(initial);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load retention settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  // ── Change detection ────────────────────────────────────────────────────────

  const getChangedValues = (): Record<string, number> => {
    if (!settings) return {};
    const changes: Record<string, number> = {};
    Object.entries(editValues).forEach(([key, val]) => {
      if (settings[key] && val !== settings[key].value) {
        changes[key] = val;
      }
    });
    return changes;
  };

  const hasChanges = Object.keys(getChangedValues()).length > 0;

  // ── Save handler ────────────────────────────────────────────────────────────

  const handleSave = async () => {
    const changes = getChangedValues();
    if (Object.keys(changes).length === 0) return;

    setSaving(true);
    try {
      const result = await updateRetentionSettings(changes);
      toast({
        title: t('mediaAssets.retention.messages.success'),
        description: `Updated ${result.updated.length} retention setting${result.updated.length > 1 ? 's' : ''}`,
        status: 'success',
        duration: 4000,
        isClosable: true,
      });
      // Reload to get fresh source indicators
      await loadSettings();
    } catch (err) {
      toast({
        title: t('mediaAssets.retention.messages.failed'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Value change handler ────────────────────────────────────────────────────

  const handleValueChange = (key: string, valueStr: string) => {
    const val = parseInt(valueStr, 10);
    if (!isNaN(val) && val >= 0) {
      setEditValues((prev) => ({ ...prev, [key]: val }));
    }
  };

  // ── Render states ───────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" py={12}>
        <Spinner size="xl" color="orange.400" thickness="4px" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert status="error" bg="red.900" borderRadius="md">
        <AlertIcon />
        {error}
      </Alert>
    );
  }

  if (!settings) return null;

  const categoryKeys = Object.keys(settings);

  return (
    <VStack spacing={4} align="stretch" p={4}>
      {/* ── Header ─────────────────────────────────────────────── */}
      <HStack justifyContent="space-between" flexWrap="wrap" gap={2}>
        <Text color="gray.200" fontWeight="bold" fontSize="lg">
          Retention Settings
        </Text>
        <Button
          colorScheme="orange"
          size="sm"
          onClick={handleSave}
          isLoading={saving}
          loadingText="Saving..."
          isDisabled={!hasChanges}
        >
          {t('mediaAssets.retention.save')}
        </Button>
      </HStack>

      <Text color="gray.400" fontSize="sm">
        Configure how long orphaned assets are retained before becoming eligible
        for deletion. Values are in days.
      </Text>

      {/* ── Settings Table ─────────────────────────────────────── */}
      <Box bg="gray.800" borderRadius="md" overflowX="auto">
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th color="gray.400">{t('mediaAssets.retention.category')}</Th>
              <Th color="gray.400">{t('mediaAssets.retention.days')}</Th>
              <Th color="gray.400">{t('mediaAssets.retention.source')}</Th>
              <Th color="gray.400" isNumeric>System Default</Th>
            </Tr>
          </Thead>
          <Tbody>
            {categoryKeys.map((key) => {
              const setting = settings[key];
              const isOverride = setting.source === 'tenant_override';
              const isChanged = editValues[key] !== setting.value;

              return (
                <Tr key={key} _hover={{ bg: 'gray.700' }}>
                  <Td color="gray.200" fontWeight="medium">
                    {CATEGORY_LABELS[key] || key}
                  </Td>
                  <Td>
                    <NumberInput
                      size="sm"
                      min={1}
                      max={9999}
                      value={editValues[key] ?? setting.value}
                      onChange={(valStr) => handleValueChange(key, valStr)}
                      w="100px"
                    >
                      <NumberInputField
                        bg="gray.700"
                        color={isChanged ? 'orange.300' : 'gray.200'}
                        borderColor={isChanged ? 'orange.400' : 'gray.600'}
                        _hover={{ borderColor: 'gray.500' }}
                        _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                      />
                    </NumberInput>
                  </Td>
                  <Td>
                    <Badge
                      colorScheme={isOverride ? 'orange' : 'gray'}
                      variant="subtle"
                      fontSize="xs"
                    >
                      {isOverride ? t('mediaAssets.retention.sources.tenantOverride') : t('mediaAssets.retention.sources.systemDefault')}
                    </Badge>
                  </Td>
                  <Td color="gray.500" isNumeric fontSize="sm">
                    {SYSTEM_DEFAULTS[key] ?? '—'}
                  </Td>
                </Tr>
              );
            })}
          </Tbody>
        </Table>
      </Box>

      {/* ── Changed indicator ──────────────────────────────────── */}
      {hasChanges && (
        <HStack bg="gray.700" p={3} borderRadius="md">
          <Text color="orange.300" fontSize="sm">
            {Object.keys(getChangedValues()).length} unsaved change
            {Object.keys(getChangedValues()).length > 1 ? 's' : ''}
          </Text>
        </HStack>
      )}
    </VStack>
  );
}
