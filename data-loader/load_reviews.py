import pandas as pd
import boto3
import uuid
import time
import json
import os
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from boto3.session import Session

# Load environment variables
load_dotenv()

def get_aws_session():
    """Create AWS session with profile from environment variable"""
    profile_name = os.getenv('AWS_PROFILE')
    region_name = os.getenv('AWS_REGION', 'us-east-1')
    
    if not profile_name:
        print("AWS_PROFILE not found in environment variables")
        print("Please set AWS_PROFILE in your .env file")
        return None
        
    try:
        print(f"Attempting to create session with profile: {profile_name}")
        session = boto3.Session(profile_name=profile_name, region_name=region_name)
        return session
    except Exception as e:
        print(f"Error creating AWS session: {str(e)}")
        print(f"Current profile: {profile_name}")
        print("Please ensure your AWS_PROFILE is correctly set in .env file")
        return None

def verify_aws_credentials():
    """Verify AWS credentials are available and valid"""
    try:
        session = get_aws_session()
        if not session:
            return False
            
        # Try to get the caller identity
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print(f"\nAWS Authentication Successful!")
        print(f"Account: {identity['Account']}")
        print(f"UserID: {identity['UserId']}")
        print(f"ARN: {identity['Arn']}")
        print(f"Using Profile: {os.getenv('AWS_PROFILE')}")
        print(f"Using Region: {os.getenv('AWS_REGION', 'us-east-1')}\n")
        return True
    except Exception as e:
        print(f"AWS Authentication Error: {str(e)}")
        print("\nPlease ensure you have:")
        print("1. Logged in using 'aws sso login'")
        print("2. Set the AWS_PROFILE in your .env file")
        print("3. Optionally set AWS_REGION in your .env file")
        return False

def verify_dynamodb_access(table_name):
    """Verify DynamoDB table exists and is accessible"""
    try:
        session = get_aws_session()
        if not session:
            return False
            
        dynamodb = session.resource('dynamodb')
        table = dynamodb.Table(table_name)
        table.table_status
        print(f"DynamoDB table '{table_name}' is accessible")
        return True
    except Exception as e:
        print(f"DynamoDB Access Error: {str(e)}")
        print(f"Please ensure the table '{table_name}' exists and you have the correct permissions")
        return False

def is_valid_review(row):
    """
    Check if a review row is valid based on our criteria:
    - Title should not be empty/null
    - Review text should not be empty/null
    """
    has_title = isinstance(row['Title'], str) and row['Title'].strip() != ''
    has_review = isinstance(row['Review Text'], str) and row['Review Text'].strip() != ''
    return has_title and has_review

def load_reviews_to_dynamodb(table_name=None, batch_size=25):
    """Load reviews into DynamoDB with verification and error handling"""
    
    # Get table name from environment variable if not provided
    if table_name is None:
        stage = os.getenv('STAGE', 'dev')
        table_name = f'ReviewsTable-{stage}'
    
    # First verify AWS credentials
    if not verify_aws_credentials():
        return
    
    # Then verify DynamoDB access
    if not verify_dynamodb_access(table_name):
        return
    
    print("\nStarting data load process...")
    
    try:
        # Read CSV
        df = pd.read_csv('reviews.csv')
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        return
        
    # Initialize counters for reporting
    total_records = len(df)
    valid_records = 0
    skipped_records = 0
    error_records = 0
    
    # Initialize DynamoDB
    session = get_aws_session()
    if not session:
        return
        
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    print(f"Starting to process {total_records} records...")
    start_time = time.time()
    
    try:
        # Process each review
        with table.batch_writer(overwrite_by_pkeys=['reviewId']) as batch:
            for index, row in df.iterrows():
                try:
                    if is_valid_review(row):
                        # Get current timestamp in ISO format with UTC timezone
                        current_time = datetime.now(timezone.utc)
                        
                        # Create review item with both numeric timestamp (for sorting)
                        # and ISO timestamp (for display)
                        review_item = {
                            'reviewId': str(uuid.uuid4()),  # String (partition key)
                            'timestamp': int(current_time.timestamp()),  # Number (sort key)
                            'timestampIso': current_time.isoformat(),  # String (for display)
                            'randomBucket': random.randint(1, 10),  # For RandomAccessIndex GSI
                            'clothingId': str(row['Clothing ID']),
                            'age': int(float(row['Age'])) if pd.notna(row['Age']) else 0,
                            'title': str(row['Title']).strip(),
                            'review': str(row['Review Text']).strip(),
                            'rating': int(float(row['Rating'])) if pd.notna(row['Rating']) else 0,
                            'recommended': bool(row['Recommended IND']),
                            'division': str(row['Division Name']) if pd.notna(row['Division Name']) else '',
                            'department': str(row['Department Name']) if pd.notna(row['Department Name']) else '',
                            'class': str(row['Class Name']) if pd.notna(row['Class Name']) else ''
                        }
                        batch.put_item(Item=review_item)
                        valid_records += 1
                    else:
                        skipped_records += 1
                except Exception as e:
                    error_records += 1
                    print(f"Error processing record {index}: {str(e)}")
                    print(f"Problematic row: {row}")
                    continue
                
                # Print progress every 100 records
                if (index + 1) % 100 == 0:
                    elapsed_time = time.time() - start_time
                    records_per_second = (index + 1) / elapsed_time
                    print(f"Processed {index + 1} records... "
                          f"({records_per_second:.2f} records/second)")
    
    except Exception as e:
        print(f"Error during batch writing: {str(e)}")
        return
    
    # Calculate final statistics
    elapsed_time = time.time() - start_time
    records_per_second = total_records / elapsed_time
    
    # Print final statistics
    print("\nLoad completed!")
    print(f"Total records processed: {total_records}")
    print(f"Valid records loaded: {valid_records}")
    print(f"Skipped records: {skipped_records}")
    print(f"Error records: {error_records}")
    print(f"Success rate: {(valid_records/total_records)*100:.2f}%")
    print(f"Total time: {elapsed_time:.2f} seconds")
    print(f"Average speed: {records_per_second:.2f} records/second")

if __name__ == "__main__":
    try:
        load_reviews_to_dynamodb()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")