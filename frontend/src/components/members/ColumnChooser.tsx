/**
 * ColumnChooser — pick which member fields show as columns (session-columns C2,
 * task 3.1; R1.1–R1.5, R7.2).
 *
 * A thin, keyboard-accessible Chakra modal opened from a toolbar button on
 * `MembersPage`. It lists EVERY candidate field (`fields.filter(isColumnCandidate)`
 * — fixed, overlay, and calculated alike, OQ-3) through the shared
 * {@link FieldChecklist}, so this chooser and the analytics pivot picker never
 * drift into two near-identical widgets (R4.1). The two differ only in output
 * contract: the pivot picker composes a `PivotConfig`; this chooser emits the
 * ordered chosen-key `string[]`.
 *
 * Selection model (R1.2 / R1.3):
 *   - `selectedKeys` = the currently-shown columns (rendered checked); every
 *     other candidate is unchecked.
 *   - Checking a field ADDS it as a column (appended, preserving order); un-
 *     checking a currently-shown field REMOVES it. The user's selection fully
 *     determines the shown set — columns are never duplicated.
 *   - `member_number` is the ONE always-on, non-toggleable column (R7.2): it is
 *     the only `disabledKeys` entry handed to the checklist (rendered checked +
 *     locked) and is NEVER part of the emitted list — it is implied and pinned
 *     first by the page (R7.1/R7.3).
 *
 * This component is PRESENTATION + selection only. It owns no persistence: it
 * reports each change via `onChange(nextKeys)`; the page both applies the result
 * live AND persists it (that wiring is task 4.1 / design C8 — NOT this component).
 *
 * Accessibility: the Chakra `Modal` traps focus, closes on Escape, and restores
 * focus on close; every label resolves from the `members` i18n namespace under
 * `columnChooser.*` (no hardcoded English, R1.5).
 *
 * @module components/members/ColumnChooser
 * @see .kiro/specs/Members/member-field-search/session-columns (design C2; R1, R7.2)
 */

import React, { useMemo, useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Button,
  Text,
  VStack,
  Input,
  InputGroup,
  InputLeftElement,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import type { FieldConfig } from '../../types/members';
import { isColumnCandidate } from './fieldValue';
import FieldChecklist, { resolveLabel } from './FieldChecklist';

/**
 * The one always-on, non-toggleable column (R7.2). It is handed to the checklist
 * as the sole `disabledKeys` entry (shown checked + locked) and is never part of
 * the emitted chosen-key list — the page pins it first unconditionally (R7.1).
 */
export const ALWAYS_ON_COLUMN_KEY = 'member_number';

/** `members`-namespace i18n key prefix for every label this modal renders. */
const T = 'columnChooser';

export interface ColumnChooserProps {
  /** Whether the modal is open. */
  isOpen: boolean;
  /** Close handler (overlay / Escape / Cancel / close button). */
  onClose: () => void;
  /** The resolved field config whose candidate fields the chooser lists (R1.1). */
  fieldConfig: FieldConfig | null;
  /**
   * The currently-shown column keys (checked). `member_number` need not be
   * present (it is implied + always-on); if it is, it is ignored here since the
   * checklist renders it locked-on regardless (R7.3).
   */
  selectedKeys: string[];
  /** Active language for bilingual label resolution. */
  language: string;
  /**
   * Fired with the FULL updated ordered chosen-key list on every toggle. Never
   * includes `member_number` (implied, R7.3). The page applies it live AND
   * persists it (C8 — not this component's concern).
   */
  onChange: (nextKeys: string[]) => void;
}

/**
 * The candidate fields the chooser lists: every visible field
 * (`isColumnCandidate`), minus `member_number` (surfaced as always-on, not a
 * toggleable candidate, R7.2) and any field without a usable key.
 */
function candidateFields(fieldConfig: FieldConfig | null) {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return [];
  return fields.filter(
    (f) => !!f && typeof f.key === 'string' && f.key !== '' && isColumnCandidate(f),
  );
}

export const ColumnChooser: React.FC<ColumnChooserProps> = ({
  isOpen,
  onClose,
  fieldConfig,
  selectedKeys,
  language,
  onChange,
}) => {
  const { t } = useTypedTranslation('members');
  const lang = (language || 'nl').slice(0, 2);

  // A local, case-insensitive filter over the candidate labels so a long field
  // catalog stays navigable (i18n `filterPlaceholder` / `empty`).
  const [filter, setFilter] = useState('');

  const candidates = useMemo(() => candidateFields(fieldConfig), [fieldConfig]);

  // The checklist always lists member_number FIRST as the locked always-on
  // column, then the (optionally filtered) remaining candidates. member_number
  // is excluded from the normal candidate pool above, so it is never duplicated.
  const memberNumberField = useMemo(
    () => (fieldConfig?.fields ?? []).find((f) => f?.key === ALWAYS_ON_COLUMN_KEY),
    [fieldConfig],
  );

  const visibleCandidates = useMemo(() => {
    const toggleable = candidates.filter((f) => f.key !== ALWAYS_ON_COLUMN_KEY);
    const needle = filter.trim().toLowerCase();
    const filtered = needle
      ? toggleable.filter((f) =>
          resolveLabel(f.label, lang, f.key).toLowerCase().includes(needle),
        )
      : toggleable;
    // Prepend the always-on member_number descriptor (unfiltered) so it is
    // always visible + locked at the top (R7.2).
    return memberNumberField ? [memberNumberField, ...filtered] : filtered;
  }, [candidates, filter, lang, memberNumberField]);

  // The emitted set never carries member_number (implied, R7.3); keep local
  // display selection aligned with that contract.
  const checklistSelected = useMemo(
    () => selectedKeys.filter((k) => k !== ALWAYS_ON_COLUMN_KEY),
    [selectedKeys],
  );

  /**
   * Toggle a candidate key: append when newly checked (preserving order),
   * remove when unchecked. member_number is locked, so a toggle can never
   * target it; guard defensively anyway. Emits the full updated ordered list
   * (R1.3) — the user's selection fully determines the shown set.
   */
  const handleToggle = (key: string) => {
    if (key === ALWAYS_ON_COLUMN_KEY) return;
    const current = checklistSelected;
    const next = current.includes(key)
      ? current.filter((k) => k !== key)
      : [...current, key];
    onChange(next);
  };

  const hasCandidates = visibleCandidates.length > 0;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="column-chooser">
        <ModalHeader>{t(`${T}.title`)}</ModalHeader>
        <ModalCloseButton aria-label={t(`${T}.cancel`)} />
        <ModalBody>
          <VStack align="stretch" spacing={4}>
            <Text fontSize="sm" color="gray.300" data-testid="column-chooser-description">
              {t(`${T}.description`)}
            </Text>

            {/* Case-insensitive label filter over the toggleable candidates. */}
            <InputGroup>
              <InputLeftElement pointerEvents="none" color="gray.400" aria-hidden>
                🔍
              </InputLeftElement>
              <Input
                aria-label={t(`${T}.filterPlaceholder`)}
                placeholder={t(`${T}.filterPlaceholder`)}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                bg="gray.900"
                color="white"
                _placeholder={{ color: 'gray.400' }}
                data-testid="column-chooser-filter"
              />
            </InputGroup>

            {hasCandidates ? (
              <FieldChecklist
                fields={visibleCandidates}
                selectedKeys={checklistSelected}
                disabledKeys={[ALWAYS_ON_COLUMN_KEY]}
                functionalGroups={fieldConfig?.functional_groups}
                lang={lang}
                onToggle={handleToggle}
                testIdPrefix="column-chooser"
              />
            ) : (
              <Text fontSize="sm" color="gray.500" data-testid="column-chooser-empty">
                {t(`${T}.empty`)}
              </Text>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} data-testid="column-chooser-close">
            {t(`${T}.cancel`)}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default ColumnChooser;
