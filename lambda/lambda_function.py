import boto3
import json
import os
from datetime import datetime
from botocore.exceptions import ClientError

ec2_client = boto3.client('ec2')
autoscaling_client = boto3.client('autoscaling')
sns_client = boto3.client('sns')

SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
ASG_NAME = os.environ['ASG_NAME']


def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")

    try:
        unhealthy_instances = find_unhealthy_instances(ASG_NAME)

        if not unhealthy_instances:
            print("No unhealthy instances found. Alarm may have self-resolved.")
            return respond(200, {"status": "no_action", "message": "No unhealthy instances detected"})

        results = []
        for instance_id, status in unhealthy_instances:
            action = determine_recovery_action(status)
            if action == "restart":
                result = restart_instance(instance_id)
            elif action == "replace":
                result = replace_instance(instance_id, ASG_NAME)
            else:
                result = {"status": "monitor", "instance_id": instance_id}
            results.append(result)
            notify_team(instance_id, action, result)

        return respond(200, {"results": results})

    except Exception as e:
        print(f"Error: {str(e)}")
        notify_team_error(str(e))
        return respond(500, {"error": str(e)})


def find_unhealthy_instances(asg_name):
    """
    Query the ASG directly to find which instances are currently unhealthy.
    This is how we avoid needing a hardcoded instance ID in the alarm.
    """
    asg_response = autoscaling_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    )
    asg = asg_response['AutoScalingGroups'][0]
    instance_ids = [i['InstanceId'] for i in asg['Instances']]

    if not instance_ids:
        return []

    status_response = ec2_client.describe_instance_status(
        InstanceIds=instance_ids,
        IncludeAllInstances=True
    )

    unhealthy = []
    for status in status_response['InstanceStatuses']:
        instance_status = status.get('InstanceStatus', {}).get('Status')
        system_status = status.get('SystemStatus', {}).get('Status')
        instance_state = status.get('InstanceState', {}).get('Name')

        if instance_status != 'ok' or system_status != 'ok' or instance_state != 'running':
            unhealthy.append((status['InstanceId'], {
                'instance_status': instance_status,
                'system_status': system_status,
                'instance_state': instance_state
            }))

    return unhealthy


def determine_recovery_action(status):
    if status['instance_state'] == 'stopped':
        return 'restart'
    if status['instance_status'] == 'impaired' and status['system_status'] == 'ok':
        return 'restart'
    if status['system_status'] == 'impaired':
        return 'replace'
    return 'monitor'


def restart_instance(instance_id):
    try:
        ec2_client.reboot_instances(InstanceIds=[instance_id])
        return {
            'status': 'success',
            'action': 'restart',
            'instance_id': instance_id,
            'timestamp': datetime.now().isoformat()
        }
    except ClientError as e:
        return {'status': 'failed', 'action': 'restart', 'instance_id': instance_id, 'error': str(e)}


def replace_instance(instance_id, asg_name):
    try:
        autoscaling_client.terminate_instance_in_auto_scaling_group(
            InstanceId=instance_id,
            ShouldDecrementDesiredCapacity=False
        )
        return {
            'status': 'success',
            'action': 'replace',
            'instance_id': instance_id,
            'asg_name': asg_name,
            'timestamp': datetime.now().isoformat()
        }
    except ClientError as e:
        return {'status': 'failed', 'action': 'replace', 'instance_id': instance_id, 'error': str(e)}


def notify_team(instance_id, action, result):
    try:
        subject = f"Auto-Healing: {action.upper()} - {instance_id}"
        message = (
            f"Instance: {instance_id}\n"
            f"Action: {action}\n"
            f"Status: {result.get('status')}\n"
            f"Timestamp: {result.get('timestamp', 'N/A')}\n\n"
            f"Details:\n{json.dumps(result, indent=2)}"
        )
        sns_client.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    except ClientError as e:
        print(f"Notification error: {str(e)}")


def notify_team_error(error_message):
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="Auto-Healing Error",
            Message=f"Error in auto-healing system:\n\n{error_message}"
        )
    except ClientError as e:
        print(f"Error sending error notification: {str(e)}")


def respond(status_code, body):
    return {'statusCode': status_code, 'body': json.dumps(body)}