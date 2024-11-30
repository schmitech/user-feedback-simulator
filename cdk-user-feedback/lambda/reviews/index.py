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
    Get random reviews using an improved sampling strategy:
    1. Query more buckets for better distribution
    2. Use simpler, more reliable random positioning
    3. Get more items initially and randomly sample from them
    """
    all_items = []
    buckets_to_try = random.sample(range(1, 11), k=5)  # Try 5 random buckets instead of 3
    items_per_bucket = batch_size  # Get full batch size from each bucket for better sampling
    
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

        try:
            # Get count first
            count_params = query_params.copy()
            count_params['Select'] = 'COUNT'
            count_result = table.query(**count_params)
            total_in_bucket = count_result['Count']

            if total_in_bucket > 0:
                # Simple random skip
                if total_in_bucket > items_per_bucket:
                    skip_items = random.randint(0, total_in_bucket - items_per_bucket)
                    if skip_items > 0:
                        query_params['Limit'] = skip_items
                        response = table.query(**query_params)
                        if 'LastEvaluatedKey' in response:
                            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                
                # Reset limit for actual query
                query_params['Limit'] = items_per_bucket
                response = table.query(**query_params)
                all_items.extend(response.get('Items', []))

        except Exception as e:
            print(f"Error querying bucket {bucket}: {str(e)}")
            continue

    # If we have more items than needed, randomly sample from them
    if len(all_items) > batch_size:
        all_items = random.sample(all_items, batch_size)
    else:
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