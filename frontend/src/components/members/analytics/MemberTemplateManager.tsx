/**
 * MemberTemplateManager — the SINGLE stored-template management surface for BOTH kinds
 * (R2 + labels sub-spec R-L1, pivot-output-actions).
 *
 * "A template is a template": one keyboard-accessible Chakra modal manages the tenant's stored
 * templates — both the historical `kind:"mail"` (bilingual NL/EN subject + HTML body) templates
 * AND the `kind:"label"` (ordered `lines` of pivot-result field keys) templates. They live in
 * the ONE shared `template#` store discriminated by `kind` (absent ⇒ `"mail"`); this surface
 * renders the right content section by the draft's kind and filters OUT the HTML body / subject /
 * AI controls for a label template.
 *
 *   - **List** the tenant's templates (`GET /members/templates`) — ALL kinds, each row carrying a
 *     small KIND badge (mail / label) so they are distinguishable — with select / edit / delete.
 *   - **Create**: a kind selector (mail | label) chooses which content section shows. The label
 *     option is only offered when the parent supplied `resultFields` (the current pivot RESULT's
 *     columns) — a label line can only ever reference a field in the result (R6: never reads
 *     `analytics.*`). Opened from mail compose (no result context) the selector is mail-only.
 *   - **Edit**: the kind is INFERRED from the fetched DTO (absent ⇒ mail) and LOCKED — this pass
 *     does not support changing an existing template's kind.
 *   - **Mail content** (`kind:"mail"`): per-language (NL/EN) subject + HTML body, with Upload-body,
 *     Improve-with-AI (`POST /members/templates/{id}/ai-improve`, only for a SAVED template; sends
 *     ONLY content + instruction, never member data, R2; fail-closed/degraded keeps the text), and
 *     NL/EN tabs. Save writes `{ name, languages }` (only usable languages).
 *   - **Label content** (`kind:"label"`): an ORDERED list of lines, each an ordered list of 1+
 *     field keys chosen from `resultFields`. Save writes `{ name, kind:"label", lines }` with NO
 *     languages.
 *
 * Save is gated per kind: mail = name + ≥1 usable language (subject + body); label = name + ≥1
 * line carrying ≥1 field key. All labels resolve from the `members` namespace (shared chrome +
 * mail section under `analytics.mail.templates.*`; the label line-builder reuses
 * `analytics.labelTemplates.*`), bilingual via the active language — no hardcoded English
 * (steering 32). The service functions are injectable so the component is testable without
 * network (steering 33).
 *
 * @module components/members/analytics/MemberTemplateManager
 * @see .kiro/specs/Members/pivot-output-actions (design §3, §5, §7; R2) + /labels (R-L1, R6)
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Badge,
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
  Textarea,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import {
  listMemberTemplates,
  getMemberTemplate,
  createMemberTemplate,
  updateMemberTemplate,
  deleteMemberTemplate,
  aiImproveMemberTemplate,
  type MemberTemplateDto,
  type MemberTemplateInput,
  type TemplateKind,
} from '../../../services/memberTemplateService';

/** `members`-namespace i18n key prefix for the shared chrome + the MAIL content section. */
const T = 'analytics.mail.templates';
/** `members`-namespace i18n key prefix for the LABEL line-builder section (reused verbatim). */
const TL = 'analytics.labelTemplates';

/** The two languages a mail template carries (NL/EN, R2). */
const LANGS = ['nl', 'en'] as const;
type Lang = (typeof LANGS)[number];

/** A result field the label-lines builder picks keys from (the current result's columns). */
export interface ResultField {
  /** The result row data key (the stored value on a label line). */
  key: string;
  /** The localized header shown in the pickers (presentation only). */
  label: string;
}

/**
 * The in-progress editor state. It carries BOTH content shapes so the one editor can switch by
 * `kind`: `languages` for a mail template, `lines` for a label template.
 */
interface DraftState {
  /** The id of the template being edited, or `null` for a new (unsaved) draft. */
  templateId: string | null;
  /** The draft's kind — chosen on create, inferred + locked on edit. */
  kind: TemplateKind;
  name: string;
  /** MAIL content: per-language subject + body. */
  languages: Record<Lang, { subject: string; body_html: string }>;
  /** LABEL content: ordered lines, each an ordered list of 1+ field keys. */
  lines: string[][];
}

/** A blank draft of the given kind (a label draft seeds one empty starter line). */
function emptyDraft(kind: TemplateKind = 'mail'): DraftState {
  return {
    templateId: null,
    kind,
    name: '',
    languages: {
      nl: { subject: '', body_html: '' },
      en: { subject: '', body_html: '' },
    },
    lines: [[]],
  };
}

/** The resolved kind of a DTO: an absent/undefined `kind` means a mail template. */
function templateKind(tpl: MemberTemplateDto): TemplateKind {
  return tpl.kind === 'label' ? 'label' : 'mail';
}

/** Build a draft from a fetched template DTO (editing an existing one). Kind is inferred. */
function draftFromTemplate(tpl: MemberTemplateDto): DraftState {
  const kind = templateKind(tpl);
  const base = emptyDraft(kind);
  const languages = { ...base.languages };
  for (const lang of LANGS) {
    const variant = tpl.languages?.[lang];
    if (variant) {
      languages[lang] = {
        subject: variant.subject ?? '',
        body_html: variant.body_html ?? '',
      };
    }
  }
  // Clone the lines so editing the draft never mutates the DTO; seed one empty line if absent.
  const lines =
    tpl.lines && tpl.lines.length > 0 ? tpl.lines.map((line) => [...line]) : [[]];
  return { templateId: tpl.template_id, kind, name: tpl.name, languages, lines };
}

/**
 * Turn a draft into the create/update request body. For a MAIL draft only languages that carry a
 * non-blank subject or body are sent (so the backend's "at least one usable language" rule is
 * satisfied). For a LABEL draft a `kind:"label"` write carries the non-empty lines + NO languages.
 */
function draftToInput(draft: DraftState): MemberTemplateInput {
  if (draft.kind === 'label') {
    const lines = draft.lines.filter((line) => line.length > 0);
    return { name: draft.name.trim(), kind: 'label', lines };
  }
  const languages: NonNullable<MemberTemplateInput['languages']> = {};
  for (const lang of LANGS) {
    const variant = draft.languages[lang];
    if (variant.subject.trim() || variant.body_html.trim()) {
      languages[lang] = { subject: variant.subject, body_html: variant.body_html };
    }
  }
  return { name: draft.name.trim(), languages };
}

export interface MemberTemplateManagerProps {
  /** Whether the manager modal is open. */
  isOpen: boolean;
  /** Close handler (overlay / Escape / Close). */
  onClose: () => void;
  /** Active language — the mail editor focuses this language's tab first + AI improves it. */
  language: string;
  /**
   * The CURRENT pivot RESULT's columns the LABEL line-builder picks keys from (R6: supplied by
   * the parent, NOT read from `analytics.*`). `key` is the result row data key (the stored line
   * value); `label` is the localized header shown for readability. When absent/empty (e.g. opened
   * from mail compose where there is no result context) the label-create path is hidden — mail
   * compose only ever manages mail templates.
   */
  resultFields?: ResultField[];
  /** Called after any create / update / delete so the caller can refresh its picker. */
  onTemplatesChanged?: () => void;
  // --- injectable services (default to the authenticated client; overridden in tests) ------
  listTemplates?: typeof listMemberTemplates;
  getTemplate?: typeof getMemberTemplate;
  createTemplate?: typeof createMemberTemplate;
  updateTemplate?: typeof updateMemberTemplate;
  deleteTemplate?: typeof deleteMemberTemplate;
  aiImprove?: typeof aiImproveMemberTemplate;
}

export const MemberTemplateManager: React.FC<MemberTemplateManagerProps> = ({
  isOpen,
  onClose,
  language,
  resultFields,
  onTemplatesChanged,
  listTemplates = listMemberTemplates,
  getTemplate = getMemberTemplate,
  createTemplate = createMemberTemplate,
  updateTemplate = updateMemberTemplate,
  deleteTemplate = deleteMemberTemplate,
  aiImprove = aiImproveMemberTemplate,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [templates, setTemplates] = useState<MemberTemplateDto[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [draft, setDraft] = useState<DraftState>(() => emptyDraft('mail'));
  // The language tab the mail editor currently shows (defaults to the active language if NL/EN).
  const [activeLang, setActiveLang] = useState<Lang>('nl');
  const [saving, setSaving] = useState(false);
  const [improving, setImproving] = useState(false);
  const [instruction, setInstruction] = useState('');

  // The label line-builder may only offer the current result's columns (R6). When the parent
  // supplies none, label creation is not possible from this surface.
  const fields = useMemo<ResultField[]>(() => resultFields ?? [], [resultFields]);
  const canCreateLabel = fields.length > 0;

  // A readable label for a result field key, falling back to the raw key.
  const fieldLabel = useCallback(
    (key: string): string => fields.find((f) => f.key === key)?.label ?? key,
    [fields],
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
    setDraft(emptyDraft('mail'));
    setInstruction('');
    setActiveLang(language === 'en' ? 'en' : 'nl');
    void refreshList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const startNew = () => {
    setDraft(emptyDraft('mail'));
    setInstruction('');
  };

  // Switch the (new, unsaved) draft's kind, keeping the name already typed.
  const setDraftKind = (kind: TemplateKind) => {
    setDraft((prev) => ({ ...emptyDraft(kind), name: prev.name }));
    setInstruction('');
  };

  const startEdit = async (templateId: string) => {
    try {
      const result = await getTemplate(templateId);
      if (!result.ok) {
        toast({ title: t(`${T}.loadError`), status: 'error' });
        return;
      }
      setDraft(draftFromTemplate(result.data));
      setInstruction('');
    } catch {
      toast({ title: t(`${T}.loadError`), status: 'error' });
    }
  };

  const canSave = useMemo(() => {
    if (!draft.name.trim()) {
      return false;
    }
    if (draft.kind === 'label') {
      // ≥1 line carrying ≥1 field key (backend's label rule).
      return draft.lines.some((line) => line.length > 0);
    }
    // At least one language must carry a non-blank subject + body (backend's usable-language rule).
    return LANGS.some(
      (lang) =>
        draft.languages[lang].subject.trim() && draft.languages[lang].body_html.trim(),
    );
  }, [draft]);

  const setLangField = (lang: Lang, field: 'subject' | 'body_html', value: string) => {
    setDraft((prev) => ({
      ...prev,
      languages: {
        ...prev.languages,
        [lang]: { ...prev.languages[lang], [field]: value },
      },
    }));
  };

  // ---- label line / field mutators -------------------------------------------------------
  const addLine = () => setDraft((prev) => ({ ...prev, lines: [...prev.lines, []] }));

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
      // Keep editing the saved template (so a follow-up AI-improve has an id to act on).
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

  // Upload a local body file into the active language's body textarea (no server round-trip).
  const handleUploadClick = () => fileInputRef.current?.click();
  const handleFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset the input so re-choosing the same file fires change again.
    e.target.value = '';
    if (!file) {
      return;
    }
    try {
      const text = await file.text();
      setLangField(activeLang, 'body_html', text);
      toast({ title: t(`${T}.uploaded`), status: 'success' });
    } catch {
      toast({ title: t(`${T}.uploadError`), status: 'error' });
    }
  };

  // Improve the active language with AI. Only for a SAVED template (operates on a stored id).
  const canImprove = Boolean(draft.templateId) && instruction.trim().length > 0 && !improving;
  const handleImprove = async () => {
    if (!draft.templateId || !canImprove) {
      return;
    }
    setImproving(true);
    try {
      const result = await aiImprove(draft.templateId, {
        lang: activeLang,
        instruction: instruction.trim(),
      });
      if (!result.ok) {
        // Fail-closed / degraded: the user keeps the un-improved template (design §9).
        toast({ title: t(`${T}.improveError`), status: 'warning' });
        return;
      }
      setLangField(activeLang, 'subject', result.data.subject);
      setLangField(activeLang, 'body_html', result.data.body_html);
      toast({ title: t(`${T}.improved`), status: 'success' });
    } catch {
      toast({ title: t(`${T}.improveError`), status: 'warning' });
    } finally {
      setImproving(false);
    }
  };

  const isLabelDraft = draft.kind === 'label';
  // The kind selector only makes sense for a NEW draft (edit locks the kind) AND when label
  // creation is possible (the parent supplied result columns).
  const showKindSelector = !draft.templateId && canCreateLabel;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="2xl" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="member-template-manager">
        <ModalHeader>{t(`${T}.title`)}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack align="stretch" spacing={4}>
            {/* The stored-template list — ALL kinds, each row carrying a kind badge. */}
            <Box>
              <HStack justify="space-between" mb={2}>
                <Text fontWeight="semibold">{t(`${T}.listTitle`)}</Text>
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="orange"
                  onClick={startNew}
                  data-testid="member-template-new"
                >
                  {t(`${T}.new`)}
                </Button>
              </HStack>
              {loadingList ? (
                <HStack color="gray.300" fontSize="sm">
                  <Spinner size="sm" />
                  <Text>{t(`${T}.loading`)}</Text>
                </HStack>
              ) : templates.length === 0 ? (
                <Text fontSize="sm" color="gray.400" data-testid="member-template-empty">
                  {t(`${T}.empty`)}
                </Text>
              ) : (
                <VStack align="stretch" spacing={1} data-testid="member-template-list">
                  {templates.map((tpl) => {
                    const kind = templateKind(tpl);
                    return (
                      <HStack
                        key={tpl.template_id}
                        justify="space-between"
                        bg="gray.900"
                        px={3}
                        py={2}
                        borderRadius="md"
                      >
                        <HStack spacing={2} minW={0}>
                          <Badge
                            colorScheme={kind === 'label' ? 'purple' : 'blue'}
                            data-testid={`member-template-kind-${tpl.template_id}`}
                          >
                            {t(`${T}.kind.${kind}`)}
                          </Badge>
                          <Text fontSize="sm" noOfLines={1}>
                            {tpl.name}
                          </Text>
                        </HStack>
                        <HStack spacing={1}>
                          <Button
                            size="xs"
                            variant="ghost"
                            colorScheme="orange"
                            onClick={() => startEdit(tpl.template_id)}
                            data-testid={`member-template-edit-${tpl.template_id}`}
                          >
                            {t(`${T}.edit`)}
                          </Button>
                          <Button
                            size="xs"
                            variant="ghost"
                            colorScheme="red"
                            onClick={() => handleDelete(tpl.template_id)}
                            data-testid={`member-template-delete-${tpl.template_id}`}
                          >
                            {t(`${T}.delete`)}
                          </Button>
                        </HStack>
                      </HStack>
                    );
                  })}
                </VStack>
              )}
            </Box>

            <Divider borderColor="gray.600" />

            {/* The create / edit editor. */}
            <Box data-testid="member-template-editor">
              <Text fontWeight="semibold" mb={2}>
                {draft.templateId ? t(`${T}.editTitle`) : t(`${T}.newTitle`)}
              </Text>

              {/* Kind selector — only for a NEW draft, and only when label creation is possible
                  (the parent supplied result columns). Editing locks the kind. */}
              {showKindSelector && (
                <FormControl mb={3}>
                  <FormLabel htmlFor="member-template-kind">{t(`${T}.kindLabel`)}</FormLabel>
                  <Select
                    id="member-template-kind"
                    data-testid="member-template-kind-select"
                    value={draft.kind}
                    onChange={(e) => setDraftKind(e.target.value as TemplateKind)}
                    bg="gray.900"
                  >
                    <option value="mail">{t(`${T}.kind.mail`)}</option>
                    <option value="label">{t(`${T}.kind.label`)}</option>
                  </Select>
                </FormControl>
              )}

              <FormControl isRequired mb={3}>
                <FormLabel htmlFor="member-template-name">{t(`${T}.name`)}</FormLabel>
                <Input
                  id="member-template-name"
                  data-testid="member-template-name"
                  value={draft.name}
                  onChange={(e) => setDraft((p) => ({ ...p, name: e.target.value }))}
                  bg="gray.900"
                />
              </FormControl>

              {/* MAIL content section — subject + HTML body + upload + AI-improve + NL/EN tabs.
                  Rendered ONLY for a mail template (filtered OUT for a label template, R-L1). */}
              {!isLabelDraft && (
                <Box data-testid="member-template-mail-section">
                  {/* Language tabs (NL/EN). */}
                  <HStack spacing={2} mb={2}>
                    {LANGS.map((lang) => (
                      <Button
                        key={lang}
                        size="sm"
                        variant={activeLang === lang ? 'solid' : 'outline'}
                        colorScheme="orange"
                        onClick={() => setActiveLang(lang)}
                        data-testid={`member-template-lang-${lang}`}
                      >
                        {t(`${T}.lang.${lang}`)}
                      </Button>
                    ))}
                  </HStack>

                  <FormControl mb={3}>
                    <FormLabel htmlFor="member-template-subject">{t(`${T}.subject`)}</FormLabel>
                    <Input
                      id="member-template-subject"
                      data-testid="member-template-subject"
                      value={draft.languages[activeLang].subject}
                      onChange={(e) => setLangField(activeLang, 'subject', e.target.value)}
                      bg="gray.900"
                    />
                  </FormControl>

                  <FormControl mb={3}>
                    <HStack justify="space-between" align="center">
                      <FormLabel htmlFor="member-template-body" mb={0}>
                        {t(`${T}.body`)}
                      </FormLabel>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={handleUploadClick}
                        data-testid="member-template-upload"
                      >
                        {t(`${T}.upload`)}
                      </Button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".html,.htm,.txt,text/html,text/plain"
                        style={{ display: 'none' }}
                        onChange={handleFileChosen}
                        data-testid="member-template-file-input"
                      />
                    </HStack>
                    <Textarea
                      id="member-template-body"
                      data-testid="member-template-body"
                      value={draft.languages[activeLang].body_html}
                      onChange={(e) => setLangField(activeLang, 'body_html', e.target.value)}
                      rows={8}
                      bg="gray.900"
                      mt={1}
                    />
                    <Text fontSize="xs" color="gray.400" mt={1}>
                      {t(`${T}.mergeHint`)}
                    </Text>
                  </FormControl>

                  {/* Improve-with-AI (R2): only for a saved template; never carries member data. */}
                  <FormControl mb={1}>
                    <FormLabel htmlFor="member-template-instruction">
                      {t(`${T}.improveLabel`)}
                    </FormLabel>
                    <HStack align="start" spacing={2}>
                      <Input
                        id="member-template-instruction"
                        data-testid="member-template-instruction"
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder={t(`${T}.improvePlaceholder`)}
                        bg="gray.900"
                      />
                      <Button
                        flexShrink={0}
                        variant="outline"
                        colorScheme="purple"
                        onClick={handleImprove}
                        isDisabled={!canImprove}
                        isLoading={improving}
                        data-testid="member-template-improve"
                      >
                        {t(`${T}.improve`)}
                      </Button>
                    </HStack>
                    {!draft.templateId && (
                      <Text
                        fontSize="xs"
                        color="yellow.300"
                        mt={1}
                        data-testid="member-template-improve-hint"
                      >
                        {t(`${T}.improveSaveFirst`)}
                      </Text>
                    )}
                  </FormControl>
                </Box>
              )}

              {/* LABEL content section — the ordered lines-of-fields builder. Rendered ONLY for a
                  label template; it offers ONLY the current result's columns (R6). */}
              {isLabelDraft && (
                <Box data-testid="member-template-label-section">
                  <HStack justify="space-between" mb={2}>
                    <Text fontWeight="semibold">{t(`${TL}.linesTitle`)}</Text>
                    <Button
                      size="sm"
                      variant="outline"
                      colorScheme="orange"
                      onClick={addLine}
                      data-testid="member-template-add-line"
                    >
                      {t(`${TL}.addLine`)}
                    </Button>
                  </HStack>

                  <VStack align="stretch" spacing={3} data-testid="member-template-lines">
                    {draft.lines.map((line, lineIndex) => (
                      <Box
                        key={lineIndex}
                        bg="gray.900"
                        px={3}
                        py={2}
                        borderRadius="md"
                        data-testid={`member-template-line-${lineIndex}`}
                      >
                        <HStack justify="space-between" mb={2}>
                          <Text fontSize="sm" color="gray.300">
                            {t(`${TL}.line`, { index: lineIndex + 1 })}
                          </Text>
                          <Button
                            size="xs"
                            variant="ghost"
                            colorScheme="red"
                            onClick={() => removeLine(lineIndex)}
                            data-testid={`member-template-remove-line-${lineIndex}`}
                          >
                            {t(`${TL}.removeLine`)}
                          </Button>
                        </HStack>

                        {line.length > 0 && (
                          <HStack
                            spacing={2}
                            mb={2}
                            flexWrap="wrap"
                            data-testid={`member-template-line-fields-${lineIndex}`}
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
                                data-testid={`member-template-field-${lineIndex}-${fieldIndex}`}
                              >
                                <Text fontSize="sm">{fieldLabel(key)}</Text>
                                <Button
                                  aria-label={t(`${TL}.removeField`)}
                                  title={t(`${TL}.removeField`)}
                                  size="xs"
                                  variant="ghost"
                                  colorScheme="whiteAlpha"
                                  minW="auto"
                                  h="auto"
                                  px={1}
                                  onClick={() => removeFieldFromLine(lineIndex, fieldIndex)}
                                  data-testid={`member-template-remove-field-${lineIndex}-${fieldIndex}`}
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
                          placeholder={t(`${TL}.fieldPlaceholder`)}
                          value=""
                          onChange={(e) => addFieldToLine(lineIndex, e.target.value)}
                          data-testid={`member-template-add-field-${lineIndex}`}
                        >
                          {fields.map((field) => (
                            <option key={field.key} value={field.key}>
                              {fieldLabel(field.key)}
                            </option>
                          ))}
                        </Select>
                      </Box>
                    ))}
                  </VStack>

                  {!canSave && (
                    <Text
                      fontSize="xs"
                      color="yellow.300"
                      mt={2}
                      data-testid="member-template-lines-hint"
                    >
                      {t(`${TL}.emptyLinesHint`)}
                    </Text>
                  )}
                </Box>
              )}
            </Box>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose} data-testid="member-template-close">
            {t(`${T}.close`)}
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isDisabled={!canSave}
            isLoading={saving}
            data-testid="member-template-save"
          >
            {t(`${T}.save`)}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MemberTemplateManager;
