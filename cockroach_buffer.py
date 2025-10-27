"""
CockroachDB Buffer Storage
Stores temporary video clips in database during processing to avoid using Render's disk space
"""

import os
import tempfile
import logging
import psycopg2
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CockroachBufferStorage:
    """
    Temporary storage for video clips in CockroachDB
    Prevents large files from consuming Render's limited disk/memory
    """
    
    def __init__(self):
        """Initialize connection to CockroachDB"""
        self.conn = None
        self.connect()
        self.ensure_table_exists()
    
    def connect(self):
        """Connect to CockroachDB"""
        try:
            connection_string = os.getenv('DATABASE_URL')
            if not connection_string:
                raise ValueError("DATABASE_URL not found in environment")
            
            # Ensure SSL mode
            if '?' in connection_string:
                connection_string += '&sslmode=require'
            else:
                connection_string += '?sslmode=require'
            
            self.conn = psycopg2.connect(connection_string)
            logger.info("✅ Connected to CockroachDB buffer storage")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to CockroachDB: {e}")
            raise
    
    def ensure_table_exists(self):
        """Create temp_clips table if not exists"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_clips (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    clip_data BYTEA NOT NULL,
                    media_type VARCHAR(10) NOT NULL,
                    file_size_mb DECIMAL(10, 2),
                    created_at TIMESTAMP DEFAULT NOW(),
                    session_id VARCHAR(100)
                )
            """)
            self.conn.commit()
            cursor.close()
            logger.info("✅ Temp clips table ready")
            
        except Exception as e:
            logger.error(f"❌ Failed to create temp_clips table: {e}")
            raise
    
    def store_clip(self, file_path: str, media_type: str, session_id: str) -> Optional[str]:
        """
        Store video/photo clip in CockroachDB buffer
        
        Args:
            file_path: Local file path to upload
            media_type: 'video' or 'photo'
            session_id: Unique session identifier for this reel generation
            
        Returns:
            Clip ID (UUID) or None if failed
        """
        try:
            # Read file data
            with open(file_path, 'rb') as f:
                clip_data = f.read()
            
            file_size_mb = len(clip_data) / (1024 * 1024)
            
            # Store in database
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO temp_clips (clip_data, media_type, file_size_mb, session_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (clip_data, media_type, file_size_mb, session_id))
            
            clip_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            
            logger.info(f"💾 Stored {media_type} clip in buffer: {file_size_mb:.2f} MB (ID: {clip_id})")
            
            # Delete local file immediately to free memory
            try:
                os.unlink(file_path)
                logger.info(f"🗑️ Deleted local file: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete local file: {e}")
            
            return str(clip_id)
            
        except Exception as e:
            logger.error(f"❌ Failed to store clip in buffer: {e}")
            return None
    
    def retrieve_clip(self, clip_id: str) -> Optional[str]:
        """
        Retrieve clip from CockroachDB buffer to temporary file
        
        Args:
            clip_id: UUID of the clip
            
        Returns:
            Path to temporary file or None if failed
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT clip_data, media_type, file_size_mb
                FROM temp_clips
                WHERE id = %s
            """, (clip_id,))
            
            row = cursor.fetchone()
            cursor.close()
            
            if not row:
                logger.error(f"❌ Clip not found: {clip_id}")
                return None
            
            clip_data, media_type, file_size_mb = row
            
            # Save to temp file
            suffix = '.mp4' if media_type == 'video' else '.jpg'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.write(clip_data)
            temp_file.close()
            
            logger.info(f"📥 Retrieved {media_type} clip from buffer: {file_size_mb:.2f} MB")
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve clip from buffer: {e}")
            return None
    
    def delete_clip(self, clip_id: str):
        """Delete a single clip from buffer"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM temp_clips WHERE id = %s", (clip_id,))
            self.conn.commit()
            cursor.close()
            logger.info(f"🗑️ Deleted clip from buffer: {clip_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to delete clip: {e}")
    
    def delete_session_clips(self, session_id: str):
        """Delete all clips for a session"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM temp_clips WHERE session_id = %s", (session_id,))
            deleted_count = cursor.rowcount
            self.conn.commit()
            cursor.close()
            
            if deleted_count > 0:
                logger.info(f"🗑️ Deleted {deleted_count} clips from session: {session_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to delete session clips: {e}")
    
    def cleanup_old_clips(self, hours: int = 2):
        """Delete clips older than specified hours (safety cleanup)"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                DELETE FROM temp_clips
                WHERE created_at < NOW() - INTERVAL '%s hours'
            """, (hours,))
            
            deleted_count = cursor.rowcount
            self.conn.commit()
            cursor.close()
            
            if deleted_count > 0:
                logger.info(f"🧹 Cleaned up {deleted_count} old clips (>{hours}h)")
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old clips: {e}")
    
    def get_buffer_stats(self):
        """Get statistics about buffer usage"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as clip_count,
                    SUM(file_size_mb) as total_mb,
                    media_type
                FROM temp_clips
                GROUP BY media_type
            """)
            
            stats = cursor.fetchall()
            cursor.close()
            
            total_clips = 0
            total_mb = 0
            
            for count, size_mb, media_type in stats:
                logger.info(f"📊 Buffer: {count} {media_type} clips, {size_mb:.2f} MB")
                total_clips += count
                total_mb += size_mb or 0
            
            logger.info(f"📊 Total buffer: {total_clips} clips, {total_mb:.2f} MB")
            
            return {'total_clips': total_clips, 'total_mb': total_mb}
            
        except Exception as e:
            logger.error(f"❌ Failed to get buffer stats: {e}")
            return {'total_clips': 0, 'total_mb': 0}
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Closed buffer storage connection")
