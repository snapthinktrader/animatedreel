"""
Lightweight Reel Creator - Offloads heavy processing to Google Cloud Run
Render service only handles: orchestration, overlays, and database storage
"""

import os
import logging
import requests
import tempfile
from typing import List, Dict, Optional
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip
from PIL import Image
import gc

# Monkey-patch for PIL compatibility
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LightweightReelCreator:
    """
    Lightweight reel creator that offloads video processing to Cloud Run
    """
    
    def __init__(self):
        # Google Cloud Run video processor URL
        self.cloud_processor_url = os.environ.get(
            'CLOUD_PROCESSOR_URL',
            'https://video-processor-<your-hash>-uc.a.run.app'
        )
        
        from anchor_overlay import AnchorOverlaySystem
        self.anchor_system = AnchorOverlaySystem()
    
    def create_animated_reel(
        self,
        headline: str,
        commentary: str,
        voice_audio_path: str,
        clips_urls: List[Dict],  # List of {"url": "...", "type": "video", "duration": 3.6}
        target_duration: int = 25,
        nyt_image_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Create animated reel using Cloud Run for heavy processing
        
        Args:
            headline: News headline
            commentary: Full commentary text
            voice_audio_path: Path to voice narration MP3
            clips_urls: List of clip URLs from Pexels
            target_duration: Target reel duration
            nyt_image_url: Optional NYT article image
            
        Returns:
            Path to final reel video or None
        """
        try:
            logger.info("🎬 Creating reel with Cloud Run processing...")
            
            # Step 1: Send clips to Cloud Run for processing
            logger.info(f"☁️ Sending {len(clips_urls)} clips to Cloud Run for processing...")
            
            response = requests.post(
                f'{self.cloud_processor_url}/process-clips',
                json={
                    'clips': clips_urls,
                    'target_width': 1080,
                    'target_height': 1920
                },
                timeout=600  # 10 minutes timeout
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Cloud processing failed: {response.text}")
                return None
            
            result = response.json()
            processed_video_url = result['video_url']
            video_duration = result['duration']
            
            logger.info(f"✅ Cloud processing complete: {video_duration:.1f}s video")
            logger.info(f"📥 Downloading processed video from Cloud Storage...")
            
            # Step 2: Download processed video
            video_response = requests.get(processed_video_url, timeout=120)
            
            if video_response.status_code != 200:
                logger.error("❌ Failed to download processed video")
                return None
            
            # Save to temp file
            temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_video.write(video_response.content)
            temp_video.close()
            
            logger.info("✅ Downloaded processed video")
            
            # Step 3: Load video (memory efficient - only final video)
            final_video = VideoFileClip(temp_video.name)
            
            # Step 4: Add text overlays (lightweight operation)
            logger.info("📝 Adding text overlays...")
            final_video = self._add_text_overlay(final_video, headline, commentary)
            
            # Step 5: Add anchor overlay (lightweight operation)
            logger.info("👩‍💼 Adding anchor overlay...")
            try:
                final_video, anchor_name = self.anchor_system.add_to_video_clip(final_video)
                logger.info(f"✅ Added anchor: {anchor_name}")
            except Exception as e:
                logger.warning(f"⚠️ Could not add anchor overlay: {e}")
            
            # Step 6: Add voice audio (lightweight operation)
            if voice_audio_path and os.path.exists(voice_audio_path):
                logger.info("🎤 Adding voice narration...")
                audio = AudioFileClip(voice_audio_path)
                
                # Adjust video to match audio duration
                if audio.duration > final_video.duration:
                    final_video = final_video.loop(duration=audio.duration)
                else:
                    final_video = final_video.subclip(0, audio.duration)
                
                final_video = final_video.set_audio(audio)
                logger.info(f"✅ Added voice ({audio.duration:.1f}s)")
            
            # Step 7: Write final video
            output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            output_path = output_file.name
            output_file.close()
            
            logger.info("💾 Writing final reel...")
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=30,
                preset='ultrafast',  # Fast encoding on Render
                threads=2,
                logger=None
            )
            
            # Cleanup
            final_video.close()
            os.unlink(temp_video.name)
            gc.collect()
            
            logger.info(f"✅ Reel created: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Error creating reel: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _add_text_overlay(self, video, headline, commentary):
        """Add text overlays (lightweight operation)"""
        # Implementation similar to existing but simpler
        # Just add headline at top
        txt_clip = TextClip(
            headline[:60],  # Truncate for display
            fontsize=36,
            color='white',
            bg_color='black',
            size=(video.w - 40, None),
            method='caption'
        ).set_position(('center', 20)).set_duration(video.duration)
        
        return CompositeVideoClip([video, txt_clip])

# Example usage
if __name__ == "__main__":
    creator = LightweightReelCreator()
    
    # Example clips from Pexels
    clips = [
        {"url": "https://...", "type": "video", "duration": 3.6},
        {"url": "https://...", "type": "video", "duration": 3.6},
    ]
    
    reel = creator.create_animated_reel(
        headline="Test Headline",
        commentary="Test commentary",
        voice_audio_path="voice.mp3",
        clips_urls=clips
    )
