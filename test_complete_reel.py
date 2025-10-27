"""
Complete Animated Reel Test with Buffer Storage
Tests the full pipeline: fetch articles, create reel with buffer
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
backinsta_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backinsta', '.env')
load_dotenv(backinsta_env)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_full_reel_creation():
    """Test creating a complete animated reel with buffer storage"""
    try:
        from animated_reel_creator import AnimatedReelCreator
        from google_tts_voice import GoogleTTSVoice
        
        logger.info("🎬 Testing Full Animated Reel Creation with Buffer Storage")
        logger.info("=" * 60)
        
        # Test article data
        headline = "Scientists Discover Breakthrough in Renewable Energy Storage Technology"
        commentary = "Researchers at leading universities have developed a revolutionary battery technology that could store renewable energy for months at a time. This breakthrough addresses one of the biggest challenges in transitioning to clean energy sources, making solar and wind power more reliable and practical for large-scale adoption."
        
        # NYT article image URL (example)
        nyt_image_url = "https://static01.nyt.com/images/2024/12/03/multimedia/03cli-energy-battery-01-vzkq/03cli-energy-battery-01-vzkq-superJumbo.jpg"
        
        logger.info(f"📰 Headline: {headline[:60]}...")
        logger.info(f"💬 Commentary: {commentary[:80]}...")
        logger.info(f"🖼️  NYT Image: {nyt_image_url[:60]}...")
        
        # Step 1: Generate voice narration
        logger.info("\n🎤 Step 1: Generating voice narration...")
        tts = GoogleTTSVoice()
        
        # Create temp file for voice
        import tempfile
        voice_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        voice_path = voice_file.name
        voice_file.close()
        
        success = tts.generate_voice(
            text=commentary,
            output_path=voice_path,
            voice_name="en-US-Studio-O"  # Female news anchor - Rachel Anderson style
        )
        
        if not success or not os.path.exists(voice_path):
            logger.error("❌ Failed to create voice narration")
            return False
        
        logger.info(f"✅ Voice created: {voice_path}")
        
        # Step 2: Create animated reel with buffer storage
        logger.info("\n🎬 Step 2: Creating animated reel with buffer storage...")
        logger.info("   This will:")
        logger.info("   - Download 3 clips to CockroachDB (not disk)")
        logger.info("   - Process them one-by-one from buffer")
        logger.info("   - Delete immediately after use")
        logger.info("   - Clean up buffer on completion")
        
        creator = AnimatedReelCreator()
        video_path = creator.create_animated_reel(
            headline=headline,
            commentary=commentary,
            voice_audio_path=voice_path,
            target_duration=20,
            clips_count=3,  # Start with 3 for testing
            nyt_image_url=nyt_image_url  # Add NYT article image
        )
        
        if not video_path:
            logger.error("❌ Failed to create reel")
            # Clean up voice file
            try:
                os.unlink(voice_path)
            except:
                pass
            return False
        
        # Check file size
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        logger.info(f"\n✅ REEL CREATED SUCCESSFULLY!")
        logger.info(f"📍 Location: {video_path}")
        logger.info(f"📊 Size: {file_size_mb:.2f} MB")
        
        # Open the video
        logger.info("\n🎥 Opening video for review...")
        os.system(f'open "{video_path}"')
        
        # Clean up voice file
        try:
            os.unlink(voice_path)
            logger.info("🗑️ Cleaned up voice file")
        except:
            pass
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("COMPLETE ANIMATED REEL TEST")
    print("Testing full pipeline with CockroachDB buffer storage")
    print("=" * 60)
    print()
    
    input("Press ENTER to start test (will take ~10 minutes)... ")
    
    success = test_full_reel_creation()
    
    if success:
        print("\n✅ Test completed successfully!")
        print("Review the video and verify quality before deploying.")
    else:
        print("\n❌ Test failed - check logs above")
    
    sys.exit(0 if success else 1)
