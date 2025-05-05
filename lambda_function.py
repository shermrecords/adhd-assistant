import boto3
import json
import random
import time
from botocore.exceptions import ClientError

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
model_id = 'anthropic.claude-3-5-sonnet-20240620-v1:0'

system_prompt = "You are a compassionate ADHD therapy assistant trained in cognitive behavioral techniques."

def exponential_backoff_with_jitter(func):
    def wrapper(*args, **kwargs):
        max_retries = 5
        initial_delay = 5
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except ClientError as e:
                if e.response['Error']['Code'] in ['Throttling', 'TooManyRequestsException', 'RequestLimitExceeded']:
                    delay = initial_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    raise
        raise e
    return wrapper

@exponential_backoff_with_jitter
def get_assistant_reply(payload):
    response = bedrock.invoke_model(
        modelId=model_id,
        body=json.dumps(payload),
        contentType='application/json'
    )
    assistant_message = response['body'].read().decode('utf-8')
    assistant_data = json.loads(assistant_message)
    return assistant_data['content'][0]['text']

def lambda_handler(event, context):
    try:
        data = json.loads(event['body'])
        user_input = data.get('input', '')

        if not user_input:
            return {
                'statusCode': 400,
                'headers': { 'Content-Type': 'application/json' },
                'body': json.dumps({ 'responseText': "No input received." })
            }

        messages = [{"role": "user", "content": user_input}]
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "system": system_prompt,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.7
        }

        reply = get_assistant_reply(payload)

        return {
            'statusCode': 200,
            'headers': { 'Content-Type': 'application/json' },
            'body': json.dumps({ 'responseText': reply })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': { 'Content-Type': 'application/json' },
            'body': json.dumps({ 'responseText': f"An error occurred: {str(e)}" })
        }
