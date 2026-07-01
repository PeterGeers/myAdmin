/**
 * BudgetTemplateFormModal — Formik modal for creating/editing budget templates.
 * Extracted from BudgetTemplatesPage.tsx for file size management.
 */

import React from 'react';
import {
  Box, Button, Text, HStack, VStack,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter,
  Input, Select, Checkbox, IconButton,
  FormControl, FormLabel, FormErrorMessage,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon } from '@chakra-ui/icons';
import { Formik, Form, Field, FieldArray, FieldProps } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import type { PeriodMode, DimensionType } from '../types/budget';
import type { Account } from '../types/chartOfAccounts';

/** Local form state for a template line */
export interface LineFormState {
  account_code: string;
  period_mode: PeriodMode;
  has_detail_dimension: boolean;
  dimension_type: DimensionType | null;
}

export const EMPTY_LINE: LineFormState = {
  account_code: '',
  period_mode: 'Monthly',
  has_detail_dimension: false,
  dimension_type: null,
};

/** Yup schema for template form validation */
export const templateSchema = Yup.object({
  name: Yup.string().required('Name is required').max(100),
  lines: Yup.array().of(
    Yup.object({
      account_code: Yup.string().required('Account code is required'),
      period_mode: Yup.string().oneOf(['Monthly', 'Annual']).required(),
      has_detail_dimension: Yup.boolean(),
      dimension_type: Yup.string().nullable().when('has_detail_dimension', {
        is: true,
        then: (schema) => schema.required('Dimension type is required'),
      }),
    })
  ).min(1, 'At least one line is required'),
});

interface BudgetTemplateFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingId: number | null;
  initialFormValues: { name: string; lines: LineFormState[] };
  accounts: Account[];
  onSave: (values: { name: string; lines: LineFormState[] }) => Promise<void>;
  onDelete: () => Promise<void>;
}

export const BudgetTemplateFormModal: React.FC<BudgetTemplateFormModalProps> = ({
  isOpen,
  onClose,
  editingId,
  initialFormValues,
  accounts,
  onSave,
  onDelete,
}) => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent maxW="700px" bg="gray.800" color="white">
        <ModalHeader>{editingId ? t('buttons.createTemplate').replace('Create', 'Edit') : t('buttons.createTemplate')}</ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialFormValues}
          validationSchema={templateSchema}
          onSubmit={onSave}
          enableReinitialize
        >
          {({ values, isSubmitting, errors, touched }) => (
            <Form>
              <ModalBody>
                <VStack spacing={4} align="stretch">
                  {/* Name */}
                  <Field name="name">
                    {({ field, meta }: FieldProps<string>) => (
                      <FormControl isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel color="white">{t('labels.templateName')}</FormLabel>
                        <Input
                          {...field}
                          maxLength={100}
                          placeholder={t('labels.templateName')}
                          bg="gray.700"
                          color="white"
                        />
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>

                  {/* Lines */}
                  <Box>
                    <Text fontWeight="semibold" mb={2} color="white">{t('columns.lines')}</Text>
                    {typeof errors.lines === 'string' && touched.lines && (
                      <Text color="red.300" fontSize="sm" mb={2}>{errors.lines}</Text>
                    )}
                    <FieldArray name="lines">
                      {({ push, remove }) => (
                        <VStack spacing={3} align="stretch">
                          {values.lines.map((_line, idx) => (
                            <Box key={idx} p={3} borderWidth="1px" borderRadius="md" bg="gray.700">
                              <HStack spacing={2} mb={2} align="flex-end">
                                <FormControl flex="3">
                                  <FormLabel fontSize="xs" color="gray.300">{t('labels.accountCode')}</FormLabel>
                                  <Field name={`lines.${idx}.account_code`}>
                                    {({ field, meta }: FieldProps<string>) => (
                                      <>
                                        <Select
                                          {...field}
                                          size="sm"
                                          placeholder={t('labels.accountCode')}
                                          bg="gray.600"
                                          color="white"
                                        >
                                          {accounts.map((acc) => (
                                            <option key={acc.Account} value={acc.Account}>
                                              {acc.Account} — {acc.AccountName}
                                            </option>
                                          ))}
                                        </Select>
                                        {meta.touched && meta.error && (
                                          <Text color="red.300" fontSize="xs">{meta.error}</Text>
                                        )}
                                      </>
                                    )}
                                  </Field>
                                </FormControl>
                                <FormControl flex="2">
                                  <FormLabel fontSize="xs" color="gray.300">{t('labels.periodMode')}</FormLabel>
                                  <Field name={`lines.${idx}.period_mode`}>
                                    {({ field }: FieldProps<string>) => (
                                      <Select {...field} size="sm" bg="gray.600" color="white">
                                        <option value="Monthly">{t('labels.monthly')}</option>
                                        <option value="Annual">{t('labels.annual')}</option>
                                      </Select>
                                    )}
                                  </Field>
                                </FormControl>
                                <IconButton
                                  aria-label={tc('buttons.remove')}
                                  icon={<DeleteIcon />}
                                  size="sm"
                                  colorScheme="red"
                                  variant="ghost"
                                  onClick={() => remove(idx)}
                                  isDisabled={values.lines.length <= 1}
                                />
                              </HStack>
                              <HStack spacing={4}>
                                <Field name={`lines.${idx}.has_detail_dimension`}>
                                  {({ field, form }: FieldProps<boolean>) => (
                                    <Checkbox
                                      size="sm"
                                      isChecked={field.value}
                                      onChange={(e) => {
                                        form.setFieldValue(`lines.${idx}.has_detail_dimension`, e.target.checked);
                                        form.setFieldValue(`lines.${idx}.dimension_type`, e.target.checked ? 'platform' : null);
                                      }}
                                      color="white"
                                    >
                                      {t('labels.detailDimension')}
                                    </Checkbox>
                                  )}
                                </Field>
                                {values.lines[idx]?.has_detail_dimension && (
                                  <Field name={`lines.${idx}.dimension_type`}>
                                    {({ field, meta }: FieldProps<string>) => (
                                      <>
                                        <Select {...field} size="sm" w="180px" bg="gray.600" color="white">
                                          <option value="platform">Platform</option>
                                          <option value="ReferenceNumber">{t('labels.referenceNumber')}</option>
                                        </Select>
                                        {meta.touched && meta.error && (
                                          <Text color="red.300" fontSize="xs">{meta.error}</Text>
                                        )}
                                      </>
                                    )}
                                  </Field>
                                )}
                              </HStack>
                            </Box>
                          ))}
                          <Button
                            size="sm"
                            leftIcon={<AddIcon />}
                            variant="outline"
                            onClick={() => push({ ...EMPTY_LINE })}
                            color="white"
                          >
                            {t('buttons.addTemplateLine')}
                          </Button>
                        </VStack>
                      )}
                    </FieldArray>
                  </Box>
                </VStack>
              </ModalBody>

              <ModalFooter>
                <HStack spacing={2}>
                  {editingId && (
                    <Button
                      colorScheme="red"
                      variant="outline"
                      onClick={onDelete}
                      isLoading={isSubmitting}
                    >
                      {tc('buttons.delete')}
                    </Button>
                  )}
                  <Button variant="ghost" onClick={onClose} color="white">
                    {tc('buttons.cancel')}
                  </Button>
                  <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                    {tc('buttons.save')}
                  </Button>
                </HStack>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};

export default BudgetTemplateFormModal;
