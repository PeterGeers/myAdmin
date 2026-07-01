/**
 * BudgetLineModal — Formik + Yup modal for creating/editing budget lines.
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack, HStack, Box,
  Input, Select, Button, FormControl, FormLabel, FormErrorMessage,
  SimpleGrid, Text,
} from '@chakra-ui/react';
import { Formik, Form, Field, FieldArray, FieldProps } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { BudgetLine, PeriodMode, DimensionType } from '../types/budget';

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

const lineSchema = Yup.object({
  account_code: Yup.string().required('Account code is required'),
  period_mode: Yup.string().oneOf(['Monthly', 'Annual']).required(),
  amounts: Yup.array().of(Yup.number()).when('period_mode', {
    is: 'Monthly',
    then: (schema) => schema.length(12),
  }),
  annual_amount: Yup.number().when('period_mode', {
    is: 'Annual',
    then: (schema) => schema.required().min(0),
  }),
  dimension_type: Yup.string().nullable(),
  dimension_value: Yup.string().nullable(),
});

interface BudgetLineModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingLine: BudgetLine | null;
  initialValues: {
    account_code: string;
    period_mode: PeriodMode;
    amounts: number[];
    annual_amount: number;
    dimension_type: string;
    dimension_value: string;
  };
  onSave: (values: {
    account_code: string;
    period_mode: PeriodMode;
    amounts: number[];
    annual_amount: number;
    dimension_type: string;
    dimension_value: string;
  }) => Promise<void>;
  onDelete: () => Promise<void>;
}

const BudgetLineModal: React.FC<BudgetLineModalProps> = ({
  isOpen, onClose, editingLine, initialValues, onSave, onDelete,
}) => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent maxW="700px" bg="gray.800" color="white">
        <ModalHeader>
          {editingLine ? t('labels.accountCode') + ' — ' + editingLine.account_code : t('buttons.addLine')}
        </ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={lineSchema}
          enableReinitialize
          onSubmit={async (values, { setSubmitting }) => {
            try {
              await onSave(values);
            } finally {
              setSubmitting(false);
            }
          }}
        >
          {({ values, isSubmitting, setFieldValue }) => (
            <Form>
              <ModalBody>
                <VStack spacing={4} align="stretch">
                  <HStack spacing={4}>
                    <Field name="account_code">
                      {({ field, meta }: FieldProps<string>) => (
                        <FormControl flex="2" isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel>{t('labels.accountCode')}</FormLabel>
                          <Input {...field} placeholder="e.g. 4000" />
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                    <Field name="period_mode">
                      {({ field, meta }: FieldProps<string>) => (
                        <FormControl flex="1" isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel>{t('labels.periodMode')}</FormLabel>
                          <Select {...field}>
                            <option value="Monthly">{t('labels.monthly')}</option>
                            <option value="Annual">{t('labels.annual')}</option>
                          </Select>
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                  </HStack>

                  {/* Monthly amounts */}
                  {values.period_mode === 'Monthly' && (
                    <Box>
                      <Text fontWeight="semibold" mb={2}>{t('labels.monthlyAmounts')}</Text>
                      <FieldArray name="amounts">
                        {() => (
                          <SimpleGrid columns={{ base: 3, md: 4, lg: 6 }} spacing={2}>
                            {MONTH_LABELS.map((label, idx) => (
                              <FormControl key={idx}>
                                <FormLabel fontSize="xs">{label}</FormLabel>
                                <Input
                                  size="sm"
                                  type="number"
                                  step="0.01"
                                  value={values.amounts[idx]}
                                  onChange={(e) => setFieldValue(`amounts.${idx}`, parseFloat(e.target.value) || 0)}
                                />
                              </FormControl>
                            ))}
                          </SimpleGrid>
                        )}
                      </FieldArray>
                    </Box>
                  )}

                  {/* Annual amount */}
                  {values.period_mode === 'Annual' && (
                    <Field name="annual_amount">
                      {({ field, meta }: FieldProps<string>) => (
                        <FormControl isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel>{t('labels.annualAmount')}</FormLabel>
                          <Input
                            {...field}
                            type="number"
                            step="0.01"
                            onChange={(e) => setFieldValue('annual_amount', parseFloat(e.target.value) || 0)}
                            placeholder="Total annual amount (divided by 12)"
                          />
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                  )}

                  {/* Dimension */}
                  <HStack spacing={4}>
                    <Field name="dimension_type">
                      {({ field }: FieldProps<string>) => (
                        <FormControl flex="1">
                          <FormLabel>{t('labels.dimensionType')} ({tc('labels.optional')})</FormLabel>
                          <Select {...field}>
                            <option value="">None</option>
                            <option value="platform">Platform</option>
                            <option value="ReferenceNumber">{t('labels.referenceNumber')}</option>
                          </Select>
                        </FormControl>
                      )}
                    </Field>
                    {values.dimension_type && (
                      <Field name="dimension_value">
                        {({ field }: FieldProps<string>) => (
                          <FormControl flex="1">
                            <FormLabel>{t('labels.dimensionValue')}</FormLabel>
                            <Input
                              {...field}
                              placeholder={values.dimension_type === 'platform' ? 'e.g. Airbnb' : 'e.g. REF001'}
                            />
                          </FormControl>
                        )}
                      </Field>
                    )}
                  </HStack>
                </VStack>
              </ModalBody>
              <ModalFooter>
                <HStack spacing={2}>
                  {editingLine && (
                    <Button colorScheme="red" variant="outline" onClick={onDelete} isLoading={isSubmitting}>
                      {tc('buttons.delete')}
                    </Button>
                  )}
                  <Button variant="ghost" onClick={onClose}>
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

export default BudgetLineModal;
