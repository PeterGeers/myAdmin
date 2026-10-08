/**
 * MemberTemplateManager — the stored mail-template management surface (R2, pivot-output-actions).
 *
 * A keyboard-accessible Chakra modal (opened from the "Manage templates" button in
 * {@link MemberMailCompose}) that lets a user manage the tenant's stored, bilingual (NL/EN)
 * mail templates on the Members plane:
 *
 *   - **List** the tenant's templates (`GET /members/templates`), with select / edit / delete.
 *   - **Create / edit** a template: a name + per-language (NL/EN) subject + body. Editing
 *     fetches the full template (`GET /members/templates/{id}`) so the body HTML is loaded.
 *   - **Upload** a body: read a local `.html` / `.txt` file into the active language's body
 *     textarea (no server round-trip — the file content just fills the field).
 *   - **Improve with AI** (`POST /members/templates/{id}/ai-improve`): send ONLY the template
 *     content + a free-text instruction (never member data, R2) to the backend's fail-closed
 *     free-model adapter; the improved subject/body replaces the editor's fields on success,
 *     and on any failure the user keeps the un-improved text (design §9) with a toast. The
 *     action is only available for a SAVED template (it operates on a stored id); for an unsaved
 *     draft it is disabled with a hint to save first. When the backend AI seam is not present
 *     the route answers a clear code and the user simply keeps the template — the UI degrades,
 *     never crashes.
 *
 * All labels resolve from the `members` namespace (`analytics.mail.templates.*`), bilingual via
 * the active language — no hardcoded English (steering 32). The service functions are injectable
 * so the component is testable without network (steering 33).
 *
 * @module components/members/analytics/MemberTemplateManager
 * @see .kiro/specs/Members/pivot-output-actions (design §3, §5, §7; requirements R2)
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
  Box,
  Button,
  Divider,
  FormControl,
  FormLabel,
  HStack,
  Input,
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
} from '../../../services/memberTemplateService';

/** `members`-namespace i18n key prefix for every label this surface renders. */
const T = 'analytics.mail.templates';

/** The two languages a template carries (NL/EN, R2). */
const LANGS = ['nl', 'en'] as const;
type Lang = (typeof LANGS)[number];

/** The in-progress editor state: a name + per-language subject + body. */
interface DraftState {
  /** The id of the template being edited, or `null` for a new (unsaved) draft. */
  templateId: string | null;
  name: string;
  languages: Record<Lang, { subject: string; body_html: string }>;
}

/** A blank draft (new template). */
function emptyDraft(): DraftState {
  return {
    templateId: null,
    name: '',
    languages: {
      nl: { subject: '', body_html: '' },
      en: { subject: '', body_html: '' },
    },
  };
}

/** Build a draft from a fetched template DTO (editing an existing one). */
function draftFromTemplate(tpl: MemberTemplateDto): DraftState {
  const languages = { ...emptyDraft().languages };
  for (const lang of LANGS) {
    const variant = tpl.languages?.[lang];
    if (variant) {
      languages[lang] = {
        subject: variant.subject ?? '',
        body_html: variant.body_html ?? '',
      };
    }
  }
  return { templateId: tpl.template_id, name: tpl.name, languages };
}

/**
 * Turn a draft into the create/update request body: only languages that carry a non-blank
 * subject or body are sent (an all-blank variant is dropped so the backend's "at least one
 * usable language" rule is satisfied by the user filling at least one).
 */
function draftToInput(draft: DraftState): MemberTemplateInput {
  const languages: MemberTemplateInput['languages'] = {};
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
  /** Active language — the editor focuses this language's tab first + AI improves it. */
  language: string;
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
  const [draft, setDraft] = useState<DraftState>(emptyDraft);
  // The language tab the editor currently shows (defaults to the active language if NL/EN).
  const [activeLang, setActiveLang] = useState<Lang>('nl');
  const [saving, setSaving] = useState(false);
  const [improving, setImproving] = useState(false);
  const [instruction, setInstruction] = useState('');

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
    setInstruction('');
    setActiveLang(language === 'en' ? 'en' : 'nl');
    void refreshList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const startNew = () => {
    setDraft(emptyDraft());
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

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="2xl" isCentered scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" data-testid="member-template-manager">
        <ModalHeader>{t(`${T}.title`)}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack align="stretch" spacing={4}>
            {/* The stored-template list. */}
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
                  {templates.map((tpl) => (
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
                  ))}
                </VStack>
              )}
            </Box>

            <Divider borderColor="gray.600" />

            {/* The create / edit editor. */}
            <Box data-testid="member-template-editor">
              <Text fontWeight="semibold" mb={2}>
                {draft.templateId ? t(`${T}.editTitle`) : t(`${T}.newTitle`)}
              </Text>

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
                  <Text fontSize="xs" color="yellow.300" mt={1} data-testid="member-template-improve-hint">
                    {t(`${T}.improveSaveFirst`)}
                  </Text>
                )}
              </FormControl>
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
