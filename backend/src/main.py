from pdf_processor import PDFProcessor

# Initialize in test mode
processor = PDFProcessor(test_mode=True)

# Example usage
drive_result = {
    'id': 'test_doc_123',
    'url': 'https://example.com/test.pdf'
}

# Process a PDF (will use testFacturen folder)
# result = processor.process_pdf('path/to/your/pdf.pdf', drive_result, 'Action')
# transactions = processor.extract_transactions(result)

print("PDF Processor initialized in test mode")
print("Files will be stored in: testFacturen/")