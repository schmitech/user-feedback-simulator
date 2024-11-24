import boto3
import os
from dotenv import load_dotenv

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
        return None

def create_reviews_table():
    """Create DynamoDB table for reviews with proper schema"""
    try:
        session = get_aws_session()
        if not session:
            return False
            
        dynamodb = session.resource('dynamodb')
        table_name = os.getenv('DYNAMODB_TABLE', 'reviews-table')
        
        # Check if table already exists
        existing_tables = dynamodb.tables.all()
        if table_name in [table.name for table in existing_tables]:
            print(f"Table {table_name} already exists")
            return True
            
        # Create table
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'reviewId',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'timestamp',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'reviewId',
                    'AttributeType': 'S'  # String
                },
                {
                    'AttributeName': 'timestamp',
                    'AttributeType': 'N'  # Number
                }
            ],
            BillingMode='PAY_PER_REQUEST'  # On-demand capacity
        )
        
        # Wait for table to be created
        print(f"Creating table {table_name}...")
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
        print(f"Table {table_name} created successfully!")
        
        return True
        
    except Exception as e:
        print(f"Error creating table: {str(e)}")
        return False

if __name__ == "__main__":
    create_reviews_table()