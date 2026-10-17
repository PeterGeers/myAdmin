/**
 * Membership-type create / edit / retire modal (membership-type-catalog-admin-ui, task 2.2).
 *
 * The authoring leaf for the TenantAdmin "Lidmaatschapstypes" surface (`MembershipTypesManager`,
 * task 2.1). Opened from the manager's create button (CREATE mode) or a row-click (EDIT mode,
 * pre-filled with the selected entry). It owns the three catalog mutations, each wired to the
 * task-1 service wrapper, and on success it asks the manager to refresh its list (R2.6) and close.
 *
 *   - CREATE (R2.1): `type_code` (text) + bilingual `label` (nl + en) + `order` (number). `active`
 *     defaults true (shown read-only), and is NOT submitted — the server defaults it. On submit
 *     calls `createMembershipType({ type_code, label, order })`.
 *   - EDIT (R2.2): `type_code` is the stable id — shown but LOCKED (never editable in place). The
 *     admin edits `label` (nl/en), `order`, and `active` (a toggle). On submit calls
 *     `updateMembershipType(typeCode, { label, order, active })`.
 *   - RETIRE (R2.3): a soft-delete button (edit mode only) with a confirm step; calls
 *     `deactivateMembershipType(typeCode)` (sets `active=false`; NEVER a hard delete — existing
 *     members keep their reference, the type drops out of the active-only assignment dropdown).
 *
 * ## Scope of THIS task (2.2) — modal + mutations + refresh seam
 *
 * This component delivers the modal, the three mutation calls, and the success/refresh/close flow.
 * It leaves CLEAN SEAMS for the sibling tasks so they are not duplicated here:
 *
 *   - Pre-submit validation (TASK 2.3): client-side rules mirroring the SAM domain run BEFORE the
 *     service call for fast feedback — `type_code` (create only, locked on edit) non-blank and with
 *     NO `#` (the sort-key separator the domain rejects); a non-blank `nl` label; `order` (optional)
 *     must parse to an INTEGER when present (blank = omit → server defaults 0). A failing rule shows
 *     an inline `FormErrorMessage` on the offending input and blocks the submit (the SAM domain stays
 *     the authoritative validator). The Save-disabled gate remains a coarse guard on top.
 *   - Server-error surfacing (TASK 2.3): a thrown `ApiError` goes through the house `applyApiError`
 *     helper → localized inline field errors (e.g. a 409 duplicate `type_code` matched to the code
 *     input) + a localized summary toast; a 404 (absent) on edit/retire and any other 4xx surface
 *     readably; a non-`ApiError` degrades to the localized server-error toast.
 *   - Capability gating of the create/edit/retire actions is TASK 2.4 (SAM enforces authoritatively;
 *     the UI gate is a UX convenience layered on later).
 *   - Component tests are TASK 2.5 (this file ships testable `data-testid`s, no test here).
 *
 * House style mirrors `MembersFieldModal` / `MembersConfigEditor`: Chakra `Modal`, the `t(nl,en)`
 * bilingual helper driven by `useTranslation`, `useToast`, dark `gray.800` surface, orange accents.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Button,
  FormControl,
  FormErrorMessage,
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
  Switch,
  Text,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { applyApiError } from '../../../shared/api/applyApiError';
import {
  createMembershipType,
  updateMembershipType,
  deactivateMembershipType,
} from '../../../services/members/membersConfigApi';
import type {
  LocalizedLabel,
  MembershipType,
  MembershipTypeCreateBody,
  MembershipTypeUpdateBody,
} from '../../../types/members';

export type MembershipTypeModalMode = 'create' | 'edit';

export interface MembershipTypeModalProps {
  isOpen: boolean;
  onClose: () => void;
  mode: MembershipTypeModalMode;
  /**
   * The entry being edited (EDIT mode) — the modal seeds its form from it and locks `type_code`.
   * Ignored / unused in CREATE mode.
   */
  entry?: MembershipType | null;
  /**
   * Called after a successful create / update / retire so the manager refreshes its list (R2.6).
   * The modal awaits this before closing so the refreshed list is in flight as the modal unmounts.
   */
  onMutated: () => void | Promise<void>;
  lang: 'nl' | 'en';
  /**
   * Defense-in-depth UX gate for `members:admin` (task 2.4; R1.3). The manager only ever OPENS this
   * modal for an admin, so in practice this is `true` whenever the modal is rendered — but if the
   * modal is ever mounted for a non-admin, the mutating buttons (Save / Retire) are hidden here too.
   * Defaults `true` so the admin path and any direct caller are unaffected. NOT a security boundary —
   * the SAM `CATALOG` write routes enforce `members:admin` authoritatively (a 403 surfaces readably).
   */
  canMutate?: boolean;
}

/** The editable form shape (strings for inputs; parsed on submit). */
interface TypeForm {
  type_code: string;
  label_nl: string;
  label_en: string;
  order: string;
  active: boolean;
}

const EMPTY_FORM: TypeForm = {
  type_code: '',
  label_nl: '',
  label_en: '',
  order: '',
  active: true,
};

/** Read the bilingual label dict off an entry (tolerant of a plain-string legacy label). */
function labelDict(label: MembershipType['label']): LocalizedLabel {
  if (typeof label === 'string') return { nl: label };
  if (label && typeof label === 'object') return label as LocalizedLabel;
  return {};
}

/** Seed the editable form from an entry (edit mode) or the empty defaults (create mode). */
function formFromEntry(entry: MembershipType | null | undefined): TypeForm {
  if (!entry) return { ...EMPTY_FORM };
  const label = labelDict(entry.label);
  return {
    type_code: entry.type_code ?? entry.key ?? '',
    label_nl: typeof label.nl === 'string' ? label.nl : '',
    label_en: typeof label.en === 'string' ? label.en : '',
    order: typeof entry.order === 'number' ? String(entry.order) : '',
    active: entry.active !== false,
  };
}

/** Assemble a `LocalizedLabel` from the two inputs (nl required; en only when non-blank). */
function buildLabel(form: TypeForm): LocalizedLabel {
  const nl = form.label_nl.trim();
  const en = form.label_en.trim();
  return { nl, ...(en ? { en } : {}) };
}

/** Parse the order input to an integer, or `undefined` when blank/unparseable (2.3 validates). */
function parseOrder(order: string): number | undefined {
  const trimmed = order.trim();
  if (!trimmed) return undefined;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : undefined;
}

/** Per-field inline validation errors, keyed by the form field that owns the message. */
interface FieldErrors {
  type_code?: string;
  label_nl?: string;
  order?: string;
}

/** The form fields this modal owns — the `knownFields` set `applyApiError` matches against. */
const KNOWN_FIELDS = ['type_code', 'label', 'label.nl', 'order', 'active'] as const;

export const MembershipTypeModal: React.FC<MembershipTypeModalProps> = ({
  isOpen,
  onClose,
  mode,
  entry,
  onMutated,
  lang,
  canMutate = true,
}) => {
  // `t(nl,en)` = the modal's bilingual helper (own copy, incl. the client-validation messages).
  // `tApi` = react-i18next's key-based translate, passed to `applyApiError` so a backend `code`
  //          resolves to localized copy (it builds the `errors:<path>` key itself, regardless of ns).
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const { t: tApi } = useTypedTranslation('errors');
  const toast = useToast();

  const [form, setForm] = useState<TypeForm>(() =>
    mode === 'edit' ? formFromEntry(entry) : { ...EMPTY_FORM },
  );
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [confirmRetireOpen, setConfirmRetireOpen] = useState(false);
  const cancelRetireRef = useRef<HTMLButtonElement>(null);

  // Re-seed whenever the modal (re)opens or the target entry changes.
  useEffect(() => {
    if (isOpen) {
      setForm(mode === 'edit' ? formFromEntry(entry) : { ...EMPTY_FORM });
      setFieldErrors({});
      setSubmitting(false);
      setConfirmRetireOpen(false);
    }
  }, [isOpen, mode, entry]);

  // Editing a field both updates the value AND clears any inline error on the field(s) it feeds,
  // so a corrected input drops its message immediately (the `nl` label owns the `label_nl` key).
  const set = <K extends keyof TypeForm>(k: K, v: TypeForm[K]) => {
    setForm((prev) => ({ ...prev, [k]: v }));
    setFieldErrors((prev) => {
      if (k === 'type_code' && prev.type_code) return { ...prev, type_code: undefined };
      if (k === 'label_nl' && prev.label_nl) return { ...prev, label_nl: undefined };
      if (k === 'order' && prev.order) return { ...prev, order: undefined };
      return prev;
    });
  };

  /**
   * Client-side pre-submit validation (R2.4) mirroring the SAM domain rules — fast feedback before
   * the service call; the domain stays authoritative. Returns the per-field errors ({} = valid).
   *   - `type_code` (create only; locked on edit): non-blank AND must NOT contain `#`.
   *   - `label.nl`: non-blank.
   *   - `order`: optional (blank = omit → server defaults 0); when present must parse to an INTEGER.
   */
  const validate = (f: TypeForm): FieldErrors => {
    const errors: FieldErrors = {};
    if (mode === 'create') {
      const code = f.type_code.trim();
      if (!code) {
        errors.type_code = t('Code is verplicht.', 'Code is required.');
      } else if (code.includes('#')) {
        errors.type_code = t(
          'Code mag geen # bevatten.',
          'Code must not contain a # character.',
        );
      }
    }
    if (!f.label_nl.trim()) {
      errors.label_nl = t('Nederlands label is verplicht.', 'A Dutch (nl) label is required.');
    }
    const order = f.order.trim();
    if (order) {
      const n = Number(order);
      if (!Number.isInteger(n)) {
        errors.order = t(
          'Volgorde moet een geheel getal zijn.',
          'Order must be a whole number.',
        );
      }
    }
    return errors;
  };

  /**
   * Set an inline error from a backend field key (the `setFieldError` seam `applyApiError` calls).
   * Maps the dotted backend key (`type_code`, `label`, `label.nl`, `order`) onto this form's own
   * field-error slots so e.g. a 409 duplicate `type_code` lands inline on the code input.
   */
  const setBackendFieldError = (field: string, message: string) => {
    const bare = field.includes('.') ? field.slice(field.lastIndexOf('.') + 1) : field;
    setFieldErrors((prev) => {
      if (field === 'type_code' || bare === 'type_code') return { ...prev, type_code: message };
      if (field === 'order' || bare === 'order') return { ...prev, order: message };
      if (field === 'label' || field === 'label.nl' || bare === 'nl' || bare === 'label') {
        return { ...prev, label_nl: message };
      }
      return prev;
    });
  };

  // Coarse Save-disabled gate: create needs a `type_code`; both modes need an `nl` label. The FULL
  // rules (no `#`, integer `order`) run in `validate()` on submit and surface inline (task 2.3), so
  // the user sees WHY a near-complete form is rejected rather than a silently-disabled button.
  const canSubmit = useMemo(() => {
    const hasLabel = form.label_nl.trim().length > 0;
    if (mode === 'create') return form.type_code.trim().length > 0 && hasLabel;
    return hasLabel;
  }, [mode, form.type_code, form.label_nl]);

  /**
   * Surface a thrown error through the house `applyApiError` helper (R2.4): localized inline field
   * errors (e.g. a 409 duplicate `type_code` matched to the code input) + a localized summary toast;
   * a 404 / other 4xx surfaces readably; a non-`ApiError` degrades to the server-error toast.
   */
  const surfaceError = (e: unknown) => {
    applyApiError(e, {
      toast,
      t: tApi,
      setFieldError: setBackendFieldError,
      knownFields: KNOWN_FIELDS,
    });
  };

  const handleSave = async () => {
    if (submitting) return;
    // Pre-submit validation — block and show inline errors when any rule fails (do NOT call the
    // service with invalid input). The Save-disabled gate is coarse; this gives the WHY.
    const errors = validate(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setSubmitting(true);
    try {
      if (mode === 'create') {
        const body: MembershipTypeCreateBody = {
          type_code: form.type_code.trim(),
          label: buildLabel(form),
        };
        const order = parseOrder(form.order);
        if (order !== undefined) body.order = order;
        await createMembershipType(body);
        toast({
          title: t('Type aangemaakt', 'Type created'),
          status: 'success',
          duration: 3000,
        });
      } else {
        const typeCode = entry?.type_code ?? entry?.key ?? form.type_code.trim();
        const body: MembershipTypeUpdateBody = {
          label: buildLabel(form),
          active: form.active,
        };
        const order = parseOrder(form.order);
        if (order !== undefined) body.order = order;
        await updateMembershipType(typeCode, body);
        toast({
          title: t('Type bijgewerkt', 'Type updated'),
          status: 'success',
          duration: 3000,
        });
      }
      await onMutated();
      onClose();
    } catch (e) {
      surfaceError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetire = async () => {
    const typeCode = entry?.type_code ?? entry?.key ?? '';
    if (!typeCode || submitting) return;
    setSubmitting(true);
    try {
      await deactivateMembershipType(typeCode);
      toast({
        title: t('Type gepensioneerd', 'Type retired'),
        description: t(
          'Bestaande leden behouden hun verwijzing; het type verdwijnt uit de keuzelijst.',
          'Existing members keep their reference; the type drops out of the dropdown.',
        ),
        status: 'success',
        duration: 4000,
      });
      setConfirmRetireOpen(false);
      await onMutated();
      onClose();
    } catch (e) {
      // A 404 (absent) / other 4xx surfaces readably; close the confirm so the toast is visible.
      setConfirmRetireOpen(false);
      surfaceError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const inputProps = {
    bg: 'gray.700',
    color: 'white',
    borderColor: 'gray.600',
  } as const;

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} size="lg" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent bg="gray.800" data-testid="membership-type-modal">
          <ModalHeader color="orange.400">
            {mode === 'create'
              ? t('Lidmaatschapstype aanmaken', 'Create membership type')
              : t('Lidmaatschapstype bewerken', 'Edit membership type')}
          </ModalHeader>
          <ModalCloseButton color="white" />

          <ModalBody>
            <VStack spacing={4} align="stretch" pb={2}>
              {/* Identity — `type_code` is the stable id: editable on create, LOCKED on edit (R2.2). */}
              <FormControl isRequired={mode === 'create'} isInvalid={!!fieldErrors.type_code}>
                <FormLabel color="gray.300">{t('Code', 'Code')}</FormLabel>
                <Input
                  {...inputProps}
                  value={form.type_code}
                  onChange={(e) => set('type_code', e.target.value)}
                  isDisabled={mode === 'edit'}
                  isReadOnly={mode === 'edit'}
                  aria-label={t('Code', 'Code')}
                  data-testid="membership-type-modal-code"
                />
                {fieldErrors.type_code && (
                  <FormErrorMessage data-testid="membership-type-modal-code-error">
                    {fieldErrors.type_code}
                  </FormErrorMessage>
                )}
                {mode === 'edit' && (
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    {t('De code kan niet worden gewijzigd', 'The code cannot be changed')}
                  </Text>
                )}
              </FormControl>

              <HStack align="start" spacing={3}>
                <FormControl isRequired isInvalid={!!fieldErrors.label_nl}>
                  <FormLabel color="gray.300">{t('Label (Nederlands)', 'Label (Dutch)')}</FormLabel>
                  <Input
                    {...inputProps}
                    value={form.label_nl}
                    onChange={(e) => set('label_nl', e.target.value)}
                    aria-label={t('Label (Nederlands)', 'Label (Dutch)')}
                    data-testid="membership-type-modal-label-nl"
                  />
                  {fieldErrors.label_nl && (
                    <FormErrorMessage data-testid="membership-type-modal-label-nl-error">
                      {fieldErrors.label_nl}
                    </FormErrorMessage>
                  )}
                </FormControl>
                <FormControl>
                  <FormLabel color="gray.300">{t('Label (Engels)', 'Label (English)')}</FormLabel>
                  <Input
                    {...inputProps}
                    value={form.label_en}
                    onChange={(e) => set('label_en', e.target.value)}
                    aria-label={t('Label (Engels)', 'Label (English)')}
                    data-testid="membership-type-modal-label-en"
                  />
                </FormControl>
              </HStack>

              <HStack align="start" spacing={6}>
                <FormControl maxW="40" isInvalid={!!fieldErrors.order}>
                  <FormLabel color="gray.300">{t('Volgorde', 'Order')}</FormLabel>
                  <Input
                    {...inputProps}
                    type="number"
                    value={form.order}
                    onChange={(e) => set('order', e.target.value)}
                    aria-label={t('Volgorde', 'Order')}
                    data-testid="membership-type-modal-order"
                  />
                  {fieldErrors.order && (
                    <FormErrorMessage data-testid="membership-type-modal-order-error">
                      {fieldErrors.order}
                    </FormErrorMessage>
                  )}
                </FormControl>

                {/* `active`: read-only true on create (server defaults it); a toggle on edit (R2.2). */}
                <FormControl display="flex" alignItems="center" w="auto" pt={7}>
                  <FormLabel color="gray.300" mb={0} mr={2}>
                    {t('Actief', 'Active')}
                  </FormLabel>
                  <Switch
                    isChecked={mode === 'create' ? true : form.active}
                    onChange={(e) => set('active', e.target.checked)}
                    isDisabled={mode === 'create'}
                    colorScheme="orange"
                    aria-label={t('Actief', 'Active')}
                    data-testid="membership-type-modal-active"
                  />
                </FormControl>
              </HStack>
            </VStack>
          </ModalBody>

          <ModalFooter>
            <HStack justify="space-between" w="100%">
              {/* Retire (soft-delete) — edit mode only; confirm-before-retire (R2.3). Hidden for a
                  non-admin (defense-in-depth UX gate, task 2.4; SAM's 403 is the real guard). */}
              <HStack>
                {mode === 'edit' && canMutate && (
                  <Button
                    variant="outline"
                    colorScheme="red"
                    size="sm"
                    isDisabled={submitting}
                    onClick={() => setConfirmRetireOpen(true)}
                    data-testid="membership-type-modal-retire"
                  >
                    {t('Pensioneren', 'Retire')}
                  </Button>
                )}
              </HStack>
              <HStack>
                <Button
                  variant="ghost"
                  color="gray.300"
                  onClick={onClose}
                  isDisabled={submitting}
                  data-testid="membership-type-modal-cancel"
                >
                  {t('Annuleren', 'Cancel')}
                </Button>
                {/* Save (create/update) — hidden for a non-admin (defense-in-depth UX gate, task 2.4;
                    SAM's 403 is the authoritative guard). */}
                {canMutate && (
                  <Button
                    colorScheme="orange"
                    onClick={handleSave}
                    isDisabled={!canSubmit || submitting}
                    isLoading={submitting && !confirmRetireOpen}
                    data-testid="membership-type-modal-save"
                  >
                    {t('Opslaan', 'Save')}
                  </Button>
                )}
              </HStack>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Confirm-before-retire — keep it simple; a plain confirm dialog over the soft-delete. */}
      <AlertDialog
        isOpen={confirmRetireOpen}
        leastDestructiveRef={cancelRetireRef}
        onClose={() => setConfirmRetireOpen(false)}
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" data-testid="membership-type-retire-confirm">
            <AlertDialogHeader color="orange.400">
              {t('Type pensioneren?', 'Retire type?')}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              {t(
                'Dit zet het type op inactief. Bestaande leden behouden hun verwijzing, maar het type verdwijnt uit de keuzelijst. Dit is geen definitieve verwijdering.',
                'This deactivates the type. Existing members keep their reference, but the type drops out of the assignment dropdown. This is not a permanent delete.',
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={cancelRetireRef}
                variant="ghost"
                color="gray.300"
                onClick={() => setConfirmRetireOpen(false)}
                isDisabled={submitting}
                data-testid="membership-type-retire-cancel"
              >
                {t('Annuleren', 'Cancel')}
              </Button>
              <Button
                colorScheme="red"
                ml={3}
                onClick={handleRetire}
                isLoading={submitting}
                data-testid="membership-type-retire-confirm-button"
              >
                {t('Pensioneren', 'Retire')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
};

export default MembershipTypeModal;
