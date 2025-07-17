# YouTube Video Summarizer (RecapIt)

RecapIt is a Flask web application that summarizes YouTube videos using AI. It supports login/signup (including Google OAuth), stores summaries in a local SQLite database, and provides a modern UI.

## Features
- Summarize YouTube videos and playlists
- User authentication (email/password and Google OAuth)
- Stores transcripts and summaries in a database
- Responsive UI with login/signup/logout and user icon

## Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/SruthiJayaram/youtube-vedio-summarizer.git
cd youtube-vedio-summarizer
```

### 2. Python Environment
Create a virtual environment and activate it:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
If you don't have a `requirements.txt`, install manually:
```bash
pip install flask flask-session moviepy openai-whisper yt-dlp transformers python-dotenv requests werkzeug torch ffmpeg-python
```

### 4. FFmpeg
Make sure FFmpeg is installed on your system:
```bash
sudo apt update && sudo apt install -y ffmpeg
```

### 5. Environment Variables
Create a `.env` file in the project root:
```
GOOGLE_OAUTH_CLIENT_ID=your-client-id-here
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret-here
```
**Do not commit your real `.env` file!**
Instead, commit `.env.example` with placeholder values.

### 6. Google OAuth Setup
- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create OAuth 2.0 credentials (type: Web application)
- Add your Codespaces public URL as an authorized redirect URI, e.g.:
  ```
  https://your-codespace-id-5000.app.github.dev/login/google/callback
  ```
- Copy your client ID and secret into `.env`

### 7. Run the App
```bash
source .venv/bin/activate
python main.py
```

## Usage
- Visit the app in your browser (Codespaces public URL or `http://127.0.0.1:5000` if local)
- Register or log in
- Paste a YouTube video link and click "Generate Summary"
- View transcript and summary

## Development Notes
- The repo includes a patch for `moviepy/editor.py` if you encounter import errors with Python 3.12+
- If you use Codespaces, update the redirect URI in `main.py` and Google Cloud Console to match your public URL
- `.env` is ignored by git; use `.env.example` for sharing config


---
**For questions or issues, open an issue on GitHub or contact the repo owner.**
