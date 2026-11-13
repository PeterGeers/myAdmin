/**
 * MemberPivotToolbar — the Pivot Views selector + manage-set toolbar.
 *
 * Extracted verbatim from `MemberPivotViews.tsx` (code-quality task 10) with
 * ZERO behaviour change: a pure presentational component driven by props. All
 * state and handlers stay in the parent; every testid and i18n key is identical.
 */

import React from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Select,
  Tooltip,
} from '@chakra-ui/react';
import type { MemberAnalyticsSetSummary } from '../../../types/members';
import type { MemberAnalyticsCapabilities } from './areas/types';
import AnalyticsStateNotice from './areas/AnalyticsStateNotice';
import type { SelectableSet } from './memberPivotViewsHelpers';

type TFunction = (key: string, options?: Record<string, unknown>) => string;

export interface MemberPivotToolbarProps {
  t: TFunction;
  dropdownSets: SelectableSet[];
  selectedValue: string;
  onSelectValue: (value: string) => void;
  onExecute: () => void;
  selectedSet: SelectableSet | undefined;
  isExecuting: boolean;
  capabilities: MemberAnalyticsCapabilities;
  onOpenLibrary: () => void;
  onOpenMailStatus: () => void;
  canManageSets: boolean;
  onNewSet: () => void;
  onSaveAs: () => void;
  onUpdate: () => void;
  onDelivery: () => void;
  onSchedule: () => void;
  selectedModelSummary: MemberAnalyticsSetSummary | undefined;
  isDeliveringNow: boolean;
  onRequestDeliverNow: () => void;
  canSchedule: boolean;
  setsCount: number;
}

const MemberPivotToolbar: React.FC<MemberPivotToolbarProps> = ({
  t,
  dropdownSets,
  selectedValue,
  onSelectValue,
  onExecute,
  selectedSet,
  isExecuting,
  capabilities,
  onOpenLibrary,
  onOpenMailStatus,
  canManageSets,
  onNewSet,
  onSaveAs,
  onUpdate,
  onDelivery,
  onSchedule,
  selectedModelSummary,
  isDeliveringNow,
  onRequestDeliverNow,
  canSchedule,
  setsCount,
}) => (
  <>
        <HStack align="flex-end" spacing={3}>
          <FormControl maxW="sm">
            <FormLabel htmlFor="member-pivot-set-select" color="gray.300" fontSize="sm" mb={1}>
              {t('analytics.pivotViews.selectSet')}
            </FormLabel>
            {/* The dropdown lists ONLY the user's preferred saved sets (in saved
                order). There are no predefined presets — every view is one the
                user built generically and saved. The full library is behind the
                "All sets" button beside it. */}
            <Select
              id="member-pivot-set-select"
              placeholder={t('analytics.pivotViews.selectSetPlaceholder')}
              value={selectedValue}
              onChange={(e) => onSelectValue(e.target.value)}
              bg="gray.700"
              color="white"
              data-testid="member-pivot-set-select"
            >
              {dropdownSets.map((s) => (
                <option key={s.optionValue} value={s.optionValue}>
                  {s.label}
                </option>
              ))}
            </Select>
          </FormControl>

          {/* Execute — sits right next to the selected pivot (R1.6: nothing runs
              until clicked; disabled until a set is chosen). */}
          <Button
            colorScheme="orange"
            onClick={onExecute}
            isDisabled={!selectedSet}
            isLoading={isExecuting}
            data-testid="member-pivot-execute"
          >
            {t('analytics.pivotViews.execute')}
          </Button>

          {/* Secondary navigation collapsed into a quiet "More" menu (redesign
              Q2): the library browser ("All sets") + the send-status/history
              screen ("Mail status"). Neither is part of the run flow, so they
              sit behind one overflow control instead of competing with Execute.
              Mail status is export-gated (its read routes are, R9.3); All sets is
              always available. The item testids are preserved so existing flows
              (and tests) reach them unchanged — just open the menu first. */}
          <Menu>
            <MenuButton
              as={Button}
              variant="outline"
              colorScheme="orange"
              ml={2}
              data-testid="member-pivot-more"
            >
              {t('analytics.pivotViews.more')}
            </MenuButton>
            <MenuList bg="gray.800" borderColor="gray.600">
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onOpenLibrary}
                data-testid="member-pivot-open-library"
              >
                {t('analytics.pivotViews.library.open')}
              </MenuItem>
              {capabilities.canExport && (
                <MenuItem
                  bg="gray.800"
                  _hover={{ bg: 'gray.700' }}
                  onClick={onOpenMailStatus}
                  data-testid="member-pivot-open-mail-status"
                >
                  {t('analytics.mailRuns.action')}
                </MenuItem>
              )}
            </MenuList>
          </Menu>
        </HStack>

        {/* Save lifecycle actions (task 7.5) — all EXPLICIT user actions (R4.4b):
              - New set: compose + save a brand-new member set (R4.4);
              - Save as: save the selected set as a NEW variant (R4.4);
              - Update / Delete: act on the selected SAVED model only.
            Nothing here is auto-saved; the page's live filter is never baked into
            a saved set (R4.4a — the picker is never handed the page filter). */}
        {/* Create/edit a shared set needs members:export OR members:write (R11);
            delete needs members:write OR members:admin. A read-only caller sees
            no set-mutation actions at all (the whole HStack is gated). */}
        {/* Set-management actions collapsed into ONE "Manage set" menu
            (redesign Q1): New set / Save as / Update / Delivery / Deliver now /
            Schedule. They are occasional, admin-ish actions contextual to a
            selected saved set and rarely all needed at once, so a menu removes
            the wall of six buttons without changing any gate. Every item keeps
            its EXACT testid, onClick, and disabled rule, so existing flows and
            tests reach them unchanged — just open the menu first. */}
        {canManageSets && (
          <Menu>
            <MenuButton
              as={Button}
              variant="outline"
              colorScheme="orange"
              data-testid="member-pivot-manage-set"
            >
              {t('analytics.pivotViews.manageSet')}
            </MenuButton>
            <MenuList bg="gray.800" borderColor="gray.600" data-testid="member-pivot-set-actions">
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onNewSet}
                data-testid="member-pivot-new-set"
              >
                {t('analytics.pivotViews.newSet')}
              </MenuItem>
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onSaveAs}
                isDisabled={!selectedSet}
                data-testid="member-pivot-save-as"
              >
                {t('analytics.pivotViews.saveAs')}
              </MenuItem>
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onUpdate}
                isDisabled={!selectedModelSummary}
                data-testid="member-pivot-update"
              >
                {t('analytics.pivotViews.update')}
              </MenuItem>
              {/* Delivery — edit the SAVED set's stored delivery block (R3). */}
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={onDelivery}
                isDisabled={!selectedModelSummary}
                data-testid="member-pivot-delivery"
              >
                {t('analytics.delivery.action')}
              </MenuItem>
              {/* Deliver now — send the on-screen result to the set's stored fixed
                  recipients (R3.1/R3.2). A confirm dialog opens first so the send
                  is never fired blind. */}
              <MenuItem
                bg="gray.800"
                _hover={{ bg: 'gray.700' }}
                onClick={() => {
                  // Guard the open so a disabled item can never surface the
                  // confirm (Chakra's isDisabled does not always suppress the
                  // click handler in every environment).
                  if (!selectedModelSummary || isDeliveringNow) {
                    return;
                  }
                  onRequestDeliverNow();
                }}
                isDisabled={!selectedModelSummary || isDeliveringNow}
                data-testid="member-pivot-deliver-now"
              >
                {t('analytics.delivery.deliverNow')}
              </MenuItem>
              {/* Schedule — attach/manage a recurring run (R5). Offered only when
                  the caller may schedule; disabled (with a reason) for a set with
                  no delivery block. */}
              {canSchedule &&
                (selectedModelSummary && selectedModelSummary.hasDelivery !== true ? (
                  <Tooltip label={t('analytics.schedule.needsDelivery')}>
                    {/* A disabled MenuItem does not fire pointer events, so the
                        Tooltip wraps a focusable span to still surface the reason. */}
                    <MenuItem
                      bg="gray.800"
                      _hover={{ bg: 'gray.700' }}
                      isDisabled
                      data-testid="member-pivot-schedule"
                    >
                      {t('analytics.schedule.action')}
                    </MenuItem>
                  </Tooltip>
                ) : (
                  <MenuItem
                    bg="gray.800"
                    _hover={{ bg: 'gray.700' }}
                    onClick={onSchedule}
                    isDisabled={!selectedModelSummary}
                    data-testid="member-pivot-schedule"
                  >
                    {t('analytics.schedule.action')}
                  </MenuItem>
                ))}
            </MenuList>
          </Menu>
        )}

        {/* Empty Pivot Views entry point (bugfix §3). With the preset subsystem
            removed, a tenant with NO saved sets would otherwise see an empty
            dropdown and no obvious next step. Instead of a dead control, reuse
            the shared AnalyticsStateNotice in its EMPTY variant to explain that
            the user builds a view by picking fields to group/filter, with the
            existing MemberFieldPicker "New set" button as the single CTA (gated
            on the same create permission the Manage-set menu uses). Composed from
            existing building blocks only — no new component (steering 32/37). */}
        {setsCount === 0 && (
          <Box data-testid="member-pivot-empty-hint">
            <AnalyticsStateNotice
              kind="empty"
              message={t('analytics.pivotViews.emptyHint.message')}
              testId="member-pivot-empty-hint-notice"
            />
            {canManageSets && (
              <Button
                mt={3}
                colorScheme="orange"
                onClick={onNewSet}
                data-testid="member-pivot-empty-hint-new-set"
              >
                {t('analytics.pivotViews.newSet')}
              </Button>
            )}
          </Box>
        )}
  </>
);

export default MemberPivotToolbar;
