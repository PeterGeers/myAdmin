import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Heading,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Input,
  Switch,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Alert,
  AlertIcon,
  VStack,
  HStack,
  Text
} from '@chakra-ui/react';
import { Formik, Form } from 'formik';

interface Transaction {
  row_id: number;
  TransactionNumber: string;
  TransactionDate: string;
  TransactionDescription: string;
  TransactionAmount: number;
  Debet: string;
  Credit: string;
  ReferenceNumber: string;
  Ref1: string;
  Ref2: string;
  Ref3: string;
  Ref4: string;
  Administration: string;
}



const BankingProcessor: React.FC = () => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [testMode, setTestMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [lookupData, setLookupData] = useState<{accounts: string[], descriptions: string[], bank_accounts: any[]}>({accounts: [], descriptions: [], bank_accounts: []});

  useEffect(() => {
    fetchLookupData();
  }, [testMode]);

  const fetchLookupData = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/banking/lookups');
      const data = await response.json();
      if (data.success) {
        setLookupData(data);
      }
    } catch (error) {
      console.error('Error fetching lookup data:', error);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    const csvTsvFiles = files.filter(file => 
      file.name.toLowerCase().endsWith('.csv') || 
      file.name.toLowerCase().endsWith('.tsv')
    );
    setSelectedFiles(csvTsvFiles);
    setMessage(`Selected ${csvTsvFiles.length} CSV/TSV files`);
  };

  const processFiles = async () => {
    if (selectedFiles.length === 0) {
      setMessage('Please select at least one file to process');
      return;
    }

    try {
      setLoading(true);
      
      // Ensure lookup data is loaded
      if (lookupData.bank_accounts.length === 0) {
        await fetchLookupData();
      }
      
      console.log('Bank accounts available:', lookupData.bank_accounts);
      const allTransactions: Transaction[] = [];
      
      for (const file of selectedFiles) {
        const text = await file.text();
        const rows = text.split('\n').filter(row => row.trim());
        
        // Skip header row
        const dataRows = rows.slice(1);
        
        dataRows.forEach((row, index) => {
          let columns: string[] = [];
          
          // Detect file type and parse accordingly
          if (file.name.toLowerCase().endsWith('.tsv')) {
            // TSV parsing - split by tabs
            columns = row.split('\t').map(col => col.trim());
          } else {
            // CSV parsing - handle quoted fields with commas
            let current = '';
            let inQuotes = false;
            
            for (let i = 0; i < row.length; i++) {
              const char = row[i];
              if (char === '"') {
                inQuotes = !inQuotes;
              } else if (char === ',' && !inQuotes) {
                columns.push(current.trim());
                current = '';
              } else {
                current += char;
              }
            }
            columns.push(current.trim()); // Add the last column
          }
          
          // Handle different file formats
          if (file.name.toLowerCase().endsWith('.tsv')) {
            // Revolut TSV format - following R logic
            if (columns.length >= 10) {
              const status = columns[8] || ''; // Status column
              
              // Skip REVERTED and PENDING transactions (like R filter)
              if (status.includes('REVERTED') || status.includes('PENDING')) {
                return;
              }
              
              const amountStr = columns[5] || '0'; // Bedrag column
              const feeStr = columns[6] || '0'; // Kosten column
              const amount = parseFloat(amountStr.replace(',', '.'));
              const fee = parseFloat(feeStr.replace(',', '.'));
              const balance = parseFloat((columns[9] || '0').replace(',', '.'));
              
              // Skip zero amounts
              if (amount === 0 && fee === 0) return;
              
              // Use hardcoded Revolut IBAN since it's not in the TSV file
              const revolutIban = 'NL08REVO7549383472';
              const bankLookup = lookupData.bank_accounts.find(ba => ba.rekeningNummer === revolutIban);
              const currentDate = new Date().toISOString().split('T')[0];
              
              // Main transaction
              if (amount !== 0) {
                const isNegative = amount < 0;
                const absAmount = Math.abs(amount);
                
                // Create Ref2 like R: paste_cols_by_index(df, c(1, 5, 7, 6, 8, 9, 1, 3, 2), "_")
                const ref2 = [
                  columns[0] || '', // Type
                  columns[4] || '', // Beschrijving  
                  columns[6] || '', // Kosten
                  columns[5] || '', // Bedrag
                  columns[7] || '', // Valuta
                  columns[8] || '', // Status
                  columns[0] || '', // Type (again)
                  columns[2] || '', // Startdatum
                  columns[1] || ''  // Product
                ].join('_');
                
                allTransactions.push({
                  row_id: allTransactions.length + index,
                  TransactionNumber: `Revolut ${currentDate}`,
                  TransactionDate: columns[2]?.split(' ')[0] || '', // Startdatum
                  TransactionDescription: columns[4] || '', // Beschrijving
                  TransactionAmount: absAmount,
                  Debet: isNegative ? '' : (bankLookup?.Account || '1023'),
                  Credit: isNegative ? (bankLookup?.Account || '1023') : '',
                  ReferenceNumber: '',
                  Ref1: revolutIban,
                  Ref2: ref2,
                  Ref3: balance.toString(),
                  Ref4: file.name,
                  Administration: bankLookup?.Administration || 'PeterPrive'
                });
              }
              
              // Add fee transaction if fee > 0 (like R logic)
              if (fee > 0) {
                const feeRef2 = [
                  'Revo Charges',
                  'Fee',
                  fee.toString(),
                  (-fee).toString(),
                  columns[7] || '',
                  'VOLTOOID',
                  'Revo Charges',
                  columns[2] || '',
                  'Betaalrekening'
                ].join('_');
                
                allTransactions.push({
                  row_id: allTransactions.length + index + 1000, // Offset to avoid conflicts
                  TransactionNumber: `Revolut ${currentDate}`,
                  TransactionDate: columns[2]?.split(' ')[0] || '',
                  TransactionDescription: 'Revo Charges',
                  TransactionAmount: fee,
                  Debet: '',
                  Credit: bankLookup?.Account || '1023',
                  ReferenceNumber: '',
                  Ref1: revolutIban,
                  Ref2: feeRef2,
                  Ref3: balance.toString(),
                  Ref4: file.name,
                  Administration: bankLookup?.Administration || 'PeterPrive'
                });
              }
            }
          } else {
            // Rabobank CSV format
            if (columns.length >= 20) {
              const amountStr = columns[6] || '0';
              const isNegative = amountStr.startsWith('-');
              const cleanAmount = amountStr.replace(/[+-]/g, '').replace(',', '.');
              const amount = parseFloat(cleanAmount);
              
              // Skip zero amounts
              if (amount === 0) return;
              
              // Find bank account lookup
              const iban = columns[0] || '';
              const bankLookup = lookupData.bank_accounts.find(ba => ba.rekeningNummer === iban);
              
              // Generate TransactionNumber based on IBAN
              const bankCode = iban.includes('RABO') ? 'RABO' : 'BANK';
              const currentDate = new Date().toISOString().split('T')[0];
              
              allTransactions.push({
                row_id: allTransactions.length + index,
                TransactionNumber: `${bankCode} ${currentDate}`,
                TransactionDate: columns[4] || '',
                TransactionDescription: [
                  columns[9] || '',  // Naam tegenpartij
                  columns[19] || '', // Omschrijving-1
                  columns[20] || '', // Omschrijving-2  
                  columns[21] || '', // Omschrijving-3
                  columns[18] || '', // Betalingskenmerk
                  columns[8] || '',  // Tegenrekening IBAN/BBAN
                  columns[7] || ''   // Saldo na trn
                ].filter(field => field.trim() && field.trim() !== 'NA')
                 .join(' ')
                 .replace(/\s+/g, ' ')
                 .replace(/Google Pay/g, 'GPay')
                 .trim(),
                TransactionAmount: amount,
                Debet: isNegative ? '' : (bankLookup?.Account || '1000'),
                Credit: isNegative ? (bankLookup?.Account || '1000') : '',
                ReferenceNumber: columns[15] || '',
                Ref1: columns[0] || '',
                Ref2: parseInt(columns[3] || '0').toString(), // Volgnr without leading zeros
                Ref3: '',
                Ref4: file.name,
                Administration: bankLookup?.Administration || 'GoodwinSolutions'
              });
            }
          }
        });
      }
      
      // Check sequences against database
      const iban = allTransactions[0]?.Ref1;
      const sequences = allTransactions.map(t => t.Ref2).filter(ref => ref);
      
      console.log('IBAN for sequence check:', iban);
      console.log('Sequences to check:', sequences);
      
      if (iban && sequences.length > 0) {
        const response = await fetch('http://localhost:5000/api/banking/check-sequences', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            iban: iban,
            sequences: sequences,
            test_mode: testMode
          })
        });
        
        const checkResult = await response.json();
        console.log('Sequence check result:', checkResult);
        
        if (checkResult.success && checkResult.duplicates.length > 0) {
          // Filter out duplicate transactions
          const filteredTransactions = allTransactions.filter(t => 
            !checkResult.duplicates.includes(t.Ref2)
          );
          setTransactions(filteredTransactions);
          setMessage(`Loaded ${filteredTransactions.length} new transactions. WARNING: ${checkResult.duplicates.length} duplicates filtered out`);
        } else {
          setTransactions(allTransactions);
          setMessage(`Loaded ${allTransactions.length} transactions for review`);
        }
      } else {
        setTransactions(allTransactions);
        setMessage(`Loaded ${allTransactions.length} transactions for review`);
      }
    } catch (error) {
      setMessage(`Error processing files: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveTransactions = async (values: any) => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:5000/api/banking/save-transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transactions: transactions,
          test_mode: testMode
        })
      });

      const data = await response.json();
      
      if (data.success) {
        setMessage(`Successfully saved ${data.saved_count} transactions to ${data.table}`);
        setTransactions([]);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error saving transactions: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const updateTransaction = (rowId: number, field: keyof Transaction, value: string | number) => {
    setTransactions(prev => 
      prev.map(t => 
        t.row_id === rowId ? { ...t, [field]: value } : t
      )
    );
  };



  const clearSelection = () => {
    setSelectedFiles([]);
  };

  const applyPatterns = async () => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:5000/api/banking/apply-patterns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transactions: transactions,
          test_mode: testMode
        })
      });

      const data = await response.json();
      
      if (data.success) {
        setTransactions(data.transactions);
        setMessage(`Applied patterns to transactions. Found ${data.patterns_found} historical patterns.`);
      } else {
        setMessage(`Error applying patterns: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error applying patterns: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box maxW="1200px" mx="auto">
      <Heading mb={6} color="white" fontSize="2xl">Banking Transaction Processor</Heading>

      {/* Mode Selection */}
      <FormControl mb={6}>
        <FormLabel>
          <Switch
            isChecked={testMode}
            onChange={(e) => setTestMode(e.target.checked)}
            mr={2}
          />
          Mode: {testMode ? 'TEST (mutaties_test)' : 'PRODUCTION (mutaties)'}
        </FormLabel>
      </FormControl>

      {/* File Selection */}
      <VStack align="stretch" mb={6}>
        <FormControl>
          <FormLabel color="white">Select CSV Files</FormLabel>
          <Input
            type="file"
            accept=".csv,.tsv"
            multiple
            onChange={handleFileSelect}
            bg="white"
            color="black"
          />
        </FormControl>
        
        {selectedFiles.length > 0 && (
          <VStack align="stretch" spacing={2}>
            <Text color="white">Selected Files ({selectedFiles.length}):</Text>
            {selectedFiles.map((file, index) => (
              <Text key={index} fontSize="sm" color="gray.300">
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </Text>
            ))}
            <HStack>
              <Button 
                onClick={processFiles}
                isLoading={loading}
                colorScheme="blue"
              >
                Process Files
              </Button>
              <Button onClick={clearSelection} size="sm">
                Clear Selection
              </Button>
            </HStack>
          </VStack>
        )}
      </VStack>

      {/* Message Display */}
      {message && (
        <Alert 
          status={message.includes('Error') ? 'error' : 'success'} 
          mb={6}
          bg={message.includes('Error') ? 'red.100' : 'green.100'}
          color="black"
          borderColor={message.includes('Error') ? 'red.300' : 'green.300'}
        >
          <AlertIcon color={message.includes('Error') ? 'red.600' : 'green.600'} />
          {message}
        </Alert>
      )}

      {/* Transactions Form */}
      {transactions.length > 0 && (
        <Formik
          initialValues={{}}
          onSubmit={handleSaveTransactions}
        >
          {({ handleSubmit }) => (
            <Form>
              <Box mb={6}>
                <HStack justify="space-between" mb={4}>
                  <Heading size="md">Review Transactions ({transactions.length})</Heading>
                  <HStack>
                    <Button 
                      colorScheme="blue"
                      isLoading={loading}
                      onClick={applyPatterns}
                    >
                      Apply Patterns
                    </Button>
                    <Button 
                      type="submit"
                      colorScheme="green"
                      isLoading={loading}
                      onClick={() => handleSubmit()}
                    >
                      Save to Database
                    </Button>
                  </HStack>
                </HStack>

                <Box overflowX="auto" maxH="600px">
                  <Table variant="simple" size="sm">
                    <Thead>
                      <Tr>
                        <Th>TrxNumber</Th>
                        <Th>Date</Th>
                        <Th>Description</Th>
                        <Th>Amount</Th>
                        <Th>Debet</Th>
                        <Th>Credit</Th>
                      </Tr>
                      <Tr>
                        <Th>RefNumber</Th>
                        <Th>Ref1</Th>
                        <Th>Ref2</Th>
                        <Th>Admin</Th>
                        <Th colSpan={2}></Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {transactions.map((transaction, index) => (
                        <React.Fragment key={transaction.row_id}>
                          <Tr bg={index % 2 === 0 ? 'gray.100' : 'white'}>
                            <Td>
                              <Input
                                size="sm"
                                value={transaction.TransactionNumber}
                                onChange={(e) => updateTransaction(transaction.row_id, 'TransactionNumber', e.target.value)}
                                minW="120px"
                              />
                            </Td>
                            <Td>
                              <FormControl isInvalid={!transaction.TransactionDate}>
                                <Input
                                  size="sm"
                                  type="date"
                                  value={transaction.TransactionDate}
                                  onChange={(e) => updateTransaction(transaction.row_id, 'TransactionDate', e.target.value)}
                                  isInvalid={!transaction.TransactionDate}
                                />
                                {!transaction.TransactionDate && (
                                  <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
                                )}
                              </FormControl>
                            </Td>
                            <Td>
                              <FormControl isInvalid={!transaction.TransactionDescription}>
                                <Input
                                  size="sm"
                                  value={transaction.TransactionDescription}
                                  onChange={(e) => updateTransaction(transaction.row_id, 'TransactionDescription', e.target.value)}
                                  minW="200px"
                                  isInvalid={!transaction.TransactionDescription}
                                />
                                {!transaction.TransactionDescription && (
                                  <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
                                )}
                              </FormControl>
                            </Td>
                            <Td>
                              <FormControl isInvalid={!transaction.TransactionAmount || transaction.TransactionAmount <= 0}>
                                <Input
                                  size="sm"
                                  type="number"
                                  step="0.01"
                                  value={transaction.TransactionAmount}
                                  onChange={(e) => updateTransaction(transaction.row_id, 'TransactionAmount', parseFloat(e.target.value) || 0)}
                                  isInvalid={!transaction.TransactionAmount || transaction.TransactionAmount <= 0}
                                />
                                {(!transaction.TransactionAmount || transaction.TransactionAmount <= 0) && (
                                  <FormErrorMessage fontSize="xs">Must be greater than 0</FormErrorMessage>
                                )}
                              </FormControl>
                            </Td>
                            <Td>
                              <FormControl isInvalid={!transaction.Debet}>
                                <Input
                                  size="sm"
                                  value={transaction.Debet}
                                  onChange={(e) => updateTransaction(transaction.row_id, 'Debet', e.target.value)}
                                  isInvalid={!transaction.Debet}
                                  list={`debet-accounts-${transaction.row_id}`}
                                />
                                <datalist id={`debet-accounts-${transaction.row_id}`}>
                                  {lookupData.accounts.map((account, idx) => (
                                    <option key={idx} value={account} />
                                  ))}
                                </datalist>
                                {!transaction.Debet && (
                                  <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
                                )}
                              </FormControl>
                            </Td>
                            <Td>
                              <FormControl isInvalid={!transaction.Credit}>
                                <Input
                                  size="sm"
                                  value={transaction.Credit}
                                  onChange={(e) => updateTransaction(transaction.row_id, 'Credit', e.target.value)}
                                  isInvalid={!transaction.Credit}
                                  list={`credit-accounts-${transaction.row_id}`}
                                />
                                <datalist id={`credit-accounts-${transaction.row_id}`}>
                                  {lookupData.accounts.map((account, idx) => (
                                    <option key={idx} value={account} />
                                  ))}
                                </datalist>
                                {!transaction.Credit && (
                                  <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
                                )}
                              </FormControl>
                            </Td>
                          </Tr>
                          <Tr bg={index % 2 === 0 ? 'gray.100' : 'white'}>
                            <Td>
                              <Input
                                size="sm"
                                value={transaction.ReferenceNumber}
                                onChange={(e) => updateTransaction(transaction.row_id, 'ReferenceNumber', e.target.value)}
                                minW="120px"
                              />
                            </Td>
                            <Td>
                              <Input
                                size="sm"
                                value={transaction.Ref1}
                                onChange={(e) => updateTransaction(transaction.row_id, 'Ref1', e.target.value)}
                              />
                            </Td>
                            <Td>
                              <Input
                                size="sm"
                                value={transaction.Ref2}
                                onChange={(e) => updateTransaction(transaction.row_id, 'Ref2', e.target.value)}
                                placeholder="Reference 2"
                              />
                            </Td>
                            <Td>
                              <FormControl isInvalid={!transaction.Administration}>
                                <Input
                                  size="sm"
                                  value={transaction.Administration}
                                  onChange={(e) => updateTransaction(transaction.row_id, 'Administration', e.target.value)}
                                  isInvalid={!transaction.Administration}
                                />
                                {!transaction.Administration && (
                                  <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
                                )}
                              </FormControl>
                            </Td>
                            <Td></Td>
                            <Td></Td>
                          </Tr>
                        </React.Fragment>
                      ))}
                    </Tbody>
                  </Table>
                </Box>
              </Box>
            </Form>
          )}
        </Formik>
      )}


    </Box>
  );
};

export default BankingProcessor;