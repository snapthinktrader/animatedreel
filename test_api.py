"""
Quick API Test - Test buffer storage and basic reel creation
"""
import os
import sys
from dotenv import load_dotenv

# Load env
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
backinsta_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backinsta', '.env')
load_dotenv(backinsta_env)

print("=" * 60)
print("QUICK API TEST")
print("=" * 60)

# Test 1: Buffer Storage
print("\n1️⃣ Testing CockroachDB Buffer Storage...")
try:
    from cockroach_buffer import CockroachBufferStorage
    buffer = CockroachBufferStorage()
    stats = buffer.get_buffer_stats()
    print(f"✅ Buffer connected: {stats['total_clips']} clips, {stats['total_mb']:.2f} MB")
except Exception as e:
    print(f"❌ Buffer test failed: {e}")
    sys.exit(1)

# Test 2: Pexels API
print("\n2️⃣ Testing Pexels API...")
try:
    from pexels_video_fetcher import PexelsMediaFetcher
    pexels = PexelsMediaFetcher()
    videos = pexels.search_videos("technology", per_page=2)
    print(f"✅ Pexels working: Found {len(videos)} videos")
except Exception as e:
    print(f"❌ Pexels test failed: {e}")
    sys.exit(1)

# Test 3: Google TTS
print("\n3️⃣ Testing Google TTS (Studio-O female voice)...")
try:
    from google_tts_voice import GoogleTTSVoice
    import tempfile
    tts = GoogleTTSVoice()
    temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    temp_audio.close()
    
    success = tts.generate_voice(
        "This is Rachel Anderson reporting. Testing the female news anchor voice.",
        temp_audio.name,
        "en-US-Studio-O"
    )
    
    if success and os.path.exists(temp_audio.name):
        size_kb = os.path.getsize(temp_audio.name) / 1024
        print(f"✅ Google TTS working: Generated {size_kb:.1f} KB audio (Studio-O female voice)")
        os.unlink(temp_audio.name)
    else:
        print(f"❌ TTS failed to generate audio")
        sys.exit(1)
except Exception as e:
    print(f"❌ TTS test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL API TESTS PASSED!")
print("=" * 60)
print("\nBuffer storage system is working!")
print("Female voice (Studio-O) configured!")
print("\nReady to commit and deploy to Render! 🚀")
