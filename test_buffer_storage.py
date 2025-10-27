"""
Test CockroachDB Buffer Storage System
Tests downloading clips to buffer and processing them
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables from parent directory and backinsta
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

# Also load from backinsta for COCKROACHDB_URI
backinsta_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backinsta', '.env')
load_dotenv(backinsta_env)

print(f"📁 Loading .env from: {env_path}")
print(f"📁 Loading .env from: {backinsta_env}")
print(f"✅ DATABASE_URL found: {'Yes' if os.getenv('DATABASE_URL') else 'No'}")
print(f"✅ COCKROACHDB_URI found: {'Yes' if os.getenv('COCKROACHDB_URI') else 'No'}")
print(f"✅ PEXEL found: {'Yes' if os.getenv('PEXEL') else 'No'}")
print(f"✅ GROQ_API_KEY found: {'Yes' if os.getenv('GROQ_API_KEY') else 'No'}")
print()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_buffer_storage():
    """Test buffer storage system"""
    try:
        from cockroach_buffer import CockroachBufferStorage
        from pexels_video_fetcher import PexelsMediaFetcher
        
        logger.info("🧪 Testing CockroachDB Buffer Storage System...")
        
        # Initialize buffer
        buffer = CockroachBufferStorage()
        logger.info("✅ Buffer storage initialized")
        
        # Get buffer stats
        stats = buffer.get_buffer_stats()
        logger.info(f"📊 Current buffer: {stats['total_clips']} clips, {stats['total_mb']:.2f} MB")
        
        # Initialize Pexels fetcher
        pexels = PexelsMediaFetcher()
        logger.info("✅ Pexels fetcher initialized with buffer")
        
        # Test 1: Search for videos
        logger.info("\n📹 Test 1: Searching for videos...")
        videos = pexels.search_videos("city skyline", per_page=2)
        logger.info(f"✅ Found {len(videos)} videos")
        
        if videos:
            # Test 2: Download to buffer
            logger.info("\n💾 Test 2: Downloading video to buffer...")
            session_id = "test_session_001"
            
            video_url = videos[0]['url']
            logger.info(f"Downloading from: {video_url[:60]}...")
            
            clip_id = pexels.download_media(video_url, 'video', session_id)
            
            if clip_id:
                logger.info(f"✅ Video stored in buffer (ID: {clip_id})")
                
                # Test 3: Retrieve from buffer
                logger.info("\n📥 Test 3: Retrieving video from buffer...")
                temp_path = buffer.retrieve_clip(clip_id)
                
                if temp_path:
                    logger.info(f"✅ Retrieved to: {temp_path}")
                    
                    # Check file size
                    file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                    logger.info(f"📊 File size: {file_size_mb:.2f} MB")
                    
                    # Clean up temp file
                    os.unlink(temp_path)
                    logger.info("🗑️ Deleted temp file")
                else:
                    logger.error("❌ Failed to retrieve clip from buffer")
                
                # Test 4: Buffer stats
                logger.info("\n📊 Test 4: Buffer statistics...")
                stats = buffer.get_buffer_stats()
                logger.info(f"Buffer: {stats['total_clips']} clips, {stats['total_mb']:.2f} MB")
                
                # Test 5: Delete clip
                logger.info("\n🗑️ Test 5: Deleting clip from buffer...")
                buffer.delete_clip(clip_id)
                logger.info("✅ Clip deleted")
                
                # Final stats
                stats = buffer.get_buffer_stats()
                logger.info(f"Final buffer: {stats['total_clips']} clips, {stats['total_mb']:.2f} MB")
                
            else:
                logger.error("❌ Failed to download video to buffer")
        else:
            logger.warning("⚠️ No videos found to test")
        
        # Test 6: Cleanup old clips
        logger.info("\n🧹 Test 6: Cleaning up old clips...")
        buffer.cleanup_old_clips(hours=1)
        
        # Close buffer connection
        buffer.close()
        logger.info("\n✅ All tests completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_animated_reel_with_buffer():
    """Test creating an animated reel using buffer storage"""
    try:
        from animated_reel_creator import AnimatedReelCreator
        import tempfile
        
        logger.info("\n🎬 Testing Animated Reel Creation with Buffer...")
        
        creator = AnimatedReelCreator()
        
        # Test data
        headline = "Major Tech Conference Announces AI Breakthroughs in San Francisco"
        commentary = "Industry leaders gathered at the annual tech summit to showcase groundbreaking artificial intelligence innovations that could transform multiple sectors including healthcare, education, and transportation."
        
        # Create reel
        logger.info("Creating animated reel with buffer storage...")
        video_path = creator.create_animated_reel(
            headline=headline,
            commentary=commentary,
            target_duration=20,
            clips_count=3  # Start with 3 clips for testing
        )
        
        if video_path:
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(f"✅ Reel created successfully: {file_size_mb:.2f} MB")
            logger.info(f"📍 Location: {video_path}")
            
            # Open the video
            logger.info("🎥 Opening video...")
            os.system(f'open "{video_path}"')
            
            return True
        else:
            logger.error("❌ Failed to create reel")
            return False
            
    except Exception as e:
        logger.error(f"❌ Reel creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("CockroachDB Buffer Storage Test Suite")
    print("=" * 60)
    print()
    
    # Menu
    print("Choose test:")
    print("1. Test buffer storage only (quick)")
    print("2. Test full animated reel creation (slow, ~10 min)")
    print("3. Run both tests")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        test_buffer_storage()
    elif choice == "2":
        test_animated_reel_with_buffer()
    elif choice == "3":
        test_buffer_storage()
        print("\n" + "=" * 60)
        test_animated_reel_with_buffer()
    else:
        print("Invalid choice")
