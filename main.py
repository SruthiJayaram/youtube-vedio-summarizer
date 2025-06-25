from moviepy.editor import AudioFileClip
import whisper
import yt_dlp
from transformers import pipeline
import os
import sqlite3

def download_audio(url):
    print("[1] Downloading audio...")
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
    print("[2] Converting to WAV (first 2 minutes only)...")
    clip = AudioFileClip("audio.mp3").subclip(0, 120)  # 0 to 120 seconds
    clip.write_audiofile("lecture.wav")
    print("✔️ Converted to 'lecture.wav'")

def transcribe_audio():
    print("[3] Transcribing audio using Whisper (tiny model)...")
    model = whisper.load_model("tiny")  # much faster than 'base'
    result = model.transcribe("lecture.wav", fp16=False)
    print("✔️ Transcription complete.")
    return result['text']

def summarize_text(text):
    print("[4] Summarizing transcript...")
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
    for i, chunk in enumerate(chunks):
        print(f"Summarizing chunk {i+1}/{len(chunks)}...")
        summary = summarizer(chunk, max_length=150, min_length=50, do_sample=False)
        final_summary += summary[0]['summary_text'] + " "

    return final_summary.strip()

def save_to_db(url, transcript, summary):
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("INSERT INTO summaries (url, transcript, summary) VALUES (?, ?, ?)", (url, transcript, summary))
    conn.commit()
    conn.close()
    
def check_existing_summary(url):
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("SELECT transcript, summary FROM summaries WHERE url = ?", (url,))
    row = c.fetchone()
    conn.close()
    return row


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


if __name__ == "__main__":
    init_db()
    url = input("Enter YouTube lecture URL: ")
    
    existing = check_existing_summary(url)
    if existing:
        transcript, summary = existing
        print("\n✅ Summary found in database!")
    else:
        download_audio(url)
        convert_to_wav()
        transcript = transcribe_audio()
        summary = summarize_text(transcript)
    
        with open("transcript.txt", "w", encoding="utf-8") as f:
            f.write(transcript)

        with open("summary.txt", "w", encoding="utf-8") as f:
            f.write(summary)

        save_to_db(url, transcript, summary)
        
        os.remove("audio.mp3")
        os.remove("lecture.wav")

    print("\n📝 Transcript Summary:\n")
    print(summary)

