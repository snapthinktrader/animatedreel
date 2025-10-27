#!/bin/bash
# Start script that runs both the API server and the continuous worker

echo "🚀 Starting Animated Reel System..."

# Run database migration first
echo "📊 Running database migration for chunking support..."
python migrate_chunking.py

# Start the continuous worker in the background
echo "🎬 Starting continuous reel generator..."
python generate_and_save_reels.py &
WORKER_PID=$!

# Start the API server in the foreground
echo "🌐 Starting API server..."
gunicorn api:app --bind 0.0.0.0:$PORT --timeout 600 --workers 1

# If API server exits, kill the worker
kill $WORKER_PID
