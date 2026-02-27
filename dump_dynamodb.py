import os
import sys
import csv
import json
from decimal import Decimal
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Add current path to sys.path so we can import from models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.dynamodb import db_handler

def export_dynamodb_to_csv(output_file='dynamodb_dump.csv'):
    table = db_handler.table
    if not table:
        print("Error: Could not connect to DynamoDB table.")
        return

    print(f"Scanning table: {db_handler.table_name}")
    items = []
    
    try:
        # Scan the table
        response = table.scan()
        items.extend(response.get('Items', []))
        
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
    except Exception as e:
        print(f"Error scanning table: {e}")
        return

    if not items:
        print("No items found in the table.")
        return

    print(f"Total items fetched: {len(items)}")

    # Collect all possible keys for the CSV header
    all_keys = set()
    for item in items:
        all_keys.update(item.keys())

    # Sort keys for consistent columns (maybe put 'video_id' first)
    header = sorted(list(all_keys))
    if 'video_id' in header:
        header.remove('video_id')
        header = ['video_id'] + header

    # Function to convert Decimal to float/int
    def decimal_default(obj):
        if isinstance(obj, Decimal):
            # Convert to int if it has no fractional part, else float
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        raise TypeError

    try:
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=header)
            writer.writeheader()
            
            for item in items:
                row = {}
                for key in header:
                    val = item.get(key)
                    if isinstance(val, (dict, list)):
                        # Convert dict/list to json string
                        row[key] = json.dumps(val, default=decimal_default, ensure_ascii=False)
                    elif isinstance(val, Decimal):
                        if val % 1 == 0:
                            row[key] = int(val)
                        else:
                            row[key] = float(val)
                    else:
                        row[key] = val
                writer.writerow(row)
        print(f"Successfully exported data to {output_file}")
        print(f"File absolute path: {os.path.abspath(output_file)}")
    except Exception as e:
        print(f"Error exporting to CSV: {e}")

if __name__ == "__main__":
    export_dynamodb_to_csv()
