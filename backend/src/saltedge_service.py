import os
import requests
import hashlib
import time
from datetime import datetime, timedelta

class SaltEdgeService:
    def __init__(self):
        self.app_id = os.getenv('SALT_EDGE_APP_ID')
        self.secret = os.getenv('SALT_EDGE_SECRET')
        self.base_url = 'https://www.saltedge.com/api/v5'
        
    def _generate_signature(self, method, expires_at, url, body=''):
        message = f"{expires_at}|{method}|{url}|{body}"
        return hashlib.sha256(f"{message}|{self.secret}".encode()).hexdigest()
    
    def _headers(self, method, url, body=''):
        expires_at = str(int(time.time()) + 60)
        signature = self._generate_signature(method, expires_at, url, body)
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'App-id': self.app_id,
            'Secret': self.secret,
            'Expires-at': expires_at,
            'Signature': signature
        }
    
    def get_countries(self):
        url = f"{self.base_url}/countries"
        response = requests.get(url, headers=self._headers('GET', url))
        return response.json()
    
    def get_providers(self, country_code='NL'):
        url = f"{self.base_url}/providers"
        params = {'country_code': country_code}
        response = requests.get(url, params=params, headers=self._headers('GET', url))
        return response.json()
    
    def create_customer(self, identifier):
        url = f"{self.base_url}/customers"
        body = {'data': {'identifier': identifier}}
        import json
        body_str = json.dumps(body)
        response = requests.post(url, json=body, headers=self._headers('POST', url, body_str))
        return response.json()
    
    def create_connect_session(self, customer_id, provider_code, return_url):
        url = f"{self.base_url}/connect_sessions/create"
        body = {
            'data': {
                'customer_id': customer_id,
                'consent': {
                    'scopes': ['account_details', 'transactions_details'],
                    'from_date': (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
                },
                'attempt': {
                    'return_to': return_url,
                    'fetch_scopes': ['accounts', 'transactions']
                },
                'provider_code': provider_code
            }
        }
        import json
        body_str = json.dumps(body)
        response = requests.post(url, json=body, headers=self._headers('POST', url, body_str))
        return response.json()
    
    def get_connections(self, customer_id):
        url = f"{self.base_url}/connections"
        params = {'customer_id': customer_id}
        response = requests.get(url, params=params, headers=self._headers('GET', url))
        return response.json()
    
    def get_accounts(self, connection_id):
        url = f"{self.base_url}/accounts"
        params = {'connection_id': connection_id}
        response = requests.get(url, params=params, headers=self._headers('GET', url))
        return response.json()
    
    def get_transactions(self, account_id, from_date=None):
        url = f"{self.base_url}/transactions"
        params = {'account_id': account_id}
        if from_date:
            params['from_date'] = from_date
        response = requests.get(url, params=params, headers=self._headers('GET', url))
        return response.json()
    
    def format_transactions(self, transactions, iban, account_code, administration):
        formatted = []
        for txn in transactions:
            amount = abs(float(txn['amount']))
            is_negative = float(txn['amount']) < 0
            
            formatted.append({
                'TransactionNumber': f"BANK {datetime.now().strftime('%Y-%m-%d')}",
                'TransactionDate': txn['made_on'],
                'TransactionDescription': txn['description'],
                'TransactionAmount': amount,
                'Debet': '' if is_negative else account_code,
                'Credit': account_code if is_negative else '',
                'ReferenceNumber': '',
                'Ref1': iban,
                'Ref2': f"SE_{txn['id']}",  # Prefix with SE_ to identify Salt Edge transactions
                'Ref3': '',
                'Ref4': 'SaltEdge',
                'Administration': administration
            })
        
        return formatted
