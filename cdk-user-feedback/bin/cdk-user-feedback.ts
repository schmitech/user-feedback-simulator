// bin/reviews-app.ts
import * as cdk from 'aws-cdk-lib';
import { ReviewsStack } from '../lib/cdk-user-feedback-stack';

const app = new cdk.App();
new ReviewsStack(app, 'ReviewsStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});