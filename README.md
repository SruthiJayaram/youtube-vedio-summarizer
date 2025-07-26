# YouTube Video Summarizer

AI-powered tool to transcribe and summarize YouTube videos with dual processing options.

## Features

### 🖥️ Local Processing (main.py)
- ✅ Process videos up to 1 hour
- ✅ 8GB RAM optimized
- ✅ Local SQLite + Firebase sync
- ✅ Fast for short videos

### ☁️ Google Colab Processing (main_colab.py)
- ✅ Process videos up to 6 hours
- ✅ GPU acceleration (3-5x faster)
- ✅ 12-32GB RAM available
- ✅ Shared Firebase database

## Setup

### Local Development

1. **Clone repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/youtube-video-summarizer.git
   cd youtube-video-summarizer
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Firebase Setup (Optional but recommended):**
   - Create Firebase project at [Firebase Console](https://console.firebase.google.com/)
   - Enable Firestore Database
   - Generate service account key
   - Save as `firebase-key.json` in project root
   - **⚠️ Never commit this file to Git!**

4. **Run locally:**
   ```bash
   python main.py
   ```

### Google Colab Setup

1. **Open Google Colab**
2. **Upload files:**
   - Upload `main_colab.py`
   - Upload `firebase-key.json` (for database sync)
3. **Install dependencies:**
   ```python
   !pip install -r requirements_colab.txt
   ```
4. **Run the Colab version:**
   ```python
   exec(open('main_colab.py').read())
   ```

## Database

- **Local:** SQLite database (`summaries.db`)
- **Cloud:** Firebase Firestore (shared between local and Colab)
- **Sync:** Automatic sync between both databases

## Processing Limits

| Feature | Local | Google Colab |
|---------|-------|--------------|
| Max Video Length | 1 hour | 6 hours |
| Processing Speed | Standard | 3-5x faster (GPU) |
| Memory | 8GB RAM | 12-32GB RAM |
| Database | SQLite + Firebase | Firebase |
| Cost | Free | Free (with limits) |

## File Structure

```
youtube-video-summarizer/
├── main.py              # Local version
├── main_colab.py        # Google Colab version
├── requirements.txt     # Local dependencies
├── requirements_colab.txt # Colab dependencies
├── templates/           # HTML templates
├── static/             # CSS/JS files
├── firebase-key.json   # Firebase credentials (DON'T COMMIT!)
└── summaries.db        # Local SQLite database
```

## Security Notes

- ⚠️ **Never commit `firebase-key.json`** to version control
- 🔒 Firebase rules are set to open for development - secure for production
- 🛡️ Environment variables should be in `.env` file (not committed)

## 🚨 Important Security Setup

### Firebase Credentials Setup

1. **Download your Firebase service account key:**
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Select your project
   - Go to Project Settings → Service Accounts
   - Click "Generate new private key"
   - Save the downloaded file as `firebase-key.json` in your project root

2. **⚠️ CRITICAL: Never commit Firebase credentials to Git!**
   ```bash
   # The .gitignore file prevents this, but double-check:
   git status  # firebase-key.json should NOT appear in staged files
   ```

3. **Verify your .gitignore is working:**
   ```bash
   # This should show no Firebase files:
   git ls-files | grep firebase
   ```

## For New Users

**After cloning this repository, you MUST:**

1. **Get your own Firebase credentials:**
   - Create your own Firebase project
   - Download the service account key
   - Save it as `firebase-key.json` in the project root

2. **Never commit the Firebase key:**
   - The `.gitignore` file prevents this
   - If you see `firebase-key.json` in `git status`, something is wrong!

3. **Alternative: Use without Firebase:**
   - The app works with SQLite only (local storage)
   - Skip Firebase setup if you don't need cloud sync

### First Time Setup Checklist

- [ ] Clone repository
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Download Firebase key to `firebase-key.json`
- [ ] Verify Firebase key is NOT tracked by Git
- [ ] Run application (`python main.py`)

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test both local and Colab versions
5. Submit pull request

## License

MIT License - see LICENSE file for details
