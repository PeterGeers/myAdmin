/**
 * Members Overview — "Applications inbox" preset bar (Member Application Form,
 * task 7.2). A thin row of preset entries that drive the EXISTING member overview
 * grid through the Table Filter Framework v2 — it renders NO grid of its own.
 *
 * - "Applications inbox" pins the grid to `status = application` (R8b.4, F3): the
 *   authoritative staff channel for finding applications, a view over the one
 *   member grid, not a new table.
 * - "Possible duplicates" / "Not auto-notified" quick-filter that inbox to the
 *   rows whose `overlay.additional_info` carries the stable `DUP` / `NO_NOTIFY`
 *   keyword the SAM create/notify path wrote (R8b.5).
 * - "Clear" drops the preset filters back to the full overview.
 *
 * All wiring lives in {@link useApplicationsInbox}; this component only renders
 * the entries and delegates. Labels come from the `members` i18n namespace.
 *
 * _Requirements: R8b.4, R8b.5, F3_
 */

import React from 'react';
import { Button, HStack, Text } from '@chakra-ui/react';
import { DUP_KEYWORD, NO_NOTIFY_KEYWORD, type InboxKeyword } from './useApplicationsInbox';

export interface MembersInboxBarProps {
  t: (key: string, opts?: Record<string, unknown>) => string;
  onActivateInbox: () => void;
  onFilterKeyword: (keyword: InboxKeyword) => void;
  onClear: () => void;
}

export const MembersInboxBar: React.FC<MembersInboxBarProps> = ({
  t,
  onActivateInbox,
  onFilterKeyword,
  onClear,
}) => (
  <HStack spacing={2} mb={3} wrap="wrap" data-testid="members-inbox-bar">
    <Text fontSize="sm" color="gray.400">{t('inbox.label')}</Text>
    <Button
      size="xs"
      variant="outline"
      colorScheme="orange"
      onClick={onActivateInbox}
      data-testid="members-inbox-activate"
    >
      {t('inbox.applications')}
    </Button>
    <Button
      size="xs"
      variant="ghost"
      colorScheme="orange"
      onClick={() => onFilterKeyword(DUP_KEYWORD)}
      data-testid="members-inbox-dup"
    >
      {t('inbox.duplicates')}
    </Button>
    <Button
      size="xs"
      variant="ghost"
      colorScheme="orange"
      onClick={() => onFilterKeyword(NO_NOTIFY_KEYWORD)}
      data-testid="members-inbox-no-notify"
    >
      {t('inbox.notNotified')}
    </Button>
    <Button
      size="xs"
      variant="ghost"
      colorScheme="gray"
      onClick={onClear}
      data-testid="members-inbox-clear"
    >
      {t('inbox.clear')}
    </Button>
  </HStack>
);
