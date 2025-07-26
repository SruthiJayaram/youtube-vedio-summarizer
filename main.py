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
import platform
import time
import random
import requests
from urllib.parse import urlparse, parse_qs
import secrets

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_TYPE'] = 'filesystem'
load_dotenv()
Session(app)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
REDIRECT_URI = "https://supreme-space-sniffle-44jxxx657qvhj59x-5000.app.github.dev/login/google/callback"

def init_db():
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
        summary TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        reset_token TEXT
    )''')
    
    # Add new columns if they don't exist
    try:
        c.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Add new columns to existing summaries table if they don't exist
    try:
        c.execute("ALTER TABLE summaries ADD COLUMN title TEXT")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE summaries ADD COLUMN thumbnail TEXT")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE summaries ADD COLUMN duration TEXT")
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute("ALTER TABLE summaries ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def check_existing_summary(url):
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("SELECT transcript, summary FROM summaries WHERE url = ?", (url,))
    row = c.fetchone()
    conn.close()
    return row

def save_to_db(url, transcript, summary, title=None, thumbnail=None, duration=None):
    # Normalize URL to prevent duplicates
    normalized_url = normalize_youtube_url(url)
    
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("INSERT INTO summaries (url, title, thumbnail, duration, created_at, transcript, summary) VALUES (?, ?, ?, ?, datetime('now'), ?, ?)", 
              (normalized_url, title, thumbnail, duration, transcript, summary))
    conn.commit()
    conn.close()

def get_ydl_opts(extract_flat=False):
    """Get yt-dlp options with anti-bot detection measures"""
    
    base_opts = {
        'format': 'bestaudio/best' if not extract_flat else None,
        'outtmpl': 'audio.%(ext)s' if not extract_flat else None,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_flat,
        'no_check_certificate': True,
        'prefer_insecure': True,
    }
    
    return base_opts

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
    """Normalize YouTube URL to standard format for duplicate detection"""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def get_video_info_fallback(video_url):
    """Get video info using both yt-dlp and YouTube's oEmbed API"""
    video_info = {}
    
    try:
        video_id = extract_video_id(video_url)
        if not video_id:
            return None
        
        # First try yt-dlp for duration and detailed info
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if info:
                    video_info['title'] = info.get('title', 'Unknown Title')
                    video_info['author'] = info.get('uploader', 'Unknown Author')
                    video_info['duration'] = info.get('duration', 0)
                    video_info['thumbnail'] = info.get('thumbnail', '')
                    
                    # Format duration as string
                    if video_info['duration'] > 0:
                        minutes = video_info['duration'] // 60
                        seconds = video_info['duration'] % 60
                        video_info['duration_string'] = f"{minutes}:{seconds:02d}"
                    else:
                        video_info['duration_string'] = "Unknown"
                    
                    video_info['available'] = True
                    video_info['video_id'] = video_id
                    return video_info
        except Exception as e:
            print(f"yt-dlp info extraction failed: {e}")
        
        # Fallback to YouTube's oEmbed API (no duration available)
        api_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('title', 'Unknown Title'),
                'author': data.get('author_name', 'Unknown Author'),
                'thumbnail': data.get('thumbnail_url', ''),
                'duration': 0,  # Not available from this API
                'duration_string': "Unknown",
                'available': True,
                'video_id': video_id
            }
    except Exception as e:
        print(f"Fallback API failed: {e}")
    
    return None

def generate_summary_from_metadata(video_info):
    """Generate a summary based on video metadata"""
    if not video_info:
        return "Could not retrieve video information."
    
    title = video_info.get('title', 'Unknown Title')
    author = video_info.get('author', 'Unknown Author')
    duration = video_info.get('duration', 0)
    
    # Create a summary based on available metadata
    summary_parts = []
    
    # Title analysis
    summary_parts.append(f"Video Title: {title}")
    summary_parts.append(f"Creator: {author}")
    
    # Duration info
    if duration > 0:
        minutes = duration // 60
        seconds = duration % 60
        summary_parts.append(f"Duration: {minutes}:{seconds:02d}")
    
    # Topic analysis based on title
    topic_keywords = {
        'tutorial': 'Educational/Tutorial Content',
        'review': 'Product/Service Review',
        'music': 'Music/Entertainment',
        'news': 'News/Current Events',
        'comedy': 'Comedy/Entertainment',
        'gaming': 'Gaming Content',
        'tech': 'Technology Content',
        'cooking': 'Cooking/Recipe Content',
        'travel': 'Travel/Adventure Content',
        'fitness': 'Health/Fitness Content',
        'python': 'Programming/Development Content',
        'javascript': 'Programming/Development Content',
        'programming': 'Programming/Development Content',
        'coding': 'Programming/Development Content',
        'development': 'Programming/Development Content'
    }
    
    title_lower = title.lower()
    detected_topics = []
    for keyword, topic in topic_keywords.items():
        if keyword in title_lower:
            detected_topics.append(topic)
    
    if detected_topics:
        summary_parts.append(f"Content Type: {', '.join(set(detected_topics))}")
    
    # Analyze title for key information
    if 'beginner' in title_lower or 'basics' in title_lower or 'introduction' in title_lower:
        summary_parts.append("Level: Beginner-friendly content")
    elif 'advanced' in title_lower or 'expert' in title_lower or 'pro' in title_lower:
        summary_parts.append("Level: Advanced content")
    
    # Final summary
    summary = "\n".join(summary_parts)
    
    # Add note about limitations
    summary += "\n\n[Note: This summary is based on video metadata only. Full audio transcription is currently unavailable due to YouTube's enhanced bot detection. To get full transcripts, you may need to:\n1. Update your cookies with fresh authentication data\n2. Try again later when restrictions are lifted\n3. Use YouTube's built-in transcript feature if available]"
    
    return summary

def test_video_accessibility(url):
    """Test if a video is accessible before attempting download"""
    try:
        test_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        # Use cookies if available
        if os.path.exists('cookies.txt'):
            test_opts['cookiefile'] = 'cookies.txt'
        
        with yt_dlp.YoutubeDL(test_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Check if video is available
            if not info:
                return False, "Video information not available"
            
            # Check for common restrictions
            if info.get('availability') == 'private':
                return False, "Video is private"
            
            if info.get('availability') == 'premium_only':
                return False, "Video requires premium subscription"
            
            if info.get('live_status') == 'is_live':
                return False, "Cannot process live streams"
            
            # Check duration (skip very long videos)
            duration = info.get('duration', 0)
            if duration > 3600:  # 1 hour
                return False, f"Video is too long ({duration//60} minutes). Please use videos under 1 hour."
            
            return True, "Video is accessible"
            
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            # Try fallback method immediately
            print("yt-dlp blocked, trying fallback API...")
            fallback_info = get_video_info_fallback(url)
            if fallback_info:
                print("✅ Fallback API worked! Video is accessible.")
                # Return success since we can at least verify the video exists
                return True, "Video is accessible via fallback API (download may still fail)"
            else:
                print("❌ Fallback API also failed")
                # Don't block the request - let the download attempt handle it
                return True, "Video accessibility unknown - will attempt download anyway"
        elif "Video unavailable" in error_msg:
            return False, "Video is unavailable or has been removed"
        else:
            print(f"Accessibility check failed: {error_msg}")
            # Don't block the request - let the download attempt handle it
            return True, "Video accessibility unknown - will attempt download anyway"

def download_audio(url, max_retries=3):
    """Download audio from YouTube URL with retry logic and fallback methods"""
    
    for attempt in range(max_retries):
        try:
            # Add random delay between attempts to avoid rate limiting
            if attempt > 0:
                delay = random.uniform(2, 5) * (2 ** attempt)  # Exponential backoff
                print(f"Retrying download in {delay:.1f} seconds...")
                time.sleep(delay)
            
            ydl_opts = get_ydl_opts(extract_flat=False)
            
            # Add attempt-specific modifications
            if attempt == 1:
                # Second attempt: try different player client
                ydl_opts['extractor_args']['youtube']['player_client'] = ['android', 'web']
            elif attempt == 2:
                # Third attempt: try with different user agent
                ydl_opts['user_agent'] = 'com.google.android.youtube/17.31.35 (Linux; U; Android 11)'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            print(f"Successfully downloaded audio on attempt {attempt + 1}")
            return True
            
        except Exception as e:
            print(f"Download attempt {attempt + 1} failed: {e}")
            error_msg = str(e)
            
            # Check if it's a bot detection error
            if "Sign in to confirm you're not a bot" in error_msg:
                print("Bot detection encountered, trying alternative approaches...")
                
                # Try emergency methods with even more variations
                emergency_methods = [
                    {
                        'name': 'Android client (worst quality)',
                        'opts': {
                            'format': 'worst[ext=mp4]/worst/bestaudio[ext=m4a]/bestaudio',
                            'outtmpl': 'audio.%(ext)s',
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '96',
                            }],
                            'quiet': True,
                            'no_warnings': True,
                            'user_agent': 'com.google.android.youtube/17.31.35 (Linux; U; Android 11)',
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['android'],
                                    'skip': ['dash', 'hls'],
                                }
                            }
                        }
                    },
                    {
                        'name': 'iOS client (worst quality)',
                        'opts': {
                            'format': 'worst[ext=mp4]/worst/bestaudio[ext=m4a]/bestaudio',
                            'outtmpl': 'audio.%(ext)s',
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '96',
                            }],
                            'quiet': True,
                            'no_warnings': True,
                            'user_agent': 'com.google.ios.youtube/17.33.2 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)',
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['ios'],
                                    'skip': ['dash', 'hls'],
                                }
                            }
                        }
                    },
                    {
                        'name': 'TV client (basic)',
                        'opts': {
                            'format': 'worst[ext=mp4]/worst',
                            'outtmpl': 'audio.%(ext)s',
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '64',
                            }],
                            'quiet': True,
                            'no_warnings': True,
                            'user_agent': 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebKit/538.1',
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['tv'],
                                    'skip': ['dash', 'hls'],
                                }
                            }
                        }
                    },
                    {
                        'name': 'Web client (no cookies)',
                        'opts': {
                            'format': 'worst[ext=mp4]/worst/bestaudio[ext=m4a]/bestaudio',
                            'outtmpl': 'audio.%(ext)s',
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '96',
                            }],
                            'quiet': True,
                            'no_warnings': True,
                            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['web'],
                                    'skip': ['dash', 'hls'],
                                }
                            },
                            # Don't use cookies for this attempt
                            'cookiefile': None,
                            'cookiesfrombrowser': None,
                        }
                    }
                ]
                
                # Add cookies to all methods except the last one
                for i, method in enumerate(emergency_methods[:-1]):
                    if os.path.exists('cookies.txt'):
                        method['opts']['cookiefile'] = 'cookies.txt'
                
                for method in emergency_methods:
                    try:
                        print(f"Trying emergency method: {method['name']}")
                        time.sleep(random.uniform(1, 3))  # Random delay
                        with yt_dlp.YoutubeDL(method['opts']) as ydl:
                            ydl.download([url])
                        print(f"✅ Emergency method {method['name']} worked!")
                        return True
                    except Exception as emergency_error:
                        print(f"❌ Emergency method {method['name']} failed: {emergency_error}")
                        continue
            
            # If this is the last attempt, try one more minimal fallback
            if attempt == max_retries - 1:
                print("Attempting final minimal fallback...")
                try:
                    fallback_opts = {
                        'format': 'worst[ext=mp4]/worst',
                        'outtmpl': 'audio.%(ext)s',
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '64',
                        }],
                        'quiet': True,
                        'no_warnings': True,
                        'user_agent': 'yt-dlp/2024.07.16',
                        'no_check_certificate': True,
                    }
                    
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        ydl.download([url])
                    
                    print("✅ Minimal fallback download successful")
                    return True
                    
                except Exception as fallback_error:
                    print(f"❌ Minimal fallback also failed: {fallback_error}")
    
    print("❌ All download attempts failed")
    
    # Final fallback: try to get video info and create a summary based on metadata
    print("🔄 Attempting metadata-based summary...")
    try:
        video_info = get_video_info_fallback(url)
        if video_info and video_info.get('title'):
            print(f"✅ Got video title: {video_info['title']}")
            
            # Generate a summary based on video metadata
            summary = generate_summary_from_metadata(video_info)
            
            # Return info indicating we have metadata-based summary
            return {
                'title': video_info['title'], 
                'audio_available': False,
                'metadata_summary': summary,
                'video_info': video_info
            }
            
    except Exception as e:
        print(f"❌ Metadata fallback method also failed: {e}")
    
    return False

def convert_to_wav():
    """Convert audio file to WAV format with proper duration handling"""
    try:
        from moviepy.editor import AudioFileClip
        
        # Find the downloaded audio file
        audio_files = ["audio.mp3", "audio.m4a", "audio.webm", "audio.wav", "audio.mp4"]
        audio_file = None
        
        for file in audio_files:
            if os.path.exists(file):
                audio_file = file
                break
        
        if not audio_file:
            raise FileNotFoundError("No audio file found to convert")
        
        # Load audio clip
        clip = AudioFileClip(audio_file)
        duration = clip.duration
        
        print(f"Audio file: {audio_file}")
        print(f"Audio duration: {duration} seconds")
        
        # Use the actual duration or 120 seconds, whichever is smaller
        max_duration = min(duration, 120)
        
        # Only use subclip if we need to limit duration
        if duration > 120:
            clip = clip.subclip(0, max_duration)
            print(f"Clipped audio to {max_duration} seconds")
        
        # Write to WAV file
        clip.write_audiofile("lecture.wav", verbose=False, logger=None)
        
        # Close the clip to free memory
        clip.close()
        
        print("✅ Successfully converted to lecture.wav")
        return True
        
    except Exception as e:
        print(f"Error in convert_to_wav: {e}")
        return False

def transcribe_audio():
    """Transcribe audio using Whisper with error handling"""
    try:
        if not os.path.exists("lecture.wav"):
            raise FileNotFoundError("lecture.wav not found")
        
        model = whisper.load_model("tiny")
        result = model.transcribe("lecture.wav", fp16=False)
        
        transcript = result['text']
        print(f"✅ Transcription successful, length: {len(transcript)} characters")
        
        return transcript
        
    except Exception as e:
        print(f"Error in transcribe_audio: {e}")
        # Try with a different audio file if lecture.wav failed
        audio_files = ["audio.mp3", "audio.m4a", "audio.webm"]
        for audio_file in audio_files:
            if os.path.exists(audio_file):
                try:
                    print(f"Trying direct transcription with {audio_file}")
                    model = whisper.load_model("tiny")
                    result = model.transcribe(audio_file, fp16=False)
                    return result['text']
                except Exception as fallback_error:
                    print(f"Fallback transcription with {audio_file} failed: {fallback_error}")
                    continue
        
        return f"Transcription failed: {str(e)}"

def transcribe_audio_whisper(audio_path):
    """Transcribe audio using Whisper with better error handling"""
    try:
        import whisper
        
        # Load Whisper model
        model = whisper.load_model("base")
        
        # Transcribe with proper error handling
        result = model.transcribe(
            audio_path,
            language='en',
            task='transcribe',
            fp16=False  # Use fp32 for better compatibility
        )
        
        return result["text"]
        
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return f"Transcription failed: {str(e)}"

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
    print("Session at home:", dict(session))
    return render_template('index.html')

@app.route('/summaries')
def summaries():
    """Display all previous summaries in a grid layout, showing only the latest for each unique video"""
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    
    # Get all summaries and normalize URLs to group duplicates
    c.execute("SELECT id, url, title, thumbnail, duration, created_at, SUBSTR(summary, 1, 150) as summary_preview FROM summaries ORDER BY created_at DESC")
    all_summaries = c.fetchall()
    
    # Group by normalized URL and keep only the latest
    url_groups = {}
    for row in all_summaries:
        normalized_url = normalize_youtube_url(row[1])
        if normalized_url not in url_groups or row[5] > url_groups[normalized_url][5]:
            url_groups[normalized_url] = row
    
    # Convert back to list and sort by creation time
    summaries = []
    for row in sorted(url_groups.values(), key=lambda x: x[5], reverse=True):
        title = row[2]
        url = row[1]
        
        # If title is missing, try to fetch it from the URL
        if not title or title == 'Unknown Video':
            try:
                video_info = get_video_info_fallback(url)
                if video_info and video_info.get('title'):
                    title = video_info['title']
                    # Update the database with the fetched title
                    c.execute("UPDATE summaries SET title = ? WHERE id = ?", (title, row[0]))
                    conn.commit()
                else:
                    title = 'Unknown Video'
            except:
                title = 'Unknown Video'
        
        # If duration is missing or "Unknown", try to fetch it
        duration = row[4]
        if not duration or duration == 'Unknown':
            try:
                video_info = get_video_info_fallback(url)
                if video_info and video_info.get('duration_string'):
                    duration = video_info['duration_string']
                    # Update the database with the fetched duration
                    c.execute("UPDATE summaries SET duration = ? WHERE id = ?", (duration, row[0]))
                    conn.commit()
                else:
                    duration = 'Unknown'
            except:
                duration = 'Unknown'
        
        summary_data = {
            'id': row[0],
            'url': url,
            'title': title,
            'thumbnail': row[3] or 'https://img.youtube.com/vi/default/maxresdefault.jpg',
            'duration': duration,
            'created_at': row[5],
            'summary_preview': row[6] + '...' if row[6] else 'No summary available'
        }
        
        # Extract video ID from URL for thumbnail fallback
        if not summary_data['thumbnail'] or summary_data['thumbnail'] == 'https://img.youtube.com/vi/default/maxresdefault.jpg':
            if summary_data['url']:
                import re
                video_id_match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([^&\n?#]+)', summary_data['url'])
                if video_id_match:
                    video_id = video_id_match.group(1)
                    summary_data['thumbnail'] = f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg'
                    # Update the database with the thumbnail
                    c.execute("UPDATE summaries SET thumbnail = ? WHERE id = ?", (summary_data['thumbnail'], row[0]))
                    conn.commit()
        
        summaries.append(summary_data)
    
    conn.close()
    return render_template('summaries.html', summaries=summaries)

@app.route('/summary/<int:summary_id>')
def get_summary(summary_id):
    """Get full summary and transcript for a specific video"""
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    
    c.execute("""
        SELECT url, title, thumbnail, duration, created_at, transcript, summary
        FROM summaries 
        WHERE id = ?
    """, (summary_id,))
    
    row = c.fetchone()
    conn.close()
    
    if not row:
        return jsonify({'error': 'Summary not found'}), 404
    
    return jsonify({
        'url': row[0],
        'title': row[1] or 'Unknown Video',
        'thumbnail': row[2],
        'duration': row[3],
        'created_at': row[4],
        'transcript': row[5],
        'summary': row[6]
    })

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

@app.route('/summarize', methods=['POST'])
def summarize():
    # Temporarily bypass authentication for testing
    # if 'user_id' not in session:
    #     return jsonify({'error': 'Unauthorized'}), 403

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
            # First, test if the video is accessible
            is_accessible, access_message = test_video_accessibility(url)
            if not is_accessible:
                return jsonify({'error': access_message}), 400
            
            print(f"Video accessibility check: {access_message}")
            
            # Try to download audio
            download_result = download_audio(url)
            if not download_result:
                # Provide specific error message based on cookies
                if os.path.exists('cookies.txt'):
                    error_msg = "Failed to download video. YouTube is blocking access despite having cookies. This may be due to:\n• Expired or invalid cookies\n• IP-based restrictions\n• Video-specific restrictions\n\nPlease try:\n1. Refreshing your cookies\n2. Waiting 10-15 minutes\n3. Trying a different video"
                else:
                    error_msg = "Failed to download video due to YouTube bot detection. Please:\n1. Run 'python setup_cookies.py' to set up cookies\n2. Extract cookies from your browser\n3. Try again with cookies.txt file"
                
                return jsonify({'error': error_msg}), 500
            
            # Check if we got video info but no audio
            if isinstance(download_result, dict) and not download_result.get('audio_available', True):
                # We have metadata-based summary
                if 'metadata_summary' in download_result:
                    video_info = download_result.get('video_info', {})
                    video_title = video_info.get('title', 'Unknown Video')
                    thumbnail = video_info.get('thumbnail', '')
                    duration = video_info.get('duration_string', '')
                    metadata_summary = download_result['metadata_summary']
                    
                    # Use the metadata summary as both transcript and summary
                    transcript = f"Video: {video_title}\n\nMetadata-based information:\n{metadata_summary}"
                    summary = metadata_summary
                    
                    # Save to database with metadata
                    save_to_db(url, transcript, summary, video_title, thumbnail, duration)
                    
                    return jsonify({
                        'transcript': transcript, 
                        'summary': summary,
                        'metadata_only': True,
                        'note': 'This summary is based on video metadata only due to YouTube restrictions.'
                    })
                else:
                    video_title = download_result.get('title', 'Unknown Video')
                    error_msg = f"Unable to download audio for video: {video_title}\n\nThis may be due to:\n• YouTube's enhanced bot detection\n• Geographic restrictions\n• Video-specific protection\n\nThe video exists but cannot be processed at this time."
                    return jsonify({'error': error_msg}), 500
            
            # Extract video metadata for successful downloads
            try:
                video_info = get_video_info_fallback(url)
                video_title = video_info.get('title', 'Unknown Video') if video_info else 'Unknown Video'
                thumbnail = video_info.get('thumbnail', '') if video_info else ''
                duration = video_info.get('duration_string', '') if video_info else ''
            except:
                video_title = 'Unknown Video'
                thumbnail = ''
                duration = ''
            
            convert_to_wav()
            transcript = transcribe_audio()
            summary = summarize_text(transcript)
            transcript = capitalize_sentences(transcript)
            summary = capitalize_sentences(summary)
            save_to_db(url, transcript, summary, video_title, thumbnail, duration)
            
            # Clean up temporary files
            try:
                os.remove("audio.mp3")
                os.remove("lecture.wav")
            except FileNotFoundError:
                pass  # Files might not exist if conversion failed
                
        except Exception as e:
            print(f"Error in summarize: {e}")
            return jsonify({'error': f'An error occurred while processing the video: {str(e)}'}), 500

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

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        conn = sqlite3.connect("summaries.db")
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email = ?", (email,))
        user = c.fetchone()
        if user:
            # Generate a secure token
            token = secrets.token_urlsafe(32)
            c.execute("UPDATE users SET reset_token = ? WHERE email = ?", (token, email))
            conn.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
            conn.close()
            # In production, send this link via email!
            return f"Password reset link: <a href='{reset_link}'>{reset_link}</a>"
        conn.close()
        return "Email not found.", 404
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        conn = sqlite3.connect("summaries.db")
        c = conn.cursor()
        c.execute("UPDATE users SET password = ?, reset_token = NULL WHERE reset_token = ?", (hashed_password, token))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

@app.route('/get-playlist', methods=['POST'])
def get_playlist():
    """Extract videos from a YouTube playlist"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    
    playlist_url = request.json.get('url')
    if not playlist_url:
        return jsonify({'error': 'No playlist URL provided'}), 400
    
    try:
        # Extract playlist ID from URL
        import re
        playlist_id_match = re.search(r'list=([^&]+)', playlist_url)
        if not playlist_id_match:
            return jsonify({'error': 'Invalid playlist URL'}), 400
        
        playlist_id = playlist_id_match.group(1)
        
        # Use yt-dlp to extract playlist info
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        # Use cookies if available
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            
            if not playlist_info or 'entries' not in playlist_info:
                return jsonify({'error': 'Could not extract playlist information'}), 400
            
            videos = []
            for entry in playlist_info['entries']:
                if entry:  # Skip None entries
                    video_id = entry.get('id')
                    if video_id:
                        video = {
                            'id': video_id,
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'title': entry.get('title', 'Unknown Title'),
                            'thumbnail': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                            'duration': entry.get('duration_string', 'Unknown')
                        }
                        videos.append(video)
            
            return jsonify({
                'playlist_title': playlist_info.get('title', 'Unknown Playlist'),
                'videos': videos[:50]  # Limit to 50 videos for performance
            })
    
    except Exception as e:
        print(f"Playlist extraction error: {e}")
        return jsonify({'error': f'Failed to load playlist: {str(e)}'}), 500

def extract_audio_from_video(video_path, output_audio_path):
    """Extract audio from video file"""
    try:
        from moviepy.editor import VideoFileClip
        
        # Load video and extract audio
        video = VideoFileClip(video_path)
        audio = video.audio
        
        # Get the actual duration
        duration = audio.duration
        print(f"Audio duration: {duration} seconds")
        
        # Ensure we don't exceed the actual duration
        if duration > 0:
            # Write audio with proper duration handling
            audio.write_audiofile(
                output_audio_path,
                logger=None,  # Suppress MoviePy logs
                verbose=False,
                temp_audiofile='temp-audio.m4a'
            )
        
        # Clean up
        audio.close()
        video.close()
        
        return True
        
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False

def download_youtube_audio(url, output_path="audio"):
    """Download YouTube audio with better error handling"""
    
    max_retries = 2  # Reduce retries since cookies aren't working
    retry_delay = 3   # Shorter delay
    
    for attempt in range(max_retries):
        try:
            print(f"Download attempt {attempt + 1}")
            
            ydl_opts = get_ydl_opts(extract_flat=False)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Check if file was created
            possible_files = [
                "audio.mp3", "audio.m4a", "audio.webm", 
                "audio.wav", "audio.mp4", "audio.mkv"
            ]
            
            for file in possible_files:
                if os.path.exists(file):
                    print(f"✅ Download successful: {file}")
                    return file
            
            raise FileNotFoundError("No audio file found after download")
            
        except Exception as e:
            print(f"Download attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay += 2
            else:
                print("All download attempts failed")
                raise e

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
