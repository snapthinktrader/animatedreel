"""
Quick test for chunked buffer storage
"""

import os
import sys
import tempfile

# Add parent directory to path to import from backinsta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backinsta'))

# Load environment from backinsta .env
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', 'backinsta', '.env')
load_dotenv(env_path)

from cockroach_buffer import CockroachBufferStorage

def test_chunking():
    """Test chunked storage with a large dummy file"""
    
    print("\n🧪 Testing CockroachDB Chunked Storage...")
    
    # Initialize buffer
    buffer = CockroachBufferStorage()
    
    # Create a large dummy file (12 MB - should trigger chunking)
    print("\n📝 Creating 12 MB test file...")
    large_data = b'X' * (12 * 1024 * 1024)  # 12 MB of 'X' bytes
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
        f.write(large_data)
        temp_path = f.name
    
    file_size = os.path.getsize(temp_path) / (1024 * 1024)
    print(f"✅ Created test file: {file_size:.2f} MB")
    
    # Test storing (should chunk)
    print("\n💾 Storing large file (should chunk into 8 MB pieces)...")
    session_id = "test_chunk_session"
    clip_id = buffer.store_clip(temp_path, 'video', session_id)
    
    if not clip_id:
        print("❌ Failed to store clip")
        return False
    
    print(f"✅ Stored clip: {clip_id}")
    
    # Test retrieving (should reassemble)
    print("\n📥 Retrieving clip (should reassemble chunks)...")
    retrieved_path = buffer.retrieve_clip(clip_id)
    
    if not retrieved_path:
        print("❌ Failed to retrieve clip")
        return False
    
    # Verify data integrity
    retrieved_size = os.path.getsize(retrieved_path) / (1024 * 1024)
    print(f"✅ Retrieved clip: {retrieved_size:.2f} MB")
    
    with open(retrieved_path, 'rb') as f:
        retrieved_data = f.read()
    
    if retrieved_data == large_data:
        print("✅ Data integrity verified - chunks reassembled correctly!")
    else:
        print(f"❌ Data mismatch! Original: {len(large_data)} bytes, Retrieved: {len(retrieved_data)} bytes")
        return False
    
    # Cleanup
    os.unlink(retrieved_path)
    
    # Test deletion
    print("\n🗑️ Deleting clip and chunks...")
    buffer.delete_clip(clip_id)
    print("✅ Deleted successfully")
    
    # Test small file (should NOT chunk)
    print("\n📝 Testing small file (3 MB - should NOT chunk)...")
    small_data = b'Y' * (3 * 1024 * 1024)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
        f.write(small_data)
        small_path = f.name
    
    clip_id2 = buffer.store_clip(small_path, 'video', session_id)
    
    if not clip_id2:
        print("❌ Failed to store small clip")
        return False
    
    print(f"✅ Stored small clip: {clip_id2}")
    
    # Cleanup session
    print("\n🧹 Cleaning up session...")
    buffer.delete_session_clips(session_id)
    print("✅ Session cleanup complete")
    
    print("\n✅ All chunking tests passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_chunking()
        if success:
            print("\n🎉 Chunked storage system working perfectly!")
        else:
            print("\n❌ Chunking tests failed")
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
