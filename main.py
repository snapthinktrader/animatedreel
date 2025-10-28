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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
