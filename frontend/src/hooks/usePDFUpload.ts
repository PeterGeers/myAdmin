/**
 * usePDFUpload Hook
 *
 * Manages the PDF upload flow including:
 * - File upload with progress tracking
 * - Duplicate detection and resolution
 * - Folder management (list, search, create)
 * - Upload state and parsed results
 *
 * Extracted from PDFUploadForm.tsx for file size management.
 */

import { useCallback, useEffect, useState } from 'react';
import { authenticatedGet, authenticatedPost, authenticatedFormData } from '../services/apiService';
import { useTenant } from '../context/TenantContext';

/** Parsed invoice data from the upload response. */
export interface ParsedInvoiceData {
  vendor?: string;
  invoice_number?: string;
  date?: string;
  amount?: number;
  name?: string;
  url?: string;
  folder?: string;
  txt?: string;
  [key: string]: unknown;
}

/** Vendor metadata from the upload response. */
export interface VendorData {
  name?: string;
  account?: string;
  date?: string;
  total_amount?: string | number;
  vat_amount?: string | number;
  description?: string;
  [key: string]: unknown;
}

/** Duplicate detection info attached to a transaction. */
export interface DuplicateInfo {
  has_duplicates?: boolean;
  matches?: Array<Record<string, unknown>>;
  decision_id?: string;
  existingTransaction?: {
    id: string;
    transactionDate: string;
    transactionDescription: string;
    transactionAmount: number;
    debet: string;
    credit: string;
    referenceNumber: string;
    ref1?: string;
    ref2?: string;
    ref3?: string;
    ref4?: string;
  };
  newTransaction?: {
    id: string;
    transactionDate: string;
    transactionDescription: string;
    transactionAmount: number;
    debet: string;
    credit: string;
    referenceNumber: string;
    ref1?: string;
    ref2?: string;
    ref3?: string;
    ref4?: string;
  };
  matchCount?: number;
  [key: string]: unknown;
}

/** A prepared transaction from the upload response. */
export interface PreparedTransaction {
  ID?: number;
  date?: string;
  description?: string;
  amount?: number;
  debet?: number;
  credit?: number;
  TransactionNumber?: string;
  TransactionDate?: string;
  TransactionDescription?: string;
  TransactionAmount?: number;
  ReferenceNumber?: string;
  Debet?: string;
  Credit?: string;
  Administration?: string;
  Ref1?: string;
  Ref2?: string;
  Ref3?: string;
  Ref4?: string;
  duplicate_info?: DuplicateInfo;
  [key: string]: unknown;
}

/** Form values from Formik. */
export interface UploadFormValues {
  file: File | null;
  folderId: string;
  [key: string]: unknown;
}

export interface UsePDFUploadReturn {
  // Upload state
  loading: boolean;
  tenantSwitching: boolean;
  message: string;
  setMessage: (msg: string) => void;
  uploadProgress: number;
  parsedData: ParsedInvoiceData | null;
  vendorData: VendorData | null;
  preparedTransactions: PreparedTransaction[];
  setPreparedTransactions: React.Dispatch<React.SetStateAction<PreparedTransaction[]>>;

  // Folder state
  allFolders: string[];
  filteredFolders: string[];
  searchTerm: string;
  setSearchTerm: (term: string) => void;
  showCreateFolder: boolean;
  setShowCreateFolder: (show: boolean) => void;
  newFolderName: string;
  setNewFolderName: (name: string) => void;

  // Duplicate state
  showDuplicateDialog: boolean;
  duplicateInfo: DuplicateInfo | null;
  duplicateLoading: boolean;

  // Handlers
  handleSearch: (value: string, setFieldValue: (field: string, value: string) => void) => void;
  handleSubmit: (values: UploadFormValues, formikHelpers?: { resetForm: () => void }) => Promise<void>;
  approveTransactions: () => Promise<void>;
  createFolder: () => Promise<void>;
  handleDuplicateContinue: () => Promise<void>;
  handleDuplicateCancel: () => Promise<void>;
}

export function usePDFUpload(): UsePDFUploadReturn {
  const { currentTenant } = useTenant();

  const [loading, setLoading] = useState(false);
  const [tenantSwitching, setTenantSwitching] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [parsedData, setParsedData] = useState<ParsedInvoiceData | null>(null);
  const [vendorData, setVendorData] = useState<VendorData | null>(null);
  const [preparedTransactions, setPreparedTransactions] = useState<PreparedTransaction[]>([]);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [allFolders, setAllFolders] = useState<string[]>([]);
  const [filteredFolders, setFilteredFolders] = useState<string[]>([]);

  // Duplicate detection state
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const [duplicateInfo, setDuplicateInfo] = useState<DuplicateInfo | null>(null);
  const [duplicateLoading, setDuplicateLoading] = useState(false);
  const [pendingTransactions, setPendingTransactions] = useState<PreparedTransaction[]>([]);

  // Fetch folders on mount and when tenant changes
  useEffect(() => {
    const fetchFolders = async () => {
      try {
        const response = await authenticatedGet('/api/folders', { tenant: currentTenant || undefined });
        const data = await response.json();
        const uniqueFolders = Array.from(new Set(data)) as string[];
        setAllFolders(uniqueFolders);
        setFilteredFolders(uniqueFolders);
        setMessage('');
      } catch (error) {
        console.error('Error fetching folders:', error);
        setMessage('Error loading folders. Please try refreshing the page.');
      }
    };

    if (currentTenant) {
      setTenantSwitching(true);

      // SECURITY: Clear previous tenant data when switching
      setParsedData(null);
      setVendorData(null);
      setPreparedTransactions([]);
      setPendingTransactions([]);
      setDuplicateInfo(null);
      setShowDuplicateDialog(false);

      fetchFolders().finally(() => {
        setTenantSwitching(false);
      });
    } else {
      fetchFolders();
    }
  }, [currentTenant]);

  const handleSearch = useCallback(
    (value: string, setFieldValue: (field: string, value: string) => void) => {
      setSearchTerm(value);

      const exactMatch = allFolders.find(folder => folder === value);

      if (exactMatch) {
        setFilteredFolders([exactMatch]);
        setFieldValue('folderId', exactMatch);
      } else {
        const filtered = value.trim() === ''
          ? allFolders
          : allFolders.filter(folder => folder.toLowerCase().includes(value.toLowerCase()));
        setFilteredFolders(filtered);

        if (filtered.length === 1) {
          setFieldValue('folderId', filtered[0]);
        } else if (filtered.length === 0) {
          setFieldValue('folderId', '');
        }
      }
    },
    [allFolders]
  );

  const handleSubmit = async (values: UploadFormValues) => {
    if (loading) return;

    if (!currentTenant) {
      setMessage('Error: No tenant selected. Please select a tenant first.');
      return;
    }

    if (filteredFolders.length > 1) {
      setMessage('Please narrow down to exactly 1 folder before uploading.');
      return;
    }
    if (filteredFolders.length === 0) {
      setMessage('No folders match your search. Please adjust the filter.');
      return;
    }

    setMessage('');
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('file', values.file!);
      formData.append('folderName', values.folderId);

      const responseObj = await authenticatedFormData('/api/upload', formData, {
        tenant: currentTenant || undefined,
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
          setUploadProgress(progress);
        }
      });

      const response = await responseObj.json();

      // Handle duplicate detection from backend
      if (!response.success && response.error === 'duplicate_detected') {
        const dupData = response.duplicate_info;
        if (dupData?.existing_transactions?.length > 0) {
          const existingTxn = dupData.existing_transactions[0];
          setDuplicateInfo({
            existingTransaction: {
              id: existingTxn.id?.toString() || '',
              transactionDate: existingTxn.date || '',
              transactionDescription: existingTxn.description || '',
              transactionAmount: parseFloat(existingTxn.amount) || 0,
              debet: '', credit: '',
              referenceNumber: values.folderId || '',
              ref1: '', ref2: '',
              ref3: existingTxn.file_url || '',
              ref4: existingTxn.filename || ''
            },
            newTransaction: {
              id: 'new',
              transactionDate: existingTxn.date || '',
              transactionDescription: `New upload: ${values.file!.name}`,
              transactionAmount: parseFloat(existingTxn.amount) || 0,
              debet: '', credit: '',
              referenceNumber: values.folderId || '',
              ref1: '', ref2: '', ref3: '',
              ref4: values.file!.name || ''
            },
            matchCount: dupData.duplicate_count || 1
          });
          setShowDuplicateDialog(true);
          setLoading(false);
          return;
        }
        setMessage(response.message || 'This file has already been uploaded.');
        setLoading(false);
        return;
      }

      // Successful upload
      const fileData = {
        name: response.filename,
        url: `/uploads/${response.filename}`,
        folder: response.folder,
        txt: response.extractedText || 'No text extracted'
      };
      setParsedData(fileData);
      setVendorData(response.vendorData);

      const preparedTxns = response.preparedTransactions || [];
      const hasDuplicates = preparedTxns.some(
        (txn: PreparedTransaction) => txn.duplicate_info?.has_duplicates
      );

      if (hasDuplicates) {
        const txnWithDuplicate = preparedTxns.find(
          (txn: PreparedTransaction) => txn.duplicate_info?.has_duplicates
        );
        if (txnWithDuplicate?.duplicate_info) {
          setPendingTransactions(preparedTxns);
          const dupInfo = txnWithDuplicate.duplicate_info;
          const existingTxn = ((dupInfo as Record<string, unknown>).existing_transactions as Record<string, unknown>[] | undefined)?.[0];
          if (existingTxn) {
            setDuplicateInfo({
              existingTransaction: {
                id: String(existingTxn.ID ?? ''),
                transactionDate: String(existingTxn.TransactionDate ?? ''),
                transactionDescription: String(existingTxn.TransactionDescription ?? ''),
                transactionAmount: parseFloat(String(existingTxn.TransactionAmount)) || 0,
                debet: String(existingTxn.Debet ?? ''), credit: String(existingTxn.Credit ?? ''),
                referenceNumber: String(existingTxn.ReferenceNumber ?? ''),
                ref1: String(existingTxn.Ref1 ?? ''), ref2: String(existingTxn.Ref2 ?? ''),
                ref3: String(existingTxn.Ref3 ?? ''), ref4: String(existingTxn.Ref4 ?? '')
              },
              newTransaction: {
                id: txnWithDuplicate.ID?.toString() || 'new',
                transactionDate: txnWithDuplicate.TransactionDate || '',
                transactionDescription: txnWithDuplicate.TransactionDescription || '',
                transactionAmount: Number(txnWithDuplicate.TransactionAmount) || 0,
                debet: txnWithDuplicate.Debet || '', credit: txnWithDuplicate.Credit || '',
                referenceNumber: txnWithDuplicate.ReferenceNumber || '',
                ref1: txnWithDuplicate.Ref1 || '', ref2: txnWithDuplicate.Ref2 || '',
                ref3: txnWithDuplicate.Ref3 || '', ref4: txnWithDuplicate.Ref4 || ''
              },
              matchCount: (dupInfo as Record<string, unknown>).duplicate_count as number || 1
            });
            setShowDuplicateDialog(true);
          }
        }
      } else {
        setPreparedTransactions(preparedTxns);
      }
    } catch (error: unknown) {
      const err = error as { message?: string; response?: { status?: number; data?: Record<string, unknown> } };
      console.error('Upload error:', error);

      if (err.response?.status === 409 && err.response?.data?.error === 'duplicate_detected') {
        const dupData = err.response.data.duplicate_info as Record<string, unknown> | undefined;
        if (dupData?.existing_transactions && (dupData.existing_transactions as unknown[]).length > 0) {
          const existingTxn = (dupData.existing_transactions as Record<string, unknown>[])[0];
          setDuplicateInfo({
            existingTransaction: {
              id: String(existingTxn.id ?? ''),
              transactionDate: String(existingTxn.date ?? ''),
              transactionDescription: String(existingTxn.description ?? ''),
              transactionAmount: parseFloat(String(existingTxn.amount)) || 0,
              debet: '', credit: '',
              referenceNumber: values.folderId || '',
              ref1: '', ref2: '',
              ref3: String(existingTxn.file_url ?? ''),
              ref4: String(existingTxn.filename ?? '')
            },
            newTransaction: {
              id: 'new',
              transactionDate: String(existingTxn.date ?? ''),
              transactionDescription: `New upload: ${values.file!.name}`,
              transactionAmount: parseFloat(String(existingTxn.amount)) || 0,
              debet: '', credit: '',
              referenceNumber: values.folderId || '',
              ref1: '', ref2: '', ref3: '',
              ref4: values.file!.name || ''
            },
            matchCount: dupData.duplicate_count as number || 1
          });
          setShowDuplicateDialog(true);
          setLoading(false);
          return;
        }
        setMessage(err.response?.data?.message as string || 'This file has already been uploaded.');
        setLoading(false);
        return;
      }

      if (err.response?.status !== 409) {
        setMessage(`Upload failed: ${(err.response?.data?.message as string) || err.message || 'Unknown error'}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const approveTransactions = async () => {
    try {
      const responseObj = await authenticatedPost('/api/approve-transactions', {
        transactions: preparedTransactions
      }, { tenant: currentTenant || undefined });
      const response = await responseObj.json();
      alert(response.message);
      setPreparedTransactions([]);
    } catch (error) {
      console.error('Approval error:', error);
      alert('Error saving transactions');
    }
  };

  const createFolder = async () => {
    if (!newFolderName.trim()) return;

    try {
      await authenticatedPost('/api/create-folder', {
        folderName: newFolderName
      }, { tenant: currentTenant || undefined });

      const response = await authenticatedGet('/api/folders', { tenant: currentTenant || undefined });
      const data = await response.json();
      const uniqueFolders = Array.from(new Set(data)) as string[];
      setAllFolders(uniqueFolders);
      setFilteredFolders(uniqueFolders);
      setNewFolderName('');
      setShowCreateFolder(false);
      alert('Folder created successfully!');
    } catch (error: unknown) {
      const err = error as { message?: string; response?: { data?: { error?: string } } };
      console.error('Create folder error:', error);
      alert(`Error creating folder: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleDuplicateContinue = async () => {
    setDuplicateLoading(true);
    try {
      if (duplicateInfo) {
        await authenticatedPost('/api/log-duplicate-decision', {
          decision: 'continue',
          duplicate_info: {
            existing_transaction_id: (duplicateInfo.existingTransaction as Record<string, unknown>)?.id,
            new_transaction: duplicateInfo.newTransaction,
            reference_number: (duplicateInfo.newTransaction as Record<string, unknown>)?.referenceNumber,
            transaction_date: (duplicateInfo.newTransaction as Record<string, unknown>)?.transactionDate,
            transaction_amount: (duplicateInfo.newTransaction as Record<string, unknown>)?.transactionAmount
          }
        }, { tenant: currentTenant || undefined });
      }

      if (pendingTransactions.length > 0) {
        setPreparedTransactions(pendingTransactions);
        setPendingTransactions([]);
      } else {
        const folderName = (duplicateInfo?.newTransaction as Record<string, unknown>)?.referenceNumber as string;
        const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
        const file = fileInput?.files?.[0];

        if (folderName && file) {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('folderName', folderName);
          formData.append('forceUpload', 'true');

          const responseObj = await authenticatedFormData('/api/upload', formData, {
            tenant: currentTenant || undefined,
            onUploadProgress: (progressEvent) => {
              const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
              setUploadProgress(progress);
            }
          });

          const response = await responseObj.json();
          const fileData = {
            name: response.filename,
            url: `/uploads/${response.filename}`,
            folder: response.folder,
            txt: response.extractedText || 'No text extracted'
          };
          setParsedData(fileData);
          setVendorData(response.vendorData);
          setPreparedTransactions(response.preparedTransactions || []);
        }
      }

      setShowDuplicateDialog(false);
      setDuplicateInfo(null);
    } catch (error) {
      console.error('Error processing duplicate continue:', error);
      alert('Error processing your decision. Please try again.');
    } finally {
      setDuplicateLoading(false);
    }
  };

  const handleDuplicateCancel = async () => {
    setDuplicateLoading(true);
    try {
      if (duplicateInfo) {
        await authenticatedPost('/api/log-duplicate-decision', {
          decision: 'cancel',
          duplicate_info: {
            existing_transaction_id: (duplicateInfo.existingTransaction as Record<string, unknown>)?.id,
            new_transaction: duplicateInfo.newTransaction,
            reference_number: (duplicateInfo.newTransaction as Record<string, unknown>)?.referenceNumber,
            transaction_date: (duplicateInfo.newTransaction as Record<string, unknown>)?.transactionDate,
            transaction_amount: (duplicateInfo.newTransaction as Record<string, unknown>)?.transactionAmount,
            new_file_url: (duplicateInfo.newTransaction as Record<string, unknown>)?.ref3,
            existing_file_url: (duplicateInfo.existingTransaction as Record<string, unknown>)?.ref3
          }
        }, { tenant: currentTenant || undefined });
      }

      setPendingTransactions([]);
      setParsedData(null);
      setVendorData(null);
      setShowDuplicateDialog(false);
      setDuplicateInfo(null);
      alert('Import cancelled. The uploaded file has been cleaned up.');
    } catch (error) {
      console.error('Error cancelling duplicate:', error);
      alert('Error cancelling import. Please try again.');
    } finally {
      setDuplicateLoading(false);
    }
  };

  return {
    loading,
    tenantSwitching,
    message,
    setMessage,
    uploadProgress,
    parsedData,
    vendorData,
    preparedTransactions,
    setPreparedTransactions,
    allFolders,
    filteredFolders,
    searchTerm,
    setSearchTerm,
    showCreateFolder,
    setShowCreateFolder,
    newFolderName,
    setNewFolderName,
    showDuplicateDialog,
    duplicateInfo,
    duplicateLoading,
    handleSearch,
    handleSubmit,
    approveTransactions,
    createFolder,
    handleDuplicateContinue,
    handleDuplicateCancel,
  };
}
