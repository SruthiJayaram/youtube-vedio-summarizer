from flask import Flask, render_template, request, jsonify
from moviepy.editor import AudioFileClip
import whisper
import yt_dlp
from transformers import pipeline
import os
import sqlite3
import re

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        transcript TEXT,
        summary TEXT
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
    # Split into sentences using regex to handle ".", "!" and "?"
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Capitalize first character of each sentence
    capitalized = [s.strip().capitalize() for s in sentences]
    return ' '.join(capitalized)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/summarize', methods=['POST'])
def summarize():
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

            # Capitalize each sentence
            transcript = capitalize_sentences(transcript)
            summary = capitalize_sentences(summary)

            save_to_db(url, transcript, summary)
            os.remove("audio.mp3")
            os.remove("lecture.wav")
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'transcript': transcript, 'summary': summary})


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
