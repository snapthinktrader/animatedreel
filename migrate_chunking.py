"""
Migrate CockroachDB tables to support chunking
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load environment from parent QPost directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')
load_dotenv(env_path)

def migrate_tables():
    """Add chunking support to existing tables"""
    
    db_url = os.environ.get('COCKROACHDB_URI') or os.environ.get('DATABASE_URL')
    
    if not db_url:
        print("❌ No database URL found")
        return False
    
    try:
        print("🔌 Connecting to CockroachDB...")
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'temp_clips' 
            AND column_name IN ('is_chunked', 'total_chunks')
        """)
        existing_cols = [row[0] for row in cursor.fetchall()]
        
        if 'is_chunked' not in existing_cols:
            print("📝 Adding is_chunked column...")
            cursor.execute("""
                ALTER TABLE temp_clips 
                ADD COLUMN is_chunked BOOLEAN DEFAULT FALSE
            """)
            conn.commit()
            print("✅ Added is_chunked column")
        else:
            print("✅ is_chunked column already exists")
        
        if 'total_chunks' not in existing_cols:
            print("📝 Adding total_chunks column...")
            cursor.execute("""
                ALTER TABLE temp_clips 
                ADD COLUMN total_chunks INT DEFAULT 1
            """)
            conn.commit()
            print("✅ Added total_chunks column")
        else:
            print("✅ total_chunks column already exists")
        
        # Check if temp_clip_chunks table exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'temp_clip_chunks'
        """)
        chunks_table_exists = cursor.fetchone() is not None
        
        if not chunks_table_exists:
            print("📝 Creating temp_clip_chunks table...")
            cursor.execute("""
                CREATE TABLE temp_clip_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    clip_id UUID NOT NULL,
                    chunk_number INT NOT NULL,
                    chunk_data BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(clip_id, chunk_number)
                )
            """)
            conn.commit()
            print("✅ Created temp_clip_chunks table")
        else:
            print("✅ temp_clip_chunks table already exists")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    migrate_tables()
