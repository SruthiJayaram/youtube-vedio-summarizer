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
from flask_session import Session
import requests
import platform
import time
import random
from urllib.parse import urlparse, parse_qs
import secrets
import firebase_admin
from firebase_admin import credentials, firestore
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_TYPE'] = 'filesystem'
load_dotenv()
Session(app)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Firebase Configuration
def init_firebase():
    """Initialize Firebase connection"""
    try:
        if not firebase_admin._apps:
            # Look for standard firebase key filename
            key_files = ['firebase-key.json', 'firebase-credentials.json']
            cred_file = None
            
            for filename in key_files:
                if os.path.exists(filename):
                    cred_file = filename
                    break
            
            if cred_file:
                cred = credentials.Certificate(cred_file)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized with service account")
                return firestore.client()
            else:
                print("⚠️ Firebase key not found (firebase-key.json), using SQLite only")
                return None
    except Exception as e:
        print(f"Firebase initialization failed: {e}")
        return None

# Initialize Firebase
db_firebase = init_firebase()

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
REDIRECT_URI = "https://supreme-space-sniffle-44jxxx657qvhj59x-5000.app.github.dev/login/google/callback"

def init_local_db():
    """Initialize local SQLite database"""
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        title TEXT,
        thumbnail TEXT,
        duration TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        transcript TEXT,
        summary TEXT,
        processed_on TEXT DEFAULT 'Local'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        reset_token TEXT
    )''')
    
    # Add columns if they don't exist
    try:
        c.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE summaries ADD COLUMN processed_on TEXT DEFAULT 'Local'")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def save_to_firebase(url, transcript, summary, title=None, thumbnail=None, duration=None, processed_on='Local'):
    """Save summary to Firebase"""
    try:
        if not db_firebase:
            print("Firebase not available, skipping cloud save")
            return False
        
        doc_data = {
            'url': normalize_youtube_url(url),
            'title': title or 'Unknown Video',
            'thumbnail': thumbnail or '',
            'duration': duration or 'Unknown',
            'created_at': firestore.SERVER_TIMESTAMP,
            'transcript': transcript,
            'summary': summary,
            'processed_on': processed_on,
            'video_id': extract_video_id(url)
        }
        
        # Use video ID as document ID to prevent duplicates
        video_id = extract_video_id(url)
        if video_id:
            db_firebase.collection('summaries').document(video_id).set(doc_data)
            print(f"✅ Saved to Firebase: {title}")
            return True
        else:
            # Fallback to auto-generated ID
            db_firebase.collection('summaries').add(doc_data)
            print(f"✅ Saved to Firebase with auto ID: {title}")
            return True
            
    except Exception as e:
        print(f"Firebase save failed: {e}")
        return False

def save_to_db(url, transcript, summary, title=None, thumbnail=None, duration=None, processed_on='Local'):
    """Save to both local SQLite and Firebase"""
    normalized_url = normalize_youtube_url(url)
    
    # Save to local SQLite
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("""INSERT INTO summaries 
                 (url, title, thumbnail, duration, created_at, transcript, summary, processed_on) 
                 VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?)""", 
              (normalized_url, title, thumbnail, duration, transcript, summary, processed_on))
    conn.commit()
    conn.close()
    print(f"✅ Saved to local SQLite: {title}")
    
    # Save to Firebase
    save_to_firebase(normalized_url, transcript, summary, title, thumbnail, duration, processed_on)

def check_existing_summary(url):
    """Check for existing summary in both local and Firebase"""
    normalized_url = normalize_youtube_url(url)
    video_id = extract_video_id(url)
    
    # First check local SQLite
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("SELECT transcript, summary FROM summaries WHERE url = ?", (normalized_url,))
    row = c.fetchone()
    conn.close()
    
    if row:
        print("✅ Found existing summary in local database")
        return row
    
    # Then check Firebase
    try:
        if db_firebase and video_id:
            doc_ref = db_firebase.collection('summaries').document(video_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                print("✅ Found existing summary in Firebase")
                
                # Save to local database for faster future access
                save_to_local_only(
                    normalized_url, 
                    data.get('transcript', ''), 
                    data.get('summary', ''),
                    data.get('title', ''),
                    data.get('thumbnail', ''),
                    data.get('duration', ''),
                    data.get('processed_on', 'Firebase')
                )
                
                return (data.get('transcript', ''), data.get('summary', ''))
    except Exception as e:
        print(f"Firebase check failed: {e}")
    
    return None

def save_to_local_only(url, transcript, summary, title=None, thumbnail=None, duration=None, processed_on='Firebase'):
    """Save to local SQLite only (for Firebase sync)"""
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("""INSERT INTO summaries 
                 (url, title, thumbnail, duration, created_at, transcript, summary, processed_on) 
                 VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?)""", 
              (url, title, thumbnail, duration, transcript, summary, processed_on))
    conn.commit()
    conn.close()

def get_ydl_opts(extract_flat=False):
    """Get yt-dlp options optimized for local use"""
    base_opts = {
        'format': 'bestaudio/best' if not extract_flat else None,
        'outtmpl': 'audio.%(ext)s' if not extract_flat else None,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_flat,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'no_check_certificate': True,
        'prefer_insecure': True,
    }
    return base_opts

def test_video_accessibility(url):
    """Test if a video is accessible - LOCAL VERSION (1-hour limit)"""
    try:
        test_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        if os.path.exists('cookies.txt'):
            test_opts['cookiefile'] = 'cookies.txt'
        
        with yt_dlp.YoutubeDL(test_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return False, "Video information not available"
            
            if info.get('availability') == 'private':
                return False, "Video is private"
            
            if info.get('availability') == 'premium_only':
                return False, "Video requires premium subscription"
            
            if info.get('live_status') == 'is_live':
                return False, "Cannot process live streams"
            
            # LOCAL LIMIT: 1 hour maximum
            duration = info.get('duration', 0)
            if duration > 3600:  # 1 hour
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                return False, f"Video is too long ({hours}h {minutes}m). Local processing limited to 1 hour. Use Google Colab for longer videos."
            
            minutes = duration // 60
            seconds = duration % 60
            return True, f"Video is accessible ({minutes}m {seconds}s)"
            
    except Exception as e:
        print(f"Accessibility check failed: {e}")
        return True, "Video accessibility unknown - will attempt download anyway"

def convert_to_wav():
    """Convert audio to WAV - LOCAL VERSION with 1-hour processing"""
    try:
        audio_files = ["audio.mp3", "audio.m4a", "audio.webm", "audio.wav", "audio.mp4"]
        audio_file = None
        
        for file in audio_files:
            if os.path.exists(file):
                audio_file = file
                break
        
        if not audio_file:
            raise FileNotFoundError("No audio file found to convert")
        
        clip = AudioFileClip(audio_file)
        duration = clip.duration
        
        print(f"Audio duration: {duration/60:.1f} minutes")
        
        # LOCAL LIMIT: Enforce 1-hour maximum
        if duration > 3600:  # 1 hour
            print("❌ Video exceeds 1-hour limit for local processing")
            clip.close()
            return False
        
        # Process entire video (up to 1 hour)
        clip.write_audiofile("lecture.wav", verbose=False, logger=None)
        clip.close()
        
        print(f"✅ Successfully converted {duration/60:.1f} minute video")
        return True
        
    except Exception as e:
        print(f"Error in convert_to_wav: {e}")
        return False

def transcribe_audio():
    """Transcribe audio - LOCAL VERSION optimized for 8GB RAM"""
    try:
        if not os.path.exists("lecture.wav"):
            raise FileNotFoundError("lecture.wav not found")
        
        # Use tiny model for 8GB RAM
        model_size = "tiny"
        print(f"Loading Whisper {model_size} model for local processing...")
        model = whisper.load_model(model_size)
        
        # Get duration
        try:
            import librosa
            audio_data, sr = librosa.load("lecture.wav", sr=16000)
            duration = len(audio_data) / sr
            print(f"Transcribing {duration/60:.1f} minutes of audio...")
            print(f"Estimated time: {duration/60*2:.1f} minutes on local system")
        except:
            print("Transcribing audio...")
        
        # Transcribe with local-optimized settings
        result = model.transcribe(
            "lecture.wav",
            language='en',
            task='transcribe',
            fp16=False,  # Use fp32 for 8GB RAM stability
            verbose=True,
            word_timestamps=False,
            condition_on_previous_text=False
        )
        
        transcript = result['text']
        print(f"✅ Local transcription completed!")
        print(f"Characters: {len(transcript):,}, Words: {len(transcript.split()):,}")
        
        return transcript
        
    except Exception as e:
        print(f"Local transcription failed: {e}")
        return f"Transcription failed: {str(e)}"

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    parsed = urlparse(url)
    if parsed.hostname in ['youtube.com', 'www.youtube.com']:
        if parsed.path == '/watch':
            return parse_qs(parsed.query).get('v', [None])[0]
        elif parsed.path.startswith('/embed/'):
            return parsed.path.split('/')[2]
    elif parsed.hostname in ['youtu.be']:
        return parsed.path[1:]
    return None

def normalize_youtube_url(url):
    """Normalize YouTube URL to standard format"""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def download_audio(url, max_retries=3):
    """Download audio with local optimizations"""
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = random.uniform(2, 5) * (2 ** attempt)
                print(f"Retrying in {delay:.1f} seconds...")
                time.sleep(delay)
            
            ydl_opts = get_ydl_opts(extract_flat=False)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            print(f"✅ Downloaded on attempt {attempt + 1}")
            return True
            
        except Exception as e:
            print(f"Download attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                print("❌ All download attempts failed")
                return False
    
    return False

def summarize_text(text):
    """Summarize text using transformers"""
    try:
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
    except Exception as e:
        print(f"Summarization failed: {e}")
        return "Summary generation failed"

def capitalize_sentences(text):
    """Capitalize sentences properly"""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    capitalized = [s.strip().capitalize() for s in sentences]
    return ' '.join(capitalized)

def get_all_summaries():
    """Get summaries from both local and Firebase"""
    all_summaries = []
    
    # Get local summaries
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("""SELECT id, url, title, thumbnail, duration, created_at, 
                        SUBSTR(summary, 1, 150) as summary_preview, processed_on 
                 FROM summaries ORDER BY created_at DESC""")
    local_summaries = c.fetchall()
    conn.close()
    
    # Convert to standardized format
    for row in local_summaries:
        all_summaries.append({
            'id': f"local_{row[0]}",
            'url': row[1],
            'title': row[2] or 'Unknown Video',
            'thumbnail': row[3] or '',
            'duration': row[4] or 'Unknown',
            'created_at': row[5],
            'summary_preview': row[6] or 'No summary',
            'processed_on': row[7] or 'Local'
        })
    
    # Get Firebase summaries
    try:
        if db_firebase:
            firebase_summaries = db_firebase.collection('summaries').order_by('created_at', direction=firestore.Query.DESCENDING).limit(100).stream()
            
            for doc in firebase_summaries:
                data = doc.to_dict()
                # Skip if already exists locally
                existing = any(s['url'] == data.get('url') for s in all_summaries)
                if not existing:
                    all_summaries.append({
                        'id': f"firebase_{doc.id}",
                        'url': data.get('url', ''),
                        'title': data.get('title', 'Unknown Video'),
                        'thumbnail': data.get('thumbnail', ''),
                        'duration': data.get('duration', 'Unknown'),
                        'created_at': data.get('created_at'),
                        'summary_preview': (data.get('summary', '')[:150] + '...') if data.get('summary') else 'No summary',
                        'processed_on': data.get('processed_on', 'Firebase')
                    })
    except Exception as e:
        print(f"Failed to fetch Firebase summaries: {e}")
    
    # Remove duplicates and sort by date
    seen_urls = set()
    unique_summaries = []
    for summary in all_summaries:
        if summary['url'] not in seen_urls:
            seen_urls.add(summary['url'])
            unique_summaries.append(summary)
    
    return unique_summaries

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/summaries')
def summaries():
    """Display all summaries from both local and Firebase"""
    all_summaries = get_all_summaries()
    return render_template('summaries.html', summaries=all_summaries)

@app.route('/summarize', methods=['POST'])
def summarize():
    """Main summarization endpoint - LOCAL VERSION"""
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    # Check existing summaries
    existing = check_existing_summary(url)
    if existing:
        transcript, summary = existing
        transcript = capitalize_sentences(transcript)
        summary = capitalize_sentences(summary)
        return jsonify({
            'transcript': transcript, 
            'summary': summary,
            'source': 'existing'
        })

    try:
        # Test accessibility with 1-hour limit
        is_accessible, access_message = test_video_accessibility(url)
        if not is_accessible:
            return jsonify({'error': access_message}), 400
        
        print(f"✅ {access_message}")
        
        # Download audio
        if not download_audio(url):
            return jsonify({'error': 'Failed to download video audio'}), 500
        
        # Convert to WAV (with 1-hour limit)
        if not convert_to_wav():
            return jsonify({'error': 'Video exceeds 1-hour limit for local processing. Use Google Colab for longer videos.'}), 500

        # Transcribe
        transcript = transcribe_audio()
        if transcript.startswith("Transcription failed:"):
            return jsonify({'error': transcript}), 500
        
        # Summarize
        summary = summarize_text(transcript)
        
        # Get video metadata
        try:
            video_info = get_video_info_fallback(url)
            video_title = video_info.get('title', 'Unknown Video') if video_info else 'Unknown Video'
            thumbnail = video_info.get('thumbnail', '') if video_info else ''
            duration = video_info.get('duration_string', '') if video_info else ''
        except:
            video_title = 'Unknown Video'
            thumbnail = ''
            duration = ''
        
        # Capitalize and save
        transcript = capitalize_sentences(transcript)
        summary = capitalize_sentences(summary)
        save_to_db(url, transcript, summary, video_title, thumbnail, duration, 'Local')
        
        # Cleanup
        for f in ["audio.mp3", "audio.m4a", "audio.webm", "lecture.wav"]:
            try:
                os.remove(f)
            except:
                pass
        
        return jsonify({
            'transcript': transcript,
            'summary': summary,
            'processed_on': 'Local (8GB RAM)',
            'note': 'Processed locally with 1-hour limit'
        })
        
    except Exception as e:
        print(f"Error in summarize: {e}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    show_register = request.args.get('show') == 'register'
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
    return render_template('login_signup.html', show_register=show_register)

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
    return redirect(url_for('home'))

@app.route('/get-playlist', methods=['POST'])
def get_playlist():
    """Extract videos from a YouTube playlist"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    
    playlist_url = request.json.get('url')
    if not playlist_url:
        return jsonify({'error': 'No playlist URL provided'}), 400
    
    try:
        import re
        playlist_id_match = re.search(r'list=([^&]+)', playlist_url)
        if not playlist_id_match:
            return jsonify({'error': 'Invalid playlist URL'}), 400
        
        ydl_opts = get_ydl_opts(extract_flat=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            
            if not playlist_info or 'entries' not in playlist_info:
                return jsonify({'error': 'Could not extract playlist information'}), 400
            
            videos = []
            for entry in playlist_info['entries']:
                if entry:
                    video_id = entry.get('id')
                    if video_id:
                        # Check duration for local limit
                        duration = entry.get('duration', 0)
                        if duration > 3600:  # 1 hour
                            duration_note = "⚠️ Too long for local processing"
                        else:
                            duration_note = entry.get('duration_string', 'Unknown')
                        
                        video = {
                            'id': video_id,
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'title': entry.get('title', 'Unknown Title'),
                            'thumbnail': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                            'duration': duration_note,
                            'can_process_local': duration <= 3600
                        }
                        videos.append(video)
            
            return jsonify({
                'playlist_title': playlist_info.get('title', 'Unknown Playlist'),
                'videos': videos[:50],
                'note': 'Videos over 1 hour require Google Colab processing'
            })
    
    except Exception as e:
        print(f"Playlist extraction error: {e}")
        return jsonify({'error': f'Failed to load playlist: {str(e)}'}), 500

def get_video_info_fallback(url):
    """Get video metadata as fallback"""
    try:
        ydl_opts = get_ydl_opts(extract_flat=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                duration = info.get('duration', 0)
                duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
                
                return {
                    'title': info.get('title', 'Unknown Video'),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration_string': duration_str,
                    'duration': duration
                }
    except Exception as e:
        print(f"Failed to get video info: {e}")
    
    return {
        'title': 'Unknown Video',
        'thumbnail': '',
        'duration_string': 'Unknown',
        'duration': 0
    }

if __name__ == '__main__':
    init_local_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
