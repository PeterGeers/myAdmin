/**
 * AI Help Button Component
 * 
 * Provides AI-powered assistance for fixing template validation errors.
 * Displays suggestions in a modal with options to apply fixes.
 */

import React, { useState } from 'react';
import {
  Box,
  Button,
  VStack,
  HStack,
  Text,
  Badge,
  Code,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  useDisclosure,
  Alert,
  AlertIcon,
  AlertDescription,
  Divider,
  Checkbox,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Spinner,
} from '@chakra-ui/react';
import type { AIHelpResponse, AIFixSuggestion } from '../../../services/templateApi';

/**
 * Component props
 */
interface AIHelpButtonProps {
  onRequestHelp: () => Promise<void>;
  onApplyFixes: (fixes: AIFixSuggestion[]) => Promise<void>;
  aiSuggestions: AIHelpResponse | null;
  hasErrors: boolean;
  loading?: boolean;
  disabled?: boolean;
}

/**
 * AIHelpButton Component
 */
export const AIHelpButton: React.FC<AIHelpButtonProps> = ({
  onRequestHelp,
  onApplyFixes,
  aiSuggestions,
  hasErrors,
  loading = false,
  disabled = false,
}) => {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [selectedFixes, setSelectedFixes] = useState<Set<number>>(new Set());
  const [applyingFixes, setApplyingFixes] = useState(false);

  /**
   * Handle AI help request
   */
  const handleRequestHelp = async () => {
    await onRequestHelp();
    onOpen();
  };

  /**
   * Toggle fix selection
   */
  const toggleFix = (index: number) => {
    const newSelected = new Set(selectedFixes);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedFixes(newSelected);
  };

  /**
   * Select all auto-fixable fixes
   */
  const selectAllAutoFixable = () => {
    if (!aiSuggestions?.ai_suggestions?.fixes) return;
    
    const autoFixableIndices = aiSuggestions.ai_suggestions.fixes
      .map((fix, index) => (fix.auto_fixable ? index : -1))
      .filter((index) => index !== -1);
    
    setSelectedFixes(new Set(autoFixableIndices));
  };

  /**
   * Apply selected fixes
   */
  const handleApplySelectedFixes = async () => {
    if (!aiSuggestions?.ai_suggestions?.fixes) return;
    
    const fixesToApply = Array.from(selectedFixes)
      .map((index) => aiSuggestions.ai_suggestions!.fixes[index])
      .filter(Boolean);
    
    if (fixesToApply.length === 0) return;
    
    setApplyingFixes(true);
    try {
      await onApplyFixes(fixesToApply);
      onClose();
      setSelectedFixes(new Set());
    } finally {
      setApplyingFixes(false);
    }
  };

  /**
   * Get confidence color
   */
  const getConfidenceColor = (confidence: string): string => {
    switch (confidence) {
      case 'high':
        return 'green';
      case 'medium':
        return 'yellow';
      case 'low':
        return 'red';
      default:
        return 'gray';
    }
  };

  const fixes = aiSuggestions?.ai_suggestions?.fixes || [];
  const hasAutoFixable = fixes.some((fix) => fix.auto_fixable);

  return (
    <>
      {/* AI Help Button */}
      <Button
        leftIcon={<span>🤖</span>}
        colorScheme="blue"
        onClick={handleRequestHelp}
        isLoading={loading}
        isDisabled={disabled || !hasErrors}
        loadingText="Analyzing..."
        w="100%"
      >
        Get AI Help
      </Button>

      {/* AI Suggestions Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="xl" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent bg="brand.gray" maxH="90vh">
          <ModalHeader>
            <HStack spacing={2}>
              <Text>🤖 AI Template Assistant</Text>
              {aiSuggestions?.fallback && (
                <Badge colorScheme="yellow" fontSize="xs">
                  Fallback Mode
                </Badge>
              )}
            </HStack>
          </ModalHeader>
          <ModalCloseButton />
          
          <ModalBody>
            <VStack spacing={4} align="stretch">
              {/* Loading State */}
              {loading && (
                <Box textAlign="center" py={8}>
                  <Spinner size="xl" color="blue.400" mb={4} />
                  <Text>Analyzing your template...</Text>
                  <Text fontSize="sm" color="gray.400" mt={2}>
                    This may take a few seconds
                  </Text>
                </Box>
              )}

              {/* AI Unavailable */}
              {!loading && aiSuggestions?.fallback && (
                <Alert status="warning" bg="yellow.900" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    AI service is currently unavailable. Showing generic help instead.
                  </AlertDescription>
                </Alert>
              )}

              {/* Analysis Text */}
              {!loading && aiSuggestions?.ai_suggestions && (
                <>
                  <Box bg="blue.900" p={4} borderRadius="md">
                    <Text fontWeight="bold" mb={2}>
                      📊 Analysis
                    </Text>
                    <Text fontSize="sm" color="gray.200">
                      {aiSuggestions.ai_suggestions.analysis}
                    </Text>
                  </Box>

                  {/* Usage Stats */}
                  {aiSuggestions.tokens_used && (
                    <HStack spacing={4} fontSize="xs" color="gray.500">
                      <Text>Tokens: {aiSuggestions.tokens_used}</Text>
                      {aiSuggestions.cost_estimate && (
                        <Text>Cost: ${aiSuggestions.cost_estimate.toFixed(4)}</Text>
                      )}
                    </HStack>
                  )}

                  <Divider borderColor="gray.700" />

                  {/* Fixes List */}
                  {fixes.length > 0 && (
                    <>
                      <HStack justify="space-between">
                        <Text fontWeight="bold">
                          🔧 Suggested Fixes ({fixes.length})
                        </Text>
                        {hasAutoFixable && (
                          <Button
                            size="xs"
                            variant="ghost"
                            onClick={selectAllAutoFixable}
                          >
                            Select All Auto-Fixable
                          </Button>
                        )}
                      </HStack>

                      <Accordion allowMultiple defaultIndex={[0]}>
                        {fixes.map((fix, index) => (
                          <AccordionItem key={index} border="1px solid" borderColor="gray.700" borderRadius="md" mb={2}>
                            <AccordionButton _hover={{ bg: 'gray.800' }}>
                              <HStack flex={1} spacing={3}>
                                <Checkbox
                                  isChecked={selectedFixes.has(index)}
                                  onChange={() => toggleFix(index)}
                                  onClick={(e) => e.stopPropagation()}
                                  isDisabled={!fix.auto_fixable}
                                />
                                <VStack align="start" spacing={0} flex={1}>
                                  <Text fontSize="sm" fontWeight="medium">
                                    {fix.issue}
                                  </Text>
                                  <HStack spacing={2}>
                                    <Badge
                                      colorScheme={getConfidenceColor(fix.confidence)}
                                      fontSize="xs"
                                    >
                                      {fix.confidence} confidence
                                    </Badge>
                                    {fix.auto_fixable && (
                                      <Badge colorScheme="green" fontSize="xs">
                                        Auto-fixable
                                      </Badge>
                                    )}
                                  </HStack>
                                </VStack>
                              </HStack>
                              <AccordionIcon />
                            </AccordionButton>
                            <AccordionPanel pb={4} bg="gray.800">
                              <VStack align="stretch" spacing={3}>
                                {/* Suggestion */}
                                <Box>
                                  <Text fontSize="xs" fontWeight="bold" mb={1} color="gray.400">
                                    Suggestion:
                                  </Text>
                                  <Text fontSize="sm">{fix.suggestion}</Text>
                                </Box>

                                {/* Code Example */}
                                {fix.code_example && (
                                  <Box>
                                    <Text fontSize="xs" fontWeight="bold" mb={1} color="gray.400">
                                      Code Example:
                                    </Text>
                                    <Code
                                      display="block"
                                      whiteSpace="pre-wrap"
                                      p={2}
                                      bg="gray.900"
                                      borderRadius="md"
                                      fontSize="xs"
                                    >
                                      {fix.code_example}
                                    </Code>
                                  </Box>
                                )}

                                {/* Location */}
                                {fix.location && (
                                  <Text fontSize="xs" color="gray.500">
                                    Location: {fix.location}
                                  </Text>
                                )}
                              </VStack>
                            </AccordionPanel>
                          </AccordionItem>
                        ))}
                      </Accordion>
                    </>
                  )}

                  {/* No Fixes */}
                  {fixes.length === 0 && (
                    <Alert status="info" bg="blue.900" borderRadius="md">
                      <AlertIcon />
                      <AlertDescription fontSize="sm">
                        No automatic fixes available. Please review the validation errors manually.
                      </AlertDescription>
                    </Alert>
                  )}
                </>
              )}

              {/* No Suggestions Yet */}
              {!loading && !aiSuggestions && (
                <Box textAlign="center" py={8}>
                  <Text color="gray.500">
                    Click "Get AI Help" to analyze your template
                  </Text>
                </Box>
              )}
            </VStack>
          </ModalBody>

          <ModalFooter>
            <HStack spacing={3}>
              <Button variant="ghost" onClick={onClose}>
                Close
              </Button>
              {fixes.length > 0 && selectedFixes.size > 0 && (
                <Button
                  colorScheme="blue"
                  onClick={handleApplySelectedFixes}
                  isLoading={applyingFixes}
                  loadingText="Applying..."
                >
                  Apply {selectedFixes.size} Fix{selectedFixes.size !== 1 ? 'es' : ''}
                </Button>
              )}
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </>
  );
};

export default AIHelpButton;
