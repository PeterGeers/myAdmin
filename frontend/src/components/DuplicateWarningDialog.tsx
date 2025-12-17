import {
    Alert,
    AlertDescription,
    AlertIcon,
    AlertTitle,
    Badge,
    Box,
    Button,
    Divider,
    HStack,
    Modal,
    ModalBody,
    ModalCloseButton,
    ModalContent,
    ModalFooter,
    ModalHeader,
    ModalOverlay,
    Spinner,
    Table,
    TableContainer,
    Tbody,
    Td,
    Text,
    Th,
    Thead,
    Tr,
    VStack,
    useColorModeValue
} from '@chakra-ui/react';
import React from 'react';

interface Transaction {
  id: string;
  transactionDate: string;
  transactionDescription: string;
  transactionAmount: number;
  debet: string;
  credit: string;
  referenceNumber: string;
  ref1?: string;
  ref2?: string;
  ref3?: string; // File URL
  ref4?: string;
}

interface DuplicateWarningProps {
  isOpen: boolean;
  duplicateInfo: {
    existingTransaction: Transaction;
    newTransaction: Transaction;
    matchCount: number;
  };
  onContinue: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

const DuplicateWarningDialog: React.FC<DuplicateWarningProps> = ({
  isOpen,
  duplicateInfo,
  onContinue,
  onCancel,
  isLoading = false
}) => {
  // Use consistent colors with myAdmin theme
  const bgColor = useColorModeValue('white', '#1a1a1a');
  const textColor = useColorModeValue('black', 'white');
  const borderColor = useColorModeValue('gray.200', 'gray.600');
  
  const formatAmount = (amount: number): string => {
    return `€${Number(amount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleDateString('nl-NL');
    } catch {
      return dateString;
    }
  };

  const renderTransactionRow = (label: string, field: keyof Transaction, existing: Transaction, newTx: Transaction) => {
    const existingValue = existing[field];
    const newValue = newTx[field];
    const isMatch = existingValue === newValue;
    
    return (
      <Tr key={field}>
        <Td color={textColor} fontSize="sm" fontWeight="medium" width="120px">
          {label}
        </Td>
        <Td color={textColor} fontSize="sm" width="200px">
          {field === 'transactionAmount' && typeof existingValue === 'number' 
            ? formatAmount(existingValue)
            : field === 'transactionDate' && typeof existingValue === 'string'
            ? formatDate(existingValue)
            : String(existingValue || 'N/A')}
        </Td>
        <Td color={textColor} fontSize="sm" width="200px">
          {field === 'transactionAmount' && typeof newValue === 'number'
            ? formatAmount(newValue)
            : field === 'transactionDate' && typeof newValue === 'string'
            ? formatDate(newValue)
            : String(newValue || 'N/A')}
        </Td>
        <Td width="80px" textAlign="center">
          <Badge 
            colorScheme={isMatch ? "red" : "green"} 
            variant="solid"
            fontSize="xs"
          >
            {isMatch ? "MATCH" : "DIFF"}
          </Badge>
        </Td>
      </Tr>
    );
  };

  if (!duplicateInfo) {
    return null;
  }

  const { existingTransaction, newTransaction, matchCount } = duplicateInfo;

  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onCancel} 
      size="6xl" 
      closeOnOverlayClick={false}
      closeOnEsc={!isLoading}
    >
      <ModalOverlay bg="blackAlpha.600" />
      <ModalContent 
        bg={bgColor} 
        color={textColor}
        maxW="90vw"
        maxH="90vh"
        overflow="hidden"
      >
        <ModalHeader 
          bg="red.500" 
          color="white" 
          fontSize="lg" 
          fontWeight="bold"
          py={3}
        >
          ⚠️ Duplicate Invoice Detected
        </ModalHeader>
        
        {!isLoading && <ModalCloseButton color="white" />}
        
        <ModalBody py={4} overflow="auto">
          <VStack spacing={4} align="stretch">
            {/* Alert Section */}
            <Alert status="warning" borderRadius="md">
              <AlertIcon />
              <Box>
                <AlertTitle fontSize="md">Potential Duplicate Found!</AlertTitle>
                <AlertDescription fontSize="sm">
                  {matchCount === 1 
                    ? "An existing transaction with the same reference number, date, and amount was found."
                    : `${matchCount} existing transactions with the same reference number, date, and amount were found.`
                  }
                </AlertDescription>
              </Box>
            </Alert>

            {/* Transaction Comparison Table */}
            <Box>
              <Text fontSize="md" fontWeight="bold" mb={3} color={textColor}>
                Transaction Comparison
              </Text>
              
              <TableContainer>
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr bg="gray.100">
                      <Th color="black" fontSize="xs" width="120px">Field</Th>
                      <Th color="black" fontSize="xs" width="200px">Existing Transaction</Th>
                      <Th color="black" fontSize="xs" width="200px">New Transaction</Th>
                      <Th color="black" fontSize="xs" width="80px" textAlign="center">Status</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {renderTransactionRow("Date", "transactionDate", existingTransaction, newTransaction)}
                    {renderTransactionRow("Description", "transactionDescription", existingTransaction, newTransaction)}
                    {renderTransactionRow("Amount", "transactionAmount", existingTransaction, newTransaction)}
                    {renderTransactionRow("Reference", "referenceNumber", existingTransaction, newTransaction)}
                    {renderTransactionRow("Debet", "debet", existingTransaction, newTransaction)}
                    {renderTransactionRow("Credit", "credit", existingTransaction, newTransaction)}
                    {renderTransactionRow("Ref1", "ref1", existingTransaction, newTransaction)}
                    {renderTransactionRow("Ref2", "ref2", existingTransaction, newTransaction)}
                    {renderTransactionRow("File URL", "ref3", existingTransaction, newTransaction)}
                    {renderTransactionRow("Filename", "ref4", existingTransaction, newTransaction)}
                  </Tbody>
                </Table>
              </TableContainer>
            </Box>

            {/* File Information */}
            {(existingTransaction.ref3 || newTransaction.ref3) && (
              <>
                <Divider />
                <Box>
                  <Text fontSize="md" fontWeight="bold" mb={3} color={textColor}>
                    File Information
                  </Text>
                  
                  <VStack spacing={2} align="stretch">
                    {existingTransaction.ref3 && (
                      <Box p={3} bg="blue.50" borderRadius="md" border="1px" borderColor={borderColor}>
                        <Text fontSize="sm" fontWeight="medium" color="blue.800">
                          Existing File:
                        </Text>
                        <Text 
                          fontSize="xs" 
                          color="blue.600" 
                          as="a" 
                          href={existingTransaction.ref3} 
                          target="_blank"
                          textDecoration="underline"
                          wordBreak="break-all"
                        >
                          {existingTransaction.ref3}
                        </Text>
                      </Box>
                    )}
                    
                    {newTransaction.ref3 && (
                      <Box p={3} bg="green.50" borderRadius="md" border="1px" borderColor={borderColor}>
                        <Text fontSize="sm" fontWeight="medium" color="green.800">
                          New File:
                        </Text>
                        <Text 
                          fontSize="xs" 
                          color="green.600" 
                          as="a" 
                          href={newTransaction.ref3} 
                          target="_blank"
                          textDecoration="underline"
                          wordBreak="break-all"
                        >
                          {newTransaction.ref3}
                        </Text>
                      </Box>
                    )}
                  </VStack>
                </Box>
              </>
            )}

            {/* Decision Help */}
            <Box p={4} bg="gray.50" borderRadius="md" border="1px" borderColor={borderColor}>
              <Text fontSize="sm" fontWeight="medium" color="gray.800" mb={2}>
                What would you like to do?
              </Text>
              <VStack spacing={1} align="start">
                <Text fontSize="xs" color="gray.700">
                  • <strong>Continue:</strong> Process this as a new transaction (creates duplicate)
                </Text>
                <Text fontSize="xs" color="gray.700">
                  • <strong>Cancel:</strong> Stop processing and clean up uploaded files
                </Text>
              </VStack>
            </Box>
          </VStack>
        </ModalBody>

        <ModalFooter bg="gray.50" py={3}>
          <HStack spacing={3}>
            <Button
              colorScheme="red"
              variant="outline"
              onClick={onCancel}
              isDisabled={isLoading}
              size="md"
            >
              Cancel Import
            </Button>
            
            <Button
              bg="brand.orange"
              color="white"
              _hover={{ bg: "#e55a00" }}
              onClick={onContinue}
              isLoading={isLoading}
              loadingText="Processing..."
              spinner={<Spinner size="sm" />}
              size="md"
            >
              Continue Anyway
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default DuplicateWarningDialog;