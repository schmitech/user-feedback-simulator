# Data Loader

## This project loads sample user reviews into an AWS DynamoDB table

### Configure your AWS SSO Profile
```bash
aws sso configure
```

### Look in your AWS credentials file
```bash
cat ~/.aws/config
aws sts get-caller-identity --profile your-aws-sso-proofile
```

### Modify .env file with your settings, example:
```bash
AWS_PROFILE=MyAWSAccount
AWS_REGION=us-east-1
DYNAMODB_TABLE=reviews-table
```

```bash
cd data-loader

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate

# install the requirements:
pip install -r requirements.txt

# Create the DynamoDB table
python create_table.py

# Load the records from reviews.csv into DynamoDB:
python load_reviews.py
```

Then go to AWS console and check the new DynamoDB table, making sure records exist.