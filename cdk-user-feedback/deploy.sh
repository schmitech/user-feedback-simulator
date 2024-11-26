#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status.

# Color definitions
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Function to display usage information
show_help() {
    echo "Usage: $0 <profile-name> <stage>"
    echo
    echo "Deploy Reviews and Sentiment Analysis API CDK stacks using specified AWS profile"
    echo
    echo "Arguments:"
    echo "  profile-name    AWS Profile Name"
    echo "  stage          Deployment stage (dev/prod)"
    echo
    echo "Example:"
    echo "  $0 dev-profile dev"
    echo
    echo "Output:"
    echo "  Creates a log file with timestamp in the current directory"
}

validate_env_file() {
    local stage="$1"
    
    # Check if .env file exists
    if [ ! -f ".env" ]; then
        echo -e "${RED}Error: .env file not found${NC}" >&2
        echo "Please create .env file with required variables:"
        echo "ES_ENDPOINT=your-elasticsearch-endpoint"
        echo "ES_API_KEY=your-api-key"
        echo "ES_INDEX=your-index"
        exit 1
    fi

    # Source the .env file
    set -a
    source .env
    set +a

    # Validate required variables
    declare -a required_vars=("ES_ENDPOINT" "ES_API_KEY" "ES_INDEX")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo -e "${RED}Error: Missing required environment variables:${NC}" >&2
        printf '%s\n' "${missing_vars[@]}"
        exit 1
    fi

    # Validate URL format for ES_ENDPOINT
    if ! [[ "$ES_ENDPOINT" =~ ^https?:// ]]; then
        echo -e "${RED}Error: ES_ENDPOINT must start with http:// or https://${NC}" >&2
        exit 1
    fi
}

check_and_delete_log_groups() {
    local aws_profile="$1"
    local stage="$2"
    
    echo -e "${YELLOW}Checking for existing log groups...${NC}"
    
    # List of log groups to check
    declare -a log_groups=(
        "/aws/lambda/process-feedback-${stage}"
        "/aws/apigateway/feedback-analysis-${stage}"
    )
    
    for log_group in "${log_groups[@]}"; do
        if aws logs describe-log-groups \
            --log-group-name-prefix "$log_group" \
            --profile "$aws_profile" \
            --query "logGroups[?logGroupName=='$log_group'].logGroupName" \
            --output text | grep -q "$log_group"; then
            
            echo -e "${YELLOW}Found existing log group: $log_group${NC}"
            read -p "Do you want to delete this log group? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Deleting log group: $log_group"
                aws logs delete-log-group \
                    --log-group-name "$log_group" \
                    --profile "$aws_profile"
                echo "Log group deleted successfully"
            else
                echo -e "${RED}Deployment might fail if log groups already exist${NC}"
            fi
        fi
    done
}

# Show help if requested
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    exit 0
fi

# Check if required arguments are provided
if [ $# -ne 2 ]; then
    echo -e "${RED}Error: Both AWS profile name and stage are required${NC}" >&2
    show_help
    exit 1
fi

# Store the arguments
aws_profile="$1"
stage="$2"

# Validate stage
if [ "$stage" != "dev" ] && [ "$stage" != "prod" ]; then
    echo -e "${RED}Error: Stage must be either 'dev' or 'prod'${NC}" >&2
    exit 1
fi

# Ensure required tools are installed
for tool in cdk aws node; do
    if ! command -v $tool &> /dev/null; then
        echo -e "${RED}Error: $tool is not installed. Please install it first.${NC}" >&2
        exit 1
    fi
done

# Verify AWS profile exists
if ! aws configure list --profile "$aws_profile" &> /dev/null; then
    echo -e "${RED}Error: AWS profile '$aws_profile' not found. Please check your AWS credentials.${NC}" >&2
    exit 1
fi

# Check if cdk.json exists
if [ ! -f "cdk.json" ]; then
    echo -e "${RED}Error: cdk.json not found. Please ensure you're in the correct directory.${NC}" >&2
    exit 1
fi

# Create timestamp for unique log filename
timestamp=$(date +"%Y%m%d_%H%M%S")
logfile="user_feedback_deployment_${stage}_${timestamp}.out"

# Run the CDK deploy command and capture output
echo -e "${GREEN}Starting CDK deployment:${NC}"
echo "  Profile: ${aws_profile}"
echo "  Stage: ${stage}"
echo "  Elasticsearch Endpoint: $ES_ENDPOINT"
echo "  Elasticsearch Index: $ES_INDEX"
echo -e "${YELLOW}Logging output to: ${logfile}${NC}"

# Pre-deployment checks
echo -e "${YELLOW}Running pre-deployment checks...${NC}"

# 1. Validate environment
validate_env_file "$stage"

# 2. Check existing log groups
check_and_delete_log_groups "$aws_profile" "$stage"

# 3. Verify AWS credentials
echo "Verifying AWS credentials..."
if ! aws sts get-caller-identity --profile "$aws_profile" &>/dev/null; then
    echo -e "${RED}Error: Invalid AWS credentials or profile${NC}" >&2
    exit 1
fi

# 4. Check CDK bootstrap status
echo "Checking CDK bootstrap status..."
if ! aws cloudformation describe-stacks \
    --stack-name "CDKToolkit" \
    --profile "$aws_profile" &>/dev/null; then
    echo -e "${YELLOW}CDK not bootstrapped. Running bootstrap...${NC}"
    cdk bootstrap \
        --profile "$aws_profile" \
        -c stage="$stage"
fi

# Now proceed with deployment
echo -e "${GREEN}All checks passed. Starting deployment...${NC}"

# Deploy command with context variables
deploy_command="cdk deploy --all \
    --require-approval broadening \
    --profile ${aws_profile} \
    -c stage=${stage}"

# Use tee to capture output instead of script command
$deploy_command 2>&1 | tee "${logfile}"

# Check if the deployment was successful
deployment_exit_code=${PIPESTATUS[0]}
if [ $deployment_exit_code -eq 0 ]; then
    echo -e "\n${GREEN}Deployment completed successfully!${NC}"
    echo "Output saved to: ${logfile}"
    
    # Extract and display both API endpoints from the deployment output
    reviews_endpoint=$(grep -A 1 "ReviewsEndpoint" "${logfile}" | tail -n 1 | awk '{print $NF}')
    sentiment_endpoint=$(grep -A 1 "ApiEndpoint.*FeedbackAnalysisStack" "${logfile}" | tail -n 1 | awk '{print $NF}')
    
    echo -e "\n${GREEN}API Endpoints:${NC}"
    if [ -n "$reviews_endpoint" ]; then
        echo -e "\nReviews API:"
        echo "curl -X POST ${reviews_endpoint} \\"
        echo "  -H 'Content-Type: application/json' \\"
        echo "  -d '{\"batchSize\": 20}'"
    fi
    
    if [ -n "$sentiment_endpoint" ]; then
        echo -e "\nSentiment API:"
        echo "curl -X POST ${sentiment_endpoint}feedback \\"
        echo "  -H 'Content-Type: application/json' \\"
        echo "  -d '{\"reviews\": [{\"reviewId\": \"123\", \"review\": \"Great service!\", \"rating\": 5, \"department\": \"Clothing\", \"randomBucket\": 1}]}'"
    fi
    
    echo -e "\n${YELLOW}Next steps:${NC}"
    echo "1. Test both API endpoints"
    echo "2. Monitor the CloudWatch logs"
    echo "3. Check the DynamoDB tables"
else
    echo -e "\n${RED}Deployment failed. Check ${logfile} for details.${NC}" >&2
    exit 1
fi

# Print monitoring URLs
region=$(aws configure get region --profile "$aws_profile")
echo -e "\n${YELLOW}Useful links:${NC}"
echo "CloudFormation console:"
echo "https://${region}.console.aws.amazon.com/cloudformation/home?region=${region}"
echo
echo "CloudWatch Logs:"
echo "https://${region}.console.aws.amazon.com/cloudwatch/home?region=${region}#logsV2:log-groups"
echo
echo "DynamoDB Tables:"
echo "https://${region}.console.aws.amazon.com/dynamodbv2/home?region=${region}#tables"