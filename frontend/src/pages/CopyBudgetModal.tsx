/**
 * CopyBudgetModal — Formik + Yup modal for copying a budget version.
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack,
  Input, Select, Button, FormControl, FormLabel, FormErrorMessage,
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { BudgetVersion } from '../types/budget';

const copyBudgetSchema = Yup.object({
  source_version_id: Yup.number().required('Source version is required').positive(),
  target_fiscal_year: Yup.number().required('Target year is required').min(2000).max(2100),
  version_name: Yup.string().required('Version name is required').max(100),
});

interface CopyBudgetModalProps {
  isOpen: boolean;
  onClose: () => void;
  versions: BudgetVersion[];
  initialValues: {
    source_version_id: number;
    target_fiscal_year: number;
    version_name: string;
  };
  onCopy: (values: { source_version_id: number; target_fiscal_year: number; version_name: string }) => Promise<void>;
}

const CopyBudgetModal: React.FC<CopyBudgetModalProps> = ({
  isOpen, onClose, versions, initialValues, onCopy,
}) => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{t('buttons.copyBudget')}</ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={copyBudgetSchema}
          enableReinitialize
          onSubmit={async (values, { setSubmitting }) => {
            try {
              await onCopy(values);
            } finally {
              setSubmitting(false);
            }
          }}
        >
          {({ isSubmitting, setFieldValue }) => (
            <Form>
              <ModalBody>
                <VStack spacing={4}>
                  <Field name="source_version_id">
                    {({ field, meta }: any) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.sourceVersion')}</FormLabel>
                        <Select
                          value={field.value || ''}
                          onChange={(e) => setFieldValue('source_version_id', Number(e.target.value))}
                        >
                          {versions.map((v) => (
                            <option key={v.id} value={v.id}>{v.name} ({v.fiscal_year})</option>
                          ))}
                        </Select>
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>
                  <Field name="target_fiscal_year">
                    {({ field, meta }: any) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.targetYear')}</FormLabel>
                        <Input
                          type="number"
                          {...field}
                          onChange={(e) => setFieldValue('target_fiscal_year', Number(e.target.value))}
                          min={2000}
                          max={2100}
                        />
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>
                  <Field name="version_name">
                    {({ field, meta }: any) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.versionName')}</FormLabel>
                        <Input
                          {...field}
                          placeholder="e.g. Copy of 2025 Approved"
                          maxLength={100}
                        />
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>
                </VStack>
              </ModalBody>
              <ModalFooter>
                <Button variant="ghost" mr={3} onClick={onClose}>
                  {tc('buttons.cancel')}
                </Button>
                <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                  {t('buttons.copyBudget')}
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};

export default CopyBudgetModal;
