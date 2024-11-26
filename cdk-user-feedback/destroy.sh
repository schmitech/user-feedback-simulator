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
    echo "Destroy Reviews and Sentiment Analysis API CDK stacks and clean up resources"
    echo
    echo "Arguments:"
    echo "  profile-name    AWS Profile Name"
    echo "  stage          Deployment stage (dev/prod)"
    echo
    echo "Example:"
    echo "  $0 dev-profile dev"
    echo
    echo "Actions performed:"
    echo "  1. Destroys both Reviews API and Sentiment Analysis stacks"
    echo "  2. Removes all DynamoDB tables"
    echo "  3. Deletes CloudWatch log groups"
    echo "  4. Deletes API Gateways"
    echo "  5. Removes Lambda functions and layers"
    echo "  6. Cleans up local CDK files"
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
    echo -e "${RED}WARNING: This will destroy all resources in the $STAGE environment including:${NC}"
    echo "  - Reviews API Stack (ReviewsStack-${STAGE})"
    echo "  - Sentiment Analysis Stack (SentimentStack-${STAGE})"
    echo "  - All associated resources (DynamoDB tables, Lambda functions, API Gateways, etc.)"
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

    # 1. List resources before destruction
    echo -e "\n${YELLOW}Resources to be destroyed:${NC}"
    echo "DynamoDB Tables:"
    run_aws_command aws dynamodb list-tables --profile "$AWS_PROFILE" --query "TableNames[?contains(@, '${STAGE}')]" --output text
    
    echo -e "\nLambda Functions:"
    run_aws_command aws lambda list-functions --profile "$AWS_PROFILE" --query "Functions[?contains(FunctionName, '${STAGE}')].FunctionName" --output text
    
    echo -e "\nAPI Gateways:"
    run_aws_command aws apigateway get-rest-apis --profile "$AWS_PROFILE" --query "items[?contains(name, '${STAGE}')].name" --output text

    # 2. Destroy CDK stacks
    echo -e "\n${YELLOW}Destroying CDK stacks...${NC}"
    cdk destroy --all --profile "$AWS_PROFILE" --force -c stage="$STAGE"

    # 3. Clean up CloudWatch log groups
    echo -e "\n${YELLOW}Cleaning up CloudWatch log groups...${NC}"
    for log_group in $(aws logs describe-log-groups \
        --profile "$AWS_PROFILE" \
        --query "logGroups[?contains(logGroupName, '${STAGE}')].logGroupName" \
        --output text); do
        echo "Deleting log group: $log_group"
        run_aws_command aws logs delete-log-group --log-group-name "$log_group" --profile "$AWS_PROFILE"
    done

    # 4. Delete CDKToolkit CloudFormation stack if requested
    echo -e "\n${YELLOW}Do you want to delete the CDKToolkit CloudFormation stack?${NC}"
    echo "WARNING: Only do this if no other CDK apps are deployed in this account/region"
    read -p "Delete CDKToolkit stack? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Deleting CDKToolkit CloudFormation stack"
        run_aws_command aws cloudformation delete-stack --stack-name CDKToolkit --profile "$AWS_PROFILE"
        # Wait for stack deletion
        echo "Waiting for CDKToolkit stack deletion..."
        run_aws_command aws cloudformation wait stack-delete-complete --stack-name CDKToolkit --profile "$AWS_PROFILE"
    fi

    # 5. Clean up local CDK files
    echo -e "\n${YELLOW}Clearing CDK context and local files...${NC}"
    cdk context --clear
    rm -rf cdk.context.json cdk.out user_feedback_deployment_${STAGE}_*.out

    echo -e "\n${GREEN}Cleanup completed successfully!${NC}"
    
    # Final instructions
    echo -e "\n${YELLOW}Additional manual verification steps:${NC}"
    echo "1. Verify in AWS Console that all resources have been removed:"
    echo "   CloudFormation: https://${REGION}.console.aws.amazon.com/cloudformation/home?region=${REGION}"
    echo "   DynamoDB: https://${REGION}.console.aws.amazon.com/dynamodbv2/home?region=${REGION}#tables"
    echo "   Lambda: https://${REGION}.console.aws.amazon.com/lambda/home?region=${REGION}#/functions"
    echo "   API Gateway: https://${REGION}.console.aws.amazon.com/apigateway/main/apis?region=${REGION}"
    echo "   CloudWatch: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups"
    echo "2. Check for any remaining Lambda layers"
    echo "3. Verify all log groups have been cleaned up"
}

# Main execution
confirm_destruction
cleanup