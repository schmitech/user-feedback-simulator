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
    echo "Deploy Reviews API CDK stack using specified AWS profile"
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
if ! command -v cdk &> /dev/null; then
    echo -e "${RED}Error: CDK is not installed. Please install it first.${NC}" >&2
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed. Please install it first.${NC}" >&2
    exit 1
fi

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

# Get AWS account details
echo "Verifying AWS credentials..."
account_id=$(aws sts get-caller-identity --profile "$aws_profile" --query Account --output text)
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to get AWS account details. Please check your credentials.${NC}" >&2
    exit 1
fi

# Create timestamp for unique log filename
timestamp=$(date +"%Y%m%d_%H%M%S")
logfile="reviews_api_deployment_${stage}_${timestamp}.out"

# Run the CDK deploy command and capture output
echo -e "${GREEN}Starting CDK deployment:${NC}"
echo "  Profile: ${aws_profile}"
echo "  Stage: ${stage}"
echo -e "${YELLOW}Logging output to: ${logfile}${NC}"

# Deploy command with context variables
deploy_command="cdk deploy '*' \
    --require-approval broadening \
    --profile ${aws_profile} \
    -c stage=${stage}"

# Use tee to capture output instead of script command
$deploy_command 2>&1 | tee "${logfile}"

# Check if the deployment was successful
deployment_exit_code=${PIPESTATUS[0]}  # Get the exit code of the cdk deploy command
if [ $deployment_exit_code -eq 0 ]; then
    echo -e "\n${GREEN}Deployment completed successfully!${NC}"
    echo "Output saved to: ${logfile}"
    
    # Extract and display the API endpoint from the deployment output
    api_endpoint=$(grep -A 1 "ApiUrl" "${logfile}" | tail -n 1 | awk '{print $NF}')
    if [ -n "$api_endpoint" ]; then
        echo -e "\n${GREEN}API Endpoint:${NC} ${api_endpoint}"
        echo -e "\nTest your API with:"
        echo "curl -X POST ${api_endpoint}dev/reviews \\"
        echo "  -H 'Content-Type: application/json' \\"
        echo "  -d '{\"batchSize\": 20}'"
    fi
    
    echo -e "\n${YELLOW}Next steps:${NC}"
    echo "1. Test the API endpoint"
    echo "2. Monitor the CloudWatch logs"
    echo "3. Check the DynamoDB table"
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