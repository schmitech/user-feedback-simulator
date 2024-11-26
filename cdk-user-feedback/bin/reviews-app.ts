import * as cdk from 'aws-cdk-lib';
import { ReviewsStack } from '../lib/reviews-stack';
import { SentimentStack } from '../lib/sentiment-stack';
import * as dotenv from 'dotenv';

// Load environment variables at the app level
dotenv.config();

const app = new cdk.App();

// Get context values or use defaults
const stage = app.node.tryGetContext('stage') || 'dev';

// Validate required environment variables
if (!process.env.ES_ENDPOINT || !process.env.ES_API_KEY || !process.env.ES_INDEX) {
  throw new Error('Missing required environment variables for Sentiment Analysis Stack');
}

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

const reviewsStack = new ReviewsStack(app, `ReviewsStack-${stage}`, {
  stage,
  env,
});

const sentimentStack = new SentimentStack(app, `SentimentStack-${stage}`, {
  stage,
  env,
});

// Add stack tags for better resource management
const tags = {
  Environment: stage,
  Project: 'UserFeedback',
  ManagedBy: 'CDK',
};

Object.entries(tags).forEach(([key, value]) => {
  cdk.Tags.of(reviewsStack).add(key, value);
  cdk.Tags.of(sentimentStack).add(key, value);
});

app.synth();