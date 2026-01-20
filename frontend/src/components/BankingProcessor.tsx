import {
    Alert, AlertIcon,
    Box, Button,
    Card, CardBody,
    Checkbox,
    FormControl,
    FormErrorMessage,
    FormLabel,
    Grid, GridItem,
    HStack,
    Heading,
    Input,
    Menu,
    MenuButton,
    MenuItem,
    MenuList,
    Modal,
    ModalBody, ModalCloseButton,
    ModalContent,
    ModalFooter,
    ModalHeader,
    ModalOverlay,
    Select,
    Tab,
    TabList,
    TabPanel,
    TabPanels,
    Table,
    TableContainer,
    Tabs,
    Tbody,
    Td,
    Text,
    Textarea,
    Th,
    Thead,
    Tr,
    VStack,
    useDisclosure
} from '@chakra-ui/react';
import { Form, Formik } from 'formik';
import React, { useCallback, useEffect, useMemo, useState } from 'react';

interface Transaction {
  ID?: number;
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

interface LookupData {
  accounts: string[];
  descriptions: string[];
  bank_accounts: Array<{ rekeningNummer: string; Account: string; Administration: string }>;
}

interface BankingBalance {
  Reknum: string;
  Administration: string;
  calculated_balance: number;
  account_name: string;
  last_transaction_date: string;
  last_transaction_description: string;
  last_transaction_amount: number;
  last_transactions: Array<{
    TransactionDate: string;
    TransactionDescription: string;
    TransactionAmount: number;
    Debet: string;
    Credit: string;
    Ref2: string;
    Ref3: string;
  }>;
}

// File processing utilities
const parseCSVRow = (row: string): string[] => {
  const columns: string[] = [];
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
  columns.push(current.trim());
  return columns;
};

const processRevolutTransaction = (columns: string[], index: number, bankLookup: any, fileName: string, header?: string[]): Transaction[] => {
  const transactions: Transaction[] = [];
  
  // Helper to find column index by name (supports Dutch and English)
  const getColIdx = (names: string[], fallback: number): number => {
    if (!header) return fallback;
    const idx = header.findIndex(h => names.some(n => h.toLowerCase().includes(n.toLowerCase())));
    return idx >= 0 ? idx : fallback;
  };
  
  // Map columns by name with fallback to position
  // Dutch:   Type, Product, Startdatum, Datum voltooid, Beschrijving, Bedrag, Kosten, Valuta, Status, Saldo
  // English: Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State, Balance
  const startdatumIdx = getColIdx(['startdatum', 'started date', 'started'], 2);
  const beschrijvingIdx = getColIdx(['beschrijving', 'description'], 4);
  const bedragIdx = getColIdx(['bedrag', 'amount'], 5);
  const kostenIdx = getColIdx(['kosten', 'fee'], 6);
  const statusIdx = getColIdx(['status', 'state'], 8);
  const saldoIdx = getColIdx(['saldo', 'balance'], 9);
  
  const startdatum = columns[startdatumIdx] || '';
  const beschrijving = columns[beschrijvingIdx] || '';
  const bedrag = columns[bedragIdx] || '0';
  const kosten = columns[kostenIdx] || '0';
  const status = columns[statusIdx] || '';
  // Always format saldo to 2 decimals for consistency (514.3 -> 514.30)
  const saldoRaw = columns[saldoIdx] || '0';
  const saldo = parseFloat(saldoRaw.replace(',', '.')).toFixed(2);

  if (status.includes('REVERTED') || status.includes('PENDING')) return transactions;

  const amount = parseFloat(bedrag.replace(',', '.'));
  const fee = parseFloat(kosten.replace(',', '.'));
  const balance = parseFloat(saldo.replace(',', '.'));

  if (amount === 0 && fee === 0) return transactions;

  const revolutIban = 'NL08REVO7549383472';
  const currentDate = new Date().toISOString().split('T')[0];

  // Main transaction
  if (amount !== 0) {
    const isNegative = amount < 0;
    const absAmount = Math.abs(amount);
    // Use raw saldo string to avoid formatting differences (514.3 vs 514.30)
    const ref2 = [beschrijving, saldo, startdatum].join('_');

    transactions.push({
      row_id: index,
      TransactionNumber: `Revolut ${currentDate}`,
      TransactionDate: startdatum.split(' ')[0] || '',
      TransactionDescription: beschrijving,
      TransactionAmount: absAmount,
      Debet: isNegative ? '' : (bankLookup?.Account || '1023'),
      Credit: isNegative ? (bankLookup?.Account || '1023') : '',
      ReferenceNumber: '',
      Ref1: revolutIban,
      Ref2: ref2,
      Ref3: balance.toString(),
      Ref4: fileName,
      Administration: bankLookup?.Administration || 'PeterPrive'
    });
  }

  // Fee transaction
  if (fee > 0) {
    // Use raw saldo string to avoid formatting differences
    const feeRef2 = ['Revo Charges', saldo, startdatum].join('_');

    transactions.push({
      row_id: index + 1000,
      TransactionNumber: `Revolut ${currentDate}`,
      TransactionDate: startdatum.split(' ')[0] || '',
      TransactionDescription: 'Revo Charges',
      TransactionAmount: fee,
      Debet: '',
      Credit: bankLookup?.Account || '1023',
      ReferenceNumber: '',
      Ref1: revolutIban,
      Ref2: feeRef2,
      Ref3: balance.toString(),
      Ref4: fileName,
      Administration: bankLookup?.Administration || 'PeterPrive'
    });
  }

  return transactions;
};

const processCreditCardTransaction = (columns: string[], index: number, lookupData: LookupData, fileName: string): Transaction | null => {
  if (columns.length < 13) return null;

  const amountStr = columns[8] || '0';
  const amount = Math.abs(parseFloat(amountStr.replace(',', '.')));
  
  if (amount === 0) return null;

  const isNegative = amountStr.startsWith('-');
  const iban = columns[0] || '';
  const administration = iban.includes('NL71RABO0148034454') ? 'PeterPrive' : 'GoodwinSolutions';
  const currentDate = new Date().toISOString().split('T')[0];
  
  // Build description from multiple columns (index 9 onwards)
  const description = columns.slice(9).filter(col => col && col.trim()).join(' ').trim();
  
  return {
    row_id: index,
    TransactionNumber: `Visa ${currentDate}`,
    TransactionDate: columns[7] || '', // Datum column
    TransactionDescription: description,
    TransactionAmount: amount,
    Debet: isNegative ? '4002' : '2001', // Negative = expense (4002), Positive = credit (2001)
    Credit: isNegative ? '2001' : '2001', // Always credit to 2001
    ReferenceNumber: 'Default',
    Ref1: columns[3] || '', // Productnaam (Rabo BusinessCard Visa)
    Ref2: columns[6] || '', // Transactiereferentie (UNIQUE transaction ID)
    Ref3: iban,
    Ref4: '',
    Administration: administration
  };
};

const processRabobankTransaction = (columns: string[], index: number, lookupData: LookupData, fileName: string): Transaction | null => {
  if (columns.length < 20) return null;

  const amountStr = columns[6] || '0';
  const isNegative = amountStr.startsWith('-');
  const amount = parseFloat(amountStr.replace(/[+-]/g, '').replace(',', '.'));

  if (amount === 0) return null;

  const iban = columns[0] || '';
  const bankLookup = lookupData.bank_accounts.find(ba => ba.rekeningNummer === iban);
  const bankCode = iban.includes('RABO') ? 'RABO' : 'BANK';
  const currentDate = new Date().toISOString().split('T')[0];

  const description = [columns[9], columns[19], columns[20], columns[21]]
    .filter(field => field?.trim() && field.trim() !== 'NA' && field.trim() !== '' && field.trim() !== 'nan')
    .join(' ')
    .replace(/\s+/g, ' ')
    .replace(/Google Pay/g, 'GPay')
    .trim();

  return {
    row_id: index,
    TransactionNumber: `${bankCode} ${currentDate}`,
    TransactionDate: columns[4] || '',
    TransactionDescription: description,
    TransactionAmount: amount,
    Debet: isNegative ? '' : (bankLookup?.Account || '1002'),
    Credit: isNegative ? (bankLookup?.Account || '1002') : '',
    ReferenceNumber: '', // Leave empty for pattern prediction to fill
    Ref1: columns[0] || '',
    Ref2: parseInt(columns[3] || '0').toString(),
    Ref3: '',
    Ref4: fileName,
    Administration: bankLookup?.Administration || 'GoodwinSolutions'
  };
};

const BankingProcessor: React.FC = () => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [mutaties, setMutaties] = useState<Transaction[]>([]);
  const [testMode] = useState(false); // Always use production mode
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [patternResults, setPatternResults] = useState<any>(null);
  const [showSaveConfirmation, setShowSaveConfirmation] = useState<boolean>(false);
  const [lookupData, setLookupData] = useState<LookupData>({ accounts: [], descriptions: [], bank_accounts: [] });
  const [filterOptions, setFilterOptions] = useState<{ years: string[], administrations: string[] }>({ years: [], administrations: [] });
  const [mutatiesFilters, setMutatiesFilters] = useState({
    years: [new Date().getFullYear().toString()],
    administration: 'all'
  });
  const [columnFilters, setColumnFilters] = useState({
    ID: '',
    TransactionNumber: '',
    TransactionDate: '',
    TransactionDescription: '',
    TransactionAmount: '',
    Debet: '',
    Credit: '',
    ReferenceNumber: '',
    Ref1: '',
    Ref2: '',
    Ref3: '',
    Ref4: '',
    Administration: ''
  });
  const [debouncedFilters, setDebouncedFilters] = useState(columnFilters);
  const [displayLimit, setDisplayLimit] = useState(100);
  const [bankingBalances, setBankingBalances] = useState<BankingBalance[]>([]);
  const [checkingAccounts, setCheckingAccounts] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [endDate, setEndDate] = useState('');
  const [sequenceResult, setSequenceResult] = useState<any>(null);
  const [checkingSequence, setCheckingSequence] = useState(false);
  const [sequenceStartDate, setSequenceStartDate] = useState('2025-01-01');
  const [selectedAccount, setSelectedAccount] = useState('1002-GoodwinSolutions');
  
  // Check Reference state
  const [checkRefFilters, setCheckRefFilters] = useState({
    administration: 'all',
    ledger: 'all',
    referenceNumber: 'all'
  });
  const [availableLedgers, setAvailableLedgers] = useState<string[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [availableReferences, setAvailableReferences] = useState<string[]>([]);
  const [refSummaryData, setRefSummaryData] = useState<any[]>([]);
  const [selectedReferenceDetails, setSelectedReferenceDetails] = useState<any[]>([]);
  const [selectedReference, setSelectedReference] = useState<string>('');
  
  // STR Channel Revenue state
  const [strChannelFilters, setStrChannelFilters] = useState({
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    administration: 'GoodwinSolutions'
  });
  const [strChannelPreview, setStrChannelPreview] = useState<any[]>([]);
  const [strChannelTransactions, setStrChannelTransactions] = useState<any[]>([]);
  const [strChannelSummary, setStrChannelSummary] = useState<any>(null);
  
  // Pattern suggestion state
  const [patternSuggestions, setPatternSuggestions] = useState<any>(null);
  const [showPatternApproval, setShowPatternApproval] = useState(false);
  const [originalTransactions, setOriginalTransactions] = useState<Transaction[]>([]);

  const toggleRowExpansion = (key: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(key)) {
      newExpanded.delete(key);
    } else {
      newExpanded.add(key);
    }
    setExpandedRows(newExpanded);
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedFilters(columnFilters);
    }, 150);
    return () => clearTimeout(timer);
  }, [columnFilters]);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [editingRecord, setEditingRecord] = useState<Transaction | null>(null);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setMessage('Copied to clipboard!');
      setTimeout(() => setMessage(''), 2000);
    });
  };

  const handleRef3Click = (ref3: string) => {
    if (ref3.startsWith('https://drive.goo')) {
      window.open(ref3, '_blank');
    } else {
      copyToClipboard(ref3);
    }
  };

  const filteredMutaties = useMemo(() => {
    const filtered = mutaties.filter(mutatie => {
      return Object.entries(debouncedFilters).every(([key, filterValue]) => {
        if (!filterValue) return true;
        try {
          const regex = new RegExp(filterValue, 'i');
          const fieldValue = String(mutatie[key as keyof Transaction] || '');
          return regex.test(fieldValue);
        } catch {
          return String(mutatie[key as keyof Transaction] || '').toLowerCase().includes(filterValue.toLowerCase());
        }
      });
    });
    return filtered.slice(0, displayLimit);
  }, [mutaties, debouncedFilters, displayLimit]);

  const openEditModal = (record: Transaction) => {
    setEditingRecord({ ...record });
    onOpen();
  };

  const updateRecord = async () => {
    if (!editingRecord) return;
    try {
      setLoading(true);
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/banking/update-mutatie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingRecord)
      });
      const data = await response.json();
      if (data.success) {
        setMessage('Record updated successfully!');
        fetchMutaties();
        onClose();
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error updating record: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchLookupData = useCallback(async () => {
    try {
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/banking/lookups');
      const data = await response.json();
      if (data.success) setLookupData(data);
    } catch (error) {
      console.error('Error fetching lookup data:', error);
    }
  }, []);

  const fetchMutaties = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        years: mutatiesFilters.years.join(','),
        administration: mutatiesFilters.administration
      });
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/banking/mutaties?${params}`);
      const data = await response.json();
      if (data.success) setMutaties(data.mutaties);
    } catch (error) {
      console.error('Error fetching mutaties:', error);
    }
  }, [mutatiesFilters]);

  const fetchFilterOptions = useCallback(async () => {
    try {
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/banking/filter-options');
      const data = await response.json();
      if (data.success) setFilterOptions(data);
    } catch (error) {
      console.error('Error fetching filter options:', error);
    }
  }, []);

  const checkBankingAccounts = useCallback(async () => {
    try {
      setCheckingAccounts(true);
      const params = new URLSearchParams({ test_mode: testMode.toString() });
      if (endDate) params.append('end_date', endDate);
      
      console.log('Calling API with params:', params.toString());
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/banking/check-accounts?${params}`);
      const data = await response.json();
      console.log('API response:', data);
      
      if (data.success) {
        setBankingBalances(data.balances);
        console.log('Setting balances:', data.balances);
        const dateMsg = endDate ? ` as of ${endDate}` : '';
        setMessage(`Found ${data.count} banking accounts${dateMsg}`);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      console.error('API call failed:', error);
      setMessage(`Error checking accounts: ${error}`);
    } finally {
      setCheckingAccounts(false);
    }
  }, [testMode, endDate]);

  const checkSequenceNumbers = useCallback(async () => {
    try {
      setCheckingSequence(true);
      const [account_code, administration] = selectedAccount.split('-');
      const params = new URLSearchParams({ 
        test_mode: testMode.toString(),
        account_code,
        administration,
        start_date: sequenceStartDate
      });
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/banking/check-sequence?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setSequenceResult(data);
        const gapMsg = data.has_gaps ? ` - ${data.sequence_issues.length} gaps found!` : ' - No gaps found';
        setMessage(`Sequence check complete for ${account_code} (${administration})${gapMsg}`);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error checking sequence: ${error}`);
    } finally {
      setCheckingSequence(false);
    }
  }, [testMode, selectedAccount, sequenceStartDate]);

  const fetchCheckRefOptions = async () => {
    try {
      const params = new URLSearchParams({
        administration: checkRefFilters.administration,
        ledger: checkRefFilters.ledger
      });
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/reports/filter-options?${params}`);
      const data = await response.json();
      if (data.success) {
        setAvailableLedgers(data.ledgers || []);
        setAvailableReferences(data.references || []);
      }
    } catch (err) {
      console.error('Error fetching filter options:', err);
    }
  };

  const fetchCheckRefData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        referenceNumber: 'all',
        ledger: checkRefFilters.ledger,
        administration: checkRefFilters.administration
      });
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/reports/check-reference?${params}`);
      const data = await response.json();
      
      if (data.success) {
        const filteredSummary = data.summary.filter((row: any) => {
          const amount = parseFloat(row.total_amount || 0);
          return Math.abs(amount) > 0.01;
        });
        setRefSummaryData(filteredSummary);
        setMessage(`Found ${filteredSummary.length} references with non-zero amounts`);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (err) {
      console.error('Error fetching check reference data:', err);
      setMessage(`Error fetching data: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchReferenceDetails = async (referenceNumber: string) => {
    try {
      const params = new URLSearchParams({
        referenceNumber: referenceNumber,
        ledger: checkRefFilters.ledger,
        administration: checkRefFilters.administration
      });
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/reports/check-reference?${params}`);
      const data = await response.json();
      
      console.log('Reference details response:', data);
      
      if (data.success) {
        setSelectedReferenceDetails(data.transactions);
        setSelectedReference(referenceNumber);
      }
    } catch (err) {
      console.error('Error fetching reference details:', err);
    }
  };

  useEffect(() => {
    fetchCheckRefOptions();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkRefFilters.administration, checkRefFilters.ledger]);

  const formatAmount = (amount: number): string => {
    const num = Number(amount) || 0;
    return `€${num.toLocaleString('nl-NL', {minimumFractionDigits: 2})}`;
  };

  // STR Channel Revenue functions
  const fetchStrChannelPreview = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        year: strChannelFilters.year.toString(),
        month: strChannelFilters.month.toString(),
        administration: strChannelFilters.administration,
        test_mode: testMode.toString()
      });
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch(`/api/str-channel/preview?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setStrChannelPreview(data.preview_data);
        setMessage(`Found ${data.preview_data.length} STR channels for ${strChannelFilters.month}/${strChannelFilters.year}`);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error fetching STR channel preview: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const calculateStrChannelRevenue = async () => {
    try {
      setLoading(true);
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/str-channel/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          year: strChannelFilters.year,
          month: strChannelFilters.month,
          administration: strChannelFilters.administration,
          test_mode: testMode
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setStrChannelTransactions(data.transactions);
        setStrChannelSummary(data.summary);
        setMessage(`Generated ${data.transactions.length} STR channel revenue transactions`);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error calculating STR channel revenue: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const saveStrChannelTransactions = async () => {
    try {
      setLoading(true);
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/str-channel/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transactions: strChannelTransactions,
          test_mode: testMode
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setMessage(`${data.saved_count} STR channel transactions loaded`);
        setStrChannelTransactions([]);
        setStrChannelSummary(null);
      } else {
        setMessage(`Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`Error saving STR channel transactions: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    const csvTsvFiles = files.filter(file =>
      file.name.toLowerCase().endsWith('.csv') ||
      file.name.toLowerCase().endsWith('.tsv')
    );
    setSelectedFiles(csvTsvFiles);
    setMessage(`Selected ${csvTsvFiles.length} CSV/TSV files`);
  }, []);

  const processFiles = useCallback(async () => {
    if (selectedFiles.length === 0) {
      setMessage('Please select at least one file to process');
      return;
    }

    try {
      setLoading(true);

      if (lookupData.bank_accounts.length === 0) {
        // IMPORTANT: Always use relative URLs - DO NOT change to localhost
        const response = await fetch('/api/banking/lookups');
        const data = await response.json();
        if (data.success) setLookupData(data);
      }

      const allTransactions: Transaction[] = [];
      let transactionIndex = 0;

      for (const file of selectedFiles) {
        const text = await file.text();
        const allRows = text.split('\n').filter(row => row.trim());
        const headerRow = allRows[0];
        const rows = allRows.slice(1); // Skip header

        for (let i = 0; i < rows.length; i++) {
          const row = rows[i];
          const currentIndex = transactionIndex + i;
          const columns = file.name.toLowerCase().endsWith('.tsv')
            ? row.split('\t').map(col => col.trim())
            : parseCSVRow(row);

          if (file.name.toLowerCase().endsWith('.tsv')) {
            const header = headerRow.split('\t').map(col => col.trim());
            const revolutTransactions = processRevolutTransaction(
              columns, currentIndex,
              lookupData.bank_accounts.find(ba => ba.rekeningNummer === 'NL08REVO7549383472'),
              file.name,
              header
            );
            allTransactions.push(...revolutTransactions);
          } else if (file.name.startsWith('CSV_CC_')) {
            const creditCardTransaction = processCreditCardTransaction(columns, currentIndex, lookupData, file.name);
            if (creditCardTransaction) allTransactions.push(creditCardTransaction);
          } else {
            const rabobankTransaction = processRabobankTransaction(columns, currentIndex, lookupData, file.name);
            if (rabobankTransaction) allTransactions.push(rabobankTransaction);
          }
        }

        transactionIndex += rows.length;
      }

      // Check for duplicates
      const iban = allTransactions[0]?.Ref1;
      const sequences = allTransactions.map(t => t.Ref2).filter(Boolean);

      if (iban && sequences.length > 0) {
        // IMPORTANT: Always use relative URLs - DO NOT change to localhost
        const response = await fetch('/api/banking/check-sequences', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ iban, sequences, test_mode: testMode })
        });

        const checkResult = await response.json();

        if (checkResult.success && checkResult.duplicates.length > 0) {
          const filteredTransactions = allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2));
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
  }, [selectedFiles, lookupData, testMode]);

  const handleSaveTransactions = async (values: any) => {
    // REQ-UI-004: Add confirmation dialog before saving transactions to database
    setShowSaveConfirmation(true);
  };

  const confirmSaveTransactions = async () => {
    try {
      setLoading(true);
      setShowSaveConfirmation(false);
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/banking/save-transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transactions: transactions,
          test_mode: testMode
        })
      });

      const data = await response.json();

      if (data.success) {
        setMessage(`✅ Successfully saved ${data.saved_count} transactions to ${data.table}`);
        setTransactions([]);
        setPatternResults(null); // Clear pattern results after saving
      } else {
        setMessage(`❌ Error: ${data.error}`);
      }
    } catch (error) {
      setMessage(`❌ Error saving transactions: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const updateTransaction = useCallback((rowId: number, field: keyof Transaction, value: string | number) => {
    setTransactions(prev =>
      prev.map(t =>
        t.row_id === rowId ? { ...t, [field]: value } : t
      )
    );
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedFiles([]);
  }, []);

  // REQ-UI-001 & REQ-UI-002: Handle ENTER key to move to next field instead of submitting form
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault(); // Prevent form submission
      
      // Move focus to next input field
      const form = e.currentTarget.closest('form');
      if (form) {
        const inputs = Array.from(form.querySelectorAll('input, select, textarea')) as HTMLElement[];
        const currentIndex = inputs.indexOf(e.currentTarget as HTMLElement);
        const nextInput = inputs[currentIndex + 1];
        
        if (nextInput) {
          nextInput.focus();
        }
      }
    }
  }, []);

  // REQ-UI-008: Helper function to check if field was auto-filled by patterns
  const isPatternFilled = useCallback((transaction: Transaction, field: string) => {
    // Check if this field was filled by comparing with original transactions
    const originalTx = originalTransactions.find(tx => tx.row_id === transaction.row_id);
    if (!originalTx) return false;
    
    const fieldKey = field === 'debet' ? 'Debet' : 
                     field === 'credit' ? 'Credit' : 
                     field === 'reference' ? 'ReferenceNumber' : field;
    
    // Field is pattern-filled if it was empty in original but has value now
    const originalValue = originalTx[fieldKey as keyof Transaction] || '';
    const currentValue = transaction[fieldKey as keyof Transaction] || '';
    
    return !originalValue && !!currentValue && patternSuggestions;
  }, [originalTransactions, patternSuggestions]);

  // REQ-UI-008: Get styling for pattern-filled fields
  const getPatternFieldStyle = useCallback((transaction: Transaction, field: string) => {
    if (isPatternFilled(transaction, field)) {
      return {
        bg: 'blue.50',
        borderColor: 'blue.300',
        borderWidth: '2px',
        _hover: { bg: 'blue.100' }
      };
    }
    return {};
  }, [isPatternFilled]);

  const applyPatterns = async () => {
    try {
      setLoading(true);
      setPatternResults(null); // Clear previous results
      
      // Store original transactions before applying suggestions
      setOriginalTransactions([...transactions]);
      
      // IMPORTANT: Always use relative URLs - DO NOT change to localhost
      const response = await fetch('/api/banking/apply-patterns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transactions: transactions,
          test_mode: testMode
        })
      });

      const data = await response.json();

      if (data.success) {
        // Update transactions with pattern predictions (suggestions filled in fields)
        setTransactions(data.transactions);
        
        // Store pattern results and suggestions for approval dialog
        const patternData = {
          patterns_found: data.patterns_found,
          predictions_made: data.predictions_made || {
            debet: 0,
            credit: 0,
            reference: 0
          },
          confidence_scores: data.confidence_scores || [],
          average_confidence: data.average_confidence || 0,
          enhanced_results: data.enhanced_results
        };
        
        setPatternResults(patternData);
        setPatternSuggestions(patternData);
        
        const totalPredictions = Object.values(data.predictions_made || {}).reduce((a: number, b: unknown) => a + (typeof b === 'number' ? b : 0), 0);
        
        if (totalPredictions > 0) {
          // Show approval dialog for pattern suggestions
          setShowPatternApproval(true);
          setMessage(`🔍 Found ${totalPredictions} pattern suggestions from ${data.patterns_found} historical patterns. Please review and approve the suggestions.`);
        } else {
          setMessage(`ℹ️ No pattern suggestions found. You may need to fill in the fields manually.`);
        }
      } else {
        setMessage(`❌ Error applying patterns: ${data.error}`);
        setPatternResults(null);
      }
    } catch (error) {
      setMessage(`❌ Error applying patterns: ${error}`);
      setPatternResults(null);
    } finally {
      setLoading(false);
    }
  };

  const approvePatternSuggestions = () => {
    // Keep the current transactions with applied suggestions
    setShowPatternApproval(false);
    setMessage(`✅ Pattern suggestions approved! Made ${Object.values(patternSuggestions?.predictions_made || {}).reduce((a: number, b: unknown) => a + (typeof b === 'number' ? b : 0), 0)} predictions. Review the highlighted fields before saving.`);
  };

  const rejectPatternSuggestions = () => {
    // Restore original transactions without suggestions
    setTransactions([...originalTransactions]);
    setPatternResults(null);
    setPatternSuggestions(null);
    setShowPatternApproval(false);
    setMessage(`❌ Pattern suggestions rejected. Fields restored to original values.`);
  };

  useEffect(() => {
    fetchLookupData();
    fetchFilterOptions();
    fetchMutaties();
  }, [testMode, fetchLookupData, fetchFilterOptions, fetchMutaties]);

  useEffect(() => {
    fetchMutaties();
  }, [fetchMutaties]);

  return (
    <Box w="100%" p={4}>
      <Tabs variant="enclosed" colorScheme="blue">
        <TabList>
          <Tab>Process Files</Tab>
          <Tab>Mutaties</Tab>
          <Tab>Check Account Balances</Tab>
          <Tab>Check Reference Numbers</Tab>
          <Tab>STR Channel Revenue</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>

            {/* File Selection */}
            <VStack align="stretch" mb={6}>
              <HStack justify="space-between" mb={2}>
                <FormLabel color="white" mb={0}>Select CSV/TSV Files (Banking or Credit Card)</FormLabel>
                <Button
                  colorScheme="green"
                  size="sm"
                  onClick={() => alert('Salt Edge integration ready! Waiting for account approval (2 business days). Bank account mappings now loaded from database.')}
                >
                  🏦 Connect Bank (Salt Edge)
                </Button>
              </HStack>
              <FormControl>
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

            {/* REQ-UI-005: Pattern Application Results Display */}
            {patternResults && (
              <Card mb={6} bg="blue.50" borderColor="blue.200" borderWidth="1px">
                <CardBody>
                  <Heading size="sm" mb={3} color="blue.800">Pattern Application Results</Heading>
                  <Grid templateColumns="repeat(2, 1fr)" gap={4}>
                    <Box>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Patterns Found:</strong> {patternResults.patterns_found}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Debet Predictions:</strong> {patternResults.predictions_made?.debet || 0}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Credit Predictions:</strong> {patternResults.predictions_made?.credit || 0}
                      </Text>
                    </Box>
                    <Box>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Reference Predictions:</strong> {patternResults.predictions_made?.reference || 0}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Average Confidence:</strong> {(patternResults.average_confidence * 100).toFixed(1)}%
                      </Text>
                      <Text fontSize="xs" color="blue.600" mt={2}>
                        💡 Fields with blue borders were auto-filled by patterns
                      </Text>
                    </Box>
                  </Grid>
                </CardBody>
              </Card>
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
                                      onKeyDown={handleKeyDown}
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
                                        onKeyDown={handleKeyDown}
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
                                        onKeyDown={handleKeyDown}
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
                                        onKeyDown={handleKeyDown}
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
                                        onKeyDown={handleKeyDown}
                                        isInvalid={!transaction.Debet}
                                        list={`debet-accounts-${transaction.row_id}`}
                                        {...getPatternFieldStyle(transaction, 'debet')}
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
                                        onKeyDown={handleKeyDown}
                                        isInvalid={!transaction.Credit}
                                        list={`credit-accounts-${transaction.row_id}`}
                                        {...getPatternFieldStyle(transaction, 'credit')}
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
                                      onKeyDown={handleKeyDown}
                                      minW="120px"
                                      {...getPatternFieldStyle(transaction, 'reference')}
                                    />
                                  </Td>
                                  <Td>
                                    <Input
                                      size="sm"
                                      value={transaction.Ref1}
                                      onChange={(e) => updateTransaction(transaction.row_id, 'Ref1', e.target.value)}
                                      onKeyDown={handleKeyDown}
                                    />
                                  </Td>
                                  <Td>
                                    <Input
                                      size="sm"
                                      value={transaction.Ref2}
                                      onChange={(e) => updateTransaction(transaction.row_id, 'Ref2', e.target.value)}
                                      onKeyDown={handleKeyDown}
                                      placeholder="Reference 2"
                                    />
                                  </Td>
                                  <Td>
                                    <FormControl isInvalid={!transaction.Administration}>
                                      <Input
                                        size="sm"
                                        value={transaction.Administration}
                                        onChange={(e) => updateTransaction(transaction.row_id, 'Administration', e.target.value)}
                                        onKeyDown={handleKeyDown}
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

          </TabPanel>

          <TabPanel>
            <VStack align="stretch" spacing={4}>
              {/* Filters */}
              <Card bg="gray.700">
                <CardBody>
                  <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
                    <GridItem>
                      <Text color="white" mb={2}>Select Years</Text>
                      <Menu closeOnSelect={false}>
                        <MenuButton
                          as={Button}
                          bg="orange.500"
                          color="white"
                          size="sm"
                          width="100%"
                          textAlign="left"
                          rightIcon={<span>▼</span>}
                          _hover={{ bg: "orange.600" }}
                          _active={{ bg: "orange.600" }}
                        >
                          {mutatiesFilters.years.length > 0 ? mutatiesFilters.years.join(', ') : 'Select years...'}
                        </MenuButton>
                        <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
                          {filterOptions.years.map(year => (
                            <MenuItem key={year} bg="gray.600" _hover={{ bg: "gray.500" }} closeOnSelect={false}>
                              <Checkbox
                                isChecked={mutatiesFilters.years.includes(year)}
                                onChange={(e) => {
                                  const isChecked = e.target.checked;
                                  setMutatiesFilters(prev => ({
                                    ...prev,
                                    years: isChecked
                                      ? [...prev.years, year]
                                      : prev.years.filter(y => y !== year)
                                  }));
                                }}
                                colorScheme="orange"
                              >
                                <Text color="white" ml={2}>{year}</Text>
                              </Checkbox>
                            </MenuItem>
                          ))}
                        </MenuList>
                      </Menu>
                    </GridItem>
                    <GridItem>
                      <Text color="white" mb={2}>Administration</Text>
                      <Select
                        value={mutatiesFilters.administration}
                        onChange={(e) => setMutatiesFilters(prev => ({ ...prev, administration: e.target.value }))}
                        bg="gray.600"
                        color="white"
                        size="sm"
                      >
                        <option value="all">All</option>
                        {filterOptions.administrations.map((admin, index) => (
                          <option key={index} value={admin}>{admin}</option>
                        ))}
                      </Select>
                    </GridItem>
                    <GridItem>
                      <Button onClick={fetchMutaties} size="sm" colorScheme="blue">
                        Refresh
                      </Button>
                    </GridItem>
                  </Grid>
                </CardBody>
              </Card>

              <HStack justify="space-between">
                <Heading size="md">Mutaties ({filteredMutaties.length} of {mutaties.length})</Heading>
                <HStack>
                  <Text color="white" fontSize="sm">Show:</Text>
                  <Select size="sm" value={displayLimit} onChange={(e) => setDisplayLimit(Number(e.target.value))} bg="gray.600" color="white" w="100px">
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                    <option value={250}>250</option>
                    <option value={500}>500</option>
                    <option value={1000}>1000</option>
                  </Select>
                </HStack>
              </HStack>

              <TableContainer maxH="600px" overflowY="auto" overflowX="auto">
                <Table size="sm" variant="simple">
                  <Thead position="sticky" top={0} bg="gray.700" zIndex={1}>
                    <Tr>
                      <Th color="white">ID</Th>
                      <Th color="white">TrxNumber</Th>
                      <Th color="white">Date</Th>
                      <Th color="white" maxW="225px">Description</Th>
                      <Th color="white">Amount</Th>
                      <Th color="white">Debet</Th>
                      <Th color="white">Credit</Th>
                      <Th color="white" maxW="100px">Reference</Th>
                      <Th color="white" maxW="100px">Ref1</Th>
                      <Th color="white" maxW="100px">Ref2</Th>
                      <Th color="white" maxW="100px">Ref3</Th>
                      <Th color="white" maxW="100px">Ref4</Th>
                      <Th color="white">Admin</Th>
                    </Tr>
                    <Tr>
                      <Th p={1}><Input size="xs" placeholder="ID" value={columnFilters.ID} onChange={(e) => setColumnFilters(prev => ({ ...prev, ID: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1}><Input size="xs" placeholder="TrxNumber" value={columnFilters.TransactionNumber} onChange={(e) => setColumnFilters(prev => ({ ...prev, TransactionNumber: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1}><Input size="xs" placeholder="Date" value={columnFilters.TransactionDate} onChange={(e) => setColumnFilters(prev => ({ ...prev, TransactionDate: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1} maxW="225px"><Input size="xs" placeholder="Description" value={columnFilters.TransactionDescription} onChange={(e) => setColumnFilters(prev => ({ ...prev, TransactionDescription: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1}><Input size="xs" placeholder="Amount" value={columnFilters.TransactionAmount} onChange={(e) => setColumnFilters(prev => ({ ...prev, TransactionAmount: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1}><Input size="xs" placeholder="Debet" value={columnFilters.Debet} onChange={(e) => setColumnFilters(prev => ({ ...prev, Debet: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1}><Input size="xs" placeholder="Credit" value={columnFilters.Credit} onChange={(e) => setColumnFilters(prev => ({ ...prev, Credit: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1} maxW="100px"><Input size="xs" placeholder="Reference" value={columnFilters.ReferenceNumber} onChange={(e) => setColumnFilters(prev => ({ ...prev, ReferenceNumber: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1} maxW="100px"><Input size="xs" placeholder="Ref1" value={columnFilters.Ref1} onChange={(e) => setColumnFilters(prev => ({ ...prev, Ref1: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1} maxW="100px"><Input size="xs" placeholder="Ref2" value={columnFilters.Ref2} onChange={(e) => setColumnFilters(prev => ({ ...prev, Ref2: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1} maxW="100px"><Input size="xs" placeholder="Ref3" value={columnFilters.Ref3} onChange={(e) => setColumnFilters(prev => ({ ...prev, Ref3: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1} maxW="100px"><Input size="xs" placeholder="Ref4" value={columnFilters.Ref4} onChange={(e) => setColumnFilters(prev => ({ ...prev, Ref4: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                      <Th p={1}><Input size="xs" placeholder="Admin" value={columnFilters.Administration} onChange={(e) => setColumnFilters(prev => ({ ...prev, Administration: e.target.value }))} onKeyDown={handleKeyDown} bg="gray.600" color="white" /></Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {filteredMutaties.map((mutatie, index) => (
                      <Tr key={mutatie.ID}>
                        <Td color="white" fontSize="sm" cursor="pointer" _hover={{ bg: "gray.600" }} onClick={() => openEditModal(mutatie)}>{mutatie.ID}</Td>
                        <Td color="white" fontSize="sm">{mutatie.TransactionNumber}</Td>
                        <Td color="white" fontSize="sm">{new Date(mutatie.TransactionDate).toLocaleDateString('nl-NL')}</Td>
                        <Td color="white" fontSize="sm" maxW="225px" isTruncated title={mutatie.TransactionDescription} cursor="pointer" onClick={() => copyToClipboard(mutatie.TransactionDescription)}>{mutatie.TransactionDescription}</Td>
                        <Td color="white" fontSize="sm">€{Number(mutatie.TransactionAmount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}</Td>
                        <Td color="white" fontSize="sm">{mutatie.Debet}</Td>
                        <Td color="white" fontSize="sm">{mutatie.Credit}</Td>
                        <Td color="white" fontSize="sm" maxW="100px" isTruncated title={mutatie.ReferenceNumber} cursor="pointer" onClick={() => copyToClipboard(mutatie.ReferenceNumber)}>{mutatie.ReferenceNumber}</Td>
                        <Td color="white" fontSize="sm" maxW="100px" isTruncated title={mutatie.Ref1} cursor="pointer" onClick={() => copyToClipboard(mutatie.Ref1)}>{mutatie.Ref1}</Td>
                        <Td color="white" fontSize="sm" maxW="100px" isTruncated title={mutatie.Ref2} cursor="pointer" onClick={() => copyToClipboard(mutatie.Ref2)}>{mutatie.Ref2}</Td>
                        <Td color="white" fontSize="sm" maxW="100px" isTruncated title={mutatie.Ref3} cursor="pointer" onClick={() => handleRef3Click(mutatie.Ref3)}>{mutatie.Ref3}</Td>
                        <Td color="white" fontSize="sm" maxW="100px" isTruncated title={mutatie.Ref4} cursor="pointer" onClick={() => copyToClipboard(mutatie.Ref4)}>{mutatie.Ref4}</Td>
                        <Td color="white" fontSize="sm">{mutatie.Administration}</Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            </VStack>
          </TabPanel>

          <TabPanel>
            <VStack align="stretch" spacing={4}>
              <HStack justify="space-between">
                <Heading size="md">Check Account Balances</Heading>
                <HStack wrap="wrap" spacing={3}>
                  <Button
                    onClick={checkBankingAccounts}
                    isLoading={checkingAccounts}
                    colorScheme="blue"
                    alignSelf="flex-end"
                    size="sm"
                  >
                    Check Account Balances
                  </Button>
                  <FormControl maxW="130px">
                    <FormLabel color="white" fontSize="sm">End Date (optional)</FormLabel>
                    <Input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      onKeyDown={handleKeyDown}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    />
                  </FormControl>
                  <Button
                    onClick={checkSequenceNumbers}
                    isLoading={checkingSequence}
                    colorScheme="orange"
                    alignSelf="flex-end"
                    size="sm"
                  >
                    Check Sequence
                  </Button>
                  <FormControl maxW="160px">
                    <FormLabel color="white" fontSize="sm">Account</FormLabel>
                    <Select
                      value={selectedAccount}
                      onChange={(e) => setSelectedAccount(e.target.value)}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    >
                      <option value="1002-GoodwinSolutions">1002 - GoodwinSolutions</option>
                      <option value="1011-GoodwinSolutions">1011 - GoodwinSolutions</option>
                      <option value="1012-GoodwinSolutions">1012 - GoodwinSolutions</option>
                      <option value="1003-PeterPrive">1003 - PeterPrive</option>
                      <option value="1011-PeterPrive">1011 - PeterPrive</option>
                      <option value="1012-PeterPrive">1012 - PeterPrive</option>
                    </Select>
                  </FormControl>
                  <FormControl maxW="130px">
                    <FormLabel color="white" fontSize="sm">Start Date</FormLabel>
                    <Input
                      type="date"
                      value={sequenceStartDate}
                      onChange={(e) => setSequenceStartDate(e.target.value)}
                      onKeyDown={handleKeyDown}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    />
                  </FormControl>
                </HStack>
              </HStack>

              {bankingBalances.length > 0 && (
                <TableContainer>
                  <Table size="sm" variant="simple">
                    <Thead>
                      <Tr>
                        <Th color="white" w="20px"></Th>
                        <Th color="white">Administration</Th>
                        <Th color="white">Account</Th>
                        <Th color="white">Account Name</Th>
                        <Th color="white" isNumeric>Calculated Balance</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {bankingBalances
                        .sort((a, b) => {
                          if (a.Administration !== b.Administration) {
                            return a.Administration.localeCompare(b.Administration);
                          }
                          return a.Reknum.localeCompare(b.Reknum);
                        })
                        .map((balance, index) => {
                          const rowKey = `${balance.Reknum}-${balance.Administration}`;
                          const isExpanded = expandedRows.has(rowKey);
                          return (
                            <React.Fragment key={rowKey}>
                              <Tr>
                                <Td color="white" fontSize="sm" w="20px">
                                  <Button
                                    size="xs"
                                    variant="ghost"
                                    onClick={() => toggleRowExpansion(rowKey)}
                                    color="white"
                                  >
                                    {isExpanded ? '▼' : '▶'}
                                  </Button>
                                </Td>
                                <Td color="white" fontSize="sm">{balance.Administration}</Td>
                                <Td color="white" fontSize="sm">{balance.Reknum}</Td>
                                <Td color="white" fontSize="sm">{balance.account_name}</Td>
                                <Td color="white" fontSize="sm" isNumeric>
                                  €{Number(balance.calculated_balance).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                                </Td>
                              </Tr>
                              {isExpanded && balance.last_transactions && balance.last_transactions.length > 0 && (
                                <Tr>
                                  <Td colSpan={5} p={0}>
                                    <Box bg="gray.800" p={2}>
                                      <Text color="white" fontSize="xs" mb={2} fontWeight="bold">
                                        Last Transaction Date: {balance.last_transaction_date ? new Date(balance.last_transaction_date).toLocaleDateString('nl-NL') : 'N/A'}
                                      </Text>
                                      <Table size="xs" variant="simple">
                                        <Thead>
                                          <Tr>
                                            <Th color="gray.300" fontSize="xs">Description</Th>
                                            <Th color="gray.300" fontSize="xs" isNumeric pr={4}>Amount</Th>
                                            <Th color="gray.300" fontSize="xs" pl={4}>Debet</Th>
                                            <Th color="gray.300" fontSize="xs">Credit</Th>
                                            <Th color="gray.300" fontSize="xs">Ref2</Th>
                                            <Th color="gray.300" fontSize="xs">Ref3</Th>
                                          </Tr>
                                        </Thead>
                                        <Tbody>
                                          {balance.last_transactions.map((transaction, txIndex) => (
                                            <Tr key={txIndex}>
                                              <Td color="gray.300" fontSize="xs" maxW="200px" isTruncated title={transaction.TransactionDescription}>
                                                {transaction.TransactionDescription}
                                              </Td>
                                              <Td color="gray.300" fontSize="xs" isNumeric pr={4}>
                                                €{Number(transaction.TransactionAmount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                                              </Td>
                                              <Td color="gray.300" fontSize="xs" pl={4}>{transaction.Debet}</Td>
                                              <Td color="gray.300" fontSize="xs">{transaction.Credit}</Td>
                                              <Td color="gray.300" fontSize="xs">{transaction.Ref2}</Td>
                                              <Td color="gray.300" fontSize="xs" maxW="100px" isTruncated title={transaction.Ref3}>{transaction.Ref3}</Td>
                                            </Tr>
                                          ))}
                                        </Tbody>
                                      </Table>
                                    </Box>
                                  </Td>
                                </Tr>
                              )}
                            </React.Fragment>
                          );
                        })}
                    </Tbody>
                  </Table>
                </TableContainer>
              )}

              {sequenceResult && (
                <Box bg="gray.800" p={4} borderRadius="md">
                  <Heading size="sm" color="white" mb={3}>Sequence Check Results</Heading>
                  <Grid templateColumns="repeat(2, 1fr)" gap={4} mb={4}>
                    <Text color="white" fontSize="sm">Account: {sequenceResult.account_code} ({sequenceResult.administration})</Text>
                    <Text color="white" fontSize="sm">IBAN: {sequenceResult.iban}</Text>
                    <Text color="white" fontSize="sm">Since: {sequenceResult.start_date}</Text>
                    <Text color="white" fontSize="sm">Total Transactions: {sequenceResult.total_transactions}</Text>
                    <Text color="white" fontSize="sm" gridColumn="span 2">Sequence Range: {sequenceResult.first_sequence} - {sequenceResult.last_sequence}</Text>
                  </Grid>
                  
                  {sequenceResult.has_gaps ? (
                    <Box>
                      <Text color="red.300" fontWeight="bold" mb={2}>⚠️ {sequenceResult.sequence_issues.length} Sequence Issues Found:</Text>
                      <Table size="sm" variant="simple">
                        <Thead>
                          <Tr>
                            <Th color="gray.300" fontSize="xs">Expected</Th>
                            <Th color="gray.300" fontSize="xs">Found</Th>
                            <Th color="gray.300" fontSize="xs">Gap</Th>
                            <Th color="gray.300" fontSize="xs">Date</Th>
                            <Th color="gray.300" fontSize="xs">Description</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {sequenceResult.sequence_issues.map((issue: any, index: number) => (
                            <Tr key={index}>
                              <Td color="gray.300" fontSize="xs">{issue.expected}</Td>
                              <Td color="gray.300" fontSize="xs">{issue.found}</Td>
                              <Td color="gray.300" fontSize="xs">{issue.gap > 0 ? `+${issue.gap}` : issue.gap}</Td>
                              <Td color="gray.300" fontSize="xs">{new Date(issue.date).toLocaleDateString('nl-NL')}</Td>
                              <Td color="gray.300" fontSize="xs" maxW="200px" isTruncated title={issue.description}>{issue.description}</Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </Box>
                  ) : (
                    <Text color="green.300" fontWeight="bold">✅ All sequence numbers are consecutive - no gaps found!</Text>
                  )}
                </Box>
              )}

              {bankingBalances.length === 0 && !checkingAccounts && !sequenceResult && (
                <Text color="white" textAlign="center" py={8}>
                  Use the buttons above to check account balances or sequence numbers
                </Text>
              )}
            </VStack>
          </TabPanel>

          <TabPanel>
            <VStack align="stretch" spacing={4}>
              <Box bg="gray.800" p={4} borderRadius="md">
                <Heading size="sm" color="white" mb={4}>Check Reference Numbers</Heading>
                <HStack spacing={4} mb={4} wrap="wrap">
                  <FormControl maxW="180px">
                    <FormLabel color="white" fontSize="sm">Administration</FormLabel>
                    <Select
                      value={checkRefFilters.administration}
                      onChange={(e) => {
                        setCheckRefFilters(prev => ({...prev, administration: e.target.value, ledger: 'all'}));
                        setRefSummaryData([]);
                        setSelectedReferenceDetails([]);
                      }}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    >
                      <option value="all">All</option>
                      <option value="GoodwinSolutions">GoodwinSolutions</option>
                      <option value="PeterPrive">PeterPrive</option>
                    </Select>
                  </FormControl>
                  <FormControl maxW="150px">
                    <FormLabel color="white" fontSize="sm">Ledger</FormLabel>
                    <Select
                      value={checkRefFilters.ledger}
                      onChange={(e) => {
                        setCheckRefFilters(prev => ({...prev, ledger: e.target.value}));
                        setRefSummaryData([]);
                        setSelectedReferenceDetails([]);
                      }}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    >
                      <option value="all">All</option>
                      {availableLedgers.map(ledger => (
                        <option key={ledger} value={ledger}>{ledger}</option>
                      ))}
                    </Select>
                  </FormControl>
                  <Button
                    onClick={fetchCheckRefData}
                    isLoading={loading}
                    colorScheme="green"
                    size="sm"
                    alignSelf="flex-end"
                  >
                    Check References
                  </Button>
                  <Button
                    onClick={async () => {
                      try {
                        setLoading(true);
                        // IMPORTANT: Always use relative URLs - DO NOT change to localhost
                        const response = await fetch('/api/cache/refresh', {
                          method: 'POST'
                        });
                        const data = await response.json();
                        if (data.success) {
                          alert(`Cache refreshed successfully!\n${data.record_count.toLocaleString()} records loaded.`);
                          // Clear current data to force re-fetch
                          setRefSummaryData([]);
                          setSelectedReferenceDetails([]);
                        } else {
                          alert(`Cache refresh failed: ${data.error}`);
                        }
                      } catch (error) {
                        alert(`Error refreshing cache: ${error}`);
                      } finally {
                        setLoading(false);
                      }
                    }}
                    isLoading={loading}
                    colorScheme="blue"
                    size="sm"
                    alignSelf="flex-end"
                    title="Refresh cache after updating records in database"
                  >
                    🔄 Refresh Cache
                  </Button>
                </HStack>

                {refSummaryData.length > 0 && (
                  <VStack align="stretch" spacing={4}>
                    <HStack justify="space-between">
                      <Heading size="xs" color="white">Reference Summary ({refSummaryData.length})</Heading>
                      <Text color="orange.300" fontWeight="bold" fontSize="sm">
                        Total: {formatAmount(refSummaryData.reduce((sum, row) => sum + (parseFloat(row.total_amount) || 0), 0))}
                      </Text>
                    </HStack>
                    <TableContainer maxH="300px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                          <Tr>
                            <Th color="white" fontSize="xs">Reference</Th>
                            <Th color="white" fontSize="xs" isNumeric>Count</Th>
                            <Th color="white" fontSize="xs" isNumeric>Total Amount</Th>
                            <Th color="white" fontSize="xs">Actions</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {refSummaryData.map((row, index) => (
                            <Tr key={index}>
                              <Td color="white" fontSize="xs" maxW="200px" isTruncated title={row.ReferenceNumber}>
                                {row.ReferenceNumber}
                              </Td>
                              <Td color="white" fontSize="xs" isNumeric>{row.transaction_count}</Td>
                              <Td color="white" fontSize="xs" isNumeric>{formatAmount(row.total_amount)}</Td>
                              <Td>
                                <Button
                                  size="xs"
                                  colorScheme="blue"
                                  onClick={() => fetchReferenceDetails(row.ReferenceNumber)}
                                >
                                  Details
                                </Button>
                              </Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>

                    {selectedReferenceDetails.length > 0 && (
                      <Box>
                        <Heading size="xs" color="white" mb={2}>
                          Transactions for Reference: {selectedReference} ({selectedReferenceDetails.length})
                        </Heading>
                        <TableContainer maxH="300px" overflowY="auto">
                          <Table size="sm" variant="simple">
                            <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                              <Tr>
                                <Th color="white" fontSize="xs">Transaction Number</Th>
                                <Th color="white" fontSize="xs">Date</Th>
                                <Th color="white" fontSize="xs" isNumeric>Amount</Th>
                                <Th color="white" fontSize="xs">Description</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {selectedReferenceDetails.map((transaction, index) => (
                                <Tr key={index}>
                                  <Td color="white" fontSize="xs">{transaction.TransactionNumber || '-'}</Td>
                                  <Td color="white" fontSize="xs">
                                    {new Date(transaction.TransactionDate).toISOString().split('T')[0]}
                                  </Td>
                                  <Td color="white" fontSize="xs" isNumeric>{formatAmount(transaction.Amount)}</Td>
                                  <Td color="white" fontSize="xs" maxW="300px" isTruncated title={transaction.TransactionDescription}>
                                    {transaction.TransactionDescription}
                                  </Td>
                                </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </TableContainer>
                      </Box>
                    )}
                  </VStack>
                )}
              </Box>

              {refSummaryData.length === 0 && (
                <Text color="white" textAlign="center" py={8}>
                  Use the button above to check reference numbers
                </Text>
              )}
            </VStack>
          </TabPanel>

          <TabPanel>
            <VStack align="stretch" spacing={4}>
              <Box bg="gray.800" p={4} borderRadius="md">
                <Heading size="sm" color="white" mb={4}>STR Channel Revenue Calculator</Heading>
                <Text color="gray.300" fontSize="sm" mb={4}>
                  Calculate monthly STR revenue based on account 1600 transactions
                </Text>
                
                <HStack spacing={4} mb={4} wrap="wrap">
                  <FormControl maxW="120px">
                    <FormLabel color="white" fontSize="sm">Year</FormLabel>
                    <Input
                      type="number"
                      value={strChannelFilters.year}
                      onChange={(e) => setStrChannelFilters(prev => ({...prev, year: parseInt(e.target.value) || new Date().getFullYear()}))}
                      onKeyDown={handleKeyDown}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    />
                  </FormControl>
                  <FormControl maxW="120px">
                    <FormLabel color="white" fontSize="sm">Month</FormLabel>
                    <Select
                      value={strChannelFilters.month}
                      onChange={(e) => setStrChannelFilters(prev => ({...prev, month: parseInt(e.target.value)}))}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    >
                      {Array.from({length: 12}, (_, i) => i + 1).map(month => (
                        <option key={month} value={month}>
                          {new Date(2000, month - 1).toLocaleString('default', { month: 'long' })}
                        </option>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl maxW="180px">
                    <FormLabel color="white" fontSize="sm">Administration</FormLabel>
                    <Select
                      value={strChannelFilters.administration}
                      onChange={(e) => setStrChannelFilters(prev => ({...prev, administration: e.target.value}))}
                      bg="gray.600"
                      color="white"
                      size="sm"
                    >
                      <option value="GoodwinSolutions">GoodwinSolutions</option>
                      <option value="PeterPrive">PeterPrive</option>
                    </Select>
                  </FormControl>
                  <Button
                    onClick={fetchStrChannelPreview}
                    isLoading={loading}
                    colorScheme="blue"
                    size="sm"
                    alignSelf="flex-end"
                  >
                    Preview Data
                  </Button>
                  <Button
                    onClick={calculateStrChannelRevenue}
                    isLoading={loading}
                    colorScheme="green"
                    size="sm"
                    alignSelf="flex-end"
                    isDisabled={strChannelPreview.length === 0}
                  >
                    Calculate Revenue
                  </Button>
                </HStack>

                {strChannelPreview.length > 0 && (
                  <VStack align="stretch" spacing={4}>
                    <Heading size="xs" color="white">Channel Data Preview ({strChannelPreview.length})</Heading>
                    <TableContainer maxH="200px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                          <Tr>
                            <Th color="white" fontSize="xs">Channel</Th>
                            <Th color="white" fontSize="xs">Account</Th>
                            <Th color="white" fontSize="xs" isNumeric>Transactions</Th>
                            <Th color="white" fontSize="xs" isNumeric>Total Amount</Th>
                            <Th color="white" fontSize="xs">Date Range</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {strChannelPreview.map((row, index) => (
                            <Tr key={index}>
                              <Td color="white" fontSize="xs">{row.ReferenceNumber}</Td>
                              <Td color="white" fontSize="xs">{row.Reknum}</Td>
                              <Td color="white" fontSize="xs" isNumeric>{row.transaction_count}</Td>
                              <Td color="white" fontSize="xs" isNumeric>{formatAmount(row.total_amount)}</Td>
                              <Td color="white" fontSize="xs">
                                {new Date(row.first_date).toLocaleDateString('nl-NL')} - {new Date(row.last_date).toLocaleDateString('nl-NL')}
                              </Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </VStack>
                )}

                {strChannelTransactions.length > 0 && (
                  <VStack align="stretch" spacing={4}>
                    <HStack justify="space-between">
                      <Heading size="xs" color="white">Proposed Transactions ({strChannelTransactions.length})</Heading>
                      <Button
                        onClick={saveStrChannelTransactions}
                        isLoading={loading}
                        colorScheme="orange"
                        size="sm"
                      >
                        Save to Database
                      </Button>
                    </HStack>
                    
                    {strChannelSummary && (
                      <Box bg="gray.700" p={3} borderRadius="md">
                        <Text color="white" fontSize="sm">
                          <strong>Reference:</strong> {strChannelSummary.ref1} | 
                          <strong>Period:</strong> {strChannelSummary.month}/{strChannelSummary.year} | 
                          <strong>End Date:</strong> {strChannelSummary.end_date}
                        </Text>
                      </Box>
                    )}
                    
                    <TableContainer maxH="400px" overflowY="auto">
                      <Table size="sm" variant="simple">
                        <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                          <Tr>
                            <Th color="white" fontSize="xs">Date</Th>
                            <Th color="white" fontSize="xs">Description</Th>
                            <Th color="white" fontSize="xs" isNumeric>Amount</Th>
                            <Th color="white" fontSize="xs">Debet</Th>
                            <Th color="white" fontSize="xs">Credit</Th>
                            <Th color="white" fontSize="xs">Reference</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {strChannelTransactions.map((transaction, index) => (
                            <Tr key={index}>
                              <Td color="white" fontSize="xs">{transaction.TransactionDate}</Td>
                              <Td color="white" fontSize="xs" maxW="200px" isTruncated title={transaction.TransactionDescription}>
                                {transaction.TransactionDescription}
                              </Td>
                              <Td color="white" fontSize="xs" isNumeric>{formatAmount(transaction.TransactionAmount)}</Td>
                              <Td color="white" fontSize="xs">{transaction.Debet}</Td>
                              <Td color="white" fontSize="xs">{transaction.Credit}</Td>
                              <Td color="white" fontSize="xs">{transaction.ReferenceNumber}</Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                    </TableContainer>
                  </VStack>
                )}
              </Box>

              {strChannelPreview.length === 0 && strChannelTransactions.length === 0 && (
                <Text color="white" textAlign="center" py={8}>
                  Select year, month, and administration, then click "Preview Data" to see available STR channel data
                </Text>
              )}
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* Edit Record Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.700">
          <ModalHeader color="white">Edit Record - ID: {editingRecord?.ID}</ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            {editingRecord && (
              <Grid templateColumns="repeat(2, 1fr)" gap={4}>
                <FormControl>
                  <FormLabel color="white">Transaction Number</FormLabel>
                  <Input value={editingRecord.TransactionNumber || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionNumber: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Transaction Date</FormLabel>
                  <Input type="date" value={editingRecord.TransactionDate ? new Date(editingRecord.TransactionDate).toISOString().split('T')[0] : ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionDate: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl gridColumn="span 2">
                  <FormLabel color="white">Description</FormLabel>
                  <Textarea value={editingRecord.TransactionDescription || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionDescription: e.target.value } : prev)} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Amount</FormLabel>
                  <Input type="number" step="0.01" value={editingRecord.TransactionAmount || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, TransactionAmount: parseFloat(e.target.value) || 0 } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Administration</FormLabel>
                  <Input value={editingRecord.Administration || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Administration: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Debet</FormLabel>
                  <Input value={editingRecord.Debet || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Debet: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Credit</FormLabel>
                  <Input value={editingRecord.Credit || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Credit: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Reference Number</FormLabel>
                  <Input value={editingRecord.ReferenceNumber || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, ReferenceNumber: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Ref1</FormLabel>
                  <Input value={editingRecord.Ref1 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref1: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Ref2</FormLabel>
                  <Input value={editingRecord.Ref2 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref2: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
                <FormControl gridColumn="span 2">
                  <FormLabel color="white">Ref3</FormLabel>
                  <Textarea value={editingRecord.Ref3 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref3: e.target.value } : prev)} bg="gray.600" color="white" />
                </FormControl>
                <FormControl>
                  <FormLabel color="white">Ref4</FormLabel>
                  <Input value={editingRecord.Ref4 || ''} onChange={(e) => setEditingRecord(prev => prev ? { ...prev, Ref4: e.target.value } : prev)} onKeyDown={handleKeyDown} bg="gray.600" color="white" />
                </FormControl>
              </Grid>
            )}
          </ModalBody>
          <ModalFooter>
            <Button colorScheme="gray" mr={3} onClick={onClose}>Cancel</Button>
            <Button colorScheme="orange" onClick={updateRecord} isLoading={loading}>Update Record</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* REQ-UI-004: Confirmation Dialog for Save to Database */}
      <Modal isOpen={showSaveConfirmation} onClose={() => setShowSaveConfirmation(false)} size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Confirm Save to Database</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack align="stretch" spacing={4}>
              <Text>
                You are about to save <strong>{transactions.length} transactions</strong> to the database.
              </Text>
              
              {patternResults && (
                <Box bg="blue.50" p={4} borderRadius="md" borderColor="blue.200" borderWidth="1px">
                  <Text fontSize="sm" fontWeight="bold" mb={2}>Pattern Application Summary:</Text>
                  <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                    <Text fontSize="sm">Debet predictions: {patternResults.predictions_made?.debet || 0}</Text>
                    <Text fontSize="sm">Credit predictions: {patternResults.predictions_made?.credit || 0}</Text>
                    <Text fontSize="sm">Reference predictions: {patternResults.predictions_made?.reference || 0}</Text>
                    <Text fontSize="sm">Avg. confidence: {(patternResults.average_confidence * 100).toFixed(1)}%</Text>
                  </Grid>
                </Box>
              )}
              
              <Text fontSize="sm" color="gray.600">
                This action cannot be undone. Please review all transactions before confirming.
              </Text>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button colorScheme="gray" mr={3} onClick={() => setShowSaveConfirmation(false)}>
              Cancel
            </Button>
            <Button colorScheme="green" onClick={confirmSaveTransactions} isLoading={loading}>
              Confirm Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Pattern Approval Dialog - REQ-UI-006: Show pattern suggestions with confidence scores */}
      <Modal isOpen={showPatternApproval} onClose={() => setShowPatternApproval(false)} size="xl">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Review Pattern Suggestions</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack align="stretch" spacing={4}>
              <Alert status="info" borderRadius="md">
                <AlertIcon />
                <Box>
                  <Text fontWeight="bold">Pattern suggestions have been filled into empty fields</Text>
                  <Text fontSize="sm">
                    Review the blue-highlighted fields below and approve or reject the suggestions.
                  </Text>
                </Box>
              </Alert>
              
              {patternSuggestions && (
                <Box bg="blue.50" p={4} borderRadius="md" borderColor="blue.200" borderWidth="1px">
                  <Text fontSize="sm" fontWeight="bold" mb={3}>Pattern Analysis Results:</Text>
                  <Grid templateColumns="repeat(2, 1fr)" gap={4}>
                    <Box>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Patterns Found:</strong> {patternSuggestions.patterns_found}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Debet Suggestions:</strong> {patternSuggestions.predictions_made?.debet || 0}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Credit Suggestions:</strong> {patternSuggestions.predictions_made?.credit || 0}
                      </Text>
                    </Box>
                    <Box>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Reference Suggestions:</strong> {patternSuggestions.predictions_made?.reference || 0}
                      </Text>
                      <Text fontSize="sm" color="blue.700">
                        <strong>Average Confidence:</strong> {(patternSuggestions.average_confidence * 100).toFixed(1)}%
                      </Text>
                      <Text fontSize="xs" color="blue.600" mt={2}>
                        💡 Suggested values are highlighted with blue borders in the transaction table
                      </Text>
                    </Box>
                  </Grid>
                </Box>
              )}
              
              <Box bg="yellow.50" p={3} borderRadius="md" borderColor="yellow.200" borderWidth="1px">
                <Text fontSize="sm" color="yellow.800">
                  <strong>What happens next:</strong>
                </Text>
                <Text fontSize="xs" color="yellow.700" mt={1}>
                  • <strong>Approve:</strong> Keep the suggested values in the highlighted fields
                </Text>
                <Text fontSize="xs" color="yellow.700">
                  • <strong>Reject:</strong> Remove all suggestions and restore original empty fields
                </Text>
                <Text fontSize="xs" color="yellow.700">
                  • You can manually edit any field after making your choice
                </Text>
              </Box>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button colorScheme="red" mr={3} onClick={rejectPatternSuggestions}>
              Reject Suggestions
            </Button>
            <Button colorScheme="green" onClick={approvePatternSuggestions}>
              Approve Suggestions
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default BankingProcessor;