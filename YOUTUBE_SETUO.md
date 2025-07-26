
# YouTube Cookie Setup Instructions

YouTube has implemented bot detection that blocks yt-dlp access. To fix this, you need to provide your browser cookies.

## Method 1: Automatic Cookie Extraction (Recommended)

1. **Install a browser extension to export cookies:**
   - Chrome: "Get cookies.txt LOCALLY" or "cookies.txt"
   - Firefox: "cookies.txt" extension

2. **Export YouTube cookies:**
   - Go to youtube.com in your browser
   - Make sure you're logged in
   - Use the extension to export cookies for youtube.com
   - Save the cookies.txt file in your project directory

3. **Update your Flask app:**
   - The app will automatically use the cookies.txt file if present

## Method 2: Manual Cookie Extraction

1. **Open your browser's developer tools:**
   - Press F12 or right-click → Inspect
   - Go to the Network tab
   - Visit youtube.com
   - Find any request to youtube.com

2. **Copy the Cookie header:**
   - Look for the Cookie header in the request
   - Copy the entire cookie string

3. **Create a cookies.txt file:**
   - Use the format shown in the example below

## Example cookies.txt format:
```
# Netscape HTTP Cookie File
# This is a generated file! Do not edit.

.youtube.com	TRUE	/	FALSE	1234567890	VISITOR_INFO1_LIVE	ABC123
.youtube.com	TRUE	/	FALSE	1234567890	YSC	DEF456
youtube.com	FALSE	/	FALSE	1234567890	PREF	GHI789
```

## Alternative: Use your own YouTube API key

If cookie extraction doesn't work, consider using the YouTube Data API v3:
1. Go to Google Cloud Console
2. Create a new project or select existing
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Add the API key to your .env file as YOUTUBE_API_KEY

## Troubleshooting:

- **"Sign in to confirm you're not a bot"**: Your IP may be temporarily blocked. Try again in 15-30 minutes.
- **Cookies not working**: Make sure you're logged into YouTube in the browser you're extracting cookies from.
- **Still getting errors**: Try using a different browser or clearing your browser cache.

## Testing:

After setting up cookies, run:
```
python test_youtube_access.py
```

This will test if your cookie setup is working correctly.
