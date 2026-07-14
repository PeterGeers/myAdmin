/**
 * BudgetNewVersionModal — Create a new budget version with method selection.
 *
 * Options: Empty / Copy from existing / AI Draft
 * When "Copy" is selected: shows version dropdown to copy from.
 * When "AI Draft" is selected: shows context notes, calls AI to generate proposed lines,
 * then creates the version and saves accepted lines.
 */

import React, { useState } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack, Box,
  Input, Select, Button, FormControl, FormLabel, FormErrorMessage,
  Textarea, useToast, RadioGroup, Radio, Text, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Checkbox, Badge,
} from '@chakra-ui/react';
import { Formik, Field, FieldProps } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { BudgetVersion, DimensionType } from '../types/budget';
import { createVersion, copyBudget, createLine } from '../services/budgetService';
import { authenticatedPost } from '../services/apiService';

interface ProposedLine {
  account_code: string;
  account_name?: string;
  period_mode: string;
  detail_dimension_type?: string | null;
  detail_dimension_value?: string | null;
  amounts: number[];
  reasoning?: string;
  selected: boolean;
}

const createVersionSchema = Yup.object({
  name: Yup.string().required('Name is required').max(100),
  fiscal_year: Yup.number().required('Fiscal year is required').min(2000).max(2099),
  method: Yup.string().oneOf(['empty', 'copy', 'ai']).required(),
  source_version_id: Yup.number().when('method', {
    is: 'copy',
    then: (schema) => schema.required('Select a version to copy from').min(1),
  }),
  context_notes: Yup.string(),
});

interface BudgetNewVersionModalProps {
  isOpen: boolean;
  onClose: () => void;
  versions: BudgetVersion[];
  onCreated: (newVersionId: number) => void;
}

const BudgetNewVersionModal: React.FC<BudgetNewVersionModalProps> = ({
  isOpen, onClose, versions, onCreated,
}) => {
  const { t } = useTypedTranslation('budget');
  const { t: tc } = useTypedTranslation('common');
  const toast = useToast();
  const [submitting, setSubmitting] = useState(false);

  // AI Draft state
  const [aiLoading, setAiLoading] = useState(false);
  const [proposedLines, setProposedLines] = useState<ProposedLine[]>([]);
  const [aiGenerated, setAiGenerated] = useState(false);

  const initialValues = {
    name: '',
    fiscal_year: new Date().getFullYear() + 1,
    method: 'empty',
    source_version_id: 0,
    context_notes: '',
  };

  const handleGenerateAI = async (fiscalYear: number, contextNotes: string) => {
    try {
      setAiLoading(true);
      setProposedLines([]);
      const response = await authenticatedPost('/api/budget/ai/generate-lines', {
        fiscal_year: fiscalYear,
        context_notes: contextNotes,
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'AI generation failed');
      }
      const result = await response.json();
      if (result.success && result.data?.proposed_lines) {
        setProposedLines(
          result.data.proposed_lines.map((line: any) => ({ ...line, selected: true }))
        );
        setAiGenerated(true);
      } else {
        toast({ title: result.error || 'No lines generated', status: 'warning', duration: 4000 });
      }
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    } finally {
      setAiLoading(false);
    }
  };

  const toggleLine = (idx: number) => {
    setProposedLines((prev) =>
      prev.map((line, i) => i === idx ? { ...line, selected: !line.selected } : line)
    );
  };

  const handleSubmit = async (values: typeof initialValues) => {
    setSubmitting(true);
    try {
      if (values.method === 'copy' && values.source_version_id) {
        const resp = await copyBudget({
          source_version_id: values.source_version_id,
          target_fiscal_year: values.fiscal_year,
          version_name: values.name,
        });
        if (resp.success) {
          toast({ title: t('messages.budgetCopied'), status: 'success', duration: 3000 });
          onCreated(resp.data.version_id);
        }
      } else if (values.method === 'ai' && aiGenerated) {
        // Create empty version first, then add selected AI lines
        const versionResp = await createVersion({
          name: values.name,
          fiscal_year: values.fiscal_year,
        });
        if (versionResp.success) {
          const newId = versionResp.data.id;
          const selectedLines = proposedLines.filter((l) => l.selected);

          // Save each selected line
          for (const line of selectedLines) {
            try {
              await createLine(newId, {
                account_code: line.account_code,
                period_mode: 'Monthly',
                amounts: line.amounts as [number, number, number, number, number, number, number, number, number, number, number, number],
                detail_dimension_type: (line.detail_dimension_type || null) as DimensionType | null,
                detail_dimension_value: line.detail_dimension_value || null,
                notes: line.reasoning || null,
              });
            } catch {
              // Skip lines that fail (e.g. duplicate)
            }
          }

          toast({
            title: t('messages.versionCreated'),
            description: `${selectedLines.length} lines added`,
            status: 'success',
            duration: 3000,
          });
          onCreated(newId);
        }
      } else {
        // Create empty version
        const resp = await createVersion({
          name: values.name,
          fiscal_year: values.fiscal_year,
        });
        if (resp.success) {
          toast({ title: t('messages.versionCreated'), status: 'success', duration: 3000 });
          onCreated(resp.data.id);
        }
      }
    } catch (err: any) {
      toast({ title: err.message, status: 'error', duration: 4000 });
    } finally {
      setSubmitting(false);
      setProposedLines([]);
      setAiGenerated(false);
    }
  };

  const handleClose = () => {
    setProposedLines([]);
    setAiGenerated(false);
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size={aiGenerated ? '4xl' : 'md'} closeOnOverlayClick={false} scrollBehavior="inside">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" maxH="85vh">
        <ModalHeader>{t('buttons.createVersion')}</ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={createVersionSchema}
          enableReinitialize
          onSubmit={handleSubmit}
        >
          {({ values, setFieldValue, isValid, handleSubmit: formikSubmit }) => (
            <>
              <ModalBody>
                <VStack spacing={4}>
                  <Field name="name">
                    {({ field, meta }: FieldProps<string>) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.versionName')}</FormLabel>
                        <Input {...field} placeholder="e.g. Budget 2026" />
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>

                  <Field name="fiscal_year">
                    {({ field, meta }: FieldProps<string>) => (
                      <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                        <FormLabel>{t('labels.fiscalYear')}</FormLabel>
                        <Input
                          {...field}
                          type="number"
                          min={2000}
                          max={2099}
                          onChange={(e) => setFieldValue('fiscal_year', parseInt(e.target.value) || 0)}
                        />
                        <FormErrorMessage>{meta.error}</FormErrorMessage>
                      </FormControl>
                    )}
                  </Field>

                  <FormControl>
                    <FormLabel>Method</FormLabel>
                    <RadioGroup
                      value={values.method}
                      onChange={(val) => { setFieldValue('method', val); setAiGenerated(false); setProposedLines([]); }}
                    >
                      <VStack align="start" spacing={2}>
                        <Radio value="empty" colorScheme="orange">Empty (start from scratch)</Radio>
                        <Radio value="copy" colorScheme="orange">Copy from existing version</Radio>
                        <Radio value="ai" colorScheme="orange">AI Draft (generate from prior-year actuals)</Radio>
                      </VStack>
                    </RadioGroup>
                  </FormControl>

                  {/* Copy: version selector */}
                  {values.method === 'copy' && (
                    <Field name="source_version_id">
                      {({ meta }: any) => (
                        <FormControl isRequired isInvalid={!!(meta.touched && meta.error)}>
                          <FormLabel>{t('labels.sourceVersion')}</FormLabel>
                          <Select
                            placeholder="Select version..."
                            value={values.source_version_id || ''}
                            onChange={(e) => setFieldValue('source_version_id', Number(e.target.value))}
                          >
                            {versions.map((v) => (
                              <option key={v.id} value={v.id}>
                                {v.name} ({v.fiscal_year}) — {v.status}
                              </option>
                            ))}
                          </Select>
                          <FormErrorMessage>{meta.error}</FormErrorMessage>
                        </FormControl>
                      )}
                    </Field>
                  )}

                  {/* AI Draft: context notes + generate button */}
                  {values.method === 'ai' && (
                    <>
                      <FormControl>
                        <FormLabel>{t('labels.contextNotes')}</FormLabel>
                        <Textarea
                          bg="gray.700"
                          placeholder="e.g. Rent increases 5% in June, drop Booking.com platform"
                          value={values.context_notes}
                          onChange={(e) => setFieldValue('context_notes', e.target.value)}
                          rows={3}
                        />
                      </FormControl>

                      {!aiGenerated && (
                        <Button
                          colorScheme="orange"
                          variant="outline"
                          size="sm"
                          isLoading={aiLoading}
                          onClick={() => handleGenerateAI(values.fiscal_year, values.context_notes || '')}
                        >
                          Generate AI Proposal
                        </Button>
                      )}

                      {aiLoading && (
                        <Box textAlign="center" py={4}>
                          <Spinner color="orange.300" />
                          <Text fontSize="sm" color="gray.400" mt={2}>Generating budget lines...</Text>
                        </Box>
                      )}

                      {/* Proposed lines review table */}
                      {aiGenerated && proposedLines.length > 0 && (
                        <Box overflowX="auto" w="100%">
                          <Text fontSize="sm" color="gray.300" mb={2}>
                            {proposedLines.filter((l) => l.selected).length} / {proposedLines.length} lines selected
                          </Text>
                          <Table size="sm" variant="simple" bg="gray.800">
                            <Thead>
                              <Tr>
                                <Th bg="gray.700" color="gray.300" w="40px">✓</Th>
                                <Th bg="gray.700" color="gray.300">Account</Th>
                                <Th bg="gray.700" color="gray.300">Name</Th>
                                <Th bg="gray.700" color="gray.300" isNumeric>Total</Th>
                                <Th bg="gray.700" color="gray.300">Reasoning</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {proposedLines.map((line, idx) => (
                                <Tr key={idx} opacity={line.selected ? 1 : 0.5}
                                  _hover={{ bg: 'gray.700' }}>
                                  <Td>
                                    <Checkbox
                                      isChecked={line.selected}
                                      onChange={() => toggleLine(idx)}
                                      colorScheme="orange"
                                    />
                                  </Td>
                                  <Td>{line.account_code}</Td>
                                  <Td>{line.account_name || '—'}</Td>
                                  <Td isNumeric>
                                    {line.amounts.reduce((a, b) => a + b, 0).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                                  </Td>
                                  <Td>
                                    <Text fontSize="xs" color="gray.400" noOfLines={2}>{line.reasoning || ''}</Text>
                                  </Td>
                                </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </Box>
                      )}

                      {aiGenerated && proposedLines.length === 0 && (
                        <Text color="gray.400" fontSize="sm">No lines were proposed by AI. You can create an empty version and add lines manually.</Text>
                      )}
                    </>
                  )}
                </VStack>
              </ModalBody>
              <ModalFooter>
                <Button variant="ghost" mr={3} onClick={handleClose} color="white">
                  {tc('buttons.cancel')}
                </Button>
                <Button
                  colorScheme="orange"
                  isLoading={submitting}
                  isDisabled={values.method === 'ai' && !aiGenerated && !aiLoading ? true : !isValid}
                  onClick={() => formikSubmit()}
                >
                  {values.method === 'ai' && aiGenerated
                    ? `Create with ${proposedLines.filter((l) => l.selected).length} lines`
                    : tc('buttons.create')}
                </Button>
              </ModalFooter>
            </>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};

export default BudgetNewVersionModal;
