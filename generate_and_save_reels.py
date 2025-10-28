#!/usr/bin/env python3
"""
Continuous reel generation worker for Render deployment
Fetches NYT articles, generates animated reels, saves to CockroachDB
Runs continuously with 12-minute intervals between generations
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

# Load environment variables from parent QPost directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')
load_dotenv(env_path)

# FIX: Pillow 10.0+ compatibility - patch BEFORE importing MoviePy
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
except:
    pass

from lightweight_reel_creator import LightweightReelCreator
from google_tts_voice import GoogleTTSVoice

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
NYT_API_KEY = os.getenv('NYT_API_KEY')
COCKROACHDB_URI = os.getenv('COCKROACHDB_URI')

def get_db_connection():
    """Get CockroachDB connection"""
    try:
        conn = psycopg2.connect(COCKROACHDB_URI)
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None

def fetch_nyt_articles(section='world', limit=5):
    """Fetch latest NYT articles"""
    if not NYT_API_KEY:
        logger.error("❌ NYT_API_KEY not set")
        return []
    
    try:
        url = f"https://api.nytimes.com/svc/topstories/v2/{section}.json"
        params = {'api-key': NYT_API_KEY}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        articles = data.get('results', [])[:limit]
        
        logger.info(f"✅ Fetched {len(articles)} articles from NYT")
        return articles
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch NYT articles: {e}")
        return []

def check_article_exists(conn, article_url):
    """Check if article already processed"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM reels WHERE article_url = %s",
            (article_url,)
        )
        count = cursor.fetchone()[0]
        cursor.close()
        return count > 0
    except Exception as e:
        logger.error(f"❌ Error checking article: {e}")
        return False

def generate_commentary(headline, abstract):
    """Generate commentary from headline and abstract"""
    if abstract:
        return f"{headline}. {abstract}"
    return headline

def save_reel_to_db(conn, reel_data):
    """Save generated reel to CockroachDB"""
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reels (
                id, headline, video_data, duration, 
                article_url, article_id, status, created_at
            ) VALUES (
                gen_random_uuid(), %s, %s, %s, 
                %s, %s, %s, NOW()
            )
            RETURNING id
        """, (
            reel_data['headline'],
            reel_data['video_data'],
            reel_data['duration'],
            reel_data['article_url'],
            reel_data['article_id'],
            'pending'
        ))
        
        reel_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        
        logger.info(f"✅ Saved reel to database: {reel_id}")
        return reel_id
        
    except Exception as e:
        logger.error(f"❌ Failed to save reel: {e}")
        conn.rollback()
        return None

def generate_reel(article):
    """Generate animated reel for an article"""
    try:
        headline = article.get('title', '')
        abstract = article.get('abstract', '')
        article_url = article.get('url', '')
        article_id = article.get('uri', '').split('/')[-1]
        
        # Get article image
        multimedia = article.get('multimedia', [])
        nyt_image_url = None
        for media in multimedia:
            if media.get('format') in ['superJumbo', 'mediumThreeByTwo440']:
                nyt_image_url = media.get('url')
                break
        
        logger.info(f"🎬 Generating reel: {headline[:50]}...")
        
        # Generate commentary
        commentary = generate_commentary(headline, abstract)
        
        # Generate voice narration
        logger.info("🎤 Generating voice narration...")
        tts = GoogleTTSVoice()
        
        import tempfile
        voice_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        voice_audio.close()
        
        voice_path = tts.generate_voice(
            commentary,
            voice_audio.name,
            voice_name="en-US-Studio-O"  # Female news anchor - Rachel Anderson
        )
        
        if not voice_path:
            logger.error("❌ Failed to generate voice")
            return None
        
        # Create animated reel (using Cloud Run for heavy processing)
        logger.info("🎥 Creating animated reel with Cloud Run hybrid architecture...")
        creator = LightweightReelCreator()
        
        video_path = creator.create_animated_reel(
            headline=headline,
            commentary=commentary,
            voice_audio_path=voice_path,
            target_duration=25,
            clips_count=6,
            nyt_image_url=nyt_image_url
        )
        
        if not video_path:
            logger.error("❌ Failed to create reel")
            os.unlink(voice_path)
            return None
        
        # Read video data
        with open(video_path, 'rb') as f:
            video_data = f.read()
        
        file_size_mb = len(video_data) / (1024 * 1024)
        logger.info(f"✅ Generated reel: {file_size_mb:.2f} MB")
        
        # Clean up temp files
        os.unlink(voice_path)
        os.unlink(video_path)
        
        return {
            'headline': headline,
            'video_data': video_data,
            'duration': 25.0,
            'article_url': article_url,
            'article_id': article_id
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating reel: {e}")
        import traceback
        traceback.print_exc()
        return None

def keep_alive_during_sleep(sleep_duration, ping_interval=720):
    """
    Keep Render service alive during sleep by pinging health endpoint
    
    Args:
        sleep_duration: Total time to sleep in seconds
        ping_interval: Time between pings in seconds (default 12 minutes = 720s)
    """
    service_url = os.getenv('RENDER_EXTERNAL_URL', 'http://localhost:10000')
    health_url = f"{service_url}/health"
    
    elapsed = 0
    while elapsed < sleep_duration:
        sleep_time = min(ping_interval, sleep_duration - elapsed)
        time.sleep(sleep_time)
        elapsed += sleep_time
        
        if elapsed < sleep_duration:
            try:
                response = requests.get(health_url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"💓 Keep-alive ping successful ({elapsed}/{sleep_duration}s)")
            except:
                pass

def main():
    """Main generation loop - runs continuously"""
    print("=" * 70)
    print("🚀 Animated Reel Generator Starting...")
    print("=" * 70)
    print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏰ Generation interval: 12 minutes")
    print("=" * 70)
    print()
    
    # Note: Health checks are handled by the main API server (api.py)
    # No need for separate health check server here
    
    # Generation interval (12 minutes = 720 seconds)
    GENERATION_INTERVAL = 12 * 60
    
    generation_count = 0
    error_count = 0
    
    while True:
        try:
            cycle_start = datetime.now()
            logger.info(f"\n{'='*70}")
            logger.info(f"🔄 Generation Cycle #{generation_count + 1}")
            logger.info(f"   Started at: {cycle_start.strftime('%H:%M:%S')}")
            logger.info(f"{'='*70}")
            
            # Get database connection
            conn = get_db_connection()
            if not conn:
                logger.error("❌ Cannot connect to database, retrying in 5 minutes...")
                time.sleep(300)
                continue
            
            try:
                # Fetch NYT articles
                logger.info("\n📰 Fetching NYT articles...")
                articles = fetch_nyt_articles(section='world', limit=10)
                
                if not articles:
                    logger.warning("⚠️ No articles fetched")
                else:
                    # Try to find an unprocessed article
                    generated_this_cycle = False
                    
                    for article in articles:
                        article_url = article.get('url', '')
                        headline = article.get('title', '')[:60]
                        
                        # Check if already processed
                        if check_article_exists(conn, article_url):
                            logger.info(f"⏭️  Already processed: {headline}...")
                            continue
                        
                        # Generate reel for this article
                        logger.info(f"🎬 Generating reel: {headline}...")
                        reel_data = generate_reel(article)
                        
                        if reel_data:
                            # Save to database
                            reel_id = save_reel_to_db(conn, reel_data)
                            
                            if reel_id:
                                generation_count += 1
                                error_count = 0
                                logger.info(f"✅ Reel saved: {reel_id}")
                                logger.info(f"📊 Total generated: {generation_count}")
                                generated_this_cycle = True
                                break  # Only generate one per cycle
                        else:
                            error_count += 1
                            logger.error("❌ Failed to generate reel")
                    
                    if not generated_this_cycle:
                        logger.info("✅ All articles already processed")
                
            finally:
                conn.close()
            
            # Calculate next generation time
            next_gen_time = datetime.now().timestamp() + GENERATION_INTERVAL
            next_gen_datetime = datetime.fromtimestamp(next_gen_time)
            
            logger.info(f"\n⏰ Next generation: {next_gen_datetime.strftime('%H:%M:%S')}")
            logger.info(f"💤 Sleeping for 12 minutes...\n")
            
            # Sleep with keep-alive pings
            keep_alive_during_sleep(GENERATION_INTERVAL, ping_interval=720)
            
        except KeyboardInterrupt:
            logger.info("\n\n⚠️ Received interrupt signal")
            logger.info(f"📊 Total reels generated: {generation_count}")
            logger.info("👋 Shutting down gracefully...")
            break
            
        except Exception as e:
            logger.error(f"❌ Unexpected error in main loop: {e}")
            import traceback
            traceback.print_exc()
            logger.info("⏰ Waiting 5 minutes before retry...")
            time.sleep(300)
    
    return 0

if __name__ == '__main__':
    main()
