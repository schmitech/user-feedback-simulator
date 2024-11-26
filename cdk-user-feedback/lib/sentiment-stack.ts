import * as cdk from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as path from 'path';
import { Construct } from 'constructs';
import * as cr from 'aws-cdk-lib/custom-resources';
import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

export interface SentimentStackProps extends cdk.StackProps {
  stage: string;
}

export class SentimentStack extends cdk.Stack {
  public readonly feedbackTable: dynamodb.Table;
  public readonly api: apigateway.RestApi;
  public readonly processingFunction: lambda.Function;
  private readonly stage: string;

  private createApiGatewayAccountSettings(): cr.AwsCustomResource {
    const region = cdk.Stack.of(this).region;

    // Create the role for API Gateway CloudWatch logging
    const apiGatewayLoggingRole = new iam.Role(this, 'ApiGatewayCloudWatchRole', {
      assumedBy: new iam.ServicePrincipal('apigateway.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonAPIGatewayPushToCloudWatchLogs'),
      ],
    });

    // Create custom resource to update API Gateway account settings
    return new cr.AwsCustomResource(this, 'ApiGatewayAccountSettings', {
      onCreate: {
        service: 'APIGateway',
        action: 'updateAccount',
        parameters: {
          patchOperations: [
            {
              op: 'replace',
              path: '/cloudwatchRoleArn',
              value: apiGatewayLoggingRole.roleArn,
            },
          ],
        },
        physicalResourceId: cr.PhysicalResourceId.of('ApiGatewayAccountSettings'),
      },
      onUpdate: {
        service: 'APIGateway',
        action: 'updateAccount',
        parameters: {
          patchOperations: [
            {
              op: 'replace',
              path: '/cloudwatchRoleArn',
              value: apiGatewayLoggingRole.roleArn,
            },
          ],
        },
        physicalResourceId: cr.PhysicalResourceId.of('ApiGatewayAccountSettings'),
      },
      policy: cr.AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['apigateway:GET', 'apigateway:POST', 'apigateway:PATCH'],
          resources: [`arn:aws:apigateway:${region}::/account`],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [apiGatewayLoggingRole.roleArn],
        }),
      ]),
    });
  }

  private createDependenciesLayer(): lambda.LayerVersion {
    return new lambda.LayerVersion(this, 'DependenciesLayer', {
      layerVersionName: `feedback-dependencies-${this.stage}`,
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/lambda-layer'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_9.bundlingImage,
          command: [
            'bash', '-c',
            'pip install --no-cache-dir -r requirements.txt -t /asset-output/python'
          ],
          user: 'root',
          workingDirectory: '/asset-input/python',
          local: {
            tryBundle(outputDir: string) {
              try {
                const child_process = require('child_process');
                child_process.execSync(`mkdir -p ${outputDir}/python`);
                // Install from requirements.txt
                child_process.execSync(
                  `pip3 install --no-cache-dir -r ${path.join(__dirname, '../lambda/lambda-layer/python/requirements.txt')} -t ${outputDir}/python`
                );
                return true;
              } catch (error) {
                console.log('Failed local bundling:', error);
                return false;
              }
            }
          }
        },
      }),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
      description: 'Dependencies for feedback processing including requests library',
    });
  }

  constructor(scope: Construct, id: string, props: SentimentStackProps) {
    super(scope, id, props);
    this.stage = props.stage;

    // Validate required environment variables
    if (!process.env.ES_ENDPOINT || !process.env.ES_API_KEY || !process.env.ES_INDEX) {
      throw new Error('Missing required environment variables for Elasticsearch configuration');
    }
    
    // Keep DynamoDB for operational data (quick lookups, etc.)
    this.feedbackTable = new dynamodb.Table(this, 'FeedbackTable', {
      tableName: `customer-feedback-${props.stage}`,
      partitionKey: { name: 'reviewId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: props.stage === 'prod' ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      pointInTimeRecovery: props.stage === 'prod',
      
      // Enable DynamoDB Streams for Glue/Athena integration
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    });
    
    // Add GSI for querying by sentiment and department
    this.feedbackTable.addGlobalSecondaryIndex({
      indexName: 'sentiment-department-index',
      partitionKey: { name: 'sentiment', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'department', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // Add GSI for timestamp-based queries
    this.feedbackTable.addGlobalSecondaryIndex({
      indexName: 'timestamp-index',
      partitionKey: { name: 'reviewDateTime', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });
    
    // Setup API Gateway account settings first
    const accountSettings = this.createApiGatewayAccountSettings();

    // Create log group for API Gateway access logs
    const apiLogGroup = new logs.LogGroup(this, 'ApiGatewayAccessLogs', {
      logGroupName: `/aws/apigateway/feedback-analysis-${props.stage}`,
      retention: props.stage === 'prod' ? logs.RetentionDays.ONE_MONTH : logs.RetentionDays.ONE_WEEK,
      removalPolicy: props.stage === 'prod' ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    });

    // Grant API Gateway permission to write to the log group
    const apiLogGroupPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      principals: [new iam.ServicePrincipal('apigateway.amazonaws.com')],
      actions: [
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        'logs:DescribeLogGroups',
        'logs:DescribeLogStreams'
      ],
      resources: [apiLogGroup.logGroupArn, `${apiLogGroup.logGroupArn}:*`]
    });

    apiLogGroup.addToResourcePolicy(apiLogGroupPolicy);
    apiLogGroup.node.addDependency(accountSettings);

    // Create the API Gateway
    this.api = new apigateway.RestApi(this, 'FeedbackAPI', {
      restApiName: `feedback-analysis-api-${props.stage}`,
      description: 'API for customer feedback processing',
      deployOptions: {
        stageName: props.stage,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        tracingEnabled: true,
        accessLogDestination: new apigateway.LogGroupLogDestination(apiLogGroup),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields(),
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    // Add explicit dependency
    this.api.node.addDependency(accountSettings);

    // CloudWatch Logs
    const processingLogGroup = new logs.LogGroup(this, 'FeedbackProcessingLogs', {
      logGroupName: `/aws/lambda/process-feedback-${props.stage}`,
      retention: props.stage === 'prod' ? logs.RetentionDays.ONE_MONTH : logs.RetentionDays.ONE_WEEK,
      removalPolicy: props.stage === 'prod' ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    });

    // Create Lambda Layer with dependencies
    const dependenciesLayer = this.createDependenciesLayer();

    // Create the Lambda function with the layer
    this.processingFunction = new lambda.Function(this, 'ProcessFeedbackFunction', {
      functionName: `process-feedback-${props.stage}`,
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'index.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/sentiment')),
      layers: [dependenciesLayer],  // Add the dependencies layer
      environment: {
        STAGE: props.stage,
        FEEDBACK_TABLE: this.feedbackTable.tableName,
        ES_ENDPOINT: process.env.ES_ENDPOINT,
        ES_API_KEY: process.env.ES_API_KEY,
        ES_INDEX: process.env.ES_INDEX
      },
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      logGroup: processingLogGroup,
      tracing: lambda.Tracing.ACTIVE,
    });

    // Grant CloudWatch Logs permissions
    this.processingFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'logs:CreateLogStream',
          'logs:PutLogEvents',
          'logs:CreateLogGroup',
          'logs:DescribeLogGroups',
          'logs:DescribeLogStreams'
        ],
        resources: ['*']
      })
    );

    // API Gateway Integration
    const feedbackResource = this.api.root.addResource('feedback');
    feedbackResource.addMethod(
      'POST',
      new apigateway.LambdaIntegration(this.processingFunction, {
        proxy: true,
        allowTestInvoke: true,
      }),
      {
        methodResponses: [
          {
            statusCode: '200',
            responseModels: {
              'application/json': apigateway.Model.EMPTY_MODEL,
            },
            responseParameters: {
              'method.response.header.Access-Control-Allow-Origin': true,
            },
          },
        ],
      }
    );

    // Grant permissions
    this.feedbackTable.grantWriteData(this.processingFunction);
    
    // Grant Comprehend permissions
    this.processingFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          'comprehend:DetectSentiment',
          'comprehend:DetectKeyPhrases',
        ],
        resources: ['*'],
      })
    );

    // CloudWatch Dashboard
    const dashboard = new cdk.aws_cloudwatch.Dashboard(this, 'FeedbackDashboard', {
      dashboardName: `feedback-analysis-${props.stage}`,
    });

    dashboard.addWidgets(
      new cdk.aws_cloudwatch.GraphWidget({
        title: 'API Requests',
        left: [this.api.metricCount()],
      }),
      new cdk.aws_cloudwatch.GraphWidget({
        title: 'Lambda Errors',
        left: [this.processingFunction.metricErrors()],
      }),
      new cdk.aws_cloudwatch.GraphWidget({
        title: 'Processing Duration',
        left: [this.processingFunction.metricDuration()],
      })
    );

    // Stack Outputs
    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: this.api.url,
      description: 'API Gateway endpoint URL',
      exportName: `${props.stage}-api-endpoint`,
    });

    new cdk.CfnOutput(this, 'FeedbackTableName', {
      value: this.feedbackTable.tableName,
      description: 'DynamoDB table name',
      exportName: `${props.stage}-table-name`,
    });
  }
}