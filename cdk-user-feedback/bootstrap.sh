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
    echo "Bootstrap AWS CDK for Reviews API"
    echo
    echo "Arguments:"
    echo "  profile-name    AWS Profile Name"
    echo "  stage          Deployment stage (dev/prod)"
    echo
    echo "Example:"
    echo "  $0 dev-profile dev"
    echo
    echo "Note: Creates and configures:"
    echo "  - CDK bootstrap stack"
    echo "  - Required IAM roles"
}

# Show help if requested
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    exit 0
fi

# Check if required arguments are provided
if [ $# -ne 2 ]; then
    echo -e "${RED}Error: Both profile name and stage are required${NC}" >&2
    show_help
    exit 1
fi

# Store the arguments
profile_name="$1"
stage="$2"

# Validate stage and set environment name
if [ "$stage" = "dev" ]; then
    environment="Development"
elif [ "$stage" = "prod" ]; then
    environment="Production"
else
    echo -e "${RED}Error: Stage must be either 'dev' or 'prod'${NC}" >&2
    exit 1
fi

# Check for required tools
for tool in aws cdk; do
    if ! command -v $tool &> /dev/null; then
        echo -e "${RED}Error: $tool is not installed. Please install it first.${NC}" >&2
        exit 1
    fi
done

# Get account and region information
account_id=$(aws sts get-caller-identity --profile "$profile_name" --query Account --output text)
region=$(aws configure get region --profile "$profile_name")
bootstrap_bucket="reviews-api-bootstrap-${stage}"

# Print configuration
echo -e "${GREEN}Using configuration:${NC}"
echo "  Account ID: $account_id"
echo "  Region: $region"
echo "  Bootstrap Bucket: $bootstrap_bucket"
echo "  Stage: $stage"
echo "  Environment: $environment"
echo

# Execute CDK bootstrap command
echo "Bootstrapping CDK..."
cdk bootstrap \
    --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
    --qualifier hnb659fds \
    aws://${account_id}/${region} \
    --profile "${profile_name}" \
    --tags Project=ReviewsAPI \
    --tags Environment="${environment}" \
    --tags ManagedBy=CDK

echo -e "\n${GREEN}Bootstrap completed successfully!${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Deploy the stack using:"
echo "   cdk deploy '*' -c stage=$stage --profile $profile_name"
echo
echo "To view the bootstrap stack in CloudFormation:"
echo "https://${region}.console.aws.amazon.com/cloudformation/home?region=${region}#/stacks"