import pandas as pd
import boto3
import uuid
import time
import json
import os
import random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from boto3.session import Session

# Load environment variables
load_dotenv()

def get_aws_session():
    """Create AWS session with profile from environment variable"""
    profile_name = os.getenv('AWS_PROFILE')
    region_name = os.getenv('AWS_REGION', 'ca-central-1')
    
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

def get_weighted_random_timestamp(months_ago=6):
    """
    Generate a random timestamp with realistic patterns:
    - More reviews on weekends
    - More reviews in evening hours
    - More reviews in recent months
    - More reviews during shopping hours
    """
    now = datetime.now(timezone.utc)
    six_months_ago = now - timedelta(days=30 * months_ago)
    
    # Step 1: Get a random date with weight towards recent dates
    days_diff = (now - six_months_ago).days
    # Use beta distribution to weight towards recent dates (alpha=2, beta=1)
    random_day = six_months_ago + timedelta(
        days=int(random.betavariate(2, 1) * days_diff)
    )
    
    # Step 2: Adjust for day of week preferences
    # Keep trying until we get a date that passes our probability check
    while True:
        # Higher probability for weekends
        day_weights = {
            0: 0.7,  # Monday
            1: 0.7,  # Tuesday
            2: 0.7,  # Wednesday
            3: 0.8,  # Thursday
            4: 0.9,  # Friday
            5: 1.0,  # Saturday
            6: 1.0,  # Sunday
        }
        if random.random() <= day_weights[random_day.weekday()]:
            break
        random_day = six_months_ago + timedelta(
            days=int(random.betavariate(2, 1) * days_diff)
        )
    
    # Step 3: Generate hour of day with realistic patterns
    # Probability distribution for each hour (24-hour format)
    hour_weights = {
        0: 0.3,   # 12 AM
        1: 0.2,   # 1 AM
        2: 0.1,   # 2 AM
        3: 0.05,  # 3 AM
        4: 0.05,  # 4 AM
        5: 0.05,  # 5 AM
        6: 0.1,   # 6 AM
        7: 0.2,   # 7 AM
        8: 0.3,   # 8 AM
        9: 0.4,   # 9 AM
        10: 0.6,  # 10 AM
        11: 0.7,  # 11 AM
        12: 0.8,  # 12 PM
        13: 0.7,  # 1 PM
        14: 0.6,  # 2 PM
        15: 0.6,  # 3 PM
        16: 0.7,  # 4 PM
        17: 0.8,  # 5 PM
        18: 0.9,  # 6 PM
        19: 1.0,  # 7 PM - Peak
        20: 1.0,  # 8 PM - Peak
        21: 0.9,  # 9 PM
        22: 0.7,  # 10 PM
        23: 0.5,  # 11 PM
    }
    
    # Keep trying until we get an hour that passes our probability check
    while True:
        hour = random.randint(0, 23)
        if random.random() <= hour_weights[hour]:
            break
    
    # Step 4: Generate random minute and second
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    
    # Combine everything into a final timestamp
    final_datetime = random_day.replace(
        hour=hour, 
        minute=minute, 
        second=second,
        microsecond=0
    )
    
    return final_datetime

def analyze_distribution(timestamps, total_records):
    """Analyze and print the distribution of timestamps"""
    # Analyze day of week distribution
    day_counts = {i: 0 for i in range(7)}
    hour_counts = {i: 0 for i in range(24)}
    month_counts = {}
    
    for ts in timestamps:
        day_counts[ts.weekday()] += 1
        hour_counts[ts.hour] += 1
        month_key = ts.strftime('%Y-%m')
        month_counts[month_key] = month_counts.get(month_key, 0) + 1
    
    # Print distribution analysis
    print("\nTimestamp Distribution Analysis:")
    print("\nDay of Week Distribution:")
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for i, day in enumerate(days):
        percentage = (day_counts[i] / total_records) * 100
        print(f"{day}: {percentage:.1f}%")
    
    print("\nHour Distribution (top 5 peak hours):")
    sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for hour, count in sorted_hours:
        percentage = (count / total_records) * 100
        print(f"{hour:02d}:00: {percentage:.1f}%")
    
    print("\nMonthly Distribution:")
    for month in sorted(month_counts.keys()):
        percentage = (month_counts[month] / total_records) * 100
        print(f"{month}: {percentage:.1f}%")

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
    
    # Store timestamps for distribution analysis
    timestamps = []
    
    try:
        # Process each review
        with table.batch_writer(overwrite_by_pkeys=['reviewId']) as batch:
            for index, row in df.iterrows():
                try:
                    if is_valid_review(row):
                        # Get random timestamp with realistic patterns
                        random_datetime = get_weighted_random_timestamp()
                        timestamps.append(random_datetime)
                        
                        review_item = {
                            'reviewId': str(uuid.uuid4()),
                            'timestamp': int(random_datetime.timestamp()),
                            'timestampIso': random_datetime.isoformat(),
                            'randomBucket': random.randint(1, 10),
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
    print(f"\nReviews are spread between: ")
    print(f"Start date: {(datetime.now(timezone.utc) - timedelta(days=30 * 6)).isoformat()}")
    print(f"End date: {datetime.now(timezone.utc).isoformat()}")
    
    # Print distribution analysis
    analyze_distribution(timestamps, valid_records)

if __name__ == "__main__":
    try:
        load_reviews_to_dynamodb()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")