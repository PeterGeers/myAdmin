"""Quick test for query=2"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from flask import Flask
from src.str_invoice_routes import str_invoice_bp
import json

app = Flask(__name__)
app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')

with app.test_client() as client:
    response = client.get('/api/str-invoice/search-booking?query=2&limit=all')
    data = json.loads(response.data)
    print(f'Results with query=2 and limit=all: {len(data.get("bookings", []))} bookings')
    
    if data.get("bookings"):
        print(f'Sample: {data["bookings"][0]["reservationCode"]} - {data["bookings"][0]["guestName"]}')
