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

def validate_environment():
    """Validate required environment variables are present"""
    required_vars = ['TABLE_NAME', 'TABLE_GSI']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

def clean_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up item data before returning"""
    integer_fields = {'age', 'rating', 'randomBucket'}
    
    for field in integer_fields:
        if field in item and isinstance(item[field], (Decimal, float)):
            item[field] = int(float(item[field]))
    
    return item

def get_random_reviews(batch_size: int, rating_filter: str = 'all', department_filter: str = 'all') -> List[Dict[str, Any]]:
    """
    Get random reviews with improved distribution between positive and negative reviews
    """
    all_items = []
    buckets_to_try = random.sample(range(1, 11), k=5)
    
    # Calculate target numbers for positive and negative reviews
    if rating_filter == 'all':
        negative_target = batch_size // 2
        positive_target = batch_size - negative_target
    else:
        negative_target = batch_size if rating_filter == 'negative' else 0
        positive_target = batch_size if rating_filter == 'positive' else 0
    
    for bucket in buckets_to_try:
        query_params = {
            'IndexName': os.environ['TABLE_GSI'],
            'KeyConditionExpression': 'randomBucket = :bucket',
            'ExpressionAttributeValues': {
                ':bucket': bucket
            }
        }
        
        # Build filter expression
        filter_expressions = []
        if department_filter != 'all':
            filter_expressions.append('department = :dept')
            query_params['ExpressionAttributeValues'][':dept'] = department_filter
            
        if rating_filter == 'positive':
            filter_expressions.append('rating >= :min_rating')
            query_params['ExpressionAttributeValues'][':min_rating'] = 4
        elif rating_filter == 'negative':
            filter_expressions.append('rating < :max_rating')
            query_params['ExpressionAttributeValues'][':max_rating'] = 4
            
        if filter_expressions:
            query_params['FilterExpression'] = ' AND '.join(filter_expressions)

        try:
            response = table.query(**query_params)
            items = response.get('Items', [])
            
            if rating_filter == 'all':
                # Split items into positive and negative
                positive_items = [item for item in items if item['rating'] >= 4]
                negative_items = [item for item in items if item['rating'] < 4]
                
                # Add items maintaining the desired ratio
                if len(positive_items) > 0 and positive_target > 0:
                    all_items.extend(random.sample(positive_items, min(len(positive_items), positive_target)))
                    positive_target = max(0, positive_target - len(positive_items))
                
                if len(negative_items) > 0 and negative_target > 0:
                    all_items.extend(random.sample(negative_items, min(len(negative_items), negative_target)))
                    negative_target = max(0, negative_target - len(negative_items))
            else:
                all_items.extend(items)

        except Exception as e:
            print(f"Error querying bucket {bucket}: {str(e)}")
            continue
        
        # If we have enough items, stop querying
        if len(all_items) >= batch_size:
            break

    # Shuffle and limit to batch size
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
    try:
        validate_environment()
    except EnvironmentError as e:
        return create_response(500, {
            'error': str(e),
            'message': 'Lambda configuration error'
        })
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
        
    try:
        body = json.loads(event['body']) if event.get('body') else {}
        batch_size = min(body.get('batchSize', 20), 50)
        rating_filter = body.get('ratingFilter', 'all')
        department_filter = body.get('departmentFilter', 'all')
        
        start_time = time.time()
        
        # Get random reviews with balanced distribution
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