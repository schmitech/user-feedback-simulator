import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as path from 'path';
import { Construct } from 'constructs';

// Define the interface for stack props
export interface ReviewsStackProps extends cdk.StackProps {
  stage: string;
}

export class ReviewsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ReviewsStackProps) {
    super(scope, id, props);

    // Use stage from props instead of context
    const stage = props.stage;

    // DynamoDB table
    const reviewsTable = new dynamodb.Table(this, 'ReviewsTable', {
      tableName: `ReviewsTable-${stage}`,
      partitionKey: { name: 'reviewId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Add GSI for random access
    reviewsTable.addGlobalSecondaryIndex({
      indexName: 'RandomAccessIndex',
      partitionKey: { name: 'randomBucket', type: dynamodb.AttributeType.NUMBER },
      sortKey: { name: 'reviewId', type: dynamodb.AttributeType.STRING },
    });

    // Lambda function
    const getReviewsFunction = new lambda.Function(this, 'GetReviewsFunction', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'index.lambda_handler',  // Matches the function name in your Python code
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/reviews')),
      environment: {
        TABLE_NAME: reviewsTable.tableName,
        TABLE_GSI: 'RandomAccessIndex',  // This matches the GSI reference in your Python code
      },
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
    });

    // Grant Lambda function read permissions on DynamoDB table
    reviewsTable.grantReadData(getReviewsFunction);

    // API Gateway
    const api = new apigateway.RestApi(this, 'ReviewsApi', {
      restApiName: `Reviews-Service-${stage}`,
      description: 'API for fetching random reviews',
      deployOptions: {
        stageName: stage,
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: ['*'],  // Be more specific in production
        allowMethods: ['POST', 'OPTIONS'],
        allowHeaders: [
          'Content-Type',
          'X-Amz-Date',
          'Authorization',
          'X-Api-Key',
          'X-Amz-Security-Token',
        ],
        maxAge: cdk.Duration.days(1),
      },
    });

    // API Gateway integration with proper response configuration
    const reviews = api.root.addResource('reviews');
    
    const integration = new apigateway.LambdaIntegration(getReviewsFunction, {
      proxy: true,
      integrationResponses: [{
        statusCode: '200',
        responseParameters: {
          'method.response.header.Access-Control-Allow-Origin': "'*'",
        },
      }],
    });

    reviews.addMethod('POST', integration, {
      methodResponses: [{
        statusCode: '200',
        responseParameters: {
          'method.response.header.Access-Control-Allow-Origin': true,
        },
      }],
    });

    // Output the API URL
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: api.url,
      description: 'API Gateway endpoint URL',
    });

    // Also output the complete endpoint for the reviews endpoint
    new cdk.CfnOutput(this, 'ReviewsEndpoint', {
      value: `${api.url}reviews`,
      description: 'Reviews endpoint URL',
    });
  }
}