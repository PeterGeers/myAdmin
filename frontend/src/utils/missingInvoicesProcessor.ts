import { generateReceipt, canvasToBlob, generateReceiptFilename } from './receiptGenerator';
import { buildApiUrl } from '../config';

interface MissingInvoiceRecord {
  ID: string;
  Date: string;
  ReferenceNumber: string;
  Ref3: string;
  Ref4: string;
}

interface TransactionData {
  ID: string;
  TransactionAmount: number;
  TransactionDate: string;
  TransactionDescription: string;
  ReferenceNumber: string;
}

export const processMissingInvoices = async (
  csvFile: File,
  onProgress: (progress: number, message: string) => void
): Promise<void> => {
  const csvText = await csvFile.text();
  const lines = csvText.split('\n').slice(1); // Skip header
  const records: MissingInvoiceRecord[] = lines
    .filter(line => line.trim())
    .map(line => {
      const [ID, Date, ReferenceNumber, Ref3, Ref4] = line.split(',');
      return { ID, Date, ReferenceNumber, Ref3, Ref4 };
    });

  onProgress(10, `Found ${records.length} records`);

  // Group by Ref4 (unique names)
  const grouped = records.reduce((acc, record) => {
    if (!acc[record.Ref4]) acc[record.Ref4] = [];
    acc[record.Ref4].push(record);
    return acc;
  }, {} as Record<string, MissingInvoiceRecord[]>);

  const groupNames = Object.keys(grouped);
  let processed = 0;

  for (const ref4Name of groupNames) {
    const group = grouped[ref4Name];
    processed++;
    const progress = 10 + (processed / groupNames.length) * 80;

    onProgress(progress, `Processing ${ref4Name}`);

    // Get transaction data
    const ids = group.map(r => r.ID);
    const transactionData = await fetchTransactionData(ids);

    if (transactionData.length === 0) continue;

    // Calculate amounts
    const amounts = transactionData.map(t => t.TransactionAmount);
    const totalAmount = amounts.length === 1 ? amounts[0] : Math.max(...amounts);
    const vatAmount = amounts.length === 2 ? Math.min(...amounts) : 0;

    // Generate receipt
    const transaction = transactionData[0];
    const receiptData = {
      supplierName: transaction.ReferenceNumber,
      transactionDate: new Date(transaction.TransactionDate).toLocaleDateString('nl-NL'),
      totalAmount,
      vatAmount: vatAmount > 0 ? vatAmount : undefined,
      description: transaction.TransactionDescription,
      referenceNumber: transaction.ReferenceNumber
    };

    const canvas = generateReceipt(receiptData);
    const blob = await canvasToBlob(canvas);
    const filename = generateReceiptFilename(transaction.ReferenceNumber, receiptData.transactionDate);

    // Upload to Google Drive and update database
    const driveUrl = await uploadToGoogleDrive(blob, filename, transaction.ReferenceNumber);
    await updateTransactionRefs(ids, driveUrl, filename);
  }

  onProgress(100, 'Process completed!');
};

const fetchTransactionData = async (ids: string[]): Promise<TransactionData[]> => {
  const response = await fetch(buildApiUrl('/api/transactions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids })
  });
  return response.json();
};

const uploadToGoogleDrive = async (blob: Blob, filename: string, supplierName: string): Promise<string> => {
  const formData = new FormData();
  formData.append('file', blob, filename);
  formData.append('supplierName', supplierName);

  const response = await fetch(buildApiUrl('/api/upload-receipt'), {
    method: 'POST',
    body: formData
  });
  
  const result = await response.json();
  return result.driveUrl;
};

const updateTransactionRefs = async (ids: string[], driveUrl: string, filename: string): Promise<void> => {
  await fetch(buildApiUrl('/api/update-transaction-refs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, driveUrl, filename })
  });
};