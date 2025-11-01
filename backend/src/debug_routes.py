#!/usr/bin/env python3
"""Debug script to test Flask routes"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app

def list_routes():
    """List all registered routes"""
    print("=== Registered Flask Routes ===")
    for rule in app.url_map.iter_rules():
        print(f"{rule.methods} {rule.rule} -> {rule.endpoint}")
    print(f"\nTotal routes: {len(list(app.url_map.iter_rules()))}")

if __name__ == "__main__":
    list_routes()