import boto3
import os
import time
from botocore.exceptions import ClientError
from decimal import Decimal
import json

class DynamoDBHandler:
    def __init__(self, table_name=None, region_name=None):
        self.region_name = region_name or os.getenv("AWS_REGION", "ap-northeast-2")
        self.table_name = table_name or os.getenv("DYNAMODB_TABLE", "SprintVideoAnalysis")
        
        # Initialize boto3 resource
        try:
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.region_name,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
            )
            self.table = self.dynamodb.Table(self.table_name)
        except Exception as e:
            print(f"❌ [DynamoDB] Init Error: {e}")
            self.table = None

    def create_table_if_not_exists(self):
        """
        Creates the DynamoDB table if it doesn't exist.
        """
        try:
            existing_tables = [t.name for t in self.dynamodb.tables.all()]
            if self.table_name in existing_tables:
                print(f"✅ [DynamoDB] Table '{self.table_name}' already exists.")
                return

            print(f"⏳ [DynamoDB] Creating table '{self.table_name}'...")
            table = self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {'AttributeName': 'video_id', 'KeyType': 'HASH'},  # Partition key
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'video_id', 'AttributeType': 'S'},
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            table.wait_until_exists()
            print(f"✅ [DynamoDB] Table '{self.table_name}' created successfully.")
            self.table = table
        except ClientError as e:
            print(f"❌ [DynamoDB] Create Table Error: {e}")

    def save_analysis_result(self, data: dict):
        """
        Saves the analysis result to DynamoDB.
        """
        if not self.table:
            print("❌ [DynamoDB] Table resource is not initialized.")
            return False

        try:
            # Convert float to Decimal for DynamoDB
            item = json.loads(json.dumps(data), parse_float=Decimal)
            item['created_at'] = int(time.time())
            
            self.table.put_item(Item=item)
            print(f"✅ [DynamoDB] Saved analysis for video: {data.get('video_id', 'Unknown')}")
            return True
        except ClientError as e:
            print(f"❌ [DynamoDB] Put Item Error: {e}")
            return False
        except Exception as e:
            print(f"❌ [DynamoDB] Error saving item: {e}")
            return False

# Singleton instance
db_handler = DynamoDBHandler()
