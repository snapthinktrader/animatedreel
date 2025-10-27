"""
Render API endpoint for generating animated reels
Uses streaming responses to prevent 30-second timeout
"""

from flask import Flask, request, jsonify, Response
import os
import sys
import logging
import json
import time
from animated_reel_creator import AnimatedReelCreator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize the reel creator (reuse instance for faster subsequent calls)
reel_creator = None

def get_reel_creator():
    """Get or create reel creator instance"""
    global reel_creator
    if reel_creator is None:
        logger.info("🎬 Initializing AnimatedReelCreator...")
        reel_creator = AnimatedReelCreator()
        logger.info("✅ AnimatedReelCreator ready")
    return reel_creator

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'animated-reel-generator'}), 200

def generate_with_progress(headline, commentary, voice_audio_path, target_duration, nyt_image_url):
    """Generator function that yields progress updates"""
    try:
        yield json.dumps({'status': 'starting', 'message': 'Initializing reel creation...'}) + '\n'
        
        creator = get_reel_creator()
        
        yield json.dumps({'status': 'progress', 'message': 'Fetching media clips...'}) + '\n'
        
        # Generate the reel (this takes 8-12 minutes)
        video_path = creator.create_animated_reel(
            headline=headline,
            commentary=commentary,
            voice_audio_path=voice_audio_path,
            target_duration=target_duration,
            clips_count=6,
            nyt_image_url=nyt_image_url
        )
        
        if not video_path:
            yield json.dumps({'status': 'error', 'message': 'Failed to generate reel'}) + '\n'
            return
        
        yield json.dumps({'status': 'progress', 'message': 'Reading video file...'}) + '\n'
        
        # Read video file
        with open(video_path, 'rb') as f:
            video_data = f.read()
        
        # Get file info
        import base64
        file_size_mb = len(video_data) / (1024 * 1024)
        video_base64 = base64.b64encode(video_data).decode('utf-8')
        
        # Clean up
        os.unlink(video_path)
        if voice_audio_path:
            os.unlink(voice_audio_path)
        
        yield json.dumps({
            'status': 'complete',
            'success': True,
            'video_base64': video_base64,
            'file_size_mb': round(file_size_mb, 2),
            'duration': target_duration
        }) + '\n'
        
    except Exception as e:
        logger.error(f"❌ Error generating reel: {e}")
        import traceback
        traceback.print_exc()
        yield json.dumps({'status': 'error', 'message': str(e)}) + '\n'

@app.route('/generate-reel', methods=['POST'])
def generate_reel():
    """
    Generate an animated reel from NYT article with streaming progress
    
    Request body:
    {
        "headline": "Article headline",
        "commentary": "AI-generated commentary",
        "voice_audio_base64": "base64-encoded audio (optional)",
        "nyt_image_url": "NYT article image URL (optional)",
        "target_duration": 30
    }
    
    Returns streaming JSON lines:
    {"status": "starting", "message": "..."}
    {"status": "progress", "message": "..."}
    {"status": "complete", "success": true, "video_base64": "...", "file_size_mb": 5.2}
    """
    try:
        data = request.json
        
        headline = data.get('headline')
        commentary = data.get('commentary')
        voice_audio_base64 = data.get('voice_audio_base64')
        nyt_image_url = data.get('nyt_image_url')
        target_duration = data.get('target_duration', 30)
        
        if not headline or not commentary:
            return jsonify({'error': 'Missing required fields: headline, commentary'}), 400
        
        logger.info(f"🎬 Generating reel: {headline[:50]}...")
        
        # Decode voice audio if provided
        voice_audio_path = None
        if voice_audio_base64:
            import base64
            import tempfile
            voice_audio = base64.b64decode(voice_audio_base64)
            temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            temp_audio.write(voice_audio)
            temp_audio.close()
            voice_audio_path = temp_audio.name
        
        # Return streaming response to prevent timeout
        return Response(
            generate_with_progress(
                headline, 
                commentary, 
                voice_audio_path, 
                target_duration, 
                nyt_image_url
            ),
            mimetype='application/x-ndjson',  # Newline-delimited JSON
            headers={'X-Accel-Buffering': 'no'}  # Disable buffering
        )
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
