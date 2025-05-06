from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import boto3
import json
import random
import time
import os
from botocore.exceptions import ClientError

app = Flask(__name__)
CORS(app)

# Secure secret key from environment variable
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_for_testing")

# AWS clients
s3 = boto3.client('s3', region_name='us-east-1')
bucket_name = "adhd-ai-logs"
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
model_id = 'anthropic.claude-3-5-sonnet-20240620-v1:0'

# System prompt for assistant
system_prompt = """
You are a compassionate ADHD therapy assistant trained in cognitive behavioral techniques.
You should:
    - Provide clear, concise, and direct responses. Avoid jargon and overly complex explanations.
    - Use a friendly, empathetic, and conversational tone. Respond in a way that feels natural and human-like.
    - Be patient, supportive, and encouraging in your tone, especially when discussing behavioral techniques.
    - Always ask if the user would like to talk more about a topic if the conversation feels incomplete.
    - Offer actionable advice and insights that the user can apply immediately in their daily life.
    - Keep responses at a practical level, avoiding theoretical over-explanation unless specifically asked for it.
    - If the user shows signs of frustration or confusion, acknowledge it empathetically and offer help.
"""

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

users = {}

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

# Utils for per-user conversation key
def get_user_convo_key(user_id):
    return f'conversations/{user_id}_history.json'

def load_conversation():
    key = get_user_convo_key(current_user.id)
    try:
        response = s3.get_object(Bucket=bucket_name, Key=key)
        conversation = json.loads(response['Body'].read().decode('utf-8'))
    except ClientError as e:
        print(f"Error loading conversation: {e}")
        conversation = []
    return conversation

def save_conversation(conversation):
    key = get_user_convo_key(current_user.id)
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(conversation, indent=2),
            ContentType='application/json'
        )
        print("Conversation saved to S3.")
    except ClientError as e:
        print(f"Error saving conversation: {e}")

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

        if not reply.strip().endswith('?'):
            reply += " Would you like to talk more about that?"

        return reply
    except ClientError as e:
        print(f"An error occurred: {e}")
        raise e

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users:
            return "User already exists!"
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        user = User(id=username, username=username, password=hashed_password)
        users[username] = user
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users.get(username)
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        return "Invalid credentials!"
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/chat', methods=['POST'])
@login_required
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

@app.route('/history')

def history():
    conversation = load_conversation()
    return jsonify(conversation)

@app.route('/history/edit')

def edit_history():
    conversation = load_conversation()
    return render_template('edit_history.html', conversation=conversation)

@app.route('/history/save', methods=['POST'])

def save_history():
    try:
        data = request.get_json()
        conversation = data.get("conversation", [])
        if not isinstance(conversation, list):
            raise ValueError("Invalid conversation format.")

        save_conversation(conversation)
        return "Conversation history updated successfully!"
    except Exception as e:
        return f"Error saving conversation: {str(e)}", 400
    

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 6969))
    app.run(debug=True, host='0.0.0.0', port=port)
