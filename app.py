from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import boto3
import json
import random
import time
import os
from botocore.exceptions import ClientError

app = Flask(__name__)
CORS(app)

# AWS Bedrock client setup
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
model_id = 'anthropic.claude-3-5-sonnet-20240620-v1:0'

system_prompt = "You are a compassionate ADHD therapy assistant trained in cognitive behavioral techniques."

# Conversation persistence
def load_conversation(filename='conversation_history.json'):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {filename} is not a valid JSON file. Starting fresh.")
    return []

def save_conversation(conversation, filename='conversation_history.json'):
    with open(filename, 'w') as f:
        json.dump(conversation, f, indent=2)

# Retry decorator for throttling
def exponential_backoff_with_jitter(func):
    def wrapper(*args, **kwargs):
        max_retries = 10
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
        raise Exception("max retries exceeded")
    return wrapper

@exponential_backoff_with_jitter
def get_assistant_reply(payload):
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(payload),
            contentType='application/json'
        )
        assistant_message = response['body'].read().decode('utf-8')
        assistant_data = json.loads(assistant_message)
        reply = assistant_data['content'][0]['text']

        # Add conversational flow prompt
        if not reply.strip().endswith('?'):
            reply += " Would you like to talk more about that?"

        return reply
    except ClientError as e:
        print(f"An error occurred: {e}")
        raise e

@app.route('/history/edit', methods=['GET'])
def edit_history():
    conversation = load_conversation()
    return render_template('edit_history.html', conversation=conversation)

@app.route('/history/save', methods=['POST'])
def save_history():
    try:
        total = int(request.form['total'])
        conversation = []
        for i in range(total):
            role = request.form.get(f'role_{i}')
            content = request.form.get(f'content_{i}')
            if role and content:
                conversation.append({"role": role, "content": content})
        save_conversation(conversation)
        return "Conversation history updated successfully!"
    except Exception as e:
        return f"Error saving conversation: {str(e)}", 400



@app.route('/')
def home():
    return render_template('index.html')

@app.route('/history')
def history():
    conversation = load_conversation()
    return jsonify(conversation)

@app.route('/', methods=['POST'])
def chat():
    data = request.get_json()
    user_input = data.get('input', '')
    if not user_input:
        return jsonify({'responseText': "No input received."})

    messages = load_conversation()
    messages.append({"role": "user", "content": user_input})

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": system_prompt,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7
    }

    try:
        reply = get_assistant_reply(payload)
        messages.append({"role": "assistant", "content": reply})
        save_conversation(messages)
        return jsonify({'responseText': reply})
    except Exception as e:
        return jsonify({'responseText': f"An error occurred: {str(e)}"})

if __name__ == '__main__':
    # Use PORT from env (e.g., Render), default to 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)