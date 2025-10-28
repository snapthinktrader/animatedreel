"""
Lightweight Reel Creator - Offloads heavy processing to Google Cloud Run
Render service only handles: orchestration, overlays, and database storage
"""

import os
import logging
import requests
import tempfile
import numpy as np
from typing import List, Dict, Optional
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip, ImageClip
from PIL import Image
import gc
from dotenv import load_dotenv

# Load environment from parent QPost directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(parent_dir, '.env')
load_dotenv(env_path)

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
            'https://video-processor-flqsiu3bra-el.a.run.app'
        )
        
        from anchor_overlay import AnchorOverlaySystem
        self.anchor_system = AnchorOverlaySystem()
    
    def create_animated_reel(
        self,
        headline: str,
        commentary: str,
        voice_audio_path: str,
        clips_urls: Optional[List[Dict]] = None,  # List of {"url": "...", "type": "video", "duration": 3.6}
        target_duration: int = 25,
        clips_count: int = 6,  # Number of clips to fetch if clips_urls not provided
        nyt_image_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Create animated reel using Cloud Run for heavy processing
        NEW ARCHITECTURE: Download clips to buffer first, then process on Cloud Run
        
        Args:
            headline: News headline
            commentary: Full commentary text
            voice_audio_path: Path to voice narration MP3
            clips_urls: Optional list of clip URLs from Pexels (if None, will fetch automatically)
            target_duration: Target reel duration
            clips_count: Number of clips to fetch if clips_urls not provided
            nyt_image_url: Optional NYT article image
            
        Returns:
            Path to final reel video or None
        """
        try:
            logger.info("🎬 Creating reel with Cloud Run processing...")
            
            # Fetch clips if not provided
            if clips_urls is None:
                logger.info(f"📥 Fetching {clips_count} clips from Pexels...")
                from pexels_video_fetcher import PexelsMediaFetcher
                pexels_fetcher = PexelsMediaFetcher()
                
                # Extract keywords and search for videos
                keywords = pexels_fetcher.extract_search_keywords(headline, commentary)
                
                clips_urls = []
                for keyword in keywords[:3]:  # Use top 3 keywords
                    videos = pexels_fetcher.search_videos(keyword, per_page=3, orientation='portrait')
                    for video in videos:
                        clips_urls.append({
                            'url': video['url'],
                            'type': 'video',
                            'duration': video.get('duration', 3.0)
                        })
                        if len(clips_urls) >= clips_count:
                            break
                    if len(clips_urls) >= clips_count:
                        break
                
                if not clips_urls:
                    logger.error("❌ Failed to fetch clips from Pexels")
                    return None
                
                # Limit to requested count
                clips_urls = clips_urls[:clips_count]
                logger.info(f"✅ Fetched {len(clips_urls)} clips from Pexels")
            
            # Step 1: Download clips from Pexels and store in CockroachDB buffer
            logger.info(f"📥 Downloading {len(clips_urls)} clips from Pexels to buffer...")
            
            from pexels_video_fetcher import PexelsMediaFetcher
            import uuid
            
            pexels_fetcher = PexelsMediaFetcher()
            session_id = str(uuid.uuid4())  # Session ID for this reel
            clip_ids = []
            
            for i, clip_info in enumerate(clips_urls):
                url = clip_info['url']
                media_type = clip_info['type']
                
                logger.info(f"  Downloading clip {i+1}/{len(clips_urls)}...")
                clip_id = pexels_fetcher.download_media(url, media_type, session_id)
                
                if clip_id:
                    clip_ids.append(clip_id)
                    logger.info(f"  ✅ Stored in buffer (ID: {clip_id})")
                else:
                    logger.warning(f"  ⚠️ Failed to download clip {i+1}")
            
            if not clip_ids:
                logger.error("❌ No clips were successfully downloaded to buffer")
                return None
            
            logger.info(f"✅ Downloaded {len(clip_ids)} clips to buffer")
            
            # Step 2: Send clip IDs to Cloud Run for processing
            logger.info(f"☁️ Sending {len(clip_ids)} clip IDs to Cloud Run for processing...")
            logger.info("⏱️ Processing will take ~30-60 seconds...")
            
            # Send request with clip IDs instead of URLs
            try:
                response = requests.post(
                    f'{self.cloud_processor_url}/process-clips',
                    json={
                        'clip_ids': clip_ids,  # Changed from 'clips' to 'clip_ids'
                        'target_width': 1080,
                        'target_height': 1920
                    },
                    timeout=300  # 5 minutes for processing (6 clips * 5s each + concatenation + writing)
                )
            except requests.exceptions.Timeout:
                logger.error("❌ Cloud Run timeout - the service may need more memory or be cold starting")
                logger.info("💡 Try again - Cold starts can take 30-60 seconds on first request")
                return None
            except Exception as e:
                logger.error(f"❌ Cloud processing request failed: {e}")
                return None
            
            if response.status_code != 200:
                logger.error(f"❌ Cloud processing failed: Status {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return None
            
            result = response.json()
            video_id = result['video_id']  # Returned video ID in buffer
            video_duration = result['duration']
            
            logger.info(f"✅ Cloud processing complete: {video_duration:.1f}s video (ID: {video_id})")
            
            # Step 3: Retrieve processed video from buffer
            logger.info(f"📥 Retrieving processed video from buffer...")
            
            from cockroach_buffer import CockroachBufferStorage
            buffer = CockroachBufferStorage()
            temp_video_path = buffer.retrieve_processed_video(video_id)
            
            if not temp_video_path:
                logger.error("❌ Failed to retrieve processed video from buffer")
                return None
            
            logger.info("✅ Retrieved processed video from buffer")
            
            # Step 3b: Download and prepare NYT article image (FIRST CLIP)
            nyt_clip = None
            if nyt_image_url:
                try:
                    logger.info(f"📰 Downloading NYT article image...")
                    import requests as req
                    from moviepy.editor import ImageClip, concatenate_videoclips
                    
                    response = req.get(nyt_image_url, timeout=10)
                    
                    if response.status_code == 200:
                        # Save to temp file
                        temp_img = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                        temp_img.write(response.content)
                        temp_img.close()
                        
                        # Create image clip (will be first in reel) - 4 seconds
                        nyt_duration = 4.0
                        nyt_clip_raw = ImageClip(temp_img.name, duration=nyt_duration)
                        
                        # Resize to portrait (1080x1920)
                        w, h = nyt_clip_raw.size
                        target_ratio = 1080 / 1920
                        current_ratio = w / h
                        
                        if current_ratio > target_ratio:
                            # Image is wider, crop width
                            new_width = int(h * target_ratio)
                            x_center = w // 2
                            x1 = x_center - new_width // 2
                            nyt_clip_raw = nyt_clip_raw.crop(x1=x1, width=new_width)
                        else:
                            # Image is taller, crop height
                            new_height = int(w / target_ratio)
                            y_center = h // 2
                            y1 = y_center - new_height // 2
                            nyt_clip_raw = nyt_clip_raw.crop(y1=y1, height=new_height)
                        
                        nyt_clip = nyt_clip_raw.resize((1080, 1920))
                        logger.info(f"✅ Created NYT image clip: {nyt_duration:.1f}s")
                        
                        # Clean up temp file
                        os.unlink(temp_img.name)
                    else:
                        logger.warning(f"⚠️ Failed to download NYT image: HTTP {response.status_code}")
                except Exception as e:
                    logger.error(f"❌ Error downloading NYT image: {e}")
            
            # Step 4: Load processed video from Cloud Run
            final_video = VideoFileClip(temp_video_path)
            
            # Step 4b: Prepend NYT image clip if available
            if nyt_clip:
                logger.info("📰 Prepending NYT article image as first clip...")
                final_video = concatenate_videoclips([nyt_clip, final_video], method="compose")
                logger.info(f"✅ NYT image prepended (total duration: {final_video.duration:.1f}s)")
            
            # Step 5: Add headline text overlay (lightweight operation)
            logger.info("📝 Adding headline text overlay...")
            final_video = self._add_text_overlay(final_video, headline, commentary)
            
            # Step 6: Add anchor overlay (lightweight operation)
            logger.info("👩‍💼 Adding anchor overlay...")
            try:
                final_video, anchor_name = self.anchor_system.add_to_video_clip(final_video)
                logger.info(f"✅ Added anchor: {anchor_name}")
            except Exception as e:
                logger.warning(f"⚠️ Could not add anchor overlay: {e}")
            
            # Step 7: Add voice audio (lightweight operation)
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
                
                # Step 7b: Add synced captions (transcribe audio and add word-by-word)
                logger.info("📝 Generating synced captions from audio...")
                final_video = self._add_synced_captions(final_video, voice_audio_path, commentary)
            else:
                logger.warning("⚠️ No voice audio provided, skipping captions")
            
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
            os.unlink(temp_video_path)
            gc.collect()
            
            logger.info(f"✅ Reel created: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Error creating reel: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _add_text_overlay(self, video_clip, headline, commentary):
        """
        Add text overlay using PIL (avoids ImageMagick dependency)
        Large, bold headline at top with readable size
        """
        try:
            try:
                from moviepy import ImageClip, CompositeVideoClip
            except:
                from moviepy.editor import ImageClip, CompositeVideoClip
            
            from PIL import Image, ImageDraw, ImageFont
            import textwrap
            import numpy as np
            
            duration = video_clip.duration
            
            # Get video dimensions
            video_width, video_height = video_clip.size
            
            # Create transparent overlay for headline
            headline_overlay = Image.new('RGBA', (video_width, 200), (0, 0, 0, 0))
            draw = ImageDraw.Draw(headline_overlay)
            
            # Add semi-transparent background
            draw.rectangle([0, 0, video_width, 200], fill=(0, 0, 0, 180))
            
            # Wrap headline text
            headline_wrapped = textwrap.fill(headline, width=35)
            
            # Load font
            try:
                headline_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 60)
            except:
                try:
                    headline_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
                except:
                    headline_font = ImageFont.load_default()
            
            # Draw headline text (centered)
            # Get text bounding box for centering
            bbox = draw.textbbox((0, 0), headline_wrapped, font=headline_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (video_width - text_width) // 2
            y = (200 - text_height) // 2
            
            # Draw text with black outline for readability
            outline_width = 3
            for adj_x in range(-outline_width, outline_width + 1):
                for adj_y in range(-outline_width, outline_width + 1):
                    draw.text((x + adj_x, y + adj_y), headline_wrapped, font=headline_font, fill='black')
            
            # Draw white text on top
            draw.text((x, y), headline_wrapped, font=headline_font, fill='white')
            
            # Convert PIL image to numpy array
            headline_array = np.array(headline_overlay)
            
            # Create ImageClip from overlay
            headline_clip = ImageClip(headline_array, duration=duration)
            headline_clip = headline_clip.set_position((0, 0))  # Top of video
            
            # Composite: video + headline
            video_with_text = CompositeVideoClip([video_clip, headline_clip])
            
            logger.info(f"✅ Added headline overlay (PIL-based): {headline[:50]}...")
            return video_with_text
            
        except Exception as e:
            logger.warning(f"⚠️ Could not add headline overlay: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            return video_clip
    
    def _add_synced_captions(self, video_clip, audio_path: str, commentary_text: str):
        """
        Add word-by-word captions synced with audio using Groq Whisper (exact copy from animated_reel_creator.py)
        """
        try:
            try:
                from moviepy import ImageClip, CompositeVideoClip
            except:
                from moviepy.editor import ImageClip, CompositeVideoClip
            from groq import Groq
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
            
            # Initialize Groq client
            groq_api_key = os.getenv('GROQ_API_KEY')
            if not groq_api_key:
                logger.warning("⚠️ No GROQ_API_KEY found, skipping captions")
                return video_clip
            
            client = Groq(api_key=groq_api_key)
            
            # Transcribe audio with word-level timestamps using Groq Whisper
            logger.info("🎤 Transcribing audio for synced captions...")
            with open(audio_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(audio_path, audio_file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            # Parse word timestamps from response
            words_data = []
            if hasattr(transcription, 'words') and transcription.words:
                for word_dict in transcription.words:
                    if isinstance(word_dict, dict):
                        words_data.append({
                            'word': word_dict.get('word', ''),
                            'start': word_dict.get('start', 0),
                            'end': word_dict.get('end', 0)
                        })
                    else:
                        words_data.append({
                            'word': word_dict.word if hasattr(word_dict, 'word') else str(word_dict),
                            'start': word_dict.start if hasattr(word_dict, 'start') else 0,
                            'end': word_dict.end if hasattr(word_dict, 'end') else 0
                        })
            elif isinstance(transcription, dict) and 'words' in transcription:
                words_data = transcription['words']
            else:
                logger.warning("⚠️ No word timestamps available")
                return video_clip
            
            if not words_data:
                logger.warning("⚠️ No words found in transcription")
                return video_clip
            
            logger.info(f"✅ Transcribed {len(words_data)} words with timestamps")
            
            # Get video dimensions
            video_width, video_height = video_clip.size
            
            # Load font for captions
            try:
                caption_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 50)
            except:
                try:
                    caption_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 50)
                except:
                    caption_font = ImageFont.load_default()
            
            # Group words into chunks of 5 words for better readability
            words_per_caption = 5
            caption_clips = []
            
            i = 0
            while i < len(words_data):
                chunk_end = min(i + words_per_caption, len(words_data))
                word_chunk = words_data[i:chunk_end]
                
                if not word_chunk:
                    break
                
                # Combine words into one caption
                caption_text = ' '.join([w.get('word', '').strip() for w in word_chunk])
                start_time = float(word_chunk[0].get('start', 0))
                end_time = float(word_chunk[-1].get('end', 0))
                duration = max(0.5, end_time - start_time)
                
                if not caption_text or duration <= 0:
                    i += words_per_caption
                    continue
                
                try:
                    # Create caption image with PIL
                    caption_upper = caption_text.upper()
                    
                    # Measure text size
                    temp_img = Image.new('RGBA', (video_width, 200), (0, 0, 0, 0))
                    temp_draw = ImageDraw.Draw(temp_img)
                    bbox = temp_draw.textbbox((0, 0), caption_upper, font=caption_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    # Create caption with padding
                    max_caption_width = video_width - 80
                    actual_caption_width = min(text_width + 40, max_caption_width)
                    
                    caption_img = Image.new('RGBA', (actual_caption_width, text_height + 30), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(caption_img)
                    
                    # Semi-transparent background
                    draw.rectangle([0, 0, actual_caption_width, text_height + 30], fill=(0, 0, 0, 200))
                    
                    # Draw text with outline
                    text_x = 20
                    text_y = 15
                    outline_width = 3
                    for adj_x in range(-outline_width, outline_width + 1):
                        for adj_y in range(-outline_width, outline_width + 1):
                            draw.text((text_x + adj_x, text_y + adj_y), caption_upper, font=caption_font, fill='black')
                    
                    # Yellow text on top
                    draw.text((text_x, text_y), caption_upper, font=caption_font, fill='#FFD700')
                    
                    # Convert to numpy array
                    caption_array = np.array(caption_img)
                    
                    # Create ImageClip
                    caption_clip = ImageClip(caption_array, duration=duration)
                    
                    # Position in lower third
                    x_position = (video_width - caption_img.width) // 2
                    max_y = video_height - caption_img.height - 200
                    y_position = min((video_height // 2) + 300, max_y)
                    
                    caption_clip = caption_clip.set_position((x_position, y_position))
                    caption_clip = caption_clip.set_start(start_time)
                    
                    caption_clips.append(caption_clip)
                    
                except Exception as e:
                    logger.debug(f"Skipped caption chunk: {e}")
                
                i += words_per_caption
            
            logger.info(f"✅ Created {len(caption_clips)} caption clips")
            
            if not caption_clips:
                return video_clip
            
            # Composite all captions onto video
            video_with_captions = CompositeVideoClip([video_clip] + caption_clips)
            logger.info(f"✅ Synced captions added")
            
            return video_with_captions
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Caption generation failed: {e}")
            logger.error(traceback.format_exc())
            return video_clip

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
