import json
import boto3
import uuid
import os
import requests
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

comprehend = boto3.client('comprehend')
dynamodb = boto3.resource('dynamodb')

def index_to_elasticsearch(data: Dict[str, Any]) -> None:
    """Index document to Elasticsearch"""
    es_endpoint = os.environ['ES_ENDPOINT']
    es_api_key = os.environ['ES_API_KEY']
    es_index = os.environ['ES_INDEX']
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"ApiKey {es_api_key}"
    }
    
    # Convert Decimal objects to float for ES
    def decimal_to_float(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: decimal_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [decimal_to_float(x) for x in obj]
        return obj
    
    es_data = decimal_to_float(data)
    
    document_id = es_data['reviewId']
    url = f"{es_endpoint}/{es_index}/_doc/{document_id}"
    
    try:
        response = requests.put(
            url,
            headers=headers,
            json=es_data,
            verify=True,
            timeout=30
        )
        
        if not response.ok:
            print(f"ES indexing failed for document {document_id}: {response.text}")
            raise RuntimeError(f"Failed to index to Elasticsearch: {response.text}")
            
        print(f"Successfully indexed document {document_id} to Elasticsearch")
            
    except requests.exceptions.Timeout:
        print(f"Timeout while indexing document {document_id}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"Error indexing document {document_id}: {str(e)}")
        raise

def handle_error(error: Exception, feedback_id: str) -> Dict[str, Any]:
    print(f"Error processing feedback {feedback_id}: {str(error)}")
    return {
        'statusCode': 500,
        'body': json.dumps({
            'message': 'Error processing feedback',
            'feedbackId': feedback_id,
            'error': str(error)
        })
    }

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)

def convert_floats_to_decimals(obj):
    """Recursively converts all float values to Decimal"""
    if isinstance(obj, dict):
        return {key: convert_floats_to_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(value) for value in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    return obj

def get_iso_timestamp() -> str:
    """Generate current timestamp in ISO format"""
    return datetime.now(timezone.utc).isoformat()

def process_feedback(review_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # Extract the review text for sentiment analysis
        review_text = review_data.get('review', '')
        
        sentiment_response = comprehend.detect_sentiment(
            Text=review_text,
            LanguageCode='en'
        )

        phrases_response = comprehend.detect_key_phrases(
            Text=review_text,
            LanguageCode='en'
        )

        # Generate ISO timestamp if not provided
        timestamp_iso = review_data.get('reviewDateTime') or get_iso_timestamp()

        # Convert numeric timestamp to string if it exists
        timestamp = review_data.get('timestamp')
        if timestamp is not None:
            timestamp = str(timestamp)

        # Build enriched review data
        processed_data = {
            # Original review data
            'reviewId': review_data.get('reviewId', str(uuid.uuid4())),
            'timestamp': timestamp,
            'reviewDateTime': timestamp_iso,
            'review': review_text,
            'title': review_data.get('title'),
            'rating': review_data.get('rating'),
            'recommended': review_data.get('recommended'),
            'age': review_data.get('age'),
            
            # Product categorization
            'department': review_data.get('department'),
            'division': review_data.get('division'),
            'class': review_data.get('class'),
            'clothingId': review_data.get('clothingId'),
            'randomBucket': review_data.get('randomBucket'),
            
            # Sentiment analysis results
            'sentiment': sentiment_response['Sentiment'],
            'sentimentScore': convert_floats_to_decimals(sentiment_response['SentimentScore']),
            'keyPhrases': [phrase['Text'] for phrase in phrases_response['KeyPhrases']],
            
            # Metadata
            'processingTimestamp': get_iso_timestamp(),
            'source': 'review-analysis'
        }

        return processed_data

    except Exception as e:
        raise RuntimeError(f"Error in sentiment analysis: {str(e)}")

def handler(event, context):
    try:
        body = json.loads(event['body'])
        
        if not isinstance(body, dict) or 'reviews' not in body:
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'Invalid request format. Expected reviews array.'})
            }

        processed_reviews = []
        errors = []
        
        # Get remaining lambda execution time
        time_remaining_ms = context.get_remaining_time_in_millis()
        
        for review in body['reviews']:
            # Check if we have enough time left to process another review (e.g., 10 seconds)
            if context.get_remaining_time_in_millis() < 10000:
                errors.append({
                    'reviewId': 'batch',
                    'error': 'Lambda timeout approaching - batch processing interrupted'
                })
                break
                
            if not review.get('review'):
                continue
                
            try:
                processed_review = process_feedback(review)
                
                # Store in DynamoDB first
                table = dynamodb.Table(os.environ['FEEDBACK_TABLE'])
                table.put_item(Item=processed_review)
                
                # Then index in Elasticsearch
                index_to_elasticsearch(processed_review)
                
                processed_reviews.append(processed_review)
                
            except Exception as e:
                print(f"Error processing review: {str(e)}")
                errors.append({
                    'reviewId': review.get('reviewId', 'unknown'),
                    'error': str(e)
                })

        response_body = {
            'message': 'Reviews processed successfully',
            'processedCount': len(processed_reviews),
            'errorCount': len(errors),
            'timestamp': get_iso_timestamp()
        }
        
        if errors:
            response_body['errors'] = errors

        return {
            'statusCode': 200 if not errors else 207,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response_body)
        }

    except Exception as e:
        return handle_error(e, 'batch-processing')