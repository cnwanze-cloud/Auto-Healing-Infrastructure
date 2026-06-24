# Auto-Healing Infrastructure for AWS EC2

A production-ready guide to implementing automatic instance recovery and replacement for AWS Auto Scaling Groups using CloudWatch, Lambda, and SNS.

## Overview

This project provides a **step-by-step implementation guide** for building an auto-healing system that automatically detects and recovers unhealthy EC2 instances within an Auto Scaling Group. Instead of manually investigating failed instances or waiting for manual intervention, the system intelligently:

- **Detects** when instance health degrades below ASG capacity targets
- **Diagnoses** whether an instance needs a restart or replacement
- **Recovers** by taking appropriate remedial action
- **Notifies** your team of every detection and action taken

## ✨ Key Features

- **ASG-Level Monitoring** — Tracks group health rather than individual instance IDs, eliminating stale alarms when instances are replaced
- **Intelligent Recovery** — Differentiates between software failures (restart) and hardware degradation (replace)
- **Zero External Dependencies** — Uses only AWS native services: CloudWatch, Lambda, SNS, EC2, and Auto Scaling
- **Audit Trail** — Dual notification system provides both detection events and action confirmations
- **No EventBridge** — Simpler architecture focused on reliability and minimal moving parts
- **Production-Ready** — Error handling, permissions scoping, and comprehensive testing built in

## 🏗️ Architecture

<img width="2720" height="2200" alt="architecture" src="https://github.com/user-attachments/assets/4b0f1e6c-f054-4012-9fc8-6e71885db111" />



```
Auto Scaling Group (EC2 instances)
         ↓
CloudWatch Alarm on GroupInServiceInstances
         ↓
    SNS Topic
    ↙      ↘
 Lambda   Email/Slack Notifications
(Orchestrator)
 ↙        ↘
Restart    Replace
Instance   Instance
```

The system works by:
1. CloudWatch continuously monitors the `GroupInServiceInstances` metric
2. When capacity drops below the desired threshold, an alarm fires
3. SNS delivers the alarm to a Lambda function
4. Lambda queries the ASG to find unhealthy instances
5. Lambda diagnoses each instance and takes appropriate action
6. Team receives notifications of both the alarm and the action taken


## 🚀 Quick Start

### 1. Gather ASG Details
```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names your-asg-name \
  --query "AutoScalingGroups[0].{Name:AutoScalingGroupName,Desired:DesiredCapacity}"
```

### 2. Create IAM Role
```bash
# Create trust policy
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name lambda-auto-healing-role \
  --assume-role-policy-document file://trust-policy.json
```

### 3. Create SNS Topic
```bash
aws sns create-topic --name auto-healing-notifications

# Subscribe your email (replace with your email)
aws sns subscribe \
  --topic-arn arn:aws:sns:region:account-id:auto-healing-notifications \
  --protocol email \
  --notification-endpoint your-email@example.com
```

### 4. Deploy Lambda Function
Download the `auto_healing_orchestrator.py` from this repository, then:
```bash
zip function.zip auto_healing_orchestrator.py

aws lambda create-function \
  --function-name auto-healing-orchestrator \
  --runtime python3.11 \
  --handler auto_healing_orchestrator.lambda_handler \
  --role arn:aws:iam::account-id:role/lambda-auto-healing-role \
  --timeout 300 \
  --memory-size 256 \
  --environment Variables={SNS_TOPIC_ARN=your-topic-arn,ASG_NAME=your-asg-name} \
  --zip-file fileb://function.zip
```

### 5. Wire Up SNS → Lambda
```bash
# Subscribe Lambda to SNS
aws sns subscribe \
  --topic-arn your-topic-arn \
  --protocol lambda \
  --notification-endpoint your-lambda-arn

# Grant SNS permission to invoke Lambda
aws lambda add-permission \
  --function-name auto-healing-orchestrator \
  --statement-id sns-invoke-permission \
  --action lambda:InvokeFunction \
  --principal sns.amazonaws.com \
  --source-arn your-topic-arn
```

### 6. Create CloudWatch Alarm
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name asg-capacity-degraded \
  --alarm-description "Triggers when healthy instance count drops below desired capacity" \
  --namespace "AWS/AutoScaling" \
  --metric-name GroupInServiceInstances \
  --dimensions Name=AutoScalingGroupName,Value=your-asg-name \
  --statistic Average \
  --period 60 \
  --evaluation-periods 2 \
  --datapoints-to-alarm 2 \
  --threshold 2 \
  --comparison-operator LessThanThreshold \
  --alarm-actions your-topic-arn \
  --treat-missing-data notBreaching
```


## 📖 Usage

### Testing the System
```bash
# Identify an instance in your ASG
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names your-asg-name \
  --query "AutoScalingGroups[0].Instances[].InstanceId"

# Stop an instance to simulate failure
aws ec2 stop-instances --instance-ids i-xxxxxxxxxx

# Watch the alarm transition to ALARM state
aws cloudwatch describe-alarms \
  --alarm-names asg-capacity-degraded \
  --query "MetricAlarms[0].StateValue"

# Check Lambda logs
aws logs tail /aws/lambda/auto-healing-orchestrator --follow
```

### Monitoring
- **CloudWatch Metrics:** View `GroupInServiceInstances` trend in AWS Console
- **Lambda Logs:** `/aws/lambda/auto-healing-orchestrator`
- **SNS Notifications:** Email notifications on every event
- **Alarm State:** Check alarm history in CloudWatch console

## 🔧 Configuration

### Environment Variables (Lambda)
- `SNS_TOPIC_ARN` — SNS topic for notifications (required)
- `ASG_NAME` — Auto Scaling Group name (required)

### Alarm Parameters
- **Period:** 60 seconds (adjust for noise vs. responsiveness)
- **Datapoints to Alarm:** 2/2 (prevents false positives from brief spikes)
- **Threshold:** Set to your ASG's `DesiredCapacity`

### Recovery Strategy
The Lambda function uses this decision tree:

| Instance State | Instance Status | System Status | Action |
|---|---|---|---|
| stopped | - | - | **Restart** |
| running | impaired | ok | **Restart** |
| running | - | impaired | **Replace** |
| running | ok | ok | **Monitor** |

## 📊 How It Works

1. **Detection:** CloudWatch monitors `GroupInServiceInstances` metric every 60 seconds
2. **Triggering:** When metric < desired capacity for 2 consecutive periods, alarm fires
3. **Notification:** SNS publishes alarm event to Lambda and email subscribers
4. **Diagnosis:** Lambda queries ASG and EC2 to determine which instance(s) are unhealthy
5. **Recovery:** Lambda reboots or terminates instance based on failure type
6. **Action Notification:** Lambda publishes detailed action summary to SNS
7. **Replacement:** ASG automatically launches replacement instance(s) if terminated

## 🔐 Security & Permissions

The Lambda IAM role includes minimum necessary permissions:
- **EC2:** DescribeInstances, DescribeInstanceStatus, RebootInstances, CreateTags
- **Auto Scaling:** DescribeAutoScalingGroups, TerminateInstanceInAutoScalingGroup, SetDesiredCapacity
- **SNS:** Publish
- **CloudWatch Logs:** CreateLogGroup, CreateLogStream, PutLogEvents

See [SETUP.md](./SETUP.md) for the complete policy document.

## ✅ Production Checklist

- [ ] Tested with manual instance stop/start
- [ ] Verified email subscriptions working
- [ ] Lambda logs reviewed for errors
- [ ] Reviewed CloudWatch alarm threshold against ASG desired capacity
- [ ] Team notified of alarm subscription
- [ ] Documented ASG name and capacity in runbooks
- [ ] Tested full recovery cycle (failure → detection → action → recovery)
- [ ] Added alarm to monitoring dashboard

## 🐛 Troubleshooting

### Alarm Never Fires
- Verify `GroupInServiceInstances` metric is enabled in ASG monitoring tab
- Check alarm threshold matches ASG desired capacity
- Confirm CloudWatch metrics are being collected (may take 5 min on first setup)

### Lambda Doesn't Trigger
- Verify SNS subscription to Lambda exists and protocol is `lambda`
- Check Lambda invoke permission allows SNS as principal
- Review SNS subscription filter policy (should be empty or null)

### No Email Notifications
- Confirm SNS email subscription was confirmed (check inbox)
- Verify SNS topic ARN in Lambda environment variable is correct
- Check SNS topic policy allows Lambda to publish

### Lambda Fails with Permission Error
- Verify IAM role ARN is correctly passed during Lambda creation
- Check all IAM policy statements are attached to the role
- Wait 5–10 seconds after attaching policies before testing

## 📄 License

This project is licensed under the MIT License. See [LICENSE](./LICENSE) for details.
