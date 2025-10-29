from pdf_processor import PDFProcessor

# Production mode - uses "Facturen" folder
processor_prod = PDFProcessor(test_mode=False)

# Test mode - uses "testFacturen" folder  
processor_test = PDFProcessor(test_mode=True)

# Example usage
drive_result = {
    'id': 'doc123',
    'url': 'https://example.com/doc.pdf'
}

# This will store in testFacturen/Action/
result = processor_test.process_pdf('sample.pdf', drive_result, 'Action')
print(f"Test folder: {result['folder']}")

# This will store in Facturen/Action/
result = processor_prod.process_pdf('sample.pdf', drive_result, 'Action')
print(f"Production folder: {result['folder']}")