import boto3
from boto3.dynamodb.conditions import Key
import os
import time
from botocore.exceptions import ClientError
from decimal import Decimal
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class FeedbackDBHandler:
    """
    SprintFeedback 테이블 핸들러
    - PK: video_id (String)
    - SK: device_id (String)
    - Attributes: vote, comment, user_verdict, updated_at
    """

    def __init__(self, table_name=None, region_name=None):
        self.region_name = region_name or os.getenv("AWS_REGION", "ap-northeast-2")
        self.table_name = table_name or os.getenv("FEEDBACK_TABLE", "SprintFeedback")

        try:
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.region_name,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
            )
            self.table = self.dynamodb.Table(self.table_name)
            print("✅ [FeedbackDB] Init Success")
        except Exception as e:
            print(f"❌ [FeedbackDB] Init Error: {e}")
            self.table = None

    def _ensure_table(self):
        """테이블이 없으면 자동 생성"""
        if not self.dynamodb:
            return
        try:
            self.table.load()
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"⏳ [FeedbackDB] Creating table '{self.table_name}'...")
                table = self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {'AttributeName': 'video_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'device_id', 'KeyType': 'RANGE'},
                    ],
                    AttributeDefinitions=[
                        {'AttributeName': 'video_id', 'AttributeType': 'S'},
                        {'AttributeName': 'device_id', 'AttributeType': 'S'},
                    ],
                    BillingMode='PAY_PER_REQUEST',
                )
                table.wait_until_exists()
                self.table = table
                print(f"✅ [FeedbackDB] Table '{self.table_name}' created.")
            else:
                raise

    def save_feedback(self, video_id: str, device_id: str, vote: str = "", comment: str = "", user_verdict: str = ""):
        """피드백 upsert (vote: 'like' | 'dislike' | '', user_verdict: '위험' | '주의' | '안전' | '')"""
        if not self.table:
            print("❌ [FeedbackDB] Table not initialized.")
            return False

        if vote and vote not in ("like", "dislike"):
            print(f"❌ [FeedbackDB] Invalid vote: {vote}")
            return False

        if user_verdict and user_verdict not in ("위험", "주의", "안전"):
            print(f"❌ [FeedbackDB] Invalid user_verdict: {user_verdict}")
            return False

        try:
            item = {
                'video_id': video_id,
                'device_id': device_id,
                'comment': comment or "",
                'updated_at': int(time.time()),
            }
            if vote:
                item['vote'] = vote
            if user_verdict:
                item['user_verdict'] = user_verdict
            self.table.put_item(Item=item)
            print(f"✅ [FeedbackDB] Saved feedback: {video_id} / {device_id} → {vote} (verdict: {user_verdict or 'N/A'})")
            return True
        except ClientError as e:
            print(f"❌ [FeedbackDB] Save Error: {e}")
            return False

    def get_feedback_summary(self, video_id: str, device_id: Optional[str] = None):
        """
        video_id에 대한 집계 + (optional) device_id의 기존 투표 반환

        Returns:
            {
                "likes": int,
                "dislikes": int,
                "my_vote": str | None,
                "my_comment": str
            }
        """
        if not self.table:
            return {"likes": 0, "dislikes": 0, "my_vote": None, "my_comment": "", "my_verdict": None, "verdict_counts": {}}

        try:
            response = self.table.query(
                KeyConditionExpression=Key('video_id').eq(video_id)
            )
            items = response.get('Items', [])

            likes = sum(1 for it in items if it.get('vote') == 'like')
            dislikes = sum(1 for it in items if it.get('vote') == 'dislike')

            # 사용자 판정 집계
            verdict_counts = {}
            for it in items:
                v = it.get('user_verdict')
                if v:
                    verdict_counts[v] = verdict_counts.get(v, 0) + 1

            my_vote = None
            my_comment = ""
            my_verdict = None
            if device_id:
                for it in items:
                    if it.get('device_id') == device_id:
                        my_vote = it.get('vote')
                        my_comment = it.get('comment', "")
                        my_verdict = it.get('user_verdict')
                        break

            return {
                "likes": likes,
                "dislikes": dislikes,
                "my_vote": my_vote,
                "my_comment": my_comment,
                "my_verdict": my_verdict,
                "verdict_counts": verdict_counts,
            }
        except ClientError as e:
            print(f"❌ [FeedbackDB] Query Error: {e}")
            return {"likes": 0, "dislikes": 0, "my_vote": None, "my_comment": "", "my_verdict": None, "verdict_counts": {}}


# Singleton
feedback_handler = FeedbackDBHandler()

if __name__ == "__main__":
    feedback_handler._ensure_table()
