import boto3
import sys
import concurrent.futures
from typing import List, Dict
import time

def get_key_schema(table) -> List[str]:
    """Get the key attribute names from the table schema"""
    return [key['AttributeName'] for key in table.key_schema]

def get_batch_items(table, segment: int, total_segments: int) -> List[Dict]:
    """Scan a segment of the table and return items"""
    return table.scan(
        Segment=segment,
        TotalSegments=total_segments,
        Select='ALL_ATTRIBUTES'
    )['Items']

def delete_batch(table, items: List[Dict], key_attrs: List[str]):
    """Delete a batch of items using batch_writer"""
    with table.batch_writer() as batch:
        for item in items:
            # Extract only the key attributes for deletion
            key_dict = {k: item[k] for k in key_attrs}
            batch.delete_item(Key=key_dict)

def empty_table(profile_name: str, table_name: str, num_threads: int = 16):
    """Empty a DynamoDB table using parallel processing"""
    # Initialize boto3 session with profile
    session = boto3.Session(profile_name=profile_name)
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    # Get key schema first
    key_attrs = get_key_schema(table)
    print(f"Table keys: {key_attrs}")
    
    start_time = time.time()
    items_deleted = 0
    
    print(f"Starting parallel scan with {num_threads} threads...")
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            # Start parallel scans
            futures = [
                executor.submit(get_batch_items, table, segment, num_threads)
                for segment in range(num_threads)
            ]
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                items = future.result()
                if items:
                    # Process items in batches of 25 (DynamoDB limit)
                    for i in range(0, len(items), 25):
                        batch = items[i:i + 25]
                        delete_batch(table, batch, key_attrs)
                        items_deleted += len(batch)
                        print(f"Deleted {items_deleted} items...", end='\r')
        
        elapsed_time = time.time() - start_time
        print(f"\nCompleted! Deleted {items_deleted} items in {elapsed_time:.2f} seconds")
        
    except KeyboardInterrupt:
        print("\nOperation interrupted by user. Cleaning up...")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <aws-profile> <table-name>")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    table_name = sys.argv[2]
    
    empty_table(profile_name, table_name)