# main_colab.py - Fixed version for Google Colab
import os
os.environ['COLAB_ENV'] = '1'


# Core imports
from flask import Flask, request, jsonify, render_template
import time
import random
from urllib.parse import urlparse, parse_qs
import re
import threading

# Ensure torch is imported before any usage
try:
    import torch
    print(f"✅ PyTorch imported successfully - CUDA: {torch.cuda.is_available()}")
except ImportError:
    print("Installing torch...")
    import subprocess
    subprocess.run(["pip", "install", "torch", "torchaudio"], check=True)
    import torch

# ML/AI imports
try:
    import whisper
    print("✅ Whisper imported successfully")
except ImportError as e:
    print(f"❌ Whisper import failed: {e}")
    print("Installing whisper...")
    import subprocess
    subprocess.run(["pip", "install", "openai-whisper"], check=True)
    import whisper

try:
    import yt_dlp
    print("✅ yt-dlp imported successfully")
except ImportError:
    print("Installing yt-dlp...")
    import subprocess
    subprocess.run(["pip", "install", "yt-dlp"], check=True)
    import yt_dlp

try:
    from transformers import pipeline
except ImportError:
    print("Installing transformers...")
    import subprocess
    subprocess.run(["pip", "install", "transformers"], check=True)
    from transformers import pipeline

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
            print("❌ No audio file found")
            return False
    
        clip = AudioFileClip(audio_file)
        duration = clip.duration
    
        print(f"Audio: {duration/60:.1f} minutes")
    
        if duration > COLAB_CONFIG['max_video_hours'] * 3600:
            print(f"❌ Video too long (max {COLAB_CONFIG['max_video_hours']} hours)")
            clip.close()
            return False
    
        clip.write_audiofile("lecture.wav", verbose=False, logger=None)
        clip.close()
        print("✅ Audio converted to WAV format")
        return True
    
    except Exception as e:
        print(f"Conversion failed: {e}")
        return False

def get_audio_duration():
    """Get duration of lecture.wav file"""
    try:
        if os.path.exists("lecture.wav"):
            clip = AudioFileClip("lecture.wav")
            duration = clip.duration
            clip.close()
            return duration
        return 0
    except Exception as e:
        print(f"Error getting audio duration: {e}")
        return 0

def transcribe_audio_colab():
    """Colab transcription with GPU acceleration"""
    try:
        if not os.path.exists("lecture.wav"):
            raise FileNotFoundError("lecture.wav not found")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using: {device}")
        
        model = whisper.load_model(COLAB_CONFIG['whisper_model'], device=device)
        
        result = model.transcribe(
            "lecture.wav",
            language='en',
            fp16=torch.cuda.is_available(),
            verbose=True
        )
        
        return result['text']
    
    except Exception as e:
        return f"Transcription failed: {e}"

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
            split_at = text.rfind(".", 0, max_chunk)
            if split_at == -1:
                split_at = max_chunk
            chunks.append(text[:split_at + 1])
            text = text[split_at + 1:]

        summary = ""
        for chunk in chunks:
            result = summarizer(chunk, max_length=150, min_length=50, do_sample=False)
            summary += result[0]['summary_text'] + " "
        
        return summary.strip()
    except Exception as e:
        return f"Summarization failed: {e}"

def capitalize_sentences(text):
    """Capitalize sentences"""
    try:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        capitalized = [s.strip().capitalize() for s in sentences if s.strip()]
        return ' '.join(capitalized)
    except Exception:
        return text

def cleanup_audio_files():
    """Clean up temporary audio files"""
    files_to_clean = ["audio.mp3", "audio.m4a", "audio.webm", "audio.wav", "audio.mp4", "lecture.wav"]
    cleaned_count = 0
    
    for file in files_to_clean:
        try:
            if os.path.exists(file):
                os.remove(file)
                cleaned_count += 1
        except Exception as e:
            print(f"⚠️ Could not remove {file}: {e}")
    
    if cleaned_count > 0:
        print(f"🧹 Cleaned up {cleaned_count} audio files")


# Initialize Flask app (ensure this is before any route definitions)
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'colab_secret_key_' + str(random.randint(1000, 9999))

# Initialize Firebase for Colab
def init_firebase_colab():
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

# Route definitions (move below app initialization)
@app.route('/')
def home():
    gpu_status = "GPU: " + ("Available" if torch.cuda.is_available() else "Not available")
    firebase_status = "Firebase: " + ("Initialized" if db_firebase else "Not initialized")
    return render_template('index.html', gpu_status=gpu_status, firebase_status=firebase_status)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'gpu_available': torch.cuda.is_available(),
        'firebase_connected': db_firebase is not None,
        'whisper_model': COLAB_CONFIG['whisper_model'],
        'max_video_hours': COLAB_CONFIG['max_video_hours']
    })

@app.route('/summarize', methods=['POST'])
def summarize():
    """Main summarization endpoint - COLAB VERSION"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    print(f"🎬 Processing video: {url}")

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

        # Transcribe (use chunked processing for videos longer than 15 minutes)
        audio_duration = get_audio_duration()
        print(f"📊 Audio duration: {audio_duration/60:.1f} minutes")
        
        if audio_duration > 900:  # 15 minutes
            print("🎬 Using chunked transcription for long video...")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            transcript = transcribe_chunked_colab(audio_duration, device)
        else:
            print("🎤 Using standard transcription...")
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
        cleanup_audio_files()
        
        return jsonify({
            'transcript': transcript,
            'summary': summary,
            'processed_on': 'Google Colab (GPU)' if torch.cuda.is_available() else 'Google Colab (CPU)',
            'note': 'Processed with GPU acceleration and saved to shared database' if torch.cuda.is_available() else 'Processed on CPU and saved to shared database'
        })
        
    except Exception as e:
        print(f"❌ Error in summarize endpoint: {e}")
        cleanup_audio_files()  # Clean up on error
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

def setup_ngrok_tunnel():
    """Set up ngrok tunnel with better error handling"""
    try:
        # Kill any existing tunnels
        ngrok.kill()
        print("🔄 Setting up ngrok tunnel...")
        
        # Create tunnel
        public_url = ngrok.connect(5000)
        public_url_str = str(public_url)
        
        print(f"✅ Public URL created: {public_url_str}")
        print(f"🔗 Click this link to access your YouTube Summarizer:")
        print(f"   {public_url_str}")
        print()
        print("🌐 You can share this URL with others!")
        print("⚠️  Note: This URL is temporary and will expire when you stop this notebook.")
        
        return public_url_str
        
    except Exception as e:
        print(f"❌ ngrok setup failed: {e}")
        print("🚀 Will run without public URL (Colab internal only)")
        return None

if __name__ == '__main__':
    print("🚀 Starting YouTube Video Summarizer...")
    print("=" * 50)
    
    # Print system info
    print(f"🐍 Python: {os.sys.version}")
    print(f"🎮 GPU Available: {torch.cuda.is_available()}")
    print(f"🔥 Firebase: {'Connected' if db_firebase else 'Not connected'}")
    print(f"⚙️ Whisper Model: {COLAB_CONFIG['whisper_model']}")
    print(f"⏱️ Max Video Length: {COLAB_CONFIG['max_video_hours']} hours")
    print()
    
    # Set up ngrok tunnel
    public_url = setup_ngrok_tunnel()
    
    if public_url:
        print(f"🌍 PUBLIC ACCESS: {public_url}")
        print("=" * 50)
    
    print("🚀 Starting Flask server...")
    print("📝 Ready to process YouTube videos!")
    print()
    print("💡 To stop the server: Press Ctrl+C or interrupt the kernel")
    print()
    
    try:
        # Run Flask app
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=False, 
            use_reloader=False,  # Important for Colab
            threaded=True
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        # Clean up
        try:
            ngrok.kill()
            print("🧹 Ngrok tunnel closed")
        except:
            pass
        
        cleanup_audio_files()
        print("👋 YouTube Summarizer stopped")

COLAB_CONFIG = {
    'whisper_model': 'base',
    'max_video_hours': 6,
    'chunk_duration': 900,
    'use_gpu': True
}
