/**
 * Members Overview — header toolbar (title + global search + primary actions).
 * Extracted from `pages/MembersPage.tsx` during the file-length split
 * (code-quality-fixes 2026-10-15, task 6) with ZERO behaviour change: the
 * header `Flex`, the inline global search, the conditional bulk-transition
 * action, the column-chooser button, the admin-gated export action, and the
 * add action are moved verbatim. All state + handlers are owned by the page and
 * passed in as props.
 */

import React from 'react';
import {
  Flex, Text, Button, HStack,
  Input, InputGroup, InputLeftElement, InputRightElement, IconButton,
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, RepeatIcon, SearchIcon, CloseIcon, SettingsIcon } from '@chakra-ui/icons';

export interface MembersToolbarProps {
  t: (key: string, opts?: Record<string, unknown>) => string;
  loading: boolean;
  globalSearch: string;
  setGlobalSearch: (value: string) => void;
  selectedCount: number;
  onBulkOpen: () => void;
  onColumnChooserOpen: () => void;
  canExport: boolean;
  onExport: () => void;
  onAddOpen: () => void;
}

export const MembersToolbar: React.FC<MembersToolbarProps> = ({
  t,
  loading,
  globalSearch,
  setGlobalSearch,
  selectedCount,
  onBulkOpen,
  onColumnChooserOpen,
  canExport,
  onExport,
  onAddOpen,
}) => (
  <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
    <Text fontSize="xl" fontWeight="bold" color="white">{t('overview.title')}</Text>
    <HStack spacing={3}>
      {/* Global all-fields search (member-field-search Option 1), INLINE in the
          toolbar row. It narrows rows across EVERY candidate field (incl.
          non-visible overlay/calculated) before the per-column filter/sort
          toolkit, so the stats strip + table follow automatically. */}
      {!loading && (
        <InputGroup size="sm" w="auto" minW="14rem">
          <InputLeftElement pointerEvents="none">
            <SearchIcon color="gray.400" boxSize="12px" />
          </InputLeftElement>
          <Input
            value={globalSearch}
            onChange={(e) => setGlobalSearch(e.target.value)}
            placeholder={t('search.placeholder')}
            aria-label={t('search.ariaLabel')}
            bg="gray.700"
            color="white"
            _placeholder={{ color: 'gray.400' }}
            borderColor="gray.600"
            autoComplete="off"
            data-testid="members-global-search"
          />
          {globalSearch !== '' && (
            <InputRightElement>
              <IconButton
                size="xs"
                variant="ghost"
                colorScheme="orange"
                aria-label={t('search.clear')}
                icon={<CloseIcon boxSize="8px" />}
                onClick={() => setGlobalSearch('')}
                data-testid="members-global-search-clear"
              />
            </InputRightElement>
          )}
        </InputGroup>
      )}
      {/* Bulk transition action (task 20.4, R8.6) — appears only when ≥1 row
          is selected; opens the bulk-transition modal over the selection. */}
      {selectedCount > 0 && (
        <Button
          size="sm"
          leftIcon={<RepeatIcon />}
          colorScheme="orange"
          variant="ghost"
          onClick={onBulkOpen}
        >
          {t('bulkTransition.barLabel', { count: selectedCount })}
        </Button>
      )}
      {/* Column chooser action (session-columns task 4.1, R1/C2). */}
      <Button
        size="sm"
        leftIcon={<SettingsIcon />}
        colorScheme="orange"
        variant="ghost"
        onClick={onColumnChooserOpen}
        data-testid="members-column-chooser-button"
      >
        {t('columnChooser.button')}
      </Button>
      {/* Export action (task 20.2, R8.4) — gated to Tenant Admin / SysAdmin only. */}
      {canExport && (
        <Button
          size="sm"
          leftIcon={<DownloadIcon />}
          colorScheme="orange"
          variant="ghost"
          onClick={onExport}
        >
          {t('actions.export')}
        </Button>
      )}
      {/* Primary action: add / application (task 20.1, R8.3) — orange, header-right. */}
      <Button
        size="sm"
        leftIcon={<AddIcon />}
        colorScheme="orange"
        onClick={onAddOpen}
      >
        {t('actions.add')}
      </Button>
    </HStack>
  </Flex>
);
