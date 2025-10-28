#!/usr/bin/env python3
"""
Test Cloud Run video processor integration
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment from parent QPost directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')
load_dotenv(env_path)

CLOUD_PROCESSOR_URL = os.getenv('CLOUD_PROCESSOR_URL')

print("=" * 80)
print("🧪 TESTING CLOUD RUN VIDEO PROCESSOR")
print("=" * 80)
print(f"Cloud Run URL: {CLOUD_PROCESSOR_URL}")
print()

# Test 1: Health Check
print("📡 Test 1: Health Check...")
try:
    response = requests.get(f"{CLOUD_PROCESSOR_URL}/", timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    if response.status_code == 200:
        print("✅ Health check PASSED")
    else:
        print("❌ Health check FAILED")
except Exception as e:
    print(f"❌ Health check ERROR: {e}")

print()

# Test 2: Sample video processing (with small test URLs)
print("📡 Test 2: Video Processing Endpoint...")
print("(Skipping actual video processing to avoid long wait)")
print("To test video processing, you would send:")
print(f"POST {CLOUD_PROCESSOR_URL}/process-clips")
print("With payload:")
sample_payload = {
    "clips": [
        {"url": "https://example.com/video1.mp4", "type": "video", "duration": 3.6},
        {"url": "https://example.com/video2.mp4", "type": "video", "duration": 3.6}
    ]
}
print(sample_payload)
print()

# Test 3: Verify LightweightReelCreator can initialize
print("📡 Test 3: LightweightReelCreator Initialization...")
try:
    from lightweight_reel_creator import LightweightReelCreator
    creator = LightweightReelCreator()
    print(f"✅ LightweightReelCreator initialized")
    print(f"✅ Using Cloud Processor: {creator.cloud_processor_url}")
except Exception as e:
    print(f"❌ LightweightReelCreator ERROR: {e}")

print()
print("=" * 80)
print("🎯 Cloud Run integration test complete!")
print("=" * 80)
