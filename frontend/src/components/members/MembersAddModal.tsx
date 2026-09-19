/**
 * Members Add / application modal (task 20.1) — REUSES the shared modal pattern
 * (R7.9): a Chakra `Modal` built with Formik + Yup, a Cancel(ghost)/Save(orange)
 * footer, and `closeOnOverlayClick={false}` (an add/edit modal must not be
 * dismissed by an accidental overlay click), following
 * `frontend/src/pages/ZZPInvoices.tsx` + `frontend/src/components/zzp/ProductModal.tsx`
 * and `.kiro/steering/32-frontend-ui.md`.
 *
 * Fields (fixed base ⊕ overlay):
 * - name / email (fixed base) + membership_type + region/scope, plus any overlay
 *   fields the resolved field config (fixed base ⊕ tenant overlay) marks visible.
 * - membership_type is a dropdown fed by `listMembershipTypes(true)` — ACTIVE-ONLY
 *   (R7.7); no free text.
 * - region/scope is a dropdown fed by the field config's scope dimension values.
 *
 * On submit the modal shapes the module's NESTED create payload
 * (`personal.name`, `personal.contact`, `membership.membership_type`,
 * `scope_values.<dimension>: [value]`) + any overlay scalars, and calls
 * `createMember(body)` → `POST /members`. The module stamps the tenant itself
 * (`_sanitize_write_payload` strips a body `tenant_id` and the service overwrites
 * it authoritatively), so the body NEVER carries a tenant field. On success the
 * optional membership is created via `createMembership(memberId, ...)` only when a
 * membership_type was chosen and the create response yields a member id
 * (otherwise the single `POST /members` already carried the membership block).
 *
 * On success: toast, close, and refresh the list via `onSaved`. On error: toast
 * the server message (the service's `handleResponse` throws with it).
 *
 * _Requirements: R8.3, R7.7, R7.9_
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
import {
  createMember, createMembership, listMembershipTypes,
} from '../../services/membersApiService';
import type {
  FieldConfig, FieldConfigField, LocalizedLabel, MembershipType,
} from '../../types/members';

interface MembersAddModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Resolved field config (fixed base ⊕ overlay + scope dimensions). */
  fieldConfig: FieldConfig | null;
  /** Called after a successful create so the page can refresh its list. */
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

export const MembersAddModal: React.FC<MembersAddModalProps> = ({
  isOpen, onClose, fieldConfig, onSaved,
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

  const initialValues: FormValues = useMemo(() => {
    const base: FormValues = { name: '', email: '', membership_type: '', region: '' };
    overlayFields.forEach(f => { base[f.key] = ''; });
    return base;
  }, [overlayFields]);

  const validationSchema = useMemo(() => {
    const shape: Record<string, Yup.AnySchema> = {
      name: Yup.string().trim().required(t('addModal.validation.nameRequired')),
      email: Yup.string()
        .trim()
        .email(t('addModal.validation.emailInvalid'))
        .required(t('addModal.validation.emailRequired')),
      membership_type: Yup.string().required(t('addModal.validation.membershipTypeRequired')),
    };
    // Region is required only when the dimension defines allowed values.
    if (regionValues.length > 0) {
      shape.region = Yup.string().required(t('addModal.validation.regionRequired'));
    }
    return Yup.object().shape(shape);
  }, [t, regionValues]);

  const handleSubmit = async (
    values: FormValues,
    { setSubmitting, resetForm }: { setSubmitting: (b: boolean) => void; resetForm: () => void },
  ) => {
    // Shape the module's NESTED create payload. NO tenant field — the module
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
      const created = await createMember<{ member_id?: string } | undefined>(body);

      // Optional POST /members/{id}/memberships: only when the create response
      // yields a member id (the base create above already carried the membership
      // block, so this is a no-op unless a distinct membership record is needed —
      // kept minimal per the task's "optional/straightforward" guidance).
      const memberId = created?.member_id;
      if (memberId && values.membership_type) {
        try {
          await createMembership(memberId, { membership_type: values.membership_type });
        } catch {
          // The member was created; a secondary membership failure is non-fatal
          // for the add flow (the base create already recorded the membership).
        }
      }

      toast({ title: t('addModal.toast.success'), status: 'success' });
      resetForm();
      onSaved();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('addModal.toast.error');
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
        <ModalHeader>{t('addModal.title')}</ModalHeader>
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
                          {t('addModal.fields.name')}
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
                          {t('addModal.fields.email')}
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
                          {t('addModal.fields.membershipType')}
                        </FormLabel>
                        <Select
                          {...field}
                          size="sm"
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          placeholder={t('addModal.fields.membershipTypePlaceholder')}
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
                            {resolveLabel(dimension?.label, lang, t('addModal.fields.region'))}
                          </FormLabel>
                          <Select
                            {...field}
                            size="sm"
                            bg="gray.700"
                            color="white"
                            borderColor="gray.600"
                            placeholder={t('addModal.fields.regionPlaceholder')}
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
