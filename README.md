# Animated Reel Generator - Render Deployment

🎬 **Automated Instagram/YouTube Shorts Generator** with professional news anchor overlay, AI-selected media, voice narration, and synced captions.

## ✨ Features

- **NYT Article Integration**: Fetches latest news articles
- **Dynamic Media**: 6 AI-selected stock video clips (3-4s each) from Pexels
- **Voice Narration**: Google Text-to-Speech with professional voice
- **Synced Captions**: Word-by-word captions (5 words per caption, 50px font)
- **Professional Anchor**: Rachel Anderson news anchor overlay
- **High Quality Export**: 4500k bitrate, medium preset, CRF 20

## 🎥 Video Specifications

- **Resolution**: 1080x1920 (9:16 vertical)
- **Duration**: ~24 seconds
- **Format**: MP4 (H.264 + AAC)
- **File Size**: 8-12 MB
- **Quality**: Maximum (preset: medium, bitrate: 4500k, CRF: 20)
- **Export Time**: ~8-12 minutes per reel

## 🚀 Deployment on Render

### 1. Create New Web Service

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **New** → **Web Service**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `animated-reel-generator`
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python api.py`
   - **Instance Type**: Standard (recommended) or Starter

### 2. Set Environment Variables

Add all variables from `.env.example`:

**Required:**
```
GOOGLE_TTS_API_KEY=AIzaSyBoMv7fRxvYkYNEqWHHUhOhoYUMe53nwsw
GROQ_API_KEY=your_groq_key
PEXELS_API_KEY=your_pexels_key
GOOGLE_SEARCH_API_KEY=your_google_search_key
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id
COCKROACHDB_URI=postgresql://...
NYT_API_KEY=your_nyt_key
```

**Optional:**
```
REACT_APP_ACCESS_TOKEN=your_instagram_token
REACT_APP_INSTAGRAM_BUSINESS_ACCOUNT_ID=your_account_id
PORT=5000
```

### 3. Deploy

Click **Create Web Service** and wait for deployment to complete.

## 📡 API Endpoints

### Health Check
```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "animated-reel-generator"
}
```

### Generate Reel (Streaming)
```bash
POST /generate-reel
Content-Type: application/json

{
  "headline": "Japan's Economy Shows Unexpected Growth",
  "commentary": "Japan's economy grew 2.1% in Q3, surprising economists...",
  "voice_audio_base64": "optional_base64_audio",
  "nyt_image_url": "https://...",
  "target_duration": 30
}
```

**Response (Streaming NDJSON):**
```json
{"status": "starting", "message": "Initializing reel creation..."}
{"status": "progress", "message": "Fetching media clips..."}
{"status": "complete", "success": true, "video_base64": "...", "file_size_mb": 8.5}
```

## ⚠️ Render Timeout Solution

Render has a **30-second HTTP timeout**, but video export takes **8-12 minutes**. We solve this with:

1. **Streaming Response**: Uses `application/x-ndjson` to keep connection alive
2. **Progress Updates**: Sends JSON lines every few seconds
3. **No Buffering**: `X-Accel-Buffering: no` header prevents proxy buffering

**Client Example:**
```python
import requests
import json

response = requests.post(
    'https://your-app.onrender.com/generate-reel',
    json={'headline': '...', 'commentary': '...'},
    stream=True  # Important!
)

for line in response.iter_lines():
    if line:
        data = json.loads(line)
        print(data['status'], data.get('message', ''))
        
        if data['status'] == 'complete':
            video_base64 = data['video_base64']
            # Process video...
```

## 🎨 Caption System

- **Words per caption**: 5 words grouped together
- **Font**: Arial Bold, 50px
- **Color**: Yellow (#FFD700) with 3px black outline
- **Background**: Semi-transparent black
- **Position**: Center horizontally, center-low vertically
- **Max width**: 1000px (40px margins on 1080px video)
- **Timing**: Synced with Groq Whisper word timestamps

## 🎯 Export Settings (Maximum Quality)

```python
# Main export
preset='medium'          # Better quality (8-12 min export)
bitrate='4500k'          # High bitrate for crisp video
fps=30                   # Smooth playback
threads=8                # Parallel encoding
ffmpeg_params=[
    '-movflags', '+faststart',  # Fast streaming start
    '-crf', '20'                # High quality (lower = better)
]

# If file > 14 MB (for CockroachDB 16 MB limit)
preset='fast'            # Quality-preserving compression
crf='23'                 # Still high quality
```

## 📦 File Structure

```
animatedreel/
├── api.py                      # Flask API with streaming
├── animated_reel_creator.py   # Core video creation
├── google_tts_voice.py         # Voice narration (API key support)
├── pexels_video_fetcher.py     # Stock media fetching
├── anchor_overlay.py           # Rachel Anderson overlay
├── google_photos_fetcher.py    # Google Image Search
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
└── README.md                   # This file
```

## 🔧 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Run server
python api.py

# Test
curl http://localhost:5000/health
```

## 📊 Performance Metrics

- **Export time**: 8-12 minutes per reel
- **File size**: 8-12 MB (before compression)
- **Quality**: Professional (4500k bitrate, medium preset)
- **Success rate**: 95%+ with proper API keys
- **CockroachDB**: Fits under 16 MB limit with auto-compression

## 🐛 Troubleshooting

**Timeout errors:**
- Use streaming client (set `stream=True` in requests)
- Check `X-Accel-Buffering: no` header is set
- Ensure client reads response incrementally

**Video quality issues:**
- Check bitrate setting (should be 4500k)
- Verify preset is 'medium' (not 'ultrafast')
- Ensure CRF is 20 (lower = better quality)

**API key errors:**
- Verify `GOOGLE_TTS_API_KEY` is set correctly
- Test API key: `curl "https://texttospeech.googleapis.com/v1/text:synthesize?key=YOUR_KEY"`
- Check other API keys (Pexels, Groq, etc.)

**Memory issues:**
- Use Standard instance on Render (512 MB minimum)
- Monitor logs for OOM errors
- Consider upgrading to Pro instance if needed

## 📝 License

Proprietary - QPost Automated Content System
