/**
 * Members Edit modal (s5c task 4.4 — BROADENED from the s5b edit modal). REUSES the shared modal
 * pattern (R7.9): a Chakra `Modal` built with Formik + Yup, a Cancel(ghost)/Save(orange) footer,
 * and `closeOnOverlayClick={false}`, following `MembersAddModal.tsx`,
 * `frontend/src/pages/ZZPInvoices.tsx` + `frontend/src/components/zzp/ProductModal.tsx` and
 * `.kiro/steering/32-frontend-ui.md`.
 *
 * Shares the Add modal's whole sectioned-form scaffolding (`MembersFieldFormBody` +
 * `fieldFormModel`) — it is pre-populated from the SELECTED member instead of starting blank. It
 * renders the RESOLVED field set (fixed base ⊕ tenant overlay ⊕ calculated), SECTIONED by
 * `functional_group` (R4.9), honoring field-level view/edit permissions (calculated / read-only
 * fields are shown disabled), `show_when` conditional visibility (R4.12), value-level
 * role-restricted enum options (R4.11/R4.12), and `member_number` manual entry with tenant-format
 * feedback (R4.8).
 *
 * On submit the modal shapes the module's NESTED update payload by each field's STORAGE group
 * (`personal.*` / `membership.*` / `overlay.*`, + `scope_values.<dimension>`) and calls
 * `updateMember(memberId, body)` → `PUT /members/{member_id}`. The module stamps the tenant and
 * is the AUTHORITATIVE validator (Property 2, R2.3). NO tenant field is ever sent.
 *
 * On success: toast, close, and refresh the list via `onSaved`. On error: toast the server
 * message.
 *
 * _Requirements: R5.5, R4.8, R4.9, R4.11, R4.12, R8.2, R7.9_
 */

import React, { useMemo } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, useToast,
} from '@chakra-ui/react';
import { Formik, Form } from 'formik';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useAuth } from '../../context/AuthContext';
import { updateMember } from '../../services/membersApiService';
import { applyApiError } from '../../shared/api/applyApiError';
import type { FieldConfig, Member, MembershipType } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import { formFields, groupFieldsBySection, memberNumberError } from './fieldForm';
import {
  buildInitialValues, buildValidationSchema, shapeWritePayload, scopeInfo,
} from './fieldFormModel';

interface MembersEditModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The member being edited (pre-fills the form). */
  member: Member | null;
  /** Resolved field config (fixed base ⊕ overlay + scope dimensions + functional groups). */
  fieldConfig: FieldConfig | null;
  /**
   * The tenant's ACTIVE **Lidmaatschap Beheer** catalog entries (R5.8), fetched by the page via
   * `listMembershipTypes(true)`. Feeds the `membership_type` dropdown with active types only; the
   * domain re-validates the chosen type authoritatively.
   */
  membershipTypes?: MembershipType[] | null;
  /** Called after a successful update so the page can refresh its list. */
  onSaved: () => void;
}

export const MembersEditModal: React.FC<MembersEditModalProps> = ({
  isOpen, onClose, member, fieldConfig, membershipTypes, onSaved,
}) => {
  const { t, i18n } = useTypedTranslation('members');
  const toast = useToast();
  const { user } = useAuth();
  const lang = (i18n?.language || 'nl').slice(0, 2);
  const callerRoles = user?.roles ?? [];

  const fields = useMemo(() => formFields(fieldConfig), [fieldConfig]);
  const sections = useMemo(
    () => groupFieldsBySection(fields, fieldConfig?.functional_groups),
    [fields, fieldConfig],
  );

  const { dimensionKey, regionValues, dimensionLabel } = useMemo(
    () => scopeInfo(fieldConfig, lang),
    [fieldConfig, lang],
  );

  const initialValues = useMemo(
    () => buildInitialValues(fields, member),
    [fields, member],
  );

  const validationSchema = useMemo(
    () => buildValidationSchema(fields, { t, memberNumberError }),
    [fields, t],
  );

  // Map a backend DOTTED field key to this form's Formik field name (bare key, or `region` for
  // the scope dimension); undefined = not on this form → folds into the summary toast (task 4.5).
  const formFieldNameFor = useMemo(() => {
    const formNames = new Set(fields.map((f) => f.key));
    return (dotted: string): string | undefined => {
      const bare = dotted.includes('.') ? dotted.slice(dotted.indexOf('.') + 1) : dotted;
      if (dimensionKey && bare === dimensionKey) return 'region';
      return formNames.has(bare) ? bare : undefined;
    };
  }, [fields, dimensionKey]);

  const handleSubmit = async (
    values: Record<string, string>,
    {
      setSubmitting,
      setFieldError,
    }: {
      setSubmitting: (b: boolean) => void;
      setFieldError: (field: string, message: string) => void;
    },
  ) => {
    if (!member) { setSubmitting(false); return; }
    // Pass the member so a CLEARED optional field (now blank, previously set) is sent as "" to
    // clear it server-side — not silently dropped ("leave unchanged").
    const body = shapeWritePayload(fields, values, { dimensionKey, member });
    try {
      await updateMember(member.member_id, body);
      toast({ title: t('editModal.toast.success'), status: 'success' });
      onSaved();
      onClose();
    } catch (err) {
      // API standard v1.0: 422 per-field errors INLINE (localized) + summary toast; unmatched /
      // non-ApiError degrade gracefully (task 4.5).
      applyApiError(err, { toast, t, setFieldError, fieldNameFor: formFieldNameFor });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      scrollBehavior="inside"
      closeOnOverlayClick={false}
      isCentered
    >
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{t('editModal.title')}</ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={validationSchema}
          onSubmit={handleSubmit}
          enableReinitialize
        >
          {({ isSubmitting, values }) => (
            <Form>
              <ModalBody maxH="70vh" overflowY="auto">
                <MembersFieldFormBody
                  sections={sections}
                  fieldConfig={fieldConfig}
                  values={values}
                  callerRoles={callerRoles}
                  lang={lang}
                  t={t}
                  dimensionKey={dimensionKey}
                  regionValues={regionValues}
                  dimensionLabel={dimensionLabel}
                  membershipTypes={membershipTypes}
                />
              </ModalBody>
              <ModalFooter>
                <Button variant="ghost" mr={3} onClick={onClose}>
                  {t('editModal.cancel')}
                </Button>
                <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                  {t('editModal.save')}
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};

export default MembersEditModal;
