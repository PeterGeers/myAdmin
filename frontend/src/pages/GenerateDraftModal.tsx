/**
 * GenerateDraftModal — Formik + Yup modal for generating budget drafts from templates.
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
import { BudgetTemplate } from '../types/budget';

const generateDraftSchema = Yup.object({
  template_id: Yup.number().required('Template is required').positive('Select a template'),
  fiscal_year: Yup.number().required('Fiscal year is required').min(2000).max(2100),
  version_name: Yup.string().required('Version name is required').max(100),
});

interface GenerateDraftModalProps {
  isOpen: boolean;
  onClose: () => void;
  templates: BudgetTemplate[];
  initialValues: {
    template_id: number;
    fiscal_year: number;
    version_name: string;
  };
  onGenerate: (values: { template_id: number; fiscal_year: number; version_name: string }) => Promise<void>;
}

const GenerateDraftModal: React.FC<GenerateDraftModalProps> = ({
  isOpen, onClose, templates, initialValues, onGenerate,
}) => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{t('buttons.generateDraft')}</ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={generateDraftSchema}
          enableReinitialize
          onSubmit={async (values, { setSubmitting }) => {
            try {
              await onGenerate(values);
            } finally {
              setSubmitting(false);
            }
          }}
        >
          {({ isSubmitting, setFieldValue }) => (
            <Form>
              <ModalBody>
                <VStack spacing={4}>
                  <Field name="template_id">
                    {({ field, meta }: any) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.template')}</FormLabel>
                        <Select
                          placeholder={t('messages.selectTemplate')}
                          value={field.value || ''}
                          onChange={(e) => setFieldValue('template_id', Number(e.target.value))}
                        >
                          {templates.map((tmpl) => (
                            <option key={tmpl.id} value={tmpl.id}>{tmpl.name}</option>
                          ))}
                        </Select>
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>
                  <Field name="fiscal_year">
                    {({ field, meta }: any) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.fiscalYear')}</FormLabel>
                        <Input
                          type="number"
                          {...field}
                          onChange={(e) => setFieldValue('fiscal_year', Number(e.target.value))}
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
                          placeholder="e.g. Draft from Actuals 2024"
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
                  {tc('buttons.generate')}
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};

export default GenerateDraftModal;
