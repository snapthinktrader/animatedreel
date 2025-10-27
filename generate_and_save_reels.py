"""
Automated reel generation script that:
1. Fetches NYT articles
2. Generates animated reels
3. Saves to CockroachDB
4. Waits 12 minutes between generations
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
import psycopg2
from animated_reel_creator import AnimatedReelCreator
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
            voice_name="en-US-Neural2-J"
        )
        
        if not voice_path:
            logger.error("❌ Failed to generate voice")
            return None
        
        # Create animated reel
        logger.info("🎥 Creating animated reel...")
        creator = AnimatedReelCreator()
        
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

def main():
    """Main generation loop"""
    logger.info("=" * 60)
    logger.info("🎬 AUTOMATED REEL GENERATION STARTED")
    logger.info("=" * 60)
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Cannot continue without database connection")
        return
    
    try:
        # Fetch NYT articles
        logger.info("\n📰 Fetching NYT articles...")
        articles = fetch_nyt_articles(section='world', limit=10)
        
        if not articles:
            logger.error("❌ No articles fetched")
            return
        
        # Process each article
        generated_count = 0
        
        for i, article in enumerate(articles, 1):
            article_url = article.get('url', '')
            headline = article.get('title', '')[:60]
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📄 Article {i}/{len(articles)}: {headline}...")
            
            # Check if already processed
            if check_article_exists(conn, article_url):
                logger.info("⏭️  Article already processed, skipping...")
                continue
            
            # Generate reel
            reel_data = generate_reel(article)
            
            if reel_data:
                # Save to database
                reel_id = save_reel_to_db(conn, reel_data)
                
                if reel_id:
                    generated_count += 1
                    logger.info(f"✅ Reel {generated_count} saved: {reel_id}")
                    
                    # Sleep 12 minutes before next generation
                    if i < len(articles):
                        logger.info("⏳ Waiting 12 minutes before next reel...")
                        time.sleep(12 * 60)  # 12 minutes
            else:
                logger.error("❌ Failed to generate reel")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ GENERATION COMPLETE")
        logger.info(f"   Generated: {generated_count} reels")
        logger.info(f"   Skipped: {len(articles) - generated_count} articles")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Generation interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error in main loop: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        logger.info("🔌 Database connection closed")

if __name__ == '__main__':
    main()
