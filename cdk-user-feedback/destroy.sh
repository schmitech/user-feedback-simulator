#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status.

# Color definitions
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

# Function to display usage information
show_help() {
    echo "Usage: $0 <profile-name> <stage>"
    echo
    echo "Destroy Reviews API CDK stacks and clean up resources"
    echo
    echo "Arguments:"
    echo "  profile-name    AWS Profile Name"
    echo "  stage          Deployment stage (dev/prod)"
    echo
    echo "Example:"
    echo "  $0 dev-profile dev"
    echo
    echo "Actions performed:"
    echo "  1. Destroys Reviews API stack"
    echo "  2. Removes DynamoDB tables"
    echo "  3. Deletes CloudWatch log groups"
    echo "  4. Deletes API Gateway"
    echo "  5. Cleans up local CDK files"
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
AWS_PROFILE="$1"
STAGE="$2"

# Validate stage
if [ "$STAGE" != "dev" ] && [ "$STAGE" != "prod" ]; then
    echo -e "${RED}Error: Stage must be either 'dev' or 'prod'${NC}" >&2
    exit 1
fi

# Check for required tools
for tool in aws cdk jq; do
    if ! command -v $tool &> /dev/null; then
        echo -e "${RED}Error: $tool is not installed. Please install it first.${NC}" >&2
        exit 1
    fi
done

# Function to run AWS CLI commands with proper error handling
run_aws_command() {
    if ! "$@"; then
        echo -e "${RED}Error executing: $*${NC}" >&2
        exit 1
    fi
}

# Function to confirm destruction
confirm_destruction() {
    echo -e "${RED}WARNING: This will destroy all resources in the $STAGE environment.${NC}"
    echo -e "${YELLOW}This action cannot be undone.${NC}"
    read -p "Are you sure you want to continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting."
        exit 1
    fi
}

# Main cleanup process
cleanup() {
    echo -e "${YELLOW}Starting cleanup process for stage: $STAGE${NC}"
    
    # Get account ID and region
    ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
    REGION=$(aws configure get region --profile "$AWS_PROFILE")

    # 1. Destroy CDK stacks
    echo "Destroying CDK stacks..."
    cdk destroy --all --profile "$AWS_PROFILE" --force -c stage="$STAGE"

    # 4. Delete CDKToolkit CloudFormation stack if no other CDK apps are using it
    echo "Do you want to delete the CDKToolkit CloudFormation stack? (Only do this if no other CDK apps are deployed)"
    read -p "Delete CDKToolkit stack? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Deleting CDKToolkit CloudFormation stack"
        run_aws_command aws cloudformation delete-stack --stack-name CDKToolkit --profile "$AWS_PROFILE"
    fi

    # 5. Clean up local CDK files
    echo "Clearing CDK context and local files..."
    cdk context --clear
    rm -rf cdk.context.json cdk.out reviews_api_deployment_${STAGE}_*.out

    echo -e "${GREEN}Cleanup completed successfully!${NC}"
    
    # Final instructions
    echo -e "\n${YELLOW}Additional manual cleanup that may be required:${NC}"
    echo "1. Check AWS Console for any remaining resources"
    echo "2. Check CloudWatch for any remaining log groups"
    echo "3. Verify API Gateway cleanup"
    echo "4. Check for any remaining Lambda functions"
}

# Main execution
confirm_destruction
cleanup