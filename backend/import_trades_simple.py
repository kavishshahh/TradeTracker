#!/usr/bin/env python3
"""
Simple CSV Trade Import Script
Usage: python import_trades_simple.py <user_id> <csv_file_path>
Example: python import_trades_simple.py VLnTlI0Z92aF7ygkE9GI5OixyCm1 "Market P_L tracker - Aug 25.csv"
"""

import csv
import os
import sys
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        if not firebase_admin._apps:
            service_account_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
            
            if service_account_json:
                import json
                service_account_info = json.loads(service_account_json)
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized")
                return firestore.client()
            else:
                print("❌ FIREBASE_SERVICE_ACCOUNT_JSON not found")
                return None
    except Exception as e:
        print(f"❌ Firebase error: {e}")
        return None

def parse_month_to_date(month_str: str) -> str:
    """Convert month string to date string"""
    month_map = {
        'January': '01', 'February': '02', 'March': '03', 'April': '04',
        'May': '05', 'June': '06', 'July': '07', 'August': '08',
        'September': '09', 'October': '10', 'November': '11', 'December': '12'
    }
    
    try:
        parts = month_str.strip().split()
        if len(parts) == 2:
            month = month_map.get(parts[0])
            year = parts[1]
            if month and year:
                return f"{year}-{month}-01"
    except:
        pass
    
    return datetime.now().strftime("%Y-%m-%d")

def parse_number(value: str) -> float:
    """Parse number from string"""
    if not value or value.strip() == '':
        return 0.0
    try:
        return float(value.strip().replace(',', ''))
    except:
        return 0.0

def import_trades(csv_file: str, user_id: str, db):
    """Import trades from CSV"""
    if not os.path.exists(csv_file):
        print(f"❌ File not found: {csv_file}")
        return
    
    trades_collection = db.collection('trades')
    imported = 0
    skipped = 0
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
            # Filter data rows (skip summary rows)
            data_rows = [line for line in lines if ',' in line and 
                        not line.startswith('Pnl') and 
                        not line.startswith('Month') and 
                        not line.startswith('Average')]
            
            for line in data_rows:
                try:
                    values = [v.strip() for v in line.split(',')]
                    
                    if len(values) < 6:
                        continue
                    
                    # Extract values
                    month = values[0]
                    ticker = values[1]
                    buy_price = parse_number(values[2])
                    sell_price = parse_number(values[3])
                    shares = parse_number(values[4])
                    risk_dollars = parse_number(values[6])
                    pnl = parse_number(values[13]) if len(values) > 13 else 0
                    
                    # Skip invalid rows
                    if not month or not ticker or buy_price <= 0 or shares <= 0:
                        continue
                    
                    # Determine status
                    status = "closed" if sell_price > 0 else "open"
                    
                    # Calculate P&L if not provided
                    if pnl == 0 and status == "closed":
                        pnl = (sell_price - buy_price) * shares
                    
                    # Create trade data
                    trade_data = {
                        'user_id': user_id,
                        'date': parse_month_to_date(month),
                        'ticker': ticker.upper(),
                        'buy_price': buy_price,
                        'sell_price': sell_price if sell_price > 0 else None,
                        'shares': shares,
                        'risk_dollars': risk_dollars if risk_dollars > 0 else None,
                        'notes': f"Imported from CSV - {month}",
                        'status': status,
                        'created_at': datetime.now(),
                        'updated_at': datetime.now()
                    }
                    
                    if status == "closed":
                        trade_data['pnl'] = pnl
                    
                    # Check for duplicates
                    existing = trades_collection.where('user_id', '==', user_id)\
                                              .where('ticker', '==', ticker.upper())\
                                              .where('date', '==', trade_data['date'])\
                                              .where('buy_price', '==', buy_price)\
                                              .limit(1).stream()
                    
                    if list(existing):
                        print(f"⚠️  Skipped duplicate: {ticker}")
                        skipped += 1
                        continue
                    
                    # Add trade
                    trades_collection.add(trade_data)
                    print(f"✅ {ticker}: {shares} shares at ${buy_price} ({status})")
                    imported += 1
                    
                except Exception as e:
                    print(f"❌ Error processing row: {e}")
                    continue
    
    except Exception as e:
        print(f"❌ File error: {e}")
        return
    
    print(f"\n📊 Import complete: {imported} imported, {skipped} skipped")

def main():
    if len(sys.argv) != 3:
        # python import_trades_simple.py VLnTlI0Z92aF7ygkE9GI5OixyCm1 "Market P_L tracker - Feb 25.csv"
        print("Usage: python import_trades_simple.py <user_id> <csv_file>")
        print("Example: python import_trades_simple.py 3OZ3orlHzxSZQZ8rQ2GInTctkYb2 'Market P_L tracker - Jun 25.csv'")
        sys.exit(1)
    
    user_id = sys.argv[1]
    csv_file = sys.argv[2]
    
    print(f"🚀 Importing trades for user: {user_id}")
    print(f"📁 CSV file: {csv_file}")
    
    db = initialize_firebase()
    if not db:
        sys.exit(1)
    
    import_trades(csv_file, user_id, db)

if __name__ == "__main__":
    main()
