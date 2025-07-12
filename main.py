from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from moviepy.editor import AudioFileClip
import whisper
import yt_dlp
from transformers import pipeline
import os
import sqlite3
import re
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
# from flask_dance.contrib.google import make_google_blueprint, google
from flask_session import Session
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_TYPE'] = 'filesystem'
load_dotenv()
Session(app)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# google_bp = make_google_blueprint(
#     client_id=os.environ.get("GOOGLE_OAUTH_CLIENT_ID"),
#     client_secret=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"),
#     scope=[
#         "https://www.googleapis.com/auth/userinfo.profile",
#         "https://www.googleapis.com/auth/userinfo.email",
#         "openid"
#     ],
#     redirect_url="/login/google/authorized"
# )
# app.register_blueprint(google_bp, url_prefix="/login")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
REDIRECT_URI = "http://127.0.0.1:5000/login/google/callback"

def init_db():
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        transcript TEXT,
        summary TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT
    )''')
    conn.commit()
    conn.close()

def check_existing_summary(url):
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("SELECT transcript, summary FROM summaries WHERE url = ?", (url,))
    row = c.fetchone()
    conn.close()
    return row

def save_to_db(url, transcript, summary):
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("INSERT INTO summaries (url, transcript, summary) VALUES (?, ?, ?)", (url, transcript, summary))
    conn.commit()
    conn.close()

def download_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def convert_to_wav():
    clip = AudioFileClip("audio.mp3").subclip(0, 120)
    clip.write_audiofile("lecture.wav")

def transcribe_audio():
    model = whisper.load_model("tiny")
    result = model.transcribe("lecture.wav", fp16=False)
    return result['text']

def summarize_text(text):
    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    max_chunk = 1000
    text = text.strip().replace("\n", " ")
    chunks = []
    while len(text) > 0:
        if len(text) <= max_chunk:
            chunks.append(text)
            break
        else:
            split_at = text.rfind(".", 0, max_chunk)
            if split_at == -1:
                split_at = max_chunk
            chunks.append(text[:split_at + 1])
            text = text[split_at + 1:]

    final_summary = ""
    for chunk in chunks:
        summary = summarizer(chunk, max_length=150, min_length=50, do_sample=False)
        final_summary += summary[0]['summary_text'] + " "
    return final_summary.strip()

def capitalize_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    capitalized = [s.strip().capitalize() for s in sentences]
    return ' '.join(capitalized)

@app.route('/')
def home():
    print("Session at home:", dict(session))  # Add this line
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect("summaries.db")
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE email = ?", (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            return redirect(url_for('home'))
        else:
            return "Invalid credentials", 401
    return render_template('login_signup.html')

@app.route('/register', methods=['POST'])
def register():
    email = request.form['email']
    password = request.form['password']
    hashed_password = generate_password_hash(password)
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        return "Email already registered", 400
    conn.close()
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/summarize', methods=['POST'])
def summarize():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    existing = check_existing_summary(url)
    if existing:
        transcript, summary = existing
        transcript = capitalize_sentences(transcript)
        summary = capitalize_sentences(summary)
    else:
        try:
            download_audio(url)
            convert_to_wav()
            transcript = transcribe_audio()
            summary = summarize_text(transcript)
            transcript = capitalize_sentences(transcript)
            summary = capitalize_sentences(summary)
            save_to_db(url, transcript, summary)
            os.remove("audio.mp3")
            os.remove("lecture.wav")
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'transcript': transcript, 'summary': summary})

@app.route('/set_test_cookie')
def set_test_cookie():
    session['test'] = 'cookie'
    return 'Test cookie set'



@app.route('/debug_session')
def debug_session():
    print("Session at debug:", dict(session))
    return "Check your terminal for session info"

@app.route('/login/google')
def login_google():
    google_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    authorization_endpoint = google_cfg["authorization_endpoint"]

    request_uri = (
        f"{authorization_endpoint}?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return redirect(request_uri)

@app.route('/login/google/callback')
def google_callback():
    code = request.args.get("code")
    google_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    token_endpoint = google_cfg["token_endpoint"]

    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    token_response = requests.post(token_endpoint, data=token_data)
    token_json = token_response.json()
    access_token = token_json.get("access_token")

    userinfo_endpoint = google_cfg["userinfo_endpoint"]
    userinfo_response = requests.get(
        userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    user_info = userinfo_response.json()
    email = user_info["email"]

    # Log in or register user
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, ""))  # No password for Google users
        conn.commit()
        user_id = c.lastrowid
    else:
        user_id = user[0]
    conn.close()

    session['user_id'] = user_id
    return redirect(url_for('home'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
