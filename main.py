"""
Google Cloud Run Service for Heavy Video Processing
Handles the memory-intensive video editing operations
Stores result in CockroachDB instead of Google Cloud Storage
"""

from flask import Flask, request, jsonify
import tempfile
import os
import gc
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
    return psycopg2.connect(db_url)

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'video-processor'}), 200

@app.route('/process-clips', methods=['POST'])
def process_clips():
    """
    Process video clips: download, resize, concatenate, store in CockroachDB
    
    Request JSON:
    {
        "clips": [
            {"url": "https://...", "type": "video", "duration": 3.6},
            {"url": "https://...", "type": "video", "duration": 3.6}
        ],
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
        clips_data = data.get('clips', [])
        target_width = data.get('target_width', 1080)
        target_height = data.get('target_height', 1920)
        
        if not clips_data:
            return jsonify({'error': 'No clips provided'}), 400
        
        logger.info(f"🎬 Processing {len(clips_data)} clips...")
        
        # Process clips
        clips = []
        
        for i, clip_info in enumerate(clips_data):
            url = clip_info['url']
            media_type = clip_info['type']
            duration = clip_info.get('duration', 3.0)
            
            try:
                # Download clip
                logger.info(f"📥 Downloading clip {i+1}...")
                response = requests.get(url, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"⚠️ Failed to download clip {i+1}")
                    continue
                
                # Save to temp file
                suffix = '.mp4' if media_type == 'video' else '.jpg'
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                temp_file.write(response.content)
                temp_file.close()
                
                # Process clip
                if media_type == 'video':
                    video_clip = VideoFileClip(temp_file.name)
                    
                    # Trim to duration
                    video_duration = min(video_clip.duration, duration)
                    video_clip = video_clip.subclip(0, video_duration)
                    
                    # Resize to portrait
                    video_clip = resize_to_portrait(video_clip, target_width, target_height)
                    
                    clips.append(video_clip)
                    logger.info(f"✅ Processed video clip {i+1}: {video_duration:.1f}s")
                
                else:  # photo
                    img_clip = ImageClip(temp_file.name, duration=duration)
                    img_clip = resize_to_portrait(img_clip, target_width, target_height)
                    clips.append(img_clip)
                    logger.info(f"✅ Processed photo clip {i+1}: {duration:.1f}s")
                
                # Clean up temp file
                os.unlink(temp_file.name)
                
            except Exception as e:
                logger.error(f"❌ Error processing clip {i+1}: {e}")
                continue
            
            # Force garbage collection
            gc.collect()
        
        if not clips:
            return jsonify({'error': 'No clips processed successfully'}), 500
        
        # Concatenate clips
        logger.info(f"🎬 Concatenating {len(clips)} clips...")
        final_video = concatenate_videoclips(clips, method="compose")
        
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Read video file
        with open(video_path, 'rb') as f:
            video_data = f.read()
        
        chunk_size = 6 * 1024 * 1024  # 6 MB chunks (same as buffer system)
        
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
        
        # Check if chunking needed
        if file_size_mb > 8:
            # Use chunking
            total_chunks = (len(video_data) + chunk_size - 1) // chunk_size
            
            # Create main entry
            cursor.execute("""
                INSERT INTO processed_videos (video_data, duration, file_size_mb, is_chunked, total_chunks)
                VALUES (%s, %s, %s, TRUE, %s)
                RETURNING id::text
            """, (b'', duration, file_size_mb, total_chunks))
            
            video_id = cursor.fetchone()[0]
            conn.commit()
            
            # Store chunks
            for i in range(total_chunks):
                start = i * chunk_size
                end = min(start + chunk_size, len(video_data))
                chunk = video_data[start:end]
                
                cursor.execute("""
                    INSERT INTO processed_video_chunks (video_id, chunk_number, chunk_data)
                    VALUES (%s::uuid, %s, %s)
                """, (video_id, i, chunk))
                conn.commit()
                
                logger.info(f"   💾 Stored chunk {i+1}/{total_chunks}")
            
            logger.info(f"💾 Stored video in CockroachDB (CHUNKED): {file_size_mb:.2f} MB in {total_chunks} chunks")
        else:
            # Store directly
            cursor.execute("""
                INSERT INTO processed_videos (video_data, duration, file_size_mb, is_chunked, total_chunks)
                VALUES (%s, %s, %s, FALSE, 1)
                RETURNING id::text
            """, (video_data, duration, file_size_mb))
            
            video_id = cursor.fetchone()[0]
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
