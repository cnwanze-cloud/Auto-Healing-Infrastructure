# CloudWatch Alarm Configuration

## Overview

This CloudWatch alarm monitors the health of the Auto Scaling Group by tracking the number of instances currently in service.

When the number of healthy instances falls below the desired capacity, the alarm enters the **ALARM** state and triggers the auto-healing workflow through Amazon SNS.

---

## Alarm Details

| Property            | Value                   |
| ------------------- | ----------------------- |
| Alarm Name          | asg-capacity-degraded   |
| Namespace           | AWS/AutoScaling         |
| Metric              | GroupInServiceInstances |
| Statistic           | Average                 |
| Period              | 60 Seconds              |
| Evaluation Periods  | 2                       |
| Datapoints to Alarm | 2                       |
| Threshold           | 2                       |
| Comparison Operator | LessThanThreshold       |
| Treat Missing Data  | notBreaching            |

---

## Purpose

The alarm serves as the primary failure detection mechanism for the auto-healing system.

It detects:

* Instance failures
* Unexpected instance terminations
* Capacity degradation
* Health check failures

Once detected, the alarm initiates automated remediation.

---

## Monitored Metric

### GroupInServiceInstances

Measures the number of healthy instances currently serving within the Auto Scaling Group.

Example:

| Desired Capacity | Healthy Instances | Alarm State |
| ---------------- | ----------------- | ----------- |
| 2                | 2                 | OK          |
| 2                | 1                 | ALARM       |
| 2                | 0                 | ALARM       |

---

## Alarm Logic

```text
IF GroupInServiceInstances < Desired Capacity
THEN Trigger Alarm
```

For this project:

```text
IF GroupInServiceInstances < 2
THEN ALARM
```

---

## Notification Flow

```text
CloudWatch Alarm
        │
        ▼
Amazon SNS Topic
        │
 ┌──────┴──────┐
 ▼             ▼
Email      Lambda
Alert    Remediation
```

---

## Alarm Actions

### SNS Topic

Target:

```text
auto-healing-notifications
```

Actions performed:

* Sends email notifications
* Invokes Lambda function
* Provides audit trail of incidents

---

## Alarm States

### OK

System operating normally.

```text
Healthy Instances = Desired Capacity
```

Example:

```text
2 / 2 Healthy Instances
```

---

### ALARM

System capacity degraded.

Example:

```text
1 / 2 Healthy Instances
```

Result:

* SNS notification sent
* Lambda remediation triggered

---

### INSUFFICIENT_DATA

Metric data unavailable.

Configuration:

```text
TreatMissingData = notBreaching
```

Prevents false alarms during temporary metric gaps.

---

## AWS CLI Configuration

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name asg-capacity-degraded \
  --alarm-description "Triggers when healthy instance count drops below desired capacity" \
  --namespace AWS/AutoScaling \
  --metric-name GroupInServiceInstances \
  --dimensions Name=AutoScalingGroupName,Value=auto-healing-asg \
  --statistic Average \
  --period 60 \
  --evaluation-periods 2 \
  --datapoints-to-alarm 2 \
  --threshold 2 \
  --comparison-operator LessThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --treat-missing-data notBreaching
```

---

## Test Scenario

### Failure Simulation

Terminate an instance:

```bash
aws ec2 terminate-instances \
  --instance-ids i-xxxxxxxxxxxxxxxxx
```

### Expected Behavior

1. GroupInServiceInstances decreases.
2. CloudWatch alarm enters ALARM state.
3. SNS sends notification.
4. Lambda performs remediation.
5. Auto Scaling Group restores capacity.
6. Alarm returns to OK state.

---

## Benefits

* Automatic failure detection
* Near real-time monitoring
* Event-driven remediation
* Reduced operational overhead
* Improved system availability

---

## Future Improvements

* Composite alarms
* Multi-metric monitoring
* Custom application health checks
* Cross-region alerting
* Integration with incident management platforms
