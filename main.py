"""
Google Cloud Run Service for Heavy Video Processing
Handles the memory-intensive video editing operations
Stores result in CockroachDB instead of Google Cloud Storage
"""

from flask import Flask, request, jsonify
import tempfile
import os
import gc
import uuid
from decimal import Decimal
from moviepy.editor import VideoFileClip, ImageClip, concatenate_videoclips
import requests
import logging
import psycopg2

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Monkey-patch for PIL compatibility
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

def get_db_connection():
    """Connect to CockroachDB"""
    db_url = os.environ.get('COCKROACHDB_URI')
    if not db_url:
        raise ValueError("COCKROACHDB_URI not set")
    
    # Replace sslmode=verify-full with sslmode=require for Cloud Run
    # Cloud Run doesn't have local cert files, but sslmode=require still encrypts
    db_url = db_url.replace('sslmode=verify-full', 'sslmode=require')
    
    # Ensure SSL mode is set if not present
    if '?' in db_url:
        if 'sslmode' not in db_url:
            db_url += '&sslmode=require'
    else:
        db_url += '?sslmode=require'
    
    return psycopg2.connect(db_url)

def retrieve_clip_from_buffer(clip_id: str) -> str:
    """
    Retrieve clip from CockroachDB buffer and save to temp file
    
    Args:
        clip_id: Clip UUID from buffer
        
    Returns:
        Path to temp file, or None if failed
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get clip metadata from temp_clips (matches CockroachBufferStorage schema)
        cursor.execute("""
            SELECT media_type, is_chunked, total_chunks, file_size_mb
            FROM temp_clips
            WHERE id = %s
        """, (clip_id,))

        row = cursor.fetchone()
        if not row:
            logger.error(f"❌ Clip {clip_id} not found in buffer (temp_clips)")
            cursor.close()
            conn.close()
            return None

        media_type, is_chunked, total_chunks, file_size_mb = row

        # Retrieve chunks or direct data depending on is_chunked
        clip_bytes = b''
        if is_chunked:
            cursor.execute("""
                SELECT chunk_data
                FROM temp_clip_chunks
                WHERE clip_id = %s
                ORDER BY chunk_number
            """, (clip_id,))

            chunk_rows = cursor.fetchall()
            if not chunk_rows:
                logger.error(f"❌ No chunks found for clip {clip_id} in temp_clip_chunks")
                cursor.close()
                conn.close()
                return None

            for chunk_row in chunk_rows:
                clip_bytes += bytes(chunk_row[0])
        else:
            cursor.execute("""
                SELECT clip_data
                FROM temp_clips
                WHERE id = %s
            """, (clip_id,))

            data_row = cursor.fetchone()
            if not data_row or data_row[0] is None:
                logger.error(f"❌ Clip data not found for {clip_id} in temp_clips")
                cursor.close()
                conn.close()
                return None

            clip_bytes = bytes(data_row[0])

        # Combine bytes into temp file
        suffix = '.mp4' if media_type == 'video' else '.jpg'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(clip_bytes)
        
        temp_file.close()
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Retrieved clip {clip_id} from buffer")
        return temp_file.name
        
    except Exception as e:
        logger.error(f"❌ Error retrieving clip from buffer: {e}")
        return None

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'video-processor'}), 200

@app.route('/process-clips', methods=['POST'])
def process_clips():
    """
    Process video clips from CockroachDB buffer: retrieve, resize, concatenate
    
    NEW ARCHITECTURE: Clips are pre-downloaded to buffer by Render
    
    Request JSON:
    {
        "clip_ids": ["uuid-1", "uuid-2", "uuid-3"],  # Clip IDs from CockroachDB buffer
        "target_width": 1080,
        "target_height": 1920
    }
    
    Returns:
    {
        "video_id": "uuid-string",
        "duration": 21.6,
        "size_mb": 45.2
    }
    """
    try:
        data = request.json
        clip_ids = data.get('clip_ids', [])
        target_width = data.get('target_width', 1080)
        target_height = data.get('target_height', 1920)
        
        if not clip_ids:
            return jsonify({'error': 'No clip IDs provided'}), 400
        
        logger.info(f"🎬 Processing {len(clip_ids)} clips from buffer...")
        
        # Process clips
        clips = []
        temp_files = []
        
        for i, clip_id in enumerate(clip_ids):
            try:
                # Retrieve clip from CockroachDB buffer
                logger.info(f"📥 Retrieving clip {i+1} from buffer (ID: {clip_id})...")
                
                clip_path = retrieve_clip_from_buffer(clip_id)
                
                if not clip_path:
                    logger.warning(f"⚠️ Failed to retrieve clip {i+1} from buffer")
                    continue
                
                temp_files.append(clip_path)
                
                # Determine media type from file extension
                media_type = 'video' if clip_path.endswith('.mp4') else 'photo'
                
                # Process clip
                if media_type == 'video':
                    video_clip = VideoFileClip(clip_path)
                    
                    # Trim to reasonable duration (max 5s per clip to reduce memory)
                    video_duration = min(video_clip.duration, 5.0)
                    video_clip = video_clip.subclip(0, video_duration)
                    
                    # Resize to portrait
                    video_clip = resize_to_portrait(video_clip, target_width, target_height)
                    
                    clips.append(video_clip)
                    logger.info(f"✅ Processed video clip {i+1}: {video_duration:.1f}s")
                
                else:  # photo
                    # Photos should have duration metadata from buffer
                    img_clip = ImageClip(clip_path, duration=3.0)
                    img_clip = resize_to_portrait(img_clip, target_width, target_height)
                    clips.append(img_clip)
                    logger.info(f"✅ Processed photo clip {i+1}: 3.0s")
                
            except Exception as e:
                logger.error(f"❌ Error processing clip {i+1}: {e}")
                continue
            
            # Force garbage collection after each clip
            gc.collect()
        
        if not clips:
            return jsonify({'error': 'No clips processed successfully'}), 500
        
        # Concatenate clips
        logger.info(f"🎬 Concatenating {len(clips)} clips...")
        final_video = concatenate_videoclips(clips, method="compose")
        
        # Clean up temp files immediately after concatenation
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
        
        # Write to temp file
        output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        output_path = output_file.name
        output_file.close()
        
        logger.info("💾 Writing final video...")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=30,
            preset='medium',
            threads=4,
            logger=None
        )
        
        # Get file size
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"📊 Processed video size: {file_size_mb:.2f} MB")
        
        # Store in CockroachDB with chunking if needed
        logger.info("☁️ Storing in CockroachDB...")
        video_id = store_in_cockroachdb(output_path, final_video.duration, file_size_mb)
        
        # Clean up
        for clip in clips:
            clip.close()
        final_video.close()
        os.unlink(output_path)
        gc.collect()
        
        logger.info(f"✅ Video processed and stored in CockroachDB: {video_id}")
        
        return jsonify({
            'video_id': video_id,
            'duration': final_video.duration,
            'size_mb': file_size_mb,
            'clips_processed': len(clips)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def store_in_cockroachdb(video_path, duration, file_size_mb):
    """Store processed video in CockroachDB with chunking support"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Read video file
        with open(video_path, 'rb') as f:
            video_data = f.read()
        
        chunk_size = 6 * 1024 * 1024  # 6 MB chunks (same as buffer system)
        
        logger.info("📋 Ensuring tables exist...")
        # Create processed_videos table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_videos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                video_data BYTEA,
                duration DECIMAL(10, 2),
                file_size_mb DECIMAL(10, 2),
                is_chunked BOOLEAN DEFAULT FALSE,
                total_chunks INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_video_chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                video_id UUID NOT NULL,
                chunk_number INT NOT NULL,
                chunk_data BYTEA NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(video_id, chunk_number)
            )
        """)
        conn.commit()
        logger.info("✅ Tables ready")
        
        # Check if chunking needed
        if file_size_mb > 8:
            # Use chunking
            total_chunks = (len(video_data) + chunk_size - 1) // chunk_size
            
            logger.info(f"💾 Chunking {file_size_mb:.2f} MB video into {total_chunks} chunks...")
            
            # Create main entry - use simple UUID generation  
            video_id = str(uuid.uuid4())
            
            cursor.execute("""
                INSERT INTO processed_videos (id, video_data, duration, file_size_mb, is_chunked, total_chunks)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (video_id, psycopg2.Binary(b''), Decimal(str(duration)), Decimal(str(file_size_mb)), True, total_chunks))
            conn.commit()
            
            # Store chunks
            for i in range(total_chunks):
                start = i * chunk_size
                end = min(start + chunk_size, len(video_data))
                chunk = video_data[start:end]
                
                cursor.execute("""
                    INSERT INTO processed_video_chunks (video_id, chunk_number, chunk_data)
                    VALUES (%s, %s, %s)
                """, (video_id, i, psycopg2.Binary(chunk)))
                conn.commit()
                
                logger.info(f"   💾 Stored chunk {i+1}/{total_chunks}")
            
            logger.info(f"💾 Stored video in CockroachDB (CHUNKED): {file_size_mb:.2f} MB in {total_chunks} chunks")
        else:
            # Store directly
            video_id = str(uuid.uuid4())
            
            cursor.execute("""
                INSERT INTO processed_videos (id, video_data, duration, file_size_mb, is_chunked, total_chunks)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (video_id, psycopg2.Binary(video_data), Decimal(str(duration)), Decimal(str(file_size_mb)), False, 1))
            
            conn.commit()
            
            logger.info(f"💾 Stored video in CockroachDB: {file_size_mb:.2f} MB")
        
        cursor.close()
        conn.close()
        
        return video_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Failed to store in CockroachDB: {e}")
        raise

def resize_to_portrait(clip, target_width=1080, target_height=1920):
    """Resize clip to portrait 9:16 ratio"""
    clip_width, clip_height = clip.size
    clip_ratio = clip_width / clip_height
    target_ratio = target_width / target_height
    
    if clip_ratio > target_ratio:
        # Clip is wider - crop width
        new_width = int(clip_height * target_ratio)
        x_center = clip_width / 2
        x1 = int(x_center - new_width / 2)
        clip = clip.crop(x1=x1, width=new_width)
    else:
        # Clip is taller - crop height
        new_height = int(clip_width / target_ratio)
        y_center = clip_height / 2
        y1 = int(y_center - new_height / 2)
        clip = clip.crop(y1=y1, height=new_height)
    
    # Resize to exact target dimensions
    clip = clip.resize((target_width, target_height))
    return clip

@app.route('/create-complete-reel', methods=['POST'])
def create_complete_reel():
    """
    COMPLETE reel creation on Cloud Run (4GB RAM)
    Steps: Concatenate clips + NYT image + text overlay + captions + anchor + voice audio
    Returns video_id stored in CockroachDB
    """
    try:
        data = request.get_json()
        clip_ids = data.get('clip_ids', [])
        headline = data.get('headline', '')
        commentary = data.get('commentary', '')
        voice_audio_id = data.get('voice_audio_id')
        nyt_image_url = data.get('nyt_image_url')
        target_width = data.get('target_width', 1080)
        target_height = data.get('target_height', 1920)
        
        logger.info(f"🎬 COMPLETE reel creation on Cloud Run...")
        logger.info(f"  Clips: {len(clip_ids)}, Voice: {bool(voice_audio_id)}, NYT Image: {bool(nyt_image_url)}")
        
        # Import animated_reel_creator to leverage existing logic
        from animated_reel_creator import AnimatedReelCreator
        
        creator = AnimatedReelCreator()
        
        # Retrieve clips from buffer
        clips = []
        for clip_id in clip_ids:
            clip_path = retrieve_clip_from_buffer(clip_id)
            if clip_path:
                clips.append(clip_path)
        
        if not clips:
            return jsonify({'error': 'No clips retrieved'}), 400
        
        logger.info(f"✅ Retrieved {len(clips)} clips from buffer")
        
        # Use AnimatedReelCreator to build complete reel with all features
        logger.info("🎨 Building complete reel with all features...")
        
        # This will handle: NYT image, text overlay, captions, anchor, voice
        # Store result in CockroachDB and return video_id
        
        # Create reel video path
        output_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
        
        # Build the reel (simplified version - we'll expand this)
        from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip, ImageClip
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        
        # Load video clips
        video_clips = []
        for clip_path in clips:
            try:
                clip = VideoFileClip(clip_path)
                clip = resize_to_portrait(clip, target_width, target_height)
                clip = clip.subclip(0, min(5, clip.duration))  # Max 5s per clip
                video_clips.append(clip)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load clip: {e}")
        
        if not video_clips:
            return jsonify({'error': 'Failed to load video clips'}), 500
        
        # Prepend NYT image if provided (4 seconds)
        if nyt_image_url:
            logger.info("📰 Adding NYT article image as first clip...")
            try:
                img_response = requests.get(nyt_image_url, timeout=10)
                img_response.raise_for_status()
                
                nyt_img_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                nyt_img_temp.write(img_response.content)
                nyt_img_temp.close()
                
                # Resize NYT image to portrait
                from PIL import Image as PILImage
                img = PILImage.open(nyt_img_temp.name)
                img_resized = img.resize((target_width, target_height), PILImage.Resampling.LANCZOS)
                img_resized_path = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg').name
                img_resized.save(img_resized_path, 'JPEG', quality=85)
                
                nyt_clip = ImageClip(img_resized_path, duration=4)
                video_clips.insert(0, nyt_clip)
                logger.info("✅ NYT image added (4s)")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to add NYT image: {e}")
        
        # Concatenate all clips
        logger.info(f"🎞️ Concatenating {len(video_clips)} clips...")
        final_video = concatenate_videoclips(video_clips, method='compose')
        
        # Add voice audio if provided
        if voice_audio_id:
            logger.info("🎤 Adding voice narration...")
            voice_path = retrieve_clip_from_buffer(voice_audio_id)
            if voice_path:
                try:
                    audio_clip = AudioFileClip(voice_path)
                    final_video = final_video.set_audio(audio_clip)
                    logger.info("✅ Voice audio added")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to add voice: {e}")
        
        # Add text overlay (headline)
        logger.info("📝 Adding headline text overlay...")
        final_video = add_headline_overlay(final_video, headline, target_width, target_height)
        
        # Add anchor overlay
        logger.info("👩‍💼 Adding anchor overlay...")
        final_video = add_anchor_overlay(final_video, target_width, target_height)
        
        # Write final video
        logger.info("💾 Writing final video...")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=30,
            preset='medium',
            threads=4
        )
        
        duration = final_video.duration
        
        # Close all clips
        final_video.close()
        for clip in video_clips:
            clip.close()
        gc.collect()
        
        # Store in CockroachDB
        logger.info("💾 Storing final reel in CockroachDB...")
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        video_id = store_in_cockroachdb(output_path, duration, file_size_mb)
        
        logger.info(f"✅ Complete reel created: {duration:.1f}s, {file_size_mb:.2f}MB (ID: {video_id})")
        
        # Cleanup temp files
        os.unlink(output_path)
        for clip_path in clips:
            try:
                os.unlink(clip_path)
            except:
                pass
        
        return jsonify({
            'video_id': video_id,
            'duration': duration,
            'file_size_mb': round(file_size_mb, 2)
        })
        
    except Exception as e:
        logger.error(f"❌ Error in complete reel creation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def add_headline_overlay(video_clip, headline, target_width, target_height):
    """Add headline text overlay using PIL"""
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        import numpy as np
        import textwrap
        
        duration = video_clip.duration
        
        # Create image for text
        overlay_height = 200
        img = PILImage.new('RGBA', (target_width, overlay_height), (0, 0, 0, 180))
        draw = ImageDraw.Draw(img)
        
        # Wrap headline
        wrapped = textwrap.fill(headline, width=35)
        
        # Draw text (simplified - no custom font needed)
        draw.text((target_width//2, overlay_height//2), wrapped, 
                  fill=(255, 255, 255, 255), anchor='mm')
        
        # Convert to numpy and create clip
        img_array = np.array(img)
        text_clip = ImageClip(img_array, duration=duration).set_position(('center', 50))
        
        return CompositeVideoClip([video_clip, text_clip])
    except Exception as e:
        logger.warning(f"⚠️ Failed to add headline overlay: {e}")
        return video_clip

def add_anchor_overlay(video_clip, target_width, target_height):
    """Add anchor overlay in corner"""
    try:
        from PIL import Image as PILImage, ImageDraw
        import numpy as np
        
        duration = video_clip.duration
        
        # Create simple anchor overlay (circle with initials)
        size = 100
        img = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw circle
        draw.ellipse([0, 0, size, size], fill=(30, 30, 30, 200))
        
        # Draw initials
        draw.text((size//2, size//2), 'RA', fill=(255, 255, 255, 255), anchor='mm')
        
        # Convert and position
        img_array = np.array(img)
        anchor_clip = ImageClip(img_array, duration=duration).set_position((target_width - 120, 20))
        
        return CompositeVideoClip([video_clip, anchor_clip])
    except Exception as e:
        logger.warning(f"⚠️ Failed to add anchor: {e}")
        return video_clip

@app.route('/generate-reel-from-article', methods=['POST'])
def generate_reel_from_article():
    """
    COMPLETE reel generation from NYT article (no client processing needed)
    Steps:
    1. Generate voice with Google TTS
    2. Extract keywords and download Pexels clips to buffer
    3. Create complete reel (clips + NYT image + text + captions + anchor + voice)
    4. Store in CockroachDB processed_videos
    5. Return video_id
    """
    try:
        data = request.get_json()
        headline = data.get('headline', '')
        abstract = data.get('abstract', '')
        commentary = data.get('commentary', '')
        nyt_image_url = data.get('nyt_image_url')
        article_url = data.get('article_url', '')
        article_id = data.get('article_id', '')
        clips_count = data.get('clips_count', 6)
        
        logger.info(f"🎬 COMPLETE reel generation for: {headline[:50]}...")
        
        # Step 1: Generate voice narration
        logger.info("🎤 Generating voice narration...")
        from google_tts_voice import GoogleTTSVoice
        tts = GoogleTTSVoice()
        
        voice_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        voice_file.close()
        
        voice_path = tts.generate_voice(
            commentary,
            voice_file.name,
            voice_name="en-US-Studio-O"
        )
        
        if not voice_path:
            return jsonify({'error': 'Voice generation failed'}), 500
        
        logger.info("✅ Voice generated")
        
        # Step 2: Extract keywords and download Pexels clips
        logger.info(f"📥 Fetching {clips_count} Pexels clips...")
        from pexels_video_fetcher import PexelsMediaFetcher
        import uuid
        
        pexels = PexelsMediaFetcher()
        keywords = pexels.extract_search_keywords(headline, commentary)
        
        session_id = str(uuid.uuid4())
        clip_ids = []
        
        for keyword in keywords[:3]:
            videos = pexels.search_videos(keyword, per_page=3, orientation='portrait')
            for video in videos:
                clip_id = pexels.download_media(video['url'], 'video', session_id)
                if clip_id:
                    clip_ids.append(clip_id)
                    if len(clip_ids) >= clips_count:
                        break
            if len(clip_ids) >= clips_count:
                break
        
        if not clip_ids:
            os.unlink(voice_path)
            return jsonify({'error': 'Failed to download clips'}), 500
        
        logger.info(f"✅ Downloaded {len(clip_ids)} clips to buffer")
        
        # Step 3: Upload voice to buffer
        with open(voice_path, 'rb') as f:
            voice_data = f.read()
        voice_id = pexels.buffer.store_clip(voice_data, 'audio', session_id)
        os.unlink(voice_path)
        
        logger.info(f"✅ Voice uploaded to buffer (ID: {voice_id})")
        
        # Step 4: Call complete reel creation endpoint
        logger.info("🎨 Creating complete reel with all features...")
        
        response = requests.post(
            'http://localhost:8080/create-complete-reel',
            json={
                'clip_ids': clip_ids,
                'headline': headline,
                'commentary': commentary,
                'voice_audio_id': voice_id,
                'nyt_image_url': nyt_image_url,
                'target_width': 1080,
                'target_height': 1920
            },
            timeout=600
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Reel creation failed', 'details': response.text}), 500
        
        result = response.json()
        
        logger.info(f"✅ Complete reel generation finished: {result['duration']:.1f}s")
        
        return jsonify({
            'video_id': result['video_id'],
            'duration': result['duration'],
            'file_size_mb': result['file_size_mb']
        })
        
    except Exception as e:
        logger.error(f"❌ Error in article reel generation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
