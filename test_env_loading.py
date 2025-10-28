#!/usr/bin/env python3
"""
Test environment variable loading from parent .env file
"""

import os
from dotenv import load_dotenv

# Load environment from parent QPost directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')

print(f"🔍 Looking for .env at: {env_path}")
print(f"✅ .env exists: {os.path.exists(env_path)}")
print()

load_dotenv(env_path)

# Test all critical environment variables
env_vars = {
    'COCKROACHDB_URI': os.getenv('COCKROACHDB_URI'),
    'CLOUD_PROCESSOR_URL': os.getenv('CLOUD_PROCESSOR_URL'),
    'NYT_API_KEY': os.getenv('NYT_API_KEY'),
    'GROQ_API_KEY': os.getenv('GROQ_API_KEY'),
    'PEXEL': os.getenv('PEXEL'),
    'REACT_APP_ACCESS_TOKEN': os.getenv('REACT_APP_ACCESS_TOKEN'),
    'REACT_APP_INSTAGRAM_BUSINESS_ACCOUNT_ID': os.getenv('REACT_APP_INSTAGRAM_BUSINESS_ACCOUNT_ID'),
}

print("=" * 80)
print("ENVIRONMENT VARIABLES TEST")
print("=" * 80)

for key, value in env_vars.items():
    if value:
        # Mask sensitive values
        if len(value) > 20:
            display_value = f"{value[:10]}...{value[-10:]}"
        else:
            display_value = f"{value[:5]}...{value[-5:]}" if len(value) > 10 else "***"
        print(f"✅ {key:45} = {display_value}")
    else:
        print(f"❌ {key:45} = NOT SET")

print("=" * 80)

# Test specific imports
print("\n🧪 Testing module imports...")
try:
    from pexels_video_fetcher import PexelsMediaFetcher
    print("✅ pexels_video_fetcher imported successfully")
except Exception as e:
    print(f"❌ pexels_video_fetcher import failed: {e}")

try:
    from lightweight_reel_creator import LightweightReelCreator
    print("✅ lightweight_reel_creator imported successfully")
    creator = LightweightReelCreator()
    print(f"✅ Cloud Processor URL: {creator.cloud_processor_url}")
except Exception as e:
    print(f"❌ lightweight_reel_creator import failed: {e}")

print("\n🎯 All tests complete!")
