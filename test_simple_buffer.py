"""
Simple end-to-end buffer storage test
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backinsta', '.env')
load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)

from cockroach_buffer import CockroachBufferStorage

# Create a test file
test_file = '/tmp/test_video.mp4'
with open(test_file, 'wb') as f:
    f.write(b'TEST VIDEO DATA' * 1000)

print(f"✅ Created test file: {test_file}")

# Test buffer
buffer = CockroachBufferStorage()
print("✅ Connected to buffer")

# Store
clip_id = buffer.store_clip(test_file, 'video', 'test_session')
print(f"✅ Stored clip: {clip_id}")
print(f"   Type: {type(clip_id)}")

# Retrieve
retrieved_path = buffer.retrieve_clip(clip_id)
if retrieved_path:
    print(f"✅ Retrieved clip to: {retrieved_path}")
    
    # Check content
    with open(retrieved_path, 'rb') as f:
        data = f.read()
    print(f"✅ Data size: {len(data)} bytes")
    
    # Cleanup
    os.unlink(retrieved_path)
    print("✅ Deleted retrieved file")
else:
    print("❌ Failed to retrieve")

# Delete from buffer
buffer.delete_clip(clip_id)
print("✅ Deleted from buffer")

# Stats
stats = buffer.get_buffer_stats()
print(f"✅ Final buffer: {stats}")

buffer.close()
print("✅ Test complete!")
