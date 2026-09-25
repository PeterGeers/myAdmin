/**
 * Members Add / application modal (s5c task 4.4 — BROADENED from the s5b add modal). REUSES
 * the shared modal pattern (R7.9): a Chakra `Modal` built with Formik + Yup, a
 * Cancel(ghost)/Save(orange) footer, and `closeOnOverlayClick={false}` (an add modal must not
 * be dismissed by an accidental overlay click), following
 * `frontend/src/pages/ZZPInvoices.tsx` + `frontend/src/components/zzp/ProductModal.tsx` and
 * `.kiro/steering/32-frontend-ui.md`.
 *
 * BROADENED over the RESOLVED field set (design C-SURFACE): instead of a hardcoded name/email
 * list it renders WHATEVER `GET /members/field-config` resolves — the fixed base ⊕ tenant
 * overlay ⊕ calculated fields — SECTIONED by each field's parameter-driven `functional_group`
 * (R4.9) via `MembersFieldFormBody`, honoring field-level view/edit permissions, `show_when`
 * conditional visibility (R4.12), value-level role-restricted enum options (R4.11/R4.12), and
 * `member_number` manual entry with tenant-format feedback (R4.8).
 *
 * On submit the modal shapes the module's NESTED create payload by each field's STORAGE group
 * (`personal.*`, `membership.*`, overlay under `overlay.*`) + `scope_values.<dimension>`, and
 * calls `createMember(body)` → `POST /members`. The module stamps the tenant itself and is the
 * AUTHORITATIVE validator (Property 2, R2.3): it re-checks required-ness, role-gated enum values,
 * `member_number` format + uniqueness, and `show_when` hidden-not-required — the frontend only
 * presents and gives early feedback. NO tenant field is ever sent.
 *
 * On success: toast, close, and refresh the list via `onSaved`. On error: toast the server
 * message (the service's `handleResponse` throws with it).
 *
 * _Requirements: R5.5, R4.8, R4.9, R4.11, R4.12, R8.3, R7.9_
 */

import React, { useMemo } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, useToast,
} from '@chakra-ui/react';
import { Formik, Form } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useAuth } from '../../context/AuthContext';
import { createMember } from '../../services/membersApiService';
import { applyApiError } from '../../shared/api/applyApiError';
import type { FieldConfig, MembershipType } from '../../types/members';
import { MembersFieldFormBody } from './MembersFieldFormBody';
import {
  formFields, groupFieldsBySection, memberNumberError,
} from './fieldForm';
import {
  buildInitialValues, buildValidationSchema, shapeWritePayload, scopeInfo,
} from './fieldFormModel';

interface MembersAddModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Resolved field config (fixed base ⊕ overlay + scope dimensions + functional groups). */
  fieldConfig: FieldConfig | null;
  /**
   * The tenant's ACTIVE **Lidmaatschap Beheer** catalog entries (R5.8), fetched by the page via
   * `listMembershipTypes(true)`. Feeds the `membership_type` dropdown with active types only; the
   * domain re-validates the chosen type authoritatively.
   */
  membershipTypes?: MembershipType[] | null;
  /** Called after a successful create so the page can refresh its list. */
  onSaved: () => void;
}

export const MembersAddModal: React.FC<MembersAddModalProps> = ({
  isOpen, onClose, fieldConfig, membershipTypes, onSaved,
}) => {
  const { t, i18n } = useTypedTranslation('members');
  const toast = useToast();
  const { user } = useAuth();
  const lang = (i18n?.language || 'nl').slice(0, 2);
  const callerRoles = user?.roles ?? [];

  // The editable resolved fields (visible, not read-only, not system) in order.
  const fields = useMemo(() => formFields(fieldConfig), [fieldConfig]);
  const sections = useMemo(
    () => groupFieldsBySection(fields, fieldConfig?.functional_groups),
    [fields, fieldConfig],
  );

  const { dimensionKey, regionValues, dimensionLabel } = useMemo(
    () => scopeInfo(fieldConfig, lang),
    [fieldConfig, lang],
  );

  // Map a backend DOTTED field key (`personal.first_name`, `overlay.<dim>`) to this form's own
  // Formik field name (the BARE key, or `region` for the scope dimension — see
  // MembersFieldFormBody where `name = isScope ? 'region' : field.key`). Returns undefined when
  // the field is not on this form, so applyApiError folds it into the summary toast (task 4.5).
  const formFieldNameFor = useMemo(() => {
    const formNames = new Set(fields.map((f) => f.key));
    return (dotted: string): string | undefined => {
      const bare = dotted.includes('.') ? dotted.slice(dotted.indexOf('.') + 1) : dotted;
      if (dimensionKey && bare === dimensionKey) return 'region';
      return formNames.has(bare) ? bare : undefined;
    };
  }, [fields, dimensionKey]);

  const initialValues = useMemo(() => buildInitialValues(fields, null), [fields]);

  const validationSchema = useMemo(
    () => buildValidationSchema(fields, { t, memberNumberError }),
    [fields, t],
  );

  const handleSubmit = async (
    values: Record<string, string>,
    {
      setSubmitting,
      resetForm,
      setFieldError,
    }: {
      setSubmitting: (b: boolean) => void;
      resetForm: () => void;
      setFieldError: (field: string, message: string) => void;
    },
  ) => {
    const body = shapeWritePayload(fields, values, { dimensionKey });
    try {
      await createMember(body);
      toast({ title: t('addModal.toast.success'), status: 'success' });
      resetForm();
      onSaved();
      onClose();
    } catch (err) {
      // API standard v1.0: render a 422's per-field errors INLINE (localized via code) + a
      // summary toast; unmatched fields / non-ApiError degrade gracefully (C3, task 4.5).
      applyApiError(err, {
        toast,
        t,
        setFieldError,
        // The backend keys fields DOTTED (`personal.first_name`); Formik names inputs by the
        // BARE key (`first_name`, or `region` for the scope dimension) — map dotted → own name.
        fieldNameFor: formFieldNameFor,
      });
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
        <ModalHeader>{t('addModal.title')}</ModalHeader>
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
                  {t('addModal.cancel')}
                </Button>
                <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                  {t('addModal.save')}
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};
export default MembersAddModal;
