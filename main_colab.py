# main_colab.py - Clean Python version for Google Colab
import os
os.environ['COLAB_ENV'] = '1'

from flask import Flask, request, jsonify
import whisper
import yt_dlp
from transformers import pipeline
import time
import random
from urllib.parse import urlparse, parse_qs
import re
import firebase_admin
from firebase_admin import credentials, firestore
import torch
from moviepy.editor import AudioFileClip
import threading

app = Flask(__name__)
app.secret_key = 'colab_secret_key'

# Initialize Firebase for Colab
def init_firebase_colab():
    """Initialize Firebase for Colab"""
    try:
        if not firebase_admin._apps:
            if os.path.exists('firebase-key.json'):
                cred = credentials.Certificate('firebase-key.json')
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized in Colab")
                return firestore.client()
            else:
                print("❌ Upload firebase-key.json to Colab first!")
                return None
        return firestore.client()
    except Exception as e:
        print(f"Firebase initialization failed: {e}")
        return None

db_firebase = init_firebase_colab()

# Colab Configuration
COLAB_CONFIG = {
    'whisper_model': 'base',
    'max_video_hours': 6,
    'chunk_duration': 900,
    'use_gpu': True
}

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
    """Normalize YouTube URL"""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def save_to_firebase_colab(url, transcript, summary, title=None, thumbnail=None, duration=None):
    """Save to Firebase from Colab"""
    try:
        if not db_firebase:
            print("Firebase not available")
            return False
        
        doc_data = {
            'url': normalize_youtube_url(url),
            'title': title or 'Unknown Video',
            'thumbnail': thumbnail or '',
            'duration': duration or 'Unknown',
            'created_at': firestore.SERVER_TIMESTAMP,
            'transcript': transcript,
            'summary': summary,
            'processed_on': 'Google Colab',
            'video_id': extract_video_id(url)
        }
        
        video_id = extract_video_id(url)
        if video_id:
            db_firebase.collection('summaries').document(video_id).set(doc_data)
            print(f"✅ Saved to Firebase from Colab: {title}")
            return True
            
    except Exception as e:
        print(f"Firebase save failed: {e}")
        return False

def check_existing_summary_colab(url):
    """Check Firebase for existing summary"""
    try:
        if not db_firebase:
            return None
            
        video_id = extract_video_id(url)
        if video_id:
            doc_ref = db_firebase.collection('summaries').document(video_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                print("✅ Found existing summary in Firebase")
                return (data.get('transcript', ''), data.get('summary', ''))
    except Exception as e:
        print(f"Firebase check failed: {e}")
    
    return None

def get_ydl_opts_colab(extract_flat=False):
    """Colab-optimized yt-dlp options"""
    return {
        'format': 'bestaudio/best' if not extract_flat else None,
        'outtmpl': 'audio.%(ext)s' if not extract_flat else None,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_flat,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

def test_video_accessibility_colab(url):
    """Test video accessibility - COLAB VERSION"""
    try:
        test_opts = get_ydl_opts_colab(extract_flat=True)
        
        with yt_dlp.YoutubeDL(test_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return False, "Video information not available"
            
            if info.get('availability') == 'private':
                return False, "Video is private"
            
            if info.get('live_status') == 'is_live':
                return False, "Cannot process live streams"
            
            duration = info.get('duration', 0)
            if duration > 21600:  # 6 hours
                hours = duration // 3600
                return False, f"Video is too long ({hours} hours). Maximum: 6 hours on Colab."
            
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            return True, f"Video accessible ({hours}h {minutes}m) - Colab can process this"
            
    except Exception as e:
        print(f"Accessibility check failed: {e}")
        return True, "Will attempt download"

def download_audio_colab(url):
    """Download audio in Colab"""
    try:
        ydl_opts = get_ydl_opts_colab()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("✅ Audio downloaded in Colab")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def convert_to_wav_colab():
    """Convert to WAV in Colab"""
    try:
        audio_files = ["audio.mp3", "audio.m4a", "audio.webm", "audio.wav", "audio.mp4"]
        audio_file = None
        
        for file in audio_files:
            if os.path.exists(file):
                audio_file = file
                break
        
        if not audio_file:
            raise FileNotFoundError("No audio file found")
        
        clip = AudioFileClip(audio_file)
        duration = clip.duration
        
        print(f"Audio duration: {duration/3600:.1f} hours ({duration/60:.1f} minutes)")
        
        if duration > 21600:  # 6 hours
            print("❌ Video exceeds 6-hour Colab limit")
            clip.close()
            return False
        
        clip.write_audiofile("lecture.wav", verbose=False, logger=None)
        clip.close()
        
        print(f"✅ Converted {duration/60:.1f} minute video in Colab")
        return True
        
    except Exception as e:
        print(f"Conversion failed: {e}")
        return False

def transcribe_audio_colab():
    """Colab transcription with GPU acceleration"""
    try:
        if not os.path.exists("lecture.wav"):
            raise FileNotFoundError("lecture.wav not found")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device}")
        
        try:
            import librosa
            audio_data, sr = librosa.load("lecture.wav", sr=16000)
            duration = len(audio_data) / sr
            print(f"Audio duration: {duration/60:.1f} minutes ({duration/3600:.1f} hours)")
        except:
            duration = 0
        
        if duration > 7200:  # 2+ hours
            return transcribe_chunked_colab(duration, device)
        
        model_size = COLAB_CONFIG['whisper_model']
        print(f"Loading Whisper {model_size} model on {device}...")
        model = whisper.load_model(model_size, device=device)
        
        print("Starting Colab transcription with GPU acceleration...")
        result = model.transcribe(
            "lecture.wav",
            language='en',
            task='transcribe',
            fp16=torch.cuda.is_available(),
            verbose=True
        )
        
        transcript = result['text']
        print(f"✅ Colab transcription completed!")
        print(f"Transcript: {len(transcript):,} characters, {len(transcript.split()):,} words")
        
        return transcript
        
    except Exception as e:
        print(f"Colab transcription failed: {e}")
        return f"Transcription failed: {str(e)}"

def transcribe_chunked_colab(duration, device):
    """Chunked transcription for very long videos in Colab"""
    try:
        print("🎬 Starting chunked transcription in Colab...")
        
        chunk_duration = COLAB_CONFIG['chunk_duration']  # 15 minutes
        
        audio = AudioFileClip("lecture.wav")
        chunks = []
        total_chunks = int(duration // chunk_duration) + 1
        
        print(f"Processing {total_chunks} chunks of {chunk_duration//60} minutes each")
        print(f"Estimated time: {total_chunks * 0.8:.1f} minutes on Colab GPU")
        
        model = whisper.load_model(COLAB_CONFIG['whisper_model'], device=device)
        start_time_overall = time.time()
        
        for i, start_time in enumerate(range(0, int(duration), chunk_duration)):
            end_time = min(start_time + chunk_duration, duration)
            progress = ((i + 1) / total_chunks) * 100
            
            print(f"🔄 Chunk {i+1}/{total_chunks} ({progress:.1f}%): {start_time//60:.0f}-{end_time//60:.0f} min")
            
            chunk = audio.subclip(start_time, end_time)
            chunk_filename = f"chunk_{start_time}.wav"
            chunk.write_audiofile(chunk_filename, verbose=False, logger=None)
            
            result = model.transcribe(chunk_filename, fp16=True, verbose=False)
            chunks.append(result['text'])
            
            chunk.close()
            os.remove(chunk_filename)
            
            elapsed = time.time() - start_time_overall
            eta = (elapsed / (i + 1)) * (total_chunks - i - 1)
            print(f"✅ Chunk completed, ETA: {eta/60:.1f} minutes")
        
        full_transcript = " ".join(chunks)
        audio.close()
        
        total_time = time.time() - start_time_overall
        print(f"🎉 Colab chunked transcription completed in {total_time/60:.1f} minutes!")
        print(f"📊 Total transcript: {len(full_transcript):,} characters")
        
        return full_transcript
        
    except Exception as e:
        print(f"Chunked transcription failed: {e}")
        return f"Transcription failed: {str(e)}"

def summarize_text_colab(text):
    """Summarize text in Colab"""
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
    """Capitalize sentences"""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    capitalized = [s.strip().capitalize() for s in sentences]
    return ' '.join(capitalized)

# Routes
@app.route('/')
def home():
    return """
    <html>
    <head><title>YouTube Summarizer - Google Colab</title></head>
    <body>
        <h1>🎬 YouTube Video Summarizer (Google Colab)</h1>
        <p><strong>Colab Advantages:</strong></p>
        <ul>
            <li>✅ Process videos up to 6 hours</li>
            <li>✅ GPU acceleration (3-5x faster)</li>
            <li>✅ 12-32GB RAM available</li>
            <li>✅ Shared Firebase database</li>
        </ul>
        
        <form id="summarizeForm">
            <label>YouTube URL:</label><br>
            <input type="text" id="url" style="width:400px" placeholder="https://youtube.com/watch?v=..."><br><br>
            <button type="submit">Generate Summary</button>
        </form>
        
        <div id="result" style="margin-top:20px;"></div>
        
        <script>
        document.getElementById('summarizeForm').onsubmit = function(e) {
            e.preventDefault();
            const url = document.getElementById('url').value;
            const resultDiv = document.getElementById('result');
            
            if (!url) {
                alert('Please enter a YouTube URL');
                return;
            }
            
            resultDiv.innerHTML = '<p>🔄 Processing video... This may take several minutes for long videos.</p>';
            
            fetch('/summarize', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: url})
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    resultDiv.innerHTML = '<p style="color:red">❌ Error: ' + data.error + '</p>';
                } else {
                    resultDiv.innerHTML = 
                        '<h3>📝 Transcript:</h3><p>' + data.transcript.substring(0, 500) + '...</p>' +
                        '<h3>📋 Summary:</h3><p>' + data.summary + '</p>' +
                        '<p><em>✅ Processed on: ' + data.processed_on + '</em></p>';
                }
            })
            .catch(error => {
                resultDiv.innerHTML = '<p style="color:red">❌ Error: ' + error + '</p>';
            });
        }
        </script>
    </body>
    </html>
    """

@app.route('/summarize', methods=['POST'])
def summarize():
    """Main summarization endpoint - COLAB VERSION"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    # Check existing
    existing = check_existing_summary_colab(url)
    if existing:
        transcript, summary = existing
        return jsonify({
            'transcript': transcript,
            'summary': summary,
            'processed_on': 'Firebase (existing)',
            'source': 'existing'
        })

    try:
        # Test accessibility
        is_accessible, access_message = test_video_accessibility_colab(url)
        if not is_accessible:
            return jsonify({'error': access_message}), 400
        
        print(f"✅ {access_message}")
        
        # Download
        if not download_audio_colab(url):
            return jsonify({'error': 'Failed to download audio'}), 500
        
        # Convert
        if not convert_to_wav_colab():
            return jsonify({'error': 'Video too long even for Colab (6+ hours)'}), 500

        # Transcribe
        transcript = transcribe_audio_colab()
        if transcript.startswith("Transcription failed:"):
            return jsonify({'error': transcript}), 500
        
        # Summarize
        summary = summarize_text_colab(transcript)
        
        # Clean up and save
        transcript = capitalize_sentences(transcript)
        summary = capitalize_sentences(summary)
        
        # Save to Firebase
        save_to_firebase_colab(url, transcript, summary, "Colab Processed Video", "", "")
        
        # Cleanup files
        for f in ["audio.mp3", "audio.m4a", "audio.webm", "lecture.wav"]:
            try:
                os.remove(f)
            except:
                pass
        
        return jsonify({
            'transcript': transcript,
            'summary': summary,
            'processed_on': 'Google Colab (GPU)',
            'note': 'Processed with GPU acceleration and saved to shared database'
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)