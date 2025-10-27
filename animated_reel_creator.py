"""
Animated Reel Creator
Creates dynamic presentation-style reels using Pexels videos/photos and Google Image Search
"""

import os
import tempfile
import logging
import gc  # For garbage collection
from typing import List, Optional

# FIX: Pillow 10.0+ removed ANTIALIAS, MoviePy 1.0.3 still uses it
# Monkey-patch PIL.Image to add ANTIALIAS back as LANCZOS
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
        logger = logging.getLogger(__name__)
        logger.info("✅ Patched PIL.Image.ANTIALIAS for MoviePy compatibility")
except Exception as e:
    pass

from pexels_video_fetcher import PexelsMediaFetcher
from google_photos_fetcher import GoogleImageSearchFetcher
from anchor_overlay import AnchorOverlaySystem

logger = logging.getLogger(__name__)

class AnimatedReelCreator:
    """Create animated presentation-style reels from multiple media clips"""
    
    def __init__(self):
        self.pexels = PexelsMediaFetcher()
        self.google_images = GoogleImageSearchFetcher()
        self.use_google_images = os.getenv('USE_GOOGLE_IMAGES', 'true').lower() == 'true'
        self.anchor_system = AnchorOverlaySystem()
    
    def create_animated_reel(
        self,
        headline: str,
        commentary: str,
        voice_audio_path: Optional[str] = None,
        target_duration: int = 30,
        clips_count: int = 4,  # REDUCED from 6 to 4 for memory optimization (512 MB limit)
        nyt_image_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Create an animated reel with NYT article image + multiple video/photo clips
        
        Args:
            headline: Article headline
            commentary: AI-generated commentary
            voice_audio_path: Path to voice narration audio file
            target_duration: Target video duration in seconds
            clips_count: Number of additional clips (4 = good balance for 512 MB RAM)
            nyt_image_url: NYT article image URL (will be first clip)
            
        Returns:
            Path to created video file or None if failed
        """
        try:
            logger.info("🎬 Creating animated reel with NYT image + stock footage...")
            
            # Import moviepy
            try:
                from moviepy import VideoFileClip, ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip
            except ImportError:
                from moviepy.editor import VideoFileClip, ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip
            
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
            import requests
            
            # Step 1: Download and prepare NYT article image (FIRST CLIP)
            nyt_clip = None
            if nyt_image_url:
                try:
                    logger.info(f"📰 Downloading NYT article image from: {nyt_image_url[:60]}...")
                    response = requests.get(nyt_image_url, timeout=10)
                    logger.info(f"   Response status: {response.status_code}")
                    
                    if response.status_code == 200:
                        # Save to temp file
                        temp_img = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                        temp_img.write(response.content)
                        temp_img.close()
                        logger.info(f"   Saved to: {temp_img.name}")
                        
                        # Create image clip (will be first in reel) - shorter duration for dynamic feel
                        nyt_duration = min(4, target_duration * 0.15)  # 4 seconds or 15% of total (reduced from 5s/30%)
                        nyt_clip_raw = ImageClip(temp_img.name, duration=nyt_duration)
                        nyt_clip = self._resize_to_portrait(nyt_clip_raw)
                        
                        logger.info(f"✅ Created NYT image clip: {nyt_duration:.1f}s, size={nyt_clip.size}")
                    else:
                        logger.warning(f"⚠️ Failed to download NYT image: HTTP {response.status_code}")
                except Exception as e:
                    logger.error(f"❌ Error downloading NYT image: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.info("ℹ️  No NYT image URL provided, using stock footage only")
            
            # Step 2: Extract keywords from headline and commentary
            keywords = self.pexels.extract_search_keywords(headline, commentary)
            
            # Step 3: Search for videos/photos on Pexels (additional clips after NYT image)
            all_media = []
            
            # Try to get videos first from Pexels (use more keywords for variety)
            for keyword in keywords[:4]:  # Increased from 2 to 4 keywords for more variety
                videos = self.pexels.search_videos(keyword, per_page=3)  # More videos per keyword
                all_media.extend([{'type': 'video', 'data': v, 'source': 'pexels'} for v in videos])
                if len(all_media) >= clips_count * 2:  # Get extra to have selection
                    break
            
            # If not enough videos, supplement with photos from Pexels
            if len(all_media) < clips_count:
                for keyword in keywords[:4]:  # Increased from 2 to 4
                    photos = self.pexels.search_photos(keyword, per_page=3)  # More photos per keyword
                    all_media.extend([{'type': 'photo', 'data': p, 'source': 'pexels'} for p in photos])
                    if len(all_media) >= clips_count * 2:
                        break
            
            # If still not enough and Google Image Search enabled, supplement with web images
            if len(all_media) < clips_count and self.use_google_images:
                logger.info("📸 Adding photos from Google Image Search...")
                for keyword in keywords[:4]:  # Increased from 2 to 4
                    google_images = self.google_images.search_photos(keyword, per_page=3)  # More images
                    all_media.extend([{'type': 'photo', 'data': p, 'source': 'google_images'} for p in google_images])
                    if len(all_media) >= clips_count * 2:
                        break
            
            # Shuffle for variety and limit to desired number of clips
            import random
            random.shuffle(all_media)
            
            # MEMORY OPTIMIZATION: Limit to 3 clips max for 512 MB RAM
            max_clips = min(3, clips_count)  # Force maximum of 3 clips
            all_media = all_media[:max_clips]
            
            if not all_media:
                logger.error("❌ No media found on Pexels or Google Images, falling back to static image")
                return None
            
            logger.info(f"✅ Found {len(all_media)} media clips (max {max_clips} for memory optimization):")
            logger.info(f"   - Videos: {sum(1 for m in all_media if m['type'] == 'video')}")
            logger.info(f"   - Photos (Pexels): {sum(1 for m in all_media if m['type'] == 'photo' and m['source'] == 'pexels')}")
            logger.info(f"   - Photos (Google): {sum(1 for m in all_media if m['type'] == 'photo' and m['source'] == 'google_images')}")
            
            # Step 3: Download media and create clips
            clips = []
            clip_duration = max(3.0, target_duration / (len(all_media) + 1))  # Shorter clips (3-5s each), +1 for NYT image
            
            logger.info(f"⏱️  Individual clip duration: {clip_duration:.1f}s for dynamic transitions")
            
            for i, media in enumerate(all_media):
                media_type = media['type']
                media_data = media['data']
                media_source = media['source']
                
                # Download media from appropriate source
                if media_source == 'pexels':
                    media_path = self.pexels.download_media(media_data['url'], media_type)
                elif media_source == 'google_images':
                    media_path = self.google_images.download_photo(media_data['url'])
                else:
                    media_path = None
                
                if not media_path:
                    logger.warning(f"⚠️ Failed to download {media_type} {i+1}, skipping")
                    continue
                
                try:
                    if media_type == 'video':
                        # Load video clip
                        video_clip = VideoFileClip(media_path)
                        
                        # Trim to desired duration
                        video_duration = min(video_clip.duration, clip_duration)
                        video_clip = video_clip.subclip(0, video_duration)
                        
                        # Resize to 9:16 (1080x1920) for Instagram Reels
                        video_clip = self._resize_to_portrait(video_clip, target_width=1080, target_height=1920)
                        
                        clips.append(video_clip)
                        logger.info(f"✅ Added video clip {i+1}: {video_duration:.1f}s")
                        
                    else:  # photo
                        # Load photo as image clip
                        img_clip = ImageClip(media_path, duration=clip_duration)
                        
                        # Resize to 9:16 portrait
                        img_clip = self._resize_to_portrait(img_clip, target_width=1080, target_height=1920)
                        
                        # Add Ken Burns effect (zoom and pan)
                        img_clip = self._add_ken_burns_effect(img_clip, clip_duration)
                        
                        clips.append(img_clip)
                        logger.info(f"✅ Added photo clip {i+1} with Ken Burns effect: {clip_duration:.1f}s")
                    
                    # MEMORY OPTIMIZATION: Clean up downloaded file immediately
                    try:
                        os.unlink(media_path)
                    except:
                        pass
                    
                    # MEMORY OPTIMIZATION: Force garbage collection after each clip
                    gc.collect()
                        
                except Exception as clip_error:
                    logger.warning(f"⚠️ Error processing clip {i+1}: {clip_error}")
                    # Clean up on error
                    try:
                        os.unlink(media_path)
                    except:
                        pass
                    continue
            
            # Step 4: Prepend NYT image clip if available
            if nyt_clip:
                clips.insert(0, nyt_clip)
                logger.info(f"✅ NYT article image INSERTED as clip #1 (total clips: {len(clips)})")
            else:
                logger.warning("⚠️ No NYT clip to insert - starting with stock footage only")
            
            if not clips:
                logger.error("❌ No clips created successfully")
                return None
            
            # Step 5: Concatenate all clips (NYT image first, then stock footage)
            logger.info(f"🎬 Concatenating {len(clips)} clips...")
            logger.info(f"   Clip order: {'NYT image → ' if nyt_clip else ''}stock footage ({len(clips) - (1 if nyt_clip else 0)} clips)")
            final_video = concatenate_videoclips(clips, method="compose", transition=None)
            
            # Step 6: Add headline text overlay THROUGHOUT the entire video
            logger.info("📝 Adding headline text overlay throughout video...")
            final_video = self._add_continuous_text_overlay(final_video, headline, commentary)
            
            # Step 6b: Add professional news anchor overlay (top right corner)
            logger.info("👩‍💼 Adding professional news anchor overlay...")
            try:
                final_video, anchor_name = self.anchor_system.add_to_video_clip(final_video, headline_height=180)
                logger.info(f"✅ Added anchor: {anchor_name} - Senior News Reporter, Forexyy Newsroom")
            except Exception as anchor_error:
                logger.warning(f"⚠️ Could not add anchor overlay: {anchor_error}")
            
            # Step 7: Add voice narration and synced captions
            if voice_audio_path and os.path.exists(voice_audio_path):
                try:
                    logger.info(f"🎤 Adding voice narration...")
                    audio = AudioFileClip(voice_audio_path)
                    
                    # Adjust video duration to match audio
                    if audio.duration > final_video.duration:
                        logger.info(f"📏 Extending video to {audio.duration:.1f}s to match narration")
                        final_video = final_video.set_duration(audio.duration)
                    elif audio.duration < final_video.duration:
                        # Trim video to match audio
                        final_video = final_video.subclip(0, audio.duration)
                    
                    final_video = final_video.set_audio(audio)
                    logger.info(f"✅ Added voice narration ({audio.duration:.1f}s)")
                    
                    # Step 7b: Add synced captions (transcribe audio and add word-by-word)
                    logger.info("📝 Generating synced captions from audio...")
                    logger.info(f"   Video before captions: duration={final_video.duration}s, size={final_video.size}")
                    final_video = self._add_synced_captions(final_video, voice_audio_path, commentary)
                    logger.info(f"   Video after captions: duration={final_video.duration}s")
                    
                except Exception as audio_error:
                    logger.warning(f"⚠️ Could not add voice narration: {audio_error}")
            
            # Step 8: Export final video
            logger.info("💾 Exporting animated reel...")
            temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_video.close()
            
            # MAXIMUM QUALITY SETTINGS for best output
            # preset='medium' = balanced speed/quality (slower but much better quality)
            # bitrate='4500k' = high quality for Instagram/YouTube Shorts
            # threads=8 = use more CPU cores for parallel encoding
            # Note: Export takes ~8-12 minutes but produces professional quality
            final_video.write_videofile(
                temp_video.name,
                fps=30,
                codec='libx264',
                audio_codec='aac' if hasattr(final_video, 'audio') and final_video.audio else None,
                logger='bar',  # Show progress bar to prevent timeout
                preset='medium',  # Better quality (was 'veryfast')
                bitrate='4500k',  # Higher bitrate for maximum quality (was 3000k)
                threads=8,  # Use more threads for faster encoding
                ffmpeg_params=['-movflags', '+faststart', '-crf', '20']  # Optimize for streaming + quality
            )
            
            # MEMORY OPTIMIZATION: Clean up clips immediately after export
            for clip in clips:
                try:
                    clip.close()
                    del clip
                except:
                    pass
            clips = []  # Clear list
            
            try:
                final_video.close()
                del final_video
            except:
                pass
            
            # MEMORY OPTIMIZATION: Force garbage collection
            gc.collect()
            
            file_size_mb = os.path.getsize(temp_video.name) / (1024 * 1024)
            logger.info(f"✅ Created animated reel: {file_size_mb:.2f} MB")
            
            # If file is too large (>14 MB), compress it further for CockroachDB
            if file_size_mb > 14:
                logger.info(f"📦 Compressing video (current: {file_size_mb:.2f} MB, target: <14 MB)...")
                compressed_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                compressed_video.close()
                
                try:
                    # Use ffmpeg for quality-preserving compression
                    import subprocess
                    result = subprocess.run([
                        'ffmpeg', '-i', temp_video.name,
                        '-c:v', 'libx264',
                        '-preset', 'fast',  # Better quality compression
                        '-crf', '23',  # High quality (lower = better, 18-28 range)
                        '-c:a', 'aac',
                        '-b:a', '128k',  # Audio bitrate
                        '-movflags', '+faststart',  # Streaming optimization
                        '-y',  # Overwrite
                        compressed_video.name
                    ], check=True, capture_output=True, text=True)
                    
                    compressed_size_mb = os.path.getsize(compressed_video.name) / (1024 * 1024)
                    logger.info(f"✅ Compressed: {file_size_mb:.2f} MB → {compressed_size_mb:.2f} MB")
                    
                    # Remove original, use compressed
                    os.unlink(temp_video.name)
                    return compressed_video.name
                    
                except subprocess.CalledProcessError as e:
                    logger.warning(f"⚠️ Compression failed: {e.stderr}")
                    logger.warning(f"⚠️ Using original video ({file_size_mb:.2f} MB) - may be too large for CockroachDB")
                    # Clean up failed compression attempt
                    try:
                        os.unlink(compressed_video.name)
                    except:
                        pass
                    # Return original video even though it's large
                    return temp_video.name
            
            return temp_video.name
            
        except Exception as e:
            logger.error(f"❌ Failed to create animated reel: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _resize_to_portrait(self, clip, target_width=1080, target_height=1920):
        """Resize clip to portrait 9:16 ratio with proper cropping/padding"""
        try:
            from moviepy import VideoFileClip, ImageClip
        except ImportError:
            from moviepy.editor import VideoFileClip, ImageClip
        
        w, h = clip.size
        target_ratio = target_width / target_height
        current_ratio = w / h
        
        if current_ratio > target_ratio:
            # Video is wider, crop width
            new_width = int(h * target_ratio)
            x_center = w // 2
            x1 = x_center - new_width // 2
            clip = clip.crop(x1=x1, width=new_width)
        else:
            # Video is taller, crop height
            new_height = int(w / target_ratio)
            y_center = h // 2
            y1 = y_center - new_height // 2
            clip = clip.crop(y1=y1, height=new_height)
        
        # Resize to target resolution
        clip = clip.resize((target_width, target_height))
        
        return clip
    
    def _add_ken_burns_effect(self, clip, duration):
        """Add zoom and pan effect to image clip (Ken Burns effect)"""
        try:
            def zoom_in(get_frame, t):
                """Zoom in gradually over time"""
                frame = get_frame(t)
                zoom_factor = 1 + (t / duration) * 0.2  # Zoom from 1x to 1.2x
                h, w = frame.shape[:2]
                
                # Calculate crop dimensions
                new_h = int(h / zoom_factor)
                new_w = int(w / zoom_factor)
                
                # Center crop
                y1 = (h - new_h) // 2
                x1 = (w - new_w) // 2
                
                # Crop and resize back
                cropped = frame[y1:y1+new_h, x1:x1+new_w]
                
                import cv2
                resized = cv2.resize(cropped, (w, h))
                
                return resized
            
            clip = clip.transform(zoom_in)
            return clip
            
        except Exception as e:
            logger.warning(f"⚠️ Could not add Ken Burns effect: {e}")
            return clip
    
    def _add_headline_overlay(self, video_clip, headline, duration=3):
        """Add headline text overlay at the beginning of the video"""
        try:
            try:
                from moviepy import TextClip, CompositeVideoClip
            except ImportError:
                from moviepy.editor import TextClip, CompositeVideoClip
            
            # Create text clip
            txt_clip = TextClip(
                text=headline,
                font='Arial-Bold',
                font_size=60,
                color='white',
                text_align='center',
                size=(1000, None),  # Wrap text at 1000px width
                method='caption',
                stroke_color='black',
                stroke_width=2
            )
            
            # Position at bottom third of screen
            txt_clip = txt_clip.set_position(('center', 1400))
            
            # Show for first 3 seconds with fade out
            txt_clip = txt_clip.set_duration(duration).fadeout(0.5)
            
            # Composite text over video
            video_with_text = CompositeVideoClip([video_clip, txt_clip])
            
            logger.info("✅ Added headline overlay")
            return video_with_text
            
        except Exception as e:
            logger.warning(f"⚠️ Could not add headline overlay: {e}")
            return video_clip
    
    def _add_continuous_text_overlay(self, video_clip, headline: str, commentary: str, duration: Optional[float] = None):
        """
        Add text overlay using PIL (more reliable than TextClip)
        Large, bold headline at top with readable size
        
        Args:
            video_clip: Video to add text to
            headline: Article headline (shown at top)
            commentary: AI commentary (not shown - will use captions instead)
            duration: Duration for text (None = full video duration)
            
        Returns:
            Video with text overlay
        """
        try:
            try:
                from moviepy import ImageClip, CompositeVideoClip
            except:
                from moviepy.editor import ImageClip, CompositeVideoClip
            
            from PIL import Image, ImageDraw, ImageFont
            import textwrap
            import numpy as np
            
            if duration is None:
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
            
        except Exception as e:
            logger.warning(f"⚠️ Could not add text overlay: {e}")
            return video_clip
    
    def _add_synced_captions(self, video_clip, audio_path: str, commentary_text: str):
        """
        Add word-by-word captions synced with audio using PIL (more reliable)
        Creates TikTok/Instagram-style captions that appear word by word at center of screen
        
        Args:
            video_clip: Video to add captions to
            audio_path: Path to audio file for transcription
            commentary_text: Fallback text if transcription fails
            
        Returns:
            Video with synced captions
        """
        try:
            try:
                from moviepy import ImageClip, CompositeVideoClip
            except:
                from moviepy.editor import ImageClip, CompositeVideoClip
            from groq import Groq
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
            import os
            
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
            
            logger.info(f"🎤 Transcription response type: {type(transcription)}")
            logger.info(f"🎤 Has 'words' attribute: {hasattr(transcription, 'words')}")
            if hasattr(transcription, 'words'):
                logger.info(f"🎤 Words count: {len(transcription.words) if transcription.words else 0}")
            
            # Parse word timestamps from response
            words_data = []
            if hasattr(transcription, 'words') and transcription.words:
                # Groq API returns list of dictionaries
                logger.info(f"   First word object type: {type(transcription.words[0])}")
                logger.info(f"   First word object: {transcription.words[0]}")
                
                for word_dict in transcription.words:
                    # Word objects are already dictionaries
                    if isinstance(word_dict, dict):
                        words_data.append({
                            'word': word_dict.get('word', ''),
                            'start': word_dict.get('start', 0),
                            'end': word_dict.get('end', 0)
                        })
                    else:
                        # Fallback for object format
                        words_data.append({
                            'word': word_dict.word if hasattr(word_dict, 'word') else str(word_dict),
                            'start': word_dict.start if hasattr(word_dict, 'start') else 0,
                            'end': word_dict.end if hasattr(word_dict, 'end') else 0
                        })
            elif isinstance(transcription, dict) and 'words' in transcription:
                # Dictionary format
                words_data = transcription['words']
            else:
                logger.warning("⚠️ No word timestamps available, using sentence captions")
                return self._add_sentence_captions(video_clip, commentary_text)
            
            if not words_data:
                logger.warning("⚠️ No words found in transcription")
                return self._add_sentence_captions(video_clip, commentary_text)
            
            logger.info(f"✅ Transcribed {len(words_data)} words with timestamps")
            if words_data:
                logger.info(f"   Sample first word: {words_data[0]}")
            
            # Get video dimensions
            video_width, video_height = video_clip.size
            logger.info(f"📐 Video dimensions: {video_width}x{video_height}")
            
            # Load font for captions (smaller size for multi-word captions)
            try:
                caption_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 50)
            except:
                try:
                    caption_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 50)
                except:
                    caption_font = ImageFont.load_default()
            
            # Group words into chunks of 4-5 words for better readability
            words_per_caption = 5
            caption_clips = []
            logger.info(f"🎨 Creating caption clips (grouping {words_per_caption} words at a time)...")
            caption_count = 0
            
            i = 0
            while i < len(words_data):
                # Get chunk of 4-5 words
                chunk_end = min(i + words_per_caption, len(words_data))
                word_chunk = words_data[i:chunk_end]
                
                if not word_chunk:
                    break
                
                # Combine words into one caption
                caption_text = ' '.join([w.get('word', '').strip() for w in word_chunk])
                start_time = float(word_chunk[0].get('start', 0))
                end_time = float(word_chunk[-1].get('end', 0))
                duration = max(0.5, end_time - start_time)  # Minimum 0.5s duration
                
                if not caption_text or duration <= 0:
                    i += words_per_caption
                    continue
                
                try:
                    # Create caption image with PIL
                    caption_upper = caption_text.upper()
                    
                    # Create temporary image to measure text size
                    temp_img = Image.new('RGBA', (video_width, 200), (0, 0, 0, 0))
                    temp_draw = ImageDraw.Draw(temp_img)
                    bbox = temp_draw.textbbox((0, 0), caption_upper, font=caption_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    # Ensure caption fits within video width (leave 40px margin on each side)
                    max_caption_width = video_width - 80  # 40px margin on each side
                    actual_caption_width = min(text_width + 40, max_caption_width)
                    
                    # Create final caption image with smaller padding
                    caption_img = Image.new('RGBA', (actual_caption_width, text_height + 30), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(caption_img)
                    
                    # Add semi-transparent background
                    draw.rectangle([0, 0, actual_caption_width, text_height + 30], fill=(0, 0, 0, 200))
                    
                    # Draw text with black outline for readability (smaller outline)
                    text_x = 20
                    text_y = 15
                    outline_width = 3
                    for adj_x in range(-outline_width, outline_width + 1):
                        for adj_y in range(-outline_width, outline_width + 1):
                            draw.text((text_x + adj_x, text_y + adj_y), caption_upper, font=caption_font, fill='black')
                    
                    # Draw yellow text on top (high contrast, engaging)
                    draw.text((text_x, text_y), caption_upper, font=caption_font, fill='#FFD700')
                    
                    # Convert PIL image to numpy array
                    caption_array = np.array(caption_img)
                    
                    # Create ImageClip
                    caption_clip = ImageClip(caption_array, duration=duration)
                    
                    # Position at CENTER of screen with safe margins
                    # Ensure caption doesn't go beyond video boundaries
                    x_position = (video_width - caption_img.width) // 2
                    
                    # Position in lower third but with margin from bottom (safe area for reels)
                    # Video height is 1920, so position at around 1300-1400 (lower third)
                    # Leave 200px margin from bottom to avoid cutoff
                    max_y = video_height - caption_img.height - 200  # 200px from bottom
                    y_position = min((video_height // 2) + 300, max_y)  # Lower third, but safe
                    
                    caption_clip = caption_clip.set_position((x_position, y_position))
                    caption_clip = caption_clip.set_start(start_time)
                    
                    caption_clips.append(caption_clip)
                    caption_count += 1
                    
                    # Log progress every 5 caption groups
                    if caption_count % 5 == 0:
                        logger.info(f"   Created {caption_count} caption clips...")
                    
                except Exception as e:
                    logger.debug(f"Skipped caption chunk: {e}")
                
                # Move to next chunk
                i += words_per_caption
            
            logger.info(f"🎨 Total caption clips created: {len(caption_clips)}")
            
            if not caption_clips:
                logger.warning("⚠️ No caption clips created")
                return video_clip
            
            # Composite all captions onto video
            logger.info(f"🎬 Compositing video: base + {len(caption_clips)} captions")
            logger.info(f"   Base video duration: {video_clip.duration}s")
            
            video_with_captions = CompositeVideoClip([video_clip] + caption_clips)
            
            logger.info(f"✅ Composite complete! Final duration: {video_with_captions.duration}s")
            
            return video_with_captions
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Caption generation failed: {e}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            # Fallback to sentence-based captions
            return self._add_sentence_captions(video_clip, commentary_text)
    
    def _add_sentence_captions(self, video_clip, text: str):
        """
        Fallback: Add sentence-based captions if word-level timing fails
        """
        try:
            try:
                from moviepy import TextClip, CompositeVideoClip
            except:
                from moviepy.editor import TextClip, CompositeVideoClip
            import textwrap
            
            # Split into sentences
            sentences = text.replace('!', '.').replace('?', '.').split('.')
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if not sentences:
                return video_clip
            
            duration_per_sentence = video_clip.duration / len(sentences)
            caption_clips = []
            
            for i, sentence in enumerate(sentences):
                wrapped = textwrap.fill(sentence, width=40)
                start_time = i * duration_per_sentence
                
                try:
                    caption_clip = TextClip(
                        text=wrapped,
                        font='Helvetica-Bold',
                        font_size=50,
                        color='yellow',
                        stroke_color='black',
                        stroke_width=3,
                        text_align='center',
                        size=(950, None),
                        method='caption'
                    )
                    caption_clip = caption_clip.set_position(('center', 1600))
                    caption_clip = caption_clip.set_start(start_time).set_duration(duration_per_sentence)
                    caption_clips.append(caption_clip)
                except:
                    continue
            
            if caption_clips:
                logger.info(f"✅ Added {len(caption_clips)} sentence captions")
                return CompositeVideoClip([video_clip] + caption_clips)
            
            return video_clip
            
        except Exception as e:
            logger.warning(f"⚠️ Could not add sentence captions: {e}")
            return video_clip

if __name__ == "__main__":
    # Test animated reel creation
    logging.basicConfig(level=logging.INFO)
    
    creator = AnimatedReelCreator()
    
    # Test with sample data
    headline = "Trump Announces New Technology Policy"
    commentary = "In a surprising move, the president announced sweeping changes to technology regulation that could reshape the industry."
    
    video_path = creator.create_animated_reel(
        headline=headline,
        commentary=commentary,
        target_duration=15,
        clips_count=3
    )
    
    if video_path:
        print(f"\n✅ Created animated reel: {video_path}")
    else:
        print("\n❌ Failed to create animated reel")
