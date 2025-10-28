#!/usr/bin/env python3
"""
Test single reel generation with Cloud Run hybrid architecture
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment from parent QPost directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')
load_dotenv(env_path)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import required modules
import requests
from lightweight_reel_creator import LightweightReelCreator
from google_tts_voice import GoogleTTSVoice
from pexels_video_fetcher import PexelsMediaFetcher

print("=" * 80)
print("🎬 TESTING SINGLE REEL GENERATION")
print("=" * 80)
print()

# Step 1: Fetch NYT article
print("📰 Step 1: Fetching NYT article...")
try:
    NYT_API_KEY = os.getenv('NYT_API_KEY')
    response = requests.get(
        'https://api.nytimes.com/svc/topstories/v2/world.json',
        params={'api-key': NYT_API_KEY},
        timeout=10
    )
    
    if response.status_code != 200:
        raise Exception(f"NYT API failed: {response.status_code}")
    
    articles = response.json()['results']
    article = articles[0]  # Get first article
    
    headline = article['title']
    abstract = article.get('abstract', '')
    
    # Limit lengths
    if len(headline) > 100:
        headline = headline[:97] + "..."
    if len(abstract) > 200:
        abstract = abstract[:197] + "..."
    
    print(f"✅ Got article:")
    print(f"   Headline: {headline}")
    print(f"   Abstract: {abstract[:80]}...")
    
    # Get image URL
    nyt_image_url = None
    if article.get('multimedia'):
        for media in article['multimedia']:
            if media.get('format') == 'Large Thumbnail':
                nyt_image_url = media['url']
                break
    
    print(f"   Image: {'Found' if nyt_image_url else 'Not found'}")
    
except Exception as e:
    logger.error(f"❌ Failed to fetch article: {e}")
    sys.exit(1)

print()

# Step 2: Generate voice
print("🗣️  Step 2: Generating voice narration...")
try:
    import tempfile
    tts = GoogleTTSVoice()
    
    # Create temp file for voice
    voice_fd, voice_path = tempfile.mkstemp(suffix='.mp3', prefix='test_voice_')
    os.close(voice_fd)
    
    tts.generate_voice(
        text=f"{headline}. {abstract}",
        output_path=voice_path,
        voice_name="en-US-Studio-O"  # Female voice
    )
    
    if not os.path.exists(voice_path) or os.path.getsize(voice_path) == 0:
        raise Exception("Voice generation failed - empty file")
    
    print(f"✅ Voice generated: {voice_path}")
    
except Exception as e:
    logger.error(f"❌ Voice generation failed: {e}")
    sys.exit(1)

print()

# Step 3: Search for video clips
print("🎥 Step 3: Searching for video clips on Pexels...")
try:
    fetcher = PexelsMediaFetcher()
    
    # Extract keywords from headline
    keywords = fetcher.extract_search_keywords(headline, abstract)
    print(f"   Keywords: {', '.join(keywords[:3])}")
    
    # Search for videos using first keyword
    search_query = keywords[0] if keywords else headline.split()[0]
    videos = fetcher.search_videos(query=search_query, per_page=6, orientation='portrait')
    
    if not videos or len(videos) < 6:
        # Try with a broader search
        print("   Trying broader search...")
        videos = fetcher.search_videos(query="news world", per_page=6, orientation='portrait')
    
    if not videos or len(videos) < 6:
        raise Exception(f"Not enough videos found: {len(videos) if videos else 0}")
    
    # The search_videos method already returns properly formatted data with 'url' field
    clips_data = []
    for video in videos[:6]:
        url = video.get('url')
        if url:
            clips_data.append({
                'url': url,
                'type': 'video',
                'duration': video.get('duration', 3.6),
                'width': video.get('width', 720),
                'height': video.get('height', 1280)
            })
            print(f"   ✓ Clip {len(clips_data)}: {url[:50]}... ({video.get('duration', 3.6)}s, {video.get('width')}x{video.get('height')})")
    
    if len(clips_data) < 6:
        raise Exception(f"Not enough video URLs extracted: {len(clips_data)}")
    
    print(f"✅ Found {len(clips_data)} video clips ready for Cloud Run")
    
except Exception as e:
    logger.error(f"❌ Clip search failed: {e}")
    import traceback
    traceback.print_exc()
    os.unlink(voice_path) if os.path.exists(voice_path) else None
    sys.exit(1)

print()

# Step 4: Create reel with Cloud Run hybrid architecture
print("🎬 Step 4: Creating reel with hybrid architecture...")
print("   (This will send clips to Cloud Run for processing)")
try:
    creator = LightweightReelCreator()
    
    print(f"   Cloud Processor: {creator.cloud_processor_url}")
    print(f"   Processing 6 clips on Cloud Run (4GB RAM)...")
    
    video_path = creator.create_animated_reel(
        headline=headline,
        commentary=abstract,
        voice_audio_path=voice_path,
        clips_urls=clips_data,  # Pass the list of clip URLs
        target_duration=25,
        nyt_image_url=nyt_image_url
    )
    
    if not video_path:
        raise Exception("Reel creation failed")
    
    # Check file size
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    
    print(f"✅ Reel created successfully!")
    print(f"   Path: {video_path}")
    print(f"   Size: {file_size_mb:.2f} MB")
    
except Exception as e:
    logger.error(f"❌ Reel creation failed: {e}")
    import traceback
    traceback.print_exc()
    os.unlink(voice_path) if os.path.exists(voice_path) else None
    sys.exit(1)

print()

# Clean up
print("🧹 Cleaning up temporary files...")
try:
    if os.path.exists(voice_path):
        os.unlink(voice_path)
        print(f"   ✅ Deleted voice file")
    
    print(f"   ✅ Keeping video: {video_path}")
    
except Exception as e:
    logger.warning(f"Cleanup warning: {e}")

print()
print("=" * 80)
print("🎉 TEST REEL GENERATION COMPLETE!")
print("=" * 80)
print()
print(f"📹 Your test reel is ready: {video_path}")
print(f"📊 File size: {file_size_mb:.2f} MB")
print()
print("Architecture tested:")
print("  ✅ NYT API → Articles fetched")
print("  ✅ Google TTS → Voice generated")
print("  ✅ Pexels API → Video URLs found")
print("  ✅ Cloud Run → Heavy processing (2GB RAM)")
print("  ✅ Local → Light overlays added")
print()
print("Ready for Render deployment! 🚀")
print("=" * 80)
