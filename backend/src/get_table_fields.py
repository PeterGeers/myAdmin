#!/usr/bin/env python3
import mysql.connector
from database import DatabaseManager

def get_table_fields():
    """Get field information for bnb, bnbplanned, and bnbfuture tables"""
    db = DatabaseManager(test_mode=False)
    
    try:
        connection = db.get_connection()
        
        cursor = connection.cursor()
        tables = ['mutaties', 'bnb', 'bnbplanned', 'bnbfuture']
        results = {}
        
        for table in tables:
            cursor.execute(f"DESCRIBE {table}")
            fields = cursor.fetchall()
            results[table] = []
            
            for field in fields:
                field_name = field[0]
                field_type = field[1]
                results[table].append({
                    'field': field_name,
                    'type': field_type
                })
        
        cursor.close()
        connection.close()
        
        return results
        
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return {}

if __name__ == "__main__":
    fields = get_table_fields()
    
    for table_name, table_fields in fields.items():
        print(f"\n{table_name} fields:")
        print("---")
        print("| Field | Type |")
        print("|-------|------|")
        for field in table_fields:
            print(f"| {field['field']} | {field['type']} |")