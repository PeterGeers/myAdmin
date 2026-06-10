/**
 * BankingPatternPanel Component
 *
 * Extracted from BankingProcessor — manages pattern matching UI including:
 * - Pattern application trigger (calls backend to apply patterns to transactions)
 * - Pattern approval/rejection dialog
 * - Pattern results display (confidence scores, prediction counts)
 * - Save confirmation dialog with pattern summary
 *
 * The parent BankingProcessor remains responsible for overall state coordination;
 * this component receives transaction data and callbacks via props.
 *
 * @module BankingPatternPanel
 */

import React from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Grid,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Text,
  VStack,
} from '@chakra-ui/react';
import type { Transaction } from './BankingProcessor';
import type { PatternResults } from './BankingProcessorTable';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PatternSuggestions {
  patterns_found: number;
  predictions_made: {
    debet: number;
    credit: number;
    reference: number;
  };
  confidence_scores: number[];
  average_confidence: number;
  enhanced_results?: unknown;
}

export interface BankingPatternPanelProps {
  /** Current transactions (used for save confirmation count) */
  transactions: Transaction[];
  /** Whether the component is in a loading state */
  loading: boolean;
  /** Pattern results after applying patterns (null if not applied yet) */
  patternResults: PatternResults | null;
  /** Pattern suggestion data for the approval dialog */
  patternSuggestions: PatternSuggestions | null;
  /** Whether the pattern approval dialog is open */
  showPatternApproval: boolean;
  /** Whether the save confirmation dialog is open */
  showSaveConfirmation: boolean;
  /** Callback to approve pattern suggestions */
  onApprovePatterns: () => void;
  /** Callback to reject pattern suggestions */
  onRejectPatterns: () => void;
  /** Callback to close the pattern approval dialog */
  onClosePatternApproval: () => void;
  /** Callback to confirm saving transactions */
  onConfirmSave: () => void;
  /** Callback to close the save confirmation dialog */
  onCloseSaveConfirmation: () => void;
  /** Translation function */
  t: (key: string, options?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BankingPatternPanel: React.FC<BankingPatternPanelProps> = ({
  transactions,
  loading,
  patternResults,
  patternSuggestions,
  showPatternApproval,
  showSaveConfirmation,
  onApprovePatterns,
  onRejectPatterns,
  onClosePatternApproval,
  onConfirmSave,
  onCloseSaveConfirmation,
  t,
}) => {
  return (
    <>
      {/* REQ-UI-004: Confirmation Dialog for Save to Database */}
      <Modal isOpen={showSaveConfirmation} onClose={onCloseSaveConfirmation} size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>{t('labels.confirmSaveToDatabase')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack align="stretch" spacing={4}>
              <Text>
                {t('labels.aboutToSave')} <strong>{transactions.length} {t('labels.transactionsToDatabase')}</strong>.
              </Text>

              {patternResults && (
                <Box bg="blue.50" p={4} borderRadius="md" borderColor="blue.200" borderWidth="1px">
                  <Text fontSize="sm" fontWeight="bold" mb={2}>{t('labels.patternApplicationSummary')}:</Text>
                  <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                    <Text fontSize="sm">{t('labels.debetPredictions')}: {patternResults.predictions_made?.debet || 0}</Text>
                    <Text fontSize="sm">{t('labels.creditPredictions')}: {patternResults.predictions_made?.credit || 0}</Text>
                    <Text fontSize="sm">{t('labels.referencePredictions')}: {patternResults.predictions_made?.reference || 0}</Text>
                    <Text fontSize="sm">{t('labels.avgConfidence')}: {(patternResults.average_confidence * 100).toFixed(1)}%</Text>
                  </Grid>
                </Box>
              )}

              <Text fontSize="sm" color="gray.600">
                {t('labels.cannotBeUndone')}
              </Text>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button colorScheme="gray" mr={3} onClick={onCloseSaveConfirmation}>
              {t('labels.cancel')}
            </Button>
            <Button colorScheme="green" onClick={onConfirmSave} isLoading={loading}>
              {t('labels.confirmSave')}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Pattern Approval Dialog - REQ-UI-006: Show pattern suggestions with confidence scores */}
      <Modal isOpen={showPatternApproval} onClose={onClosePatternApproval} size="xl">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>{t('labels.reviewPatternSuggestions')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack align="stretch" spacing={4}>
              <Alert status="info" borderRadius="md">
                <AlertIcon />
                <Box>
                  <Text fontWeight="bold">{t('labels.patternSuggestionsFilled')}</Text>
                  <Text fontSize="sm">
                    {t('labels.reviewBlueHighlighted')}
                  </Text>
                </Box>
              </Alert>

              {patternSuggestions && (
                <Box bg="blue.50" p={4} borderRadius="md" borderColor="blue.200" borderWidth="1px">
                  <Text fontSize="sm" fontWeight="bold" mb={3}>{t('labels.patternAnalysisResults')}:</Text>
                  <Grid templateColumns="repeat(2, 1fr)" gap={4}>
                    <Box>
                      <Text fontSize="sm" color="blue.700">
                        <strong>{t('labels.patternsFound')}:</strong> {patternSuggestions.patterns_found}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>{t('labels.debetSuggestions')}:</strong> {patternSuggestions.predictions_made?.debet || 0}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>{t('labels.creditSuggestions')}:</strong> {patternSuggestions.predictions_made?.credit || 0}
                      </Text>
                    </Box>
                    <Box>
                      <Text fontSize="sm" color="blue.700">
                        <strong>{t('labels.referenceSuggestions')}:</strong> {patternSuggestions.predictions_made?.reference || 0}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>{t('labels.averageConfidence')}:</strong> {(patternSuggestions.average_confidence * 100).toFixed(1)}%
                      </Text>
                      <Text fontSize="xs" color="blue.600" mt={2}>
                        {t('labels.suggestedValuesHighlighted')}
                      </Text>
                    </Box>
                  </Grid>
                </Box>
              )}

              <Box bg="yellow.50" p={3} borderRadius="md" borderColor="yellow.200" borderWidth="1px">
                <Text fontSize="sm" color="yellow.800">
                  <strong>{t('labels.whatHappensNext')}:</strong>
                </Text>
                <Text fontSize="xs" color="yellow.700" mt={1}>
                  • <strong>{t('patternApproval.approve')}:</strong> {t('labels.approveKeepValues')}
                </Text>
                <Text fontSize="xs" color="yellow.700">
                  • <strong>{t('patternApproval.reject')}:</strong> {t('labels.rejectRemoveValues')}
                </Text>
                <Text fontSize="xs" color="yellow.700">
                  • {t('labels.canManuallyEdit')}
                </Text>
              </Box>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button colorScheme="red" mr={3} onClick={onRejectPatterns}>
              {t('labels.rejectSuggestions')}
            </Button>
            <Button colorScheme="green" onClick={onApprovePatterns}>
              {t('labels.approveSuggestions')}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </>
  );
};

export default BankingPatternPanel;
