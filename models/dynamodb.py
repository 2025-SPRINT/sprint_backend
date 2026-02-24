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
        Saves or updates the analysis result to DynamoDB using partial update.
        """
        if not self.table:
            print("❌ [DynamoDB] Table resource is not initialized.")
            return False

        try:
            video_id = data.get('video_id')
            if not video_id:
                print("❌ [DynamoDB] No video_id provided.")
                return False

            # Prepare UpdateExpression
            update_parts = []
            expression_attribute_values = {}
            expression_attribute_names = {}

            # Convert float to Decimal manually if not using simplejson/dynamodbjson
            item = json.loads(json.dumps(data), parse_float=Decimal)
            
            for key, value in item.items():
                if key == 'video_id':
                    continue
                
                # Use #key to avoid reserved word conflicts (e.g., 'usage', 'date')
                attr_name = f"#{key}"
                val_name = f":{key}"
                
                update_parts.append(f"{attr_name} = {val_name}")
                expression_attribute_names[attr_name] = key
                expression_attribute_values[val_name] = value

            if not update_parts:
                return True

            # Add updated_at
            update_parts.append("#updated_at = :updated_at")
            expression_attribute_names["#updated_at"] = "updated_at"
            expression_attribute_values[":updated_at"] = int(time.time())

            update_expression = "SET " + ", ".join(update_parts)

            self.table.update_item(
                Key={'video_id': video_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values
            )
            print(f"✅ [DynamoDB] Updated analysis for video: {video_id}")
            return True
            
        except ClientError as e:
            print(f"❌ [DynamoDB] Update Item Error: {e}")
            return False
        except Exception as e:
            print(f"❌ [DynamoDB] Error updating item: {e}")
            return False

    def get_analysis_result(self, video_id: str):
        """
        Retrieves the analysis result from DynamoDB.
        """
        if not self.table:
            return None

        try:
            response = self.table.get_item(Key={'video_id': video_id})
            item = response.get('Item')
            if item:
                # Decimal -> float/int conversion for JSON serialization if needed
                # But for now, returning as is (Flask handles Decimal slightly weirdly, might need conversion)
                def decimal_default(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    raise TypeError
                
                # Clean up the item to be standard python dict with floats
                return json.loads(json.dumps(item, default=decimal_default))
            return None
        except ClientError as e:
            print(f"❌ [DynamoDB] Get Item Error: {e}")
            return None
        except Exception as e:
            print(f"❌ [DynamoDB] Error getting item: {e}")
            return None

# Singleton instance
db_handler = DynamoDBHandler()
