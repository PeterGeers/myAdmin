from flask import Blueprint, request, jsonify, send_file
from invoice_generator import InvoiceGenerator
import os
from datetime import datetime

invoice_bp = Blueprint('invoice', __name__, url_prefix='/api/invoice')
generator = InvoiceGenerator()

@invoice_bp.route('/generate', methods=['POST'])
def generate_invoice():
    try:
        data = request.json
        company_name = data.get('company_name')
        filename = data.get('filename')
        total_amount = float(data.get('total_amount'))
        vat_amount = float(data.get('vat_amount'))
        date = data.get('date')
        
        # Generate receipt
        receipt = generator.generate_receipt(
            company_name=company_name,
            filename=filename,
            total_amount=total_amount,
            vat_amount=vat_amount,
            date=date
        )
        
        # Save to temp folder
        output_dir = 'generated_receipts'
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)
        generator.save_receipt(receipt, output_path)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'path': output_path
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@invoice_bp.route('/download/<filename>', methods=['GET'])
def download_invoice(filename):
    try:
        file_path = os.path.join('generated_receipts', filename)
        return send_file(file_path, mimetype='image/jpeg', as_attachment=True)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 404
