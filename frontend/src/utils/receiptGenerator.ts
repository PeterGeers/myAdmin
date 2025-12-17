interface ReceiptData {
  supplierName: string;
  transactionDate: string;
  totalAmount: number;
  vatAmount?: number;
  description?: string;
  referenceNumber?: string;
}

export const generateReceipt = (data: ReceiptData): HTMLCanvasElement => {
  const canvas = document.createElement('canvas');
  canvas.width = 600;
  canvas.height = 800;
  const ctx = canvas.getContext('2d')!;
  
  // White background
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  
  // Set text properties
  ctx.fillStyle = 'black';
  ctx.textAlign = 'center';
  
  let yPos = 80;
  
  // Supplier name
  ctx.font = 'bold 40px Arial';
  ctx.fillText(data.supplierName, canvas.width / 2, yPos);
  yPos += 80;
  
  // Date
  ctx.font = '24px Arial';
  ctx.fillText(`Datum: ${data.transactionDate}`, canvas.width / 2, yPos);
  yPos += 60;
  
  // Reference number if available
  if (data.referenceNumber) {
    ctx.font = '20px Arial';
    ctx.fillText(`Ref: ${data.referenceNumber}`, canvas.width / 2, yPos);
    yPos += 60;
  }
  
  // Line
  ctx.beginPath();
  ctx.moveTo(50, yPos);
  ctx.lineTo(canvas.width - 50, yPos);
  ctx.strokeStyle = 'black';
  ctx.lineWidth = 2;
  ctx.stroke();
  yPos += 60;
  
  // Receipt title
  ctx.font = 'bold 40px Arial';
  ctx.fillText('KASSABON', canvas.width / 2, yPos);
  yPos += 100;
  
  // Description if available
  if (data.description) {
    ctx.font = '20px Arial';
    ctx.fillText(data.description, canvas.width / 2, yPos);
    yPos += 60;
  }
  
  // Amounts
  ctx.font = '24px Arial';
  ctx.textAlign = 'left';
  
  if (data.vatAmount && data.vatAmount > 0) {
    const netAmount = data.totalAmount - data.vatAmount;
    
    ctx.fillText('Subtotaal:', 100, yPos);
    ctx.textAlign = 'right';
    ctx.fillText(`€ ${netAmount.toFixed(2)}`, canvas.width - 100, yPos);
    yPos += 50;
    
    ctx.textAlign = 'left';
    ctx.fillText('BTW:', 100, yPos);
    ctx.textAlign = 'right';
    ctx.fillText(`€ ${data.vatAmount.toFixed(2)}`, canvas.width - 100, yPos);
    yPos += 50;
    
    // Line
    ctx.beginPath();
    ctx.moveTo(50, yPos);
    ctx.lineTo(canvas.width - 50, yPos);
    ctx.stroke();
    yPos += 60;
  }
  
  // Total
  ctx.font = 'bold 40px Arial';
  ctx.textAlign = 'left';
  ctx.fillText('TOTAAL:', 100, yPos);
  ctx.textAlign = 'right';
  ctx.fillText(`€ ${data.totalAmount.toFixed(2)}`, canvas.width - 100, yPos);
  
  // Footer
  ctx.font = '18px Arial';
  ctx.textAlign = 'center';
  ctx.fillStyle = 'gray';
  ctx.fillText('Vervangt ontbrekende kassabon', canvas.width / 2, canvas.height - 50);
  
  return canvas;
};

export const downloadReceipt = (canvas: HTMLCanvasElement, filename: string): void => {
  canvas.toBlob((blob) => {
    const url = URL.createObjectURL(blob!);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, 'image/jpeg', 0.95);
};

export const canvasToBlob = (canvas: HTMLCanvasElement): Promise<Blob> => {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      resolve(blob!);
    }, 'image/jpeg', 0.95);
  });
};

export const generateReceiptFilename = (supplierName: string, date: string): string => {
  const cleanName = supplierName.replace(/[^a-zA-Z0-9]/g, '_');
  const cleanDate = date.replace(/[^0-9]/g, '');
  return `kassabon_${cleanName}_${cleanDate}.jpg`;
};