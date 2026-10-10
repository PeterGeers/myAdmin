/**
 * MemberDeliveryEditor — the stored-delivery editor on a saved member set
 * (pivot-output-actions R3, design §2.1 / §3 / §10, task 3.4).
 *
 * A keyboard-accessible Chakra modal, opened from the "Delivery" lifecycle action
 * beside Update on a SELECTED saved set in {@link MemberPivotViews}. It edits the
 * set's OPTIONAL `delivery` block — the "what to do with the result" instruction a
 * run/schedule repeats without re-entering everything (R3). It does NOT run or
 * schedule anything; it only persists the instruction.
 *
 * What it edits (design §2.1):
 *   - **mode** (the discriminator):
 *       - `per_recipient` — mail each member in the result individually with
 *         mail-merge, using a STORED template (picked via `memberTemplateService`,
 *         the task 2.5 picker surface). Stores NO recipients (addresses resolve
 *         from the dataset at run time).
 *       - `to_fixed` — send the result as an attachment to an explicit, stored
 *         `recipients` list (e.g. a handling agent).
 *   - **attachment**: none | `csv` | `pdf_labels`.
 *   - **label_options** (only when `attachment === 'pdf_labels'`): edited through
 *     the ONE shared {@link LabelOptions} model (task 6.3, `./labelOptions`) — NOT
 *     a second, forked options shape. Projected to/from the stored snake_case
 *     block by the service mapper (`deliveryToBackend`/`deliveryFromBackend`).
 *
 * It MIRRORS the SAM entity's `validate()` rules so an invalid save is blocked
 * CLIENT-SIDE (the backend remains the authority, task 3.3):
 *   - `to_fixed` requires at least one valid recipient address;
 *   - `per_recipient` stores no recipients (the recipients field is not shown).
 *
 * Persistence (design §3): Save → `PUT /members/analytics-sets/{id}/delivery`
 * (`putAnalyticsSetDelivery`); Clear → `DELETE .../delivery`
 * (`deleteAnalyticsSetDelivery`). These are the DEDICATED delivery route (task
 * 3.3); the create/update set bodies deliberately do NOT carry delivery. The gate
 * is `members:export` + scope (no new permission) — the parent only mounts this on
 * a saved set the user can manage.
 *
 * No hardcoded English: every label resolves from the `members` namespace
 * (`analytics.delivery.*`, reusing `analytics.labels.*` for the label-options
 * sub-UI), bilingual via the active language. Native `<select>`/`<input>` controls
 * are keyboard-navigable.
 *
 * @module components/members/analytics/MemberDeliveryEditor
 * @see .kiro/specs/Members/pivot-output-actions (requirements R3; design §2.1, §3, §10)
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Text,
  Textarea,
  VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type {
  MemberDelivery,
  MemberDeliveryAttachment,
  MemberDeliveryMode,
} from '../../../types/members';
import {
  listMemberTemplates,
  type MemberTemplateDto,
} from '../../../services/memberTemplateService';
import {
  AVERY_LABEL_FORMATS,
  MAX_FONT_SIZE,
  MIN_FONT_SIZE,
  type LabelAlignment,
  type LabelSortOrder,
} from './addressLabelService';
import {
  defaultLabelOptions,
  normalizeLabelOptions,
  type LabelOptions,
} from './labelOptions';
import { isValidEmail, parseExternalRecipients } from './MemberMailCompose';

/** `members`-namespace i18n key prefix for every label this modal renders. */
const T = 'analytics.delivery';

/** The delivery modes offered, in display order (keeps the select + type in lock-step). */
const MODES: readonly MemberDeliveryMode[] = ['per_recipient', 'to_fixed'];
/** The attachment options; `'none'` is the UI sentinel for a `null` attachment. */
const ATTACHMENTS: readonly ('none' | MemberDeliveryAttachment)[] = [
  'none',
  'csv',
  'pdf_labels',
];
/** Available label-option alignments / sort orders (mirror AddressLabelGenerator). */
const ALIGNMENTS: readonly LabelAlignment[] = ['left', 'center', 'right'];
const SORT_ORDERS: readonly LabelSortOrder[] = ['name', 'postcode', 'region'];

export interface MemberDeliveryEditorProps {
  /** Whether the modal is open. */
  isOpen: boolean;
  /** Close handler (overlay / Escape / Cancel). */
  onClose: () => void;
  /** The saved set's backend `set_id` the delivery is attached to. */
  setId: string;
  /** The saved set's name (shown in the header for context). */
  setName: string;
  /** The set's EXISTING delivery block, or `undefined` for a set with none yet. */
  initialDelivery?: MemberDelivery;
  /** Active language for bilingual label resolution + template seeding. */
  language: string;
  /**
   * Persist the delivery (PUT the dedicated route). Resolves on success; rejects
   * on failure (the modal surfaces a toast and stays open). Injectable for tests;
   * the parent passes `putAnalyticsSetDelivery` bound to the set id.
   */
  onSave: (delivery: MemberDelivery) => Promise<void>;
  /**
   * Clear the delivery (DELETE the dedicated route). Resolves on success; rejects
   * on failure. Injectable for tests; the parent passes `deleteAnalyticsSetDelivery`.
   */
  onClear: () => Promise<void>;
  /**
   * List the tenant's stored templates for the `per_recipient` template picker.
   * Injectable for tests; defaults to the authenticated {@link listMemberTemplates}.
   */
  listTemplates?: typeof listMemberTemplates;
}

/**
 * The `to_fixed` recipients rule, mirrored from the SAM entity's `validate()`: a
 * `to_fixed` delivery MUST carry at least one valid recipient address. Pure, so
 * the Save gate and the test share the same predicate.
 */
export function hasValidFixedRecipients(recipients: string[]): boolean {
  return recipients.some((addr) => isValidEmail(addr));
}

const MemberDeliveryEditor: React.FC<MemberDeliveryEditorProps> = ({
  isOpen,
  onClose,
  setId,
  setName,
  initialDelivery,
  language,
  onSave,
  onClear,
  listTemplates = listMemberTemplates,
}) => {
  const { t } = useTypedTranslation('members');

  // --- Form state (seeded from the existing delivery, if any). ---------------
  const [mode, setMode] = useState<MemberDeliveryMode>('per_recipient');
  const [templateId, setTemplateId] = useState<string>('');
  // `'none'` is the UI sentinel; mapped to a `null` attachment on save.
  const [attachment, setAttachment] = useState<'none' | MemberDeliveryAttachment>('none');
  // `to_fixed` recipients as a free-text field (comma/semicolon/newline/space
  // separated), parsed + validated the SAME way the compose modal parses external
  // recipients (reuse, no second parser).
  const [recipientsRaw, setRecipientsRaw] = useState<string>('');
  const [labelOptions, setLabelOptions] = useState<LabelOptions>(defaultLabelOptions());

  const [isSaving, setIsSaving] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Stored templates for the per_recipient picker (loaded on open). A load
  // failure degrades to an empty picker (never a crash) — the user can still save
  // a per_recipient delivery with no template (template is optional, design §2.1).
  const [templates, setTemplates] = useState<MemberTemplateDto[]>([]);

  // (Re)seed the form from the existing delivery whenever the modal opens for a
  // (possibly different) set, so re-opening never shows a stale draft.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setSaveError(null);
    if (initialDelivery) {
      setMode(initialDelivery.mode);
      setTemplateId(initialDelivery.templateId ?? '');
      setAttachment(initialDelivery.attachment ?? 'none');
      setRecipientsRaw(initialDelivery.recipients.join(', '));
      setLabelOptions(
        initialDelivery.labelOptions
          ? normalizeLabelOptions(initialDelivery.labelOptions)
          : defaultLabelOptions(),
      );
    } else {
      setMode('per_recipient');
      setTemplateId('');
      setAttachment('none');
      setRecipientsRaw('');
      setLabelOptions(defaultLabelOptions());
    }
  }, [isOpen, setId, initialDelivery]);

  // Load the stored templates for the picker on open.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    let active = true;
    void listTemplates()
      .then((res) => {
        if (active && res.ok) {
          // Defensive: the service guarantees an array, but guard here too so a
          // malformed payload degrades to an empty picker instead of crashing the
          // SPA on `templates.map` (never a crash — design §2.1).
          setTemplates(Array.isArray(res.data) ? res.data : []);
        } else if (active) {
          setTemplates([]);
        }
      })
      .catch(() => {
        if (active) {
          setTemplates([]);
        }
      });
    return () => {
      active = false;
    };
  }, [isOpen, listTemplates]);

  // The parsed + validated `to_fixed` recipient addresses (reusing the compose
  // modal's parser so the two surfaces split identically). Valid, de-duplicated
  // (case-insensitive); invalid tokens are surfaced as a client-side reason.
  const { validRecipients, invalidTokens } = useMemo(() => {
    const tokens = parseExternalRecipients(recipientsRaw);
    const seen = new Set<string>();
    const valid: string[] = [];
    const invalid: string[] = [];
    for (const token of tokens) {
      if (isValidEmail(token)) {
        const norm = token.trim().toLowerCase();
        if (!seen.has(norm)) {
          seen.add(norm);
          valid.push(token.trim());
        }
      } else {
        invalid.push(token);
      }
    }
    return { validRecipients: valid, invalidTokens: invalid };
  }, [recipientsRaw]);

  // Mirror the SAM entity's `validate()` so an invalid save is blocked CLIENT-SIDE
  // (the backend is still the authority). `to_fixed` requires ≥1 valid recipient;
  // `per_recipient` stores none (so recipients never gate it).
  const canSave = useMemo(() => {
    if (mode === 'to_fixed') {
      return hasValidFixedRecipients(validRecipients);
    }
    return true; // per_recipient: no recipient requirement
  }, [mode, validRecipients]);

  // Build the camelCase MemberDelivery from the form, applying the mode rules so
  // the persisted block is well-formed: per_recipient stores NO recipients and
  // CAN carry a template; to_fixed stores the explicit recipients and no template.
  // label_options travel ONLY with a pdf_labels attachment.
  const buildDelivery = useCallback((): MemberDelivery => {
    const attach: MemberDeliveryAttachment | null =
      attachment === 'none' ? null : attachment;
    return {
      mode,
      templateId: mode === 'per_recipient' && templateId !== '' ? templateId : null,
      attachment: attach,
      recipients: mode === 'to_fixed' ? validRecipients : [],
      labelOptions: attach === 'pdf_labels' ? labelOptions : null,
    };
  }, [mode, templateId, attachment, validRecipients, labelOptions]);

  const handleSave = useCallback(async () => {
    if (!canSave) {
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      await onSave(buildDelivery());
      onClose();
    } catch {
      setSaveError(t(`${T}.saveError`));
    } finally {
      setIsSaving(false);
    }
  }, [canSave, onSave, buildDelivery, onClose, t]);

  const handleClear = useCallback(async () => {
    setIsClearing(true);
    setSaveError(null);
    try {
      await onClear();
      onClose();
    } catch {
      setSaveError(t(`${T}.clearError`));
    } finally {
      setIsClearing(false);
    }
  }, [onClear, onClose, t]);

  const showsPdfLabels = attachment === 'pdf_labels';

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="2xl" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="member-delivery-editor">
        <ModalHeader>{t(`${T}.title`, { name: setName })}</ModalHeader>
        <ModalCloseButton />
        <ModalBody pb={4}>
          <VStack align="stretch" spacing={4}>
            <Text color="gray.400" fontSize="sm" data-testid="member-delivery-intro">
              {t(`${T}.intro`)}
            </Text>

            {/* Mode discriminator. */}
            <FormControl>
              <FormLabel htmlFor="delivery-mode" color="gray.300" fontSize="sm" mb={1}>
                {t(`${T}.mode`)}
              </FormLabel>
              <Select
                id="delivery-mode"
                value={mode}
                onChange={(e) => setMode(e.target.value as MemberDeliveryMode)}
                bg="gray.700"
                color="white"
                data-testid="delivery-mode-select"
              >
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {t(`${T}.modes.${m}`)}
                  </option>
                ))}
              </Select>
              <Text color="gray.500" fontSize="xs" mt={1}>
                {t(`${T}.modeHint.${mode}`)}
              </Text>
            </FormControl>

            {/* per_recipient → stored template picker (R2 / task 2.5 surface).
                Stores NO recipients (resolved from the dataset at run time). */}
            {mode === 'per_recipient' && (
              <FormControl>
                <FormLabel htmlFor="delivery-template" color="gray.300" fontSize="sm" mb={1}>
                  {t(`${T}.template`)}
                </FormLabel>
                <Select
                  id="delivery-template"
                  placeholder={t(`${T}.templatePlaceholder`)}
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  bg="gray.700"
                  color="white"
                  data-testid="delivery-template-select"
                >
                  {templates.map((tpl) => (
                    <option key={tpl.template_id} value={tpl.template_id}>
                      {tpl.name}
                    </option>
                  ))}
                </Select>
              </FormControl>
            )}

            {/* to_fixed → explicit recipients (required ≥1). */}
            {mode === 'to_fixed' && (
              <FormControl isInvalid={!canSave || invalidTokens.length > 0}>
                <FormLabel htmlFor="delivery-recipients" color="gray.300" fontSize="sm" mb={1}>
                  {t(`${T}.recipients`)}
                </FormLabel>
                <Textarea
                  id="delivery-recipients"
                  value={recipientsRaw}
                  onChange={(e) => setRecipientsRaw(e.target.value)}
                  placeholder={t(`${T}.recipientsPlaceholder`)}
                  bg="gray.700"
                  color="white"
                  _placeholder={{ color: 'gray.400' }}
                  rows={2}
                  data-testid="delivery-recipients-input"
                />
                {invalidTokens.length > 0 && (
                  <Text color="red.300" fontSize="xs" mt={1} data-testid="delivery-recipients-invalid">
                    {t(`${T}.recipientsInvalid`, { addresses: invalidTokens.join(', ') })}
                  </Text>
                )}
                {!canSave && invalidTokens.length === 0 && (
                  <Text color="red.300" fontSize="xs" mt={1} data-testid="delivery-recipients-required">
                    {t(`${T}.recipientsRequired`)}
                  </Text>
                )}
              </FormControl>
            )}

            {/* Attachment: none | csv | pdf_labels. */}
            <FormControl>
              <FormLabel htmlFor="delivery-attachment" color="gray.300" fontSize="sm" mb={1}>
                {t(`${T}.attachment`)}
              </FormLabel>
              <Select
                id="delivery-attachment"
                value={attachment}
                onChange={(e) =>
                  setAttachment(e.target.value as 'none' | MemberDeliveryAttachment)
                }
                bg="gray.700"
                color="white"
                data-testid="delivery-attachment-select"
              >
                {ATTACHMENTS.map((a) => (
                  <option key={a} value={a}>
                    {t(`${T}.attachments.${a}`)}
                  </option>
                ))}
              </Select>
            </FormControl>

            {/* label_options — ONLY for pdf_labels, edited through the ONE shared
                LabelOptions model (task 6.3). Reuses the `analytics.labels.*`
                i18n keys the interactive generator uses (no second vocabulary). */}
            {showsPdfLabels && (
              <Box
                borderWidth="1px"
                borderColor="gray.600"
                borderRadius="md"
                p={3}
                data-testid="delivery-label-options"
              >
                <Text color="gray.300" fontSize="sm" mb={2}>
                  {t(`${T}.labelOptions`)}
                </Text>
                <VStack align="stretch" spacing={3}>
                  <HStack align="flex-end" spacing={3} flexWrap="wrap">
                    <FormControl maxW="xs">
                      <FormLabel htmlFor="delivery-label-format" color="gray.300" fontSize="sm" mb={1}>
                        {t('analytics.labels.format')}
                      </FormLabel>
                      <Select
                        id="delivery-label-format"
                        value={labelOptions.format}
                        onChange={(e) =>
                          setLabelOptions((prev) => ({ ...prev, format: e.target.value }))
                        }
                        bg="gray.700"
                        color="white"
                        data-testid="delivery-label-format-select"
                      >
                        {AVERY_LABEL_FORMATS.map((fmt) => (
                          <option key={fmt.key} value={fmt.key}>
                            {fmt.name}
                          </option>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl maxW="xs">
                      <FormLabel htmlFor="delivery-label-sort" color="gray.300" fontSize="sm" mb={1}>
                        {t('analytics.labels.sortOrder')}
                      </FormLabel>
                      <Select
                        id="delivery-label-sort"
                        value={labelOptions.sortOrder}
                        onChange={(e) =>
                          setLabelOptions((prev) => ({
                            ...prev,
                            sortOrder: e.target.value as LabelSortOrder,
                          }))
                        }
                        bg="gray.700"
                        color="white"
                        data-testid="delivery-label-sort-select"
                      >
                        {SORT_ORDERS.map((order) => (
                          <option key={order} value={order}>
                            {t(`analytics.labels.sort.${order}`)}
                          </option>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl maxW="36">
                      <FormLabel htmlFor="delivery-label-start" color="gray.300" fontSize="sm" mb={1}>
                        {t('analytics.labels.startPosition')}
                      </FormLabel>
                      <Input
                        id="delivery-label-start"
                        type="number"
                        min={0}
                        value={labelOptions.startPosition}
                        onChange={(e) => {
                          const next = Number.parseInt(e.target.value, 10);
                          setLabelOptions((prev) => ({
                            ...prev,
                            startPosition: Number.isFinite(next) ? Math.max(0, next) : 0,
                          }));
                        }}
                        bg="gray.700"
                        color="white"
                        data-testid="delivery-label-start-input"
                      />
                    </FormControl>
                  </HStack>

                  <HStack align="flex-end" spacing={3} flexWrap="wrap">
                    <FormControl maxW="xs">
                      <FormLabel htmlFor="delivery-label-align" color="gray.300" fontSize="sm" mb={1}>
                        {t('analytics.labels.alignment')}
                      </FormLabel>
                      <Select
                        id="delivery-label-align"
                        value={labelOptions.alignment}
                        onChange={(e) =>
                          setLabelOptions((prev) => ({
                            ...prev,
                            alignment: e.target.value as LabelAlignment,
                          }))
                        }
                        bg="gray.700"
                        color="white"
                        data-testid="delivery-label-align-select"
                      >
                        {ALIGNMENTS.map((a) => (
                          <option key={a} value={a}>
                            {t(`analytics.labels.align.${a}`)}
                          </option>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl maxW="36">
                      <FormLabel htmlFor="delivery-label-font" color="gray.300" fontSize="sm" mb={1}>
                        {t('analytics.labels.fontSize')}
                      </FormLabel>
                      <Input
                        id="delivery-label-font"
                        type="number"
                        min={MIN_FONT_SIZE}
                        max={MAX_FONT_SIZE}
                        value={labelOptions.fontSize}
                        onChange={(e) => {
                          const next = Number.parseInt(e.target.value, 10);
                          setLabelOptions((prev) => ({
                            ...prev,
                            fontSize: Number.isFinite(next) ? next : prev.fontSize,
                          }));
                        }}
                        bg="gray.700"
                        color="white"
                        data-testid="delivery-label-font-input"
                      />
                    </FormControl>

                    <Checkbox
                      isChecked={labelOptions.showBorder}
                      onChange={(e) =>
                        setLabelOptions((prev) => ({ ...prev, showBorder: e.target.checked }))
                      }
                      color="gray.300"
                      data-testid="delivery-label-border-checkbox"
                    >
                      {t('analytics.labels.showBorder')}
                    </Checkbox>

                    <Checkbox
                      isChecked={labelOptions.showCountry}
                      onChange={(e) =>
                        setLabelOptions((prev) => ({ ...prev, showCountry: e.target.checked }))
                      }
                      color="gray.300"
                      data-testid="delivery-label-country-checkbox"
                    >
                      {t('analytics.labels.showCountry')}
                    </Checkbox>
                  </HStack>
                </VStack>
              </Box>
            )}

            {saveError && (
              <Text color="red.300" fontSize="sm" data-testid="member-delivery-error">
                {saveError}
              </Text>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          {/* Clear removes the stored delivery (DELETE); only offered when the set
              already has one (nothing to clear otherwise). */}
          {initialDelivery && (
            <Button
              variant="ghost"
              colorScheme="red"
              mr="auto"
              onClick={handleClear}
              isLoading={isClearing}
              data-testid="member-delivery-clear"
            >
              {t(`${T}.clear`)}
            </Button>
          )}
          <Button
            variant="ghost"
            mr={3}
            onClick={onClose}
            data-testid="member-delivery-cancel"
          >
            {t(`${T}.cancel`)}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isDisabled={!canSave}
            isLoading={isSaving}
            data-testid="member-delivery-save"
          >
            {t(`${T}.save`)}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MemberDeliveryEditor;
