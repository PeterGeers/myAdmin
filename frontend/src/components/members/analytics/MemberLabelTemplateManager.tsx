/**
 * MemberLabelTemplateManager — the stored LABEL-template management surface
 * (labels sub-spec R-L1, `.kiro/specs/Members/pivot-output-actions/labels`).
 *
 * A sibling to {@link MemberTemplateManager} (the mail-template editor) — kept SEPARATE on
 * purpose so the label `lines` model does not entangle the mail body / AI-improve editor. It is
 * a keyboard-accessible Chakra modal that manages the tenant's stored label templates (the
 * `kind: "label"` records in the shared `template#` store):
 *
 *   - **List** only `kind === "label"` templates (a mail template — absent/`"mail"` kind — is
 *     excluded), with select / edit / delete.
 *   - **Create / edit** a label template: a required `name` + an ORDERED list of lines. Each
 *     line is an ordered list of 1+ field keys chosen from the result's available fields
 *     (`availableFields`, supplied by the parent — the editor never reads `analytics.*`, R6).
 *     Editing fetches the full template by id (so its lines seed the editor).
 *   - **Save** via the SAME injectable template CRUD the mail manager uses:
 *     `createMemberTemplate({ name, kind: "label", lines })` for a new draft or
 *     `updateMemberTemplate(id, { name, kind: "label", lines })` for an existing one. No
 *     `languages` is sent for a label template.
 *
 * Save is gated — disabled unless `name` is non-blank AND there is ≥1 line carrying ≥1 field
 * key (mirrors the backend validation so the user gets a disabled button, not a server error).
 * Create/update/delete/load failures surface a bilingual toast.
 *
 * All labels resolve from the `members` namespace under `analytics.labelTemplates.*`, bilingual
 * via the active language — no hardcoded English (steering 32). The service functions are
 * injectable so the component is testable without network (steering 33).
 *
 * @module components/members/analytics/MemberLabelTemplateManager
 * @see .kiro/specs/Members/pivot-output-actions/labels (design "ADD: Label-template editor"; R1, R6)
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Box,
  Button,
  Divider,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Select,
  Spinner,
  Text,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { resolveLabel } from '../fieldForm';
import type { FieldConfigField } from '../../../types/members';
import {
  listMemberTemplates,
  getMemberTemplate,
  createMemberTemplate,
  updateMemberTemplate,
  deleteMemberTemplate,
  type MemberTemplateDto,
  type MemberTemplateInput,
} from '../../../services/memberTemplateService';

/** `members`-namespace i18n key prefix for every label this surface renders. */
const T = 'analytics.labelTemplates';

/** The in-progress editor state: a name + an ordered list of lines (each a list of field keys). */
interface DraftState {
  /** The id of the label template being edited, or `null` for a new (unsaved) draft. */
  templateId: string | null;
  name: string;
  /** Ordered lines; each line is an ordered list of 1+ field keys. */
  lines: string[][];
}

/** A blank draft (one empty starter line, so the user has somewhere to add a field). */
function emptyDraft(): DraftState {
  return { templateId: null, name: '', lines: [[]] };
}

/** Build a draft from a fetched label-template DTO (editing an existing one). */
function draftFromTemplate(tpl: MemberTemplateDto): DraftState {
  // Clone the lines so editing the draft never mutates the DTO; seed one empty line if absent.
  const lines =
    tpl.lines && tpl.lines.length > 0 ? tpl.lines.map((line) => [...line]) : [[]];
  return { templateId: tpl.template_id, name: tpl.name, lines };
}

/**
 * Turn a draft into the create/update request body: a `kind: "label"` write carrying the
 * trimmed name + the non-empty lines (a line with no field keys is dropped). NO `languages`.
 */
function draftToInput(draft: DraftState): MemberTemplateInput {
  const lines = draft.lines.filter((line) => line.length > 0);
  return { name: draft.name.trim(), kind: 'label', lines };
}

/** A label template is distinguished by `kind === "label"`; absent kind means a mail template. */
function isLabelTemplate(tpl: MemberTemplateDto): boolean {
  return tpl.kind === 'label';
}

export interface MemberLabelTemplateManagerProps {
  /** Whether the manager modal is open. */
  isOpen: boolean;
  /** Close handler (overlay / Escape / Close). */
  onClose: () => void;
  /** Active language — resolves the available-field labels for the pickers. */
  language: string;
  /**
   * The result's available fields the lines pick keys from (R6: supplied by the parent, NOT
   * read from `analytics.*`). The editor offers each field's key; a localized label (if any)
   * is shown for readability but the stored value is always the key.
   */
  availableFields: FieldConfigField[];
  /** Called after any create / update / delete so a parent picker can refresh. */
  onTemplatesChanged?: () => void;
  // --- injectable services (default to the authenticated client; overridden in tests) ------
  listTemplates?: typeof listMemberTemplates;
  getTemplate?: typeof getMemberTemplate;
  createTemplate?: typeof createMemberTemplate;
  updateTemplate?: typeof updateMemberTemplate;
  deleteTemplate?: typeof deleteMemberTemplate;
}

export const MemberLabelTemplateManager: React.FC<MemberLabelTemplateManagerProps> = ({
  isOpen,
  onClose,
  language,
  availableFields,
  onTemplatesChanged,
  listTemplates = listMemberTemplates,
  getTemplate = getMemberTemplate,
  createTemplate = createMemberTemplate,
  updateTemplate = updateMemberTemplate,
  deleteTemplate = deleteMemberTemplate,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();

  const [templates, setTemplates] = useState<MemberTemplateDto[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [draft, setDraft] = useState<DraftState>(emptyDraft);
  const [saving, setSaving] = useState(false);

  // Only `kind === "label"` templates belong in this surface.
  const labelTemplates = useMemo(() => templates.filter(isLabelTemplate), [templates]);

  // A readable label for each available field (localized), falling back to the raw key.
  const fieldLabel = useCallback(
    (key: string): string => {
      const field = availableFields.find((f) => f.key === key);
      return field ? resolveLabel(field.label, language, field.key) : key;
    },
    [availableFields, language],
  );

  const refreshList = useCallback(async () => {
    setLoadingList(true);
    try {
      const result = await listTemplates();
      setTemplates(result.ok ? result.data : []);
      if (!result.ok) {
        toast({ title: t(`${T}.loadError`), status: 'error' });
      }
    } catch {
      setTemplates([]);
      toast({ title: t(`${T}.loadError`), status: 'error' });
    } finally {
      setLoadingList(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listTemplates]);

  // Load the list + reset the editor each time the manager opens.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setDraft(emptyDraft());
    void refreshList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const startNew = () => setDraft(emptyDraft());

  const startEdit = async (templateId: string) => {
    try {
      const result = await getTemplate(templateId);
      if (!result.ok) {
        toast({ title: t(`${T}.loadError`), status: 'error' });
        return;
      }
      setDraft(draftFromTemplate(result.data));
    } catch {
      toast({ title: t(`${T}.loadError`), status: 'error' });
    }
  };

  // Save is gated: a non-blank name AND ≥1 line that carries ≥1 field key (backend's rule).
  const canSave = useMemo(() => {
    if (!draft.name.trim()) {
      return false;
    }
    return draft.lines.some((line) => line.length > 0);
  }, [draft]);

  // ---- line / field mutators -------------------------------------------------------------
  const addLine = () =>
    setDraft((prev) => ({ ...prev, lines: [...prev.lines, []] }));

  const removeLine = (lineIndex: number) =>
    setDraft((prev) => {
      const lines = prev.lines.filter((_, i) => i !== lineIndex);
      // Keep at least one (empty) line so the editor always has an add-field target.
      return { ...prev, lines: lines.length > 0 ? lines : [[]] };
    });

  const addFieldToLine = (lineIndex: number, key: string) => {
    if (!key) {
      return;
    }
    setDraft((prev) => {
      const lines = prev.lines.map((line, i) =>
        // Append the key in order; skip a duplicate within the same line.
        i === lineIndex && !line.includes(key) ? [...line, key] : line,
      );
      return { ...prev, lines };
    });
  };

  const removeFieldFromLine = (lineIndex: number, fieldIndex: number) =>
    setDraft((prev) => {
      const lines = prev.lines.map((line, i) =>
        i === lineIndex ? line.filter((_, j) => j !== fieldIndex) : line,
      );
      return { ...prev, lines };
    });

  const handleSave = async () => {
    if (!canSave || saving) {
      return;
    }
    setSaving(true);
    try {
      const input = draftToInput(draft);
      const result = draft.templateId
        ? await updateTemplate(draft.templateId, input)
        : await createTemplate(input);
      if (!result.ok) {
        toast({ title: t(`${T}.saveError`), status: 'error' });
        return;
      }
      toast({ title: t(`${T}.saved`), status: 'success' });
      // Keep editing the saved template (seed from the returned DTO).
      setDraft(draftFromTemplate(result.data));
      await refreshList();
      onTemplatesChanged?.();
    } catch {
      toast({ title: t(`${T}.saveError`), status: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (templateId: string) => {
    try {
      const result = await deleteTemplate(templateId);
      if (!result.ok) {
        toast({ title: t(`${T}.deleteError`), status: 'error' });
        return;
      }
      toast({ title: t(`${T}.deleted`), status: 'success' });
      if (draft.templateId === templateId) {
        startNew();
      }
      await refreshList();
      onTemplatesChanged?.();
    } catch {
      toast({ title: t(`${T}.deleteError`), status: 'error' });
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="2xl" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="member-label-template-manager">
        <ModalHeader>{t(`${T}.title`)}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack align="stretch" spacing={4}>
            {/* The stored label-template list (kind === "label" only). */}
            <Box>
              <HStack justify="space-between" mb={2}>
                <Text fontWeight="semibold">{t(`${T}.listTitle`)}</Text>
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="orange"
                  onClick={startNew}
                  data-testid="member-label-template-new"
                >
                  {t(`${T}.new`)}
                </Button>
              </HStack>
              {loadingList ? (
                <HStack color="gray.300" fontSize="sm">
                  <Spinner size="sm" />
                  <Text>{t(`${T}.loading`)}</Text>
                </HStack>
              ) : labelTemplates.length === 0 ? (
                <Text fontSize="sm" color="gray.400" data-testid="member-label-template-empty">
                  {t(`${T}.empty`)}
                </Text>
              ) : (
                <VStack align="stretch" spacing={1} data-testid="member-label-template-list">
                  {labelTemplates.map((tpl) => (
                    <HStack
                      key={tpl.template_id}
                      justify="space-between"
                      bg="gray.900"
                      px={3}
                      py={2}
                      borderRadius="md"
                    >
                      <Text fontSize="sm" noOfLines={1}>
                        {tpl.name}
                      </Text>
                      <HStack spacing={1}>
                        <Button
                          size="xs"
                          variant="ghost"
                          colorScheme="orange"
                          onClick={() => startEdit(tpl.template_id)}
                          data-testid={`member-label-template-edit-${tpl.template_id}`}
                        >
                          {t(`${T}.edit`)}
                        </Button>
                        <Button
                          size="xs"
                          variant="ghost"
                          colorScheme="red"
                          onClick={() => handleDelete(tpl.template_id)}
                          data-testid={`member-label-template-delete-${tpl.template_id}`}
                        >
                          {t(`${T}.delete`)}
                        </Button>
                      </HStack>
                    </HStack>
                  ))}
                </VStack>
              )}
            </Box>

            <Divider borderColor="gray.600" />

            {/* The create / edit editor. */}
            <Box data-testid="member-label-template-editor">
              <Text fontWeight="semibold" mb={2}>
                {draft.templateId ? t(`${T}.editTitle`) : t(`${T}.newTitle`)}
              </Text>

              <FormControl isRequired mb={3}>
                <FormLabel htmlFor="member-label-template-name">{t(`${T}.name`)}</FormLabel>
                <Input
                  id="member-label-template-name"
                  data-testid="member-label-template-name"
                  value={draft.name}
                  onChange={(e) => setDraft((p) => ({ ...p, name: e.target.value }))}
                  bg="gray.900"
                />
              </FormControl>

              {/* The ordered lines. Each line: its field-key chips + an add-field select. */}
              <HStack justify="space-between" mb={2}>
                <Text fontWeight="semibold">{t(`${T}.linesTitle`)}</Text>
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="orange"
                  onClick={addLine}
                  data-testid="member-label-template-add-line"
                >
                  {t(`${T}.addLine`)}
                </Button>
              </HStack>

              <VStack align="stretch" spacing={3} data-testid="member-label-template-lines">
                {draft.lines.map((line, lineIndex) => (
                  <Box
                    key={lineIndex}
                    bg="gray.900"
                    px={3}
                    py={2}
                    borderRadius="md"
                    data-testid={`member-label-template-line-${lineIndex}`}
                  >
                    <HStack justify="space-between" mb={2}>
                      <Text fontSize="sm" color="gray.300">
                        {t(`${T}.line`, { index: lineIndex + 1 })}
                      </Text>
                      <Button
                        size="xs"
                        variant="ghost"
                        colorScheme="red"
                        onClick={() => removeLine(lineIndex)}
                        data-testid={`member-label-template-remove-line-${lineIndex}`}
                      >
                        {t(`${T}.removeLine`)}
                      </Button>
                    </HStack>

                    {line.length > 0 && (
                      <HStack
                        spacing={2}
                        mb={2}
                        flexWrap="wrap"
                        data-testid={`member-label-template-line-fields-${lineIndex}`}
                      >
                        {line.map((key, fieldIndex) => (
                          <HStack
                            key={`${key}-${fieldIndex}`}
                            spacing={1}
                            bg="orange.600"
                            color="white"
                            px={2}
                            py={1}
                            borderRadius="full"
                            data-testid={`member-label-template-field-${lineIndex}-${fieldIndex}`}
                          >
                            <Text fontSize="sm">{fieldLabel(key)}</Text>
                            <Button
                              aria-label={t(`${T}.removeField`)}
                              title={t(`${T}.removeField`)}
                              size="xs"
                              variant="ghost"
                              colorScheme="whiteAlpha"
                              minW="auto"
                              h="auto"
                              px={1}
                              onClick={() => removeFieldFromLine(lineIndex, fieldIndex)}
                              data-testid={`member-label-template-remove-field-${lineIndex}-${fieldIndex}`}
                            >
                              ×
                            </Button>
                          </HStack>
                        ))}
                      </HStack>
                    )}

                    <Select
                      size="sm"
                      bg="gray.800"
                      placeholder={t(`${T}.fieldPlaceholder`)}
                      value=""
                      onChange={(e) => addFieldToLine(lineIndex, e.target.value)}
                      data-testid={`member-label-template-add-field-${lineIndex}`}
                    >
                      {availableFields.map((field) => (
                        <option key={field.key} value={field.key}>
                          {fieldLabel(field.key)}
                        </option>
                      ))}
                    </Select>
                  </Box>
                ))}
              </VStack>

              {!canSave && (
                <Text fontSize="xs" color="yellow.300" mt={2} data-testid="member-label-template-hint">
                  {t(`${T}.emptyLinesHint`)}
                </Text>
              )}
            </Box>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="ghost"
            mr={3}
            onClick={onClose}
            data-testid="member-label-template-close"
          >
            {t(`${T}.close`)}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isDisabled={!canSave}
            isLoading={saving}
            data-testid="member-label-template-save"
          >
            {t(`${T}.save`)}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MemberLabelTemplateManager;
