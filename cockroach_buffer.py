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
            # Check for DATABASE_URL (Render) or COCKROACHDB_URI (local)
            connection_string = os.getenv('DATABASE_URL') or os.getenv('COCKROACHDB_URI')
            if not connection_string:
                raise ValueError("DATABASE_URL or COCKROACHDB_URI not found in environment")
            
            # Ensure SSL mode
            if '?' in connection_string:
                if 'sslmode' not in connection_string:
                    connection_string += '&sslmode=require'
            else:
                connection_string += '?sslmode=require'
            
            self.conn = psycopg2.connect(connection_string)
            logger.info("✅ Connected to CockroachDB buffer storage")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to CockroachDB: {e}")
            raise
    
    def ensure_table_exists(self):
        """Create temp_clips table with chunking support if not exists"""
        try:
            cursor = self.conn.cursor()
            
            # Main clips table (for small files <10 MB)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_clips (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    clip_data BYTEA NOT NULL,
                    media_type VARCHAR(10) NOT NULL,
                    file_size_mb DECIMAL(10, 2),
                    created_at TIMESTAMP DEFAULT NOW(),
                    session_id VARCHAR(100),
                    is_chunked BOOLEAN DEFAULT FALSE,
                    total_chunks INT DEFAULT 1
                )
            """)
            
            # Chunks table (for large files >10 MB)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_clip_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    clip_id UUID NOT NULL,
                    chunk_number INT NOT NULL,
                    chunk_data BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(clip_id, chunk_number)
                )
            """)
            
            self.conn.commit()
            cursor.close()
            logger.info("✅ Temp clips tables ready (with chunking support)")
            
        except Exception as e:
            logger.error(f"❌ Failed to create temp_clips tables: {e}")
            raise
    
    def store_clip(self, file_path: str, media_type: str, session_id: str) -> Optional[str]:
        """
        Store video/photo clip in CockroachDB buffer with automatic chunking for large files
        
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
            
            # CockroachDB has 16 MB message limit
            # Use chunking for files >8 MB to be safe
            # Chunk size: 6 MB (leaves room for encoding overhead - becomes ~12 MB message)
            chunk_size = 6 * 1024 * 1024  # 6 MB chunks
            
            if file_size_mb > 8:
                # Large file - use chunking
                clip_id = self._store_clip_chunked(clip_data, media_type, file_size_mb, session_id, chunk_size)
            else:
                # Small file - store directly
                clip_id = self._store_clip_direct(clip_data, media_type, file_size_mb, session_id)
            
            # Delete local file immediately to free memory
            if clip_id:
                try:
                    os.unlink(file_path)
                    logger.info(f"🗑️ Deleted local file: {file_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not delete local file: {e}")
            
            return clip_id
            
        except Exception as e:
            logger.error(f"❌ Failed to store clip in buffer: {e}")
            return None
    
    def _store_clip_direct(self, clip_data: bytes, media_type: str, file_size_mb: float, session_id: str) -> Optional[str]:
        """Store small clip directly in database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO temp_clips (clip_data, media_type, file_size_mb, session_id, is_chunked, total_chunks)
                VALUES (%s, %s, %s, %s, FALSE, 1)
                RETURNING id::text
            """, (clip_data, media_type, file_size_mb, session_id))
            
            clip_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            
            logger.info(f"💾 Stored {media_type} clip in buffer: {file_size_mb:.2f} MB (ID: {clip_id})")
            return str(clip_id)
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Failed to store clip directly: {e}")
            return None
    
    def _store_clip_chunked(self, clip_data: bytes, media_type: str, file_size_mb: float, session_id: str, chunk_size: int) -> Optional[str]:
        """Store large clip in chunks"""
        try:
            cursor = self.conn.cursor()
            
            # Calculate number of chunks
            total_chunks = (len(clip_data) + chunk_size - 1) // chunk_size
            
            # Create main clip entry (without data)
            cursor.execute("""
                INSERT INTO temp_clips (clip_data, media_type, file_size_mb, session_id, is_chunked, total_chunks)
                VALUES (%s, %s, %s, %s, TRUE, %s)
                RETURNING id::text
            """, (b'', media_type, file_size_mb, session_id, total_chunks))
            
            clip_id = cursor.fetchone()[0]
            self.conn.commit()
            
            # Store chunks
            for i in range(total_chunks):
                start = i * chunk_size
                end = min(start + chunk_size, len(clip_data))
                chunk = clip_data[start:end]
                
                cursor.execute("""
                    INSERT INTO temp_clip_chunks (clip_id, chunk_number, chunk_data)
                    VALUES (%s::uuid, %s, %s)
                """, (clip_id, i, chunk))
                self.conn.commit()
                
                logger.info(f"   💾 Chunk {i+1}/{total_chunks}: {len(chunk)/(1024*1024):.2f} MB")
            
            cursor.close()
            
            logger.info(f"💾 Stored {media_type} clip in buffer (CHUNKED): {file_size_mb:.2f} MB in {total_chunks} chunks (ID: {clip_id})")
            return str(clip_id)
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Failed to store clip in chunks: {e}")
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
            # Check if chunked
            cursor.execute("""
                SELECT is_chunked, media_type, file_size_mb, total_chunks
                FROM temp_clips
                WHERE id::text = %s
            """, (str(clip_id),))
            
            row = cursor.fetchone()
            
            if not row:
                cursor.close()
                logger.error(f"❌ Clip not found: {clip_id}")
                return None
            
            is_chunked, media_type, file_size_mb, total_chunks = row
            
            if is_chunked:
                # Retrieve and reassemble chunks
                cursor.execute("""
                    SELECT chunk_data
                    FROM temp_clip_chunks
                    WHERE clip_id::text = %s
                    ORDER BY chunk_number
                """, (str(clip_id),))
                
                chunks = [bytes(row[0]) for row in cursor.fetchall()]
                cursor.close()
                
                if len(chunks) != total_chunks:
                    logger.error(f"❌ Missing chunks: expected {total_chunks}, got {len(chunks)}")
                    return None
                
                clip_data = b''.join(chunks)
                logger.info(f"📥 Retrieved {media_type} clip from buffer (CHUNKED): {file_size_mb:.2f} MB from {total_chunks} chunks")
            else:
                # Retrieve normally
                cursor.execute("""
                    SELECT clip_data
                    FROM temp_clips
                    WHERE id::text = %s
                """, (str(clip_id),))
                
                row = cursor.fetchone()
                cursor.close()
                
                if not row:
                    logger.error(f"❌ Clip data not found: {clip_id}")
                    return None
                
                clip_data = bytes(row[0])
                logger.info(f"📥 Retrieved {media_type} clip from buffer: {file_size_mb:.2f} MB")
            
            # Save to temp file
            suffix = '.mp4' if media_type == 'video' else '.jpg'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.write(clip_data)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve clip from buffer: {e}")
            return None
    
    def retrieve_processed_video(self, video_id: str) -> Optional[str]:
        """
        Retrieve processed video from Cloud Run stored in CockroachDB
        
        Args:
            video_id: UUID of the processed video
            
        Returns:
            Path to temporary file or None if failed
        """
        try:
            cursor = self.conn.cursor()
            # Check if chunked
            cursor.execute("""
                SELECT is_chunked, file_size_mb, total_chunks
                FROM processed_videos
                WHERE id::text = %s
            """, (str(video_id),))
            
            row = cursor.fetchone()
            
            if not row:
                cursor.close()
                logger.error(f"❌ Processed video not found: {video_id}")
                return None
            
            is_chunked, file_size_mb, total_chunks = row
            
            if is_chunked:
                # Retrieve and reassemble chunks
                cursor.execute("""
                    SELECT chunk_data
                    FROM processed_video_chunks
                    WHERE video_id::text = %s
                    ORDER BY chunk_number
                """, (str(video_id),))
                
                chunks = [bytes(row[0]) for row in cursor.fetchall()]
                cursor.close()
                
                if len(chunks) != total_chunks:
                    logger.error(f"❌ Missing chunks: expected {total_chunks}, got {len(chunks)}")
                    return None
                
                video_data = b''.join(chunks)
                logger.info(f"📥 Retrieved processed video (CHUNKED): {file_size_mb:.2f} MB from {total_chunks} chunks")
            else:
                # Retrieve normally
                cursor.execute("""
                    SELECT video_data
                    FROM processed_videos
                    WHERE id::text = %s
                """, (str(video_id),))
                
                row = cursor.fetchone()
                cursor.close()
                
                if not row:
                    logger.error(f"❌ Processed video data not found: {video_id}")
                    return None
                
                video_data = bytes(row[0])
                logger.info(f"📥 Retrieved processed video: {file_size_mb:.2f} MB")
            
            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_file.write(video_data)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve processed video: {e}")
            return None
    
    def delete_clip(self, clip_id: str):
        """Delete a single clip from buffer (including chunks if chunked)"""
        try:
            cursor = self.conn.cursor()
            
            # Delete chunks first (if any)
            cursor.execute("DELETE FROM temp_clip_chunks WHERE clip_id::text = %s", (str(clip_id),))
            chunks_deleted = cursor.rowcount
            
            # Delete main clip entry
            cursor.execute("DELETE FROM temp_clips WHERE id::text = %s", (str(clip_id),))
            
            self.conn.commit()
            cursor.close()
            
            if chunks_deleted > 0:
                logger.info(f"🗑️ Deleted clip from buffer (and {chunks_deleted} chunks): {clip_id}")
            else:
                logger.info(f"🗑️ Deleted clip from buffer: {clip_id}")
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Failed to delete clip: {e}")
    
    def delete_session_clips(self, session_id: str):
        """Delete all clips for a session (including chunks)"""
        try:
            cursor = self.conn.cursor()
            
            # Get all clip IDs for this session
            cursor.execute("SELECT id::text FROM temp_clips WHERE session_id = %s", (session_id,))
            clip_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete chunks for all clips in session
            for clip_id in clip_ids:
                cursor.execute("DELETE FROM temp_clip_chunks WHERE clip_id::text = %s", (clip_id,))
            
            # Delete main clip entries
            cursor.execute("DELETE FROM temp_clips WHERE session_id = %s", (session_id,))
            deleted_count = cursor.rowcount
            
            self.conn.commit()
            cursor.close()
            
            if deleted_count > 0:
                logger.info(f"🗑️ Deleted {deleted_count} clips from session: {session_id}")
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Failed to delete session clips: {e}")
    
    def cleanup_old_clips(self, hours: int = 2):
        """Delete clips older than specified hours (safety cleanup, including chunks)"""
        try:
            cursor = self.conn.cursor()
            
            # Get old clip IDs
            cursor.execute("""
                SELECT id::text FROM temp_clips
                WHERE created_at < NOW() - INTERVAL '%s hours'
            """, (hours,))
            old_clip_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete chunks for old clips
            for clip_id in old_clip_ids:
                cursor.execute("DELETE FROM temp_clip_chunks WHERE clip_id::text = %s", (clip_id,))
            
            # Delete old clips
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
            self.conn.rollback()
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
