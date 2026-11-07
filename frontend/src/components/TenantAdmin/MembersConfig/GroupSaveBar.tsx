/**
 * GroupSaveBar — the consistent per-group save footer for the Application Form Builder
 * (grouped per-group-save redesign).
 *
 * Each logical authoring group (Fields, Public address, Form settings, Look & feel) owns its OWN
 * deferred Save: edits stay in the builder's in-memory draft until THIS bar's Save is pressed, at
 * which point the group commits via its own backend endpoint. This bar standardises that footer so
 * every group looks and behaves the same — the earlier screen mixed a solid global Save, a weak
 * `outline` mail Save, and two inline slug/prefix buttons, which read as incoherent.
 *
 * Contract:
 *  - a right-aligned solid-orange Save button (one visual language for every group);
 *  - a left-pushed "unsaved changes" marker shown ONLY when `dirty` (dirty-gated per decision —
 *    there is no always-visible remark);
 *  - the button is disabled when `!dirty` (nothing to commit) or while `saving`;
 *  - an optional inline error slot (`error`) rendered under the bar — used by the Public address
 *    group to surface a server-side `ApiError` (400/422/409) next to its own Save rather than as a
 *    bare toast.
 *
 * It is presentational only: it owns no network call and no draft state. The owning group passes
 * `dirty`/`saving`/`error` and an `onSave` that performs the commit.
 */
import React from 'react';
import { Box, Button, HStack, Text } from '@chakra-ui/react';

export interface GroupSaveBarProps {
  /** Whether this group has unsaved edits. Gates the Save button AND the "unsaved" marker. */
  dirty: boolean;
  /** Whether this group's commit is in flight (shows the button's loading state). */
  saving?: boolean;
  /** Commit this group's draft (the owning group wires its own endpoint call). */
  onSave: () => void;
  /**
   * An optional caller-safe error message to render inline under the bar (e.g. a slug
   * validation 422 or a stale-version 409). Absent/empty → no error row.
   */
  error?: string | null;
  /** The Save button label (bilingual string already resolved by the caller). Defaults to Save. */
  label?: string;
  lang: 'nl' | 'en';
  /** Stable test id root; the button/marker/error derive their ids from it. */
  'data-testid'?: string;
}

/**
 * The shared per-group save footer. Kept deliberately small + prop-driven so every group renders an
 * identical bar (same colour, size, placement, disabled-when-clean behaviour).
 */
export const GroupSaveBar: React.FC<GroupSaveBarProps> = ({
  dirty,
  saving = false,
  onSave,
  error = null,
  label,
  lang,
  'data-testid': testId = 'group-save-bar',
}) => {
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const saveLabel = label ?? t('Opslaan', 'Save');

  return (
    <Box borderTopWidth="1px" borderColor="gray.700" mt={4} pt={4} data-testid={testId}>
      <HStack justify="flex-end">
        {dirty && (
          <Text
            fontSize="sm"
            color="yellow.300"
            mr="auto"
            data-testid={`${testId}-unsaved`}
          >
            {t('Niet-opgeslagen wijzigingen', 'Unsaved changes')}
          </Text>
        )}
        <Button
          colorScheme="orange"
          onClick={onSave}
          isLoading={saving}
          isDisabled={!dirty || saving}
          loadingText={t('Opslaan…', 'Saving…')}
          data-testid={`${testId}-save`}
        >
          {saveLabel}
        </Button>
      </HStack>
      {error && (
        <Text
          fontSize="sm"
          color="red.300"
          mt={2}
          data-testid={`${testId}-error`}
        >
          {error}
        </Text>
      )}
    </Box>
  );
};

export default GroupSaveBar;
