"""
Quick test script to verify the animated reel API is working
"""

import requests
import json
import base64
import os

def test_health():
    """Test health endpoint"""
    print("🏥 Testing health endpoint...")
    response = requests.get('http://localhost:5000/health')
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    print()

def test_generate_reel_streaming():
    """Test reel generation with streaming"""
    print("🎬 Testing reel generation (streaming)...")
    
    # Sample data
    data = {
        "headline": "Test Animated Reel Generation",
        "commentary": "This is a test of the automated reel generation system with maximum quality settings and streaming response to prevent timeout issues.",
        "target_duration": 25
    }
    
    print(f"   Headline: {data['headline']}")
    print(f"   Commentary: {data['commentary'][:50]}...")
    print(f"\n📡 Sending request (will take 8-12 minutes)...\n")
    
    # Stream the response
    response = requests.post(
        'http://localhost:5000/generate-reel',
        json=data,
        stream=True  # Important!
    )
    
    video_data = None
    
    for line in response.iter_lines():
        if line:
            try:
                update = json.loads(line)
                status = update.get('status')
                message = update.get('message', '')
                
                if status == 'starting':
                    print(f"🎬 {message}")
                elif status == 'progress':
                    print(f"⏳ {message}")
                elif status == 'complete':
                    print(f"\n✅ COMPLETE!")
                    print(f"   File size: {update.get('file_size_mb')} MB")
                    print(f"   Duration: {update.get('duration')}s")
                    video_data = update.get('video_base64')
                elif status == 'error':
                    print(f"\n❌ ERROR: {message}")
            except json.JSONDecodeError:
                print(f"⚠️  Invalid JSON: {line}")
    
    # Save video if successful
    if video_data:
        print("\n💾 Saving video to test_output.mp4...")
        video_bytes = base64.b64decode(video_data)
        
        with open('test_output.mp4', 'wb') as f:
            f.write(video_bytes)
        
        print(f"   Saved: {len(video_bytes) / (1024*1024):.2f} MB")
        print(f"   File: {os.path.abspath('test_output.mp4')}")
        
        # Open the video
        os.system('open test_output.mp4')
        print("🎥 Opening video...")
    
    print()

if __name__ == '__main__':
    print("=" * 60)
    print("ANIMATED REEL API TEST")
    print("=" * 60)
    print()
    
    # Test health
    test_health()
    
    # Ask user if they want to test generation
    response = input("🎬 Test reel generation? (takes 8-12 min) [y/N]: ")
    
    if response.lower() == 'y':
        test_generate_reel_streaming()
    else:
        print("⏭️  Skipping reel generation test")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
