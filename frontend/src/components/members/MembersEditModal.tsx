/**
 * Members Edit modal (task 19.2) — REUSES the shared modal pattern (R7.9): a
 * Chakra `Modal` built with Formik + Yup, a Cancel(ghost)/Save(orange) footer,
 * and `closeOnOverlayClick={false}` (an edit modal must not be dismissed by an
 * accidental overlay click), following `frontend/src/components/members/MembersAddModal.tsx`,
 * `frontend/src/pages/ZZPInvoices.tsx` + `frontend/src/components/zzp/ProductModal.tsx`
 * and `.kiro/steering/32-frontend-ui.md`.
 *
 * It shares almost all of the Add modal's form scaffolding/validation — it is
 * pre-populated from the SELECTED member instead of starting blank:
 * - name / email (fixed base) + membership_type + region/scope, plus any overlay
 *   fields the resolved field config (fixed base ⊕ tenant overlay) marks visible.
 * - membership_type is a dropdown fed by `listMembershipTypes(true)` — ACTIVE-ONLY
 *   (R7.7); no free text.
 * - region/scope is a dropdown fed by the field config's scope dimension values.
 *
 * On submit the modal shapes the module's NESTED update payload (same shape as
 * create: `personal.name`, `personal.contact`, `membership.membership_type`,
 * `scope_values.<dimension>: [value]`) + any overlay scalars, and calls
 * `updateMember(memberId, body)` → `PUT /members/{member_id}`. The module stamps
 * the tenant itself (`_sanitize_write_payload` strips a body `tenant_id` and the
 * service overwrites it authoritatively), so the body NEVER carries a tenant
 * field (Property 2).
 *
 * On success: toast, close, and refresh the list via `onSaved`. On error: toast
 * the server message (the service's `handleResponse` throws with it).
 *
 * _Requirements: R8.2, R7.7, R7.9_
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  FormErrorMessage, Input, Select, VStack, useToast,
} from '@chakra-ui/react';
import { Formik, Form, Field, type FieldProps } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { updateMember, listMembershipTypes } from '../../services/membersApiService';
import type {
  FieldConfig, FieldConfigField, LocalizedLabel, MembershipType, Member,
} from '../../types/members';

interface MembersEditModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The member being edited (pre-fills the form). */
  member: Member | null;
  /** Resolved field config (fixed base ⊕ overlay + scope dimensions). */
  fieldConfig: FieldConfig | null;
  /** Called after a successful update so the page can refresh its list. */
  onSaved: () => void;
}

/** The always-present fixed keys the modal renders explicitly (not overlay). */
const FIXED_FIELD_KEYS = new Set<string>([
  'name', 'email', 'membership_type', 'region', 'member_id', 'status', 'member_number',
]);

/** Resolve a possibly-localized label to a plain string for the current lang. */
function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/** The dynamic form value shape: known fixed keys + arbitrary overlay scalars. */
type FormValues = {
  name: string;
  email: string;
  membership_type: string;
  region: string;
  [key: string]: string;
};

export const MembersEditModal: React.FC<MembersEditModalProps> = ({
  isOpen, onClose, member, fieldConfig, onSaved,
}) => {
  const { t, i18n } = useTypedTranslation('members');
  const toast = useToast();
  const lang = (i18n?.language || 'nl').slice(0, 2);

  const [membershipTypes, setMembershipTypes] = useState<MembershipType[]>([]);

  // Load the ACTIVE-ONLY membership-type catalog for the dropdown (R7.7).
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    listMembershipTypes<MembershipType[]>(true)
      .then((types) => { if (!cancelled) setMembershipTypes(Array.isArray(types) ? types : []); })
      .catch(() => { if (!cancelled) setMembershipTypes([]); });
    return () => { cancelled = true; };
  }, [isOpen]);

  // The scope dimension (e.g. region) + its allowed values from the field config.
  const dimension = fieldConfig?.dimensions?.find(d => d.enabled !== false);
  const dimensionKey = dimension?.key ?? 'region';
  const regionValues = useMemo(() => dimension?.values ?? [], [dimension]);

  // Overlay (variable) fields to render — anything not one of the fixed keys.
  const overlayFields: FieldConfigField[] = useMemo(() => {
    const fields = fieldConfig?.fields ?? [];
    return fields
      .filter(f => !FIXED_FIELD_KEYS.has(f.key))
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [fieldConfig]);

  // Pre-populate the form from the selected member (fixed keys + overlay scalars).
  const initialValues: FormValues = useMemo(() => {
    const base: FormValues = {
      name: (member?.name as string) ?? '',
      email: (member?.email as string) ?? '',
      membership_type: (member?.membership_type as string) ?? '',
      region: (member?.region as string) ?? '',
    };
    overlayFields.forEach(f => {
      const v = member?.[f.key];
      base[f.key] = v != null ? String(v) : '';
    });
    return base;
  }, [member, overlayFields]);

  const validationSchema = useMemo(() => {
    const shape: Record<string, Yup.AnySchema> = {
      name: Yup.string().trim().required(t('editModal.validation.nameRequired')),
      email: Yup.string()
        .trim()
        .email(t('editModal.validation.emailInvalid'))
        .required(t('editModal.validation.emailRequired')),
      membership_type: Yup.string().required(t('editModal.validation.membershipTypeRequired')),
    };
    // Region is required only when the dimension defines allowed values.
    if (regionValues.length > 0) {
      shape.region = Yup.string().required(t('editModal.validation.regionRequired'));
    }
    return Yup.object().shape(shape);
  }, [t, regionValues]);

  const handleSubmit = async (
    values: FormValues,
    { setSubmitting }: { setSubmitting: (b: boolean) => void },
  ) => {
    if (!member) { setSubmitting(false); return; }

    // Shape the module's NESTED update payload. NO tenant field — the module
    // stamps the tenant authoritatively (verify-before-trust, Property 2).
    const body: Record<string, unknown> = {
      personal: { name: values.name.trim(), contact: values.email.trim() },
      membership: { membership_type: values.membership_type },
    };
    if (values.region) {
      body.scope_values = { [dimensionKey]: [values.region] };
    }
    // Carry any non-empty overlay scalars through as top-level fields.
    overlayFields.forEach(f => {
      const v = values[f.key];
      if (v !== undefined && v !== '') body[f.key] = v;
    });

    try {
      await updateMember(member.member_id, body);
      toast({ title: t('editModal.toast.success'), status: 'success' });
      onSaved();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('editModal.toast.error');
      toast({ title: message, status: 'error' });
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
          {({ isSubmitting }) => (
            <Form>
              <ModalBody maxH="70vh" overflowY="auto">
                <VStack spacing={3} align="stretch">
                  <Field name="name">
                    {({ field, form }: FieldProps<string, FormValues>) => (
                      <FormControl isRequired isInvalid={!!form.errors.name && !!form.touched.name}>
                        <FormLabel color="gray.300" fontSize="sm">
                          {t('editModal.fields.name')}
                        </FormLabel>
                        <Input {...field} size="sm" bg="gray.700" color="white" borderColor="gray.600" />
                        <FormErrorMessage>{form.errors.name as string}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>

                  <Field name="email">
                    {({ field, form }: FieldProps<string, FormValues>) => (
                      <FormControl isRequired isInvalid={!!form.errors.email && !!form.touched.email}>
                        <FormLabel color="gray.300" fontSize="sm">
                          {t('editModal.fields.email')}
                        </FormLabel>
                        <Input {...field} type="email" size="sm" bg="gray.700" color="white" borderColor="gray.600" />
                        <FormErrorMessage>{form.errors.email as string}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>

                  <Field name="membership_type">
                    {({ field, form }: FieldProps<string, FormValues>) => (
                      <FormControl
                        isRequired
                        isInvalid={!!form.errors.membership_type && !!form.touched.membership_type}
                      >
                        <FormLabel color="gray.300" fontSize="sm">
                          {t('editModal.fields.membershipType')}
                        </FormLabel>
                        <Select
                          {...field}
                          size="sm"
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          placeholder={t('editModal.fields.membershipTypePlaceholder')}
                        >
                          {membershipTypes.map(mt => (
                            <option key={mt.key} value={mt.key}>
                              {resolveLabel(mt.label, lang, mt.key)}
                            </option>
                          ))}
                        </Select>
                        <FormErrorMessage>{form.errors.membership_type as string}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>

                  {regionValues.length > 0 && (
                    <Field name="region">
                      {({ field, form }: FieldProps<string, FormValues>) => (
                        <FormControl isRequired isInvalid={!!form.errors.region && !!form.touched.region}>
                          <FormLabel color="gray.300" fontSize="sm">
                            {resolveLabel(dimension?.label, lang, t('editModal.fields.region'))}
                          </FormLabel>
                          <Select
                            {...field}
                            size="sm"
                            bg="gray.700"
                            color="white"
                            borderColor="gray.600"
                            placeholder={t('editModal.fields.regionPlaceholder')}
                          >
                            {regionValues.map(v => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </Select>
                          <FormErrorMessage>{form.errors.region as string}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                  )}

                  {overlayFields.map(f => (
                    <Field key={f.key} name={f.key}>
                      {({ field }: FieldProps<string, FormValues>) => (
                        <FormControl>
                          <FormLabel color="gray.300" fontSize="sm">
                            {resolveLabel(f.label, lang, f.key)}
                          </FormLabel>
                          <Input
                            {...field}
                            type={f.type === 'number' ? 'number' : 'text'}
                            size="sm"
                            bg="gray.700"
                            color="white"
                            borderColor="gray.600"
                          />
                        </FormControl>
                      )}
                    </Field>
                  ))}
                </VStack>
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
