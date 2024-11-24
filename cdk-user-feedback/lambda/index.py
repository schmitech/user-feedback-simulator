import json
import boto3
import random
import os
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from typing import Any, Dict, List
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

class DecimalEncoder(json.JSONEncoder):
    """Handle numeric type serialization"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            n = float(obj)
            return int(n) if n.is_integer() else n
        return super(DecimalEncoder, self).default(obj)

def clean_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up item data before returning"""
    integer_fields = {'age', 'rating', 'randomBucket'}
    
    for field in integer_fields:
        if field in item and isinstance(item[field], (Decimal, float)):
            item[field] = int(float(item[field]))
    
    return item

def get_random_reviews(batch_size: int, rating_filter: str = 'all', department_filter: str = 'all') -> List[Dict[str, Any]]:
    """
    Get random reviews using multiple sampling strategies:
    1. Query multiple random buckets
    2. Use random starting points within each bucket
    3. Combine and shuffle results
    """
    all_items = []
    buckets_to_try = random.sample(range(1, 11), k=3)  # Try 3 random buckets
    items_per_bucket = batch_size // len(buckets_to_try) + 1  # Distribute batch size across buckets
    
    for bucket in buckets_to_try:
        # Base query parameters
        query_params = {
            'IndexName': os.environ['TABLE_GSI'],
            'KeyConditionExpression': 'randomBucket = :bucket',
            'ExpressionAttributeValues': {
                ':bucket': bucket
            },
            'Limit': items_per_bucket
        }
        
        # Add filters
        filter_expressions = []
        if rating_filter == 'positive':
            filter_expressions.append('rating >= :min_rating')
            query_params['ExpressionAttributeValues'][':min_rating'] = 4
        elif rating_filter == 'negative':
            filter_expressions.append('rating < :max_rating')
            query_params['ExpressionAttributeValues'][':max_rating'] = 4
            
        if department_filter != 'all':
            filter_expressions.append('department = :dept')
            query_params['ExpressionAttributeValues'][':dept'] = department_filter
            
        if filter_expressions:
            query_params['FilterExpression'] = ' AND '.join(filter_expressions)

        # Add random starting point using exclusive start key
        try:
            # First, get a count of items in this bucket
            count_params = query_params.copy()
            count_params['Select'] = 'COUNT'
            count_result = table.query(**count_params)
            total_in_bucket = count_result['Count']

            if total_in_bucket > 0:
                # Choose a random starting point
                skip_items = random.randint(0, max(0, total_in_bucket - items_per_bucket))
                if skip_items > 0:
                    # Get the item at the random position to use as exclusive start key
                    scan_params = query_params.copy()
                    scan_params['Limit'] = 1
                    for _ in range(skip_items // 100):  # Handle pagination if skip_items is large
                        response = table.query(**scan_params)
                        if 'LastEvaluatedKey' in response:
                            scan_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                        else:
                            break

                    # Now get the actual items starting from our random position
                    query_params['ExclusiveStartKey'] = response.get('LastEvaluatedKey')

        except Exception as e:
            print(f"Error in random positioning: {str(e)}")
            # Continue without random positioning if it fails

        # Get items from this bucket
        try:
            response = table.query(**query_params)
            all_items.extend(response.get('Items', []))
        except Exception as e:
            print(f"Error querying bucket {bucket}: {str(e)}")
            continue

    # Shuffle all collected items and trim to requested size
    random.shuffle(all_items)
    return [clean_item(item) for item in all_items[:batch_size]]

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create an API Gateway response with proper headers and JSON encoding"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
        
    try:
        body = json.loads(event['body']) if event.get('body') else {}
        batch_size = min(body.get('batchSize', 20), 50)
        rating_filter = body.get('ratingFilter', 'all')
        department_filter = body.get('departmentFilter', 'all')
        
        start_time = time.time()
        
        # Get random reviews
        items = get_random_reviews(batch_size, rating_filter, department_filter)
        
        # Calculate query time
        query_time = time.time() - start_time
        
        # Create response with metadata
        response_data = {
            'reviews': items,
            'metadata': {
                'count': len(items),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'queryTime': round(query_time, 3),
                'filters': {
                    'ratingFilter': rating_filter,
                    'departmentFilter': department_filter
                }
            }
        }
        
        return create_response(200, response_data)
        
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return create_response(500, {
            'error': str(e),
            'message': 'Internal server error'
        })