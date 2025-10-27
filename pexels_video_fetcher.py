"""
Pexels API Integration for Animated Reels
Fetches relevant videos/photos based on headline and creates dynamic presentation-style reels
Uses CockroachDB buffer to avoid storing large files on Render
"""

import os
import requests
import tempfile
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
from groq import Groq
from cockroach_buffer import CockroachBufferStorage

# Load environment variables from parent directory
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv('PEXEL', '')
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

class PexelsMediaFetcher:
    """Fetch videos and photos from Pexels API"""
    
    def __init__(self):
        """Initialize Pexels fetcher with API key and buffer storage"""
        self.api_key = PEXELS_API_KEY
        self.groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        self.buffer = CockroachBufferStorage()  # Initialize buffer storage
        
        # Set up headers for API requests
        self.headers = {
            'Authorization': self.api_key
        }
        
        if not self.api_key:
            logger.warning("⚠️ PEXEL API key not found in environment variables")
        
        if not os.getenv('GROQ_API_KEY'):
            logger.warning("⚠️ GROQ_API_KEY not found in environment variables")
    
    def search_videos(self, query: str, per_page: int = 5, orientation: str = 'portrait') -> List[Dict]:
        """
        Search for videos on Pexels
        
        Args:
            query: Search query (e.g., "business meeting", "technology")
            per_page: Number of results to return
            orientation: Video orientation (portrait, landscape, square)
            
        Returns:
            List of video dictionaries with download URLs
        """
        try:
            logger.info(f"🔍 Searching Pexels for videos: '{query}'")
            
            params = {
                'query': query,
                'per_page': per_page,
                'orientation': orientation,
                'size': 'medium'  # medium quality for faster downloads
            }
            
            response = requests.get(
                PEXELS_VIDEO_API,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Pexels API error: {response.status_code}")
                logger.error(f"Response: {response.text[:200]}")
                logger.error(f"Headers sent: {self.headers}")
                return []
            
            data = response.json()
            videos = data.get('videos', [])
            
            if not videos:
                logger.warning(f"⚠️ No videos found for query: '{query}'")
                return []
            
            logger.info(f"✅ Found {len(videos)} videos on Pexels")
            
            # Extract relevant video info
            video_list = []
            for video in videos:
                video_files = video.get('video_files', [])
                
                # MEMORY OPTIMIZATION: Prefer SMALLER video files for 512 MB RAM
                # Sort by file size (prefer SD quality over HD/4K)
                video_files_sorted = sorted(
                    video_files,
                    key=lambda vf: (
                        abs((vf.get('width', 0) / max(vf.get('height', 1), 1)) - 0.5625),  # Prefer 9:16 ratio
                        vf.get('width', 9999) * vf.get('height', 9999)  # Prefer smaller resolution
                    )
                )
                
                # Find portrait/vertical video (9:16 ratio preferred for reels)
                portrait_video = None
                for vf in video_files_sorted:
                    width = vf.get('width', 0)
                    height = vf.get('height', 1)
                    # Prefer SD or low-HD (smaller files)
                    if width < vf.get('height', 1) and width <= 720:  # Max 720p width
                        portrait_video = vf
                        break
                
                # Fallback to smallest available video
                if not portrait_video and video_files_sorted:
                    portrait_video = video_files_sorted[0]
                
                if portrait_video:
                    video_list.append({
                        'id': video.get('id'),
                        'url': portrait_video.get('link'),
                        'width': portrait_video.get('width'),
                        'height': portrait_video.get('height'),
                        'duration': video.get('duration', 10),
                        'thumbnail': video.get('image'),
                        'quality': portrait_video.get('quality')
                    })
            
            return video_list
            
        except Exception as e:
            logger.error(f"❌ Error searching Pexels videos: {e}")
            return []
    
    def search_photos(self, query: str, per_page: int = 5, orientation: str = 'portrait') -> List[Dict]:
        """
        Search for photos on Pexels
        
        Args:
            query: Search query
            per_page: Number of results
            orientation: Photo orientation (portrait, landscape, square)
            
        Returns:
            List of photo dictionaries with URLs
        """
        try:
            logger.info(f"🔍 Searching Pexels for photos: '{query}'")
            
            params = {
                'query': query,
                'per_page': per_page,
                'orientation': orientation
            }
            
            response = requests.get(
                PEXELS_PHOTO_API,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Pexels API error: {response.status_code}")
                return []
            
            data = response.json()
            photos = data.get('photos', [])
            
            if not photos:
                logger.warning(f"⚠️ No photos found for query: '{query}'")
                return []
            
            logger.info(f"✅ Found {len(photos)} photos on Pexels")
            
            # Extract photo URLs
            photo_list = []
            for photo in photos:
                photo_list.append({
                    'id': photo.get('id'),
                    'url': photo['src'].get('large2x'),  # High quality
                    'original': photo['src'].get('original'),
                    'medium': photo['src'].get('large'),
                    'photographer': photo.get('photographer'),
                    'width': photo.get('width'),
                    'height': photo.get('height')
                })
            
            return photo_list
            
        except Exception as e:
            logger.error(f"❌ Error searching Pexels photos: {e}")
            return []
    
    def download_media(self, url: str, media_type: str = 'video', session_id: str = None) -> Optional[str]:
        """
        Download video or photo from Pexels and store in CockroachDB buffer
        
        Args:
            url: Media URL
            media_type: 'video' or 'photo'
            session_id: Session ID for grouping clips
            
        Returns:
            Clip ID (UUID) from buffer storage, or None if failed
        """
        try:
            logger.info(f"📥 Downloading {media_type} from Pexels...")
            
            response = requests.get(url, timeout=30, stream=True)
            
            if response.status_code != 200:
                logger.error(f"❌ Download failed: {response.status_code}")
                return None
            
            # Check file size before downloading
            content_length = response.headers.get('content-length')
            if content_length:
                size_mb = int(content_length) / (1024 * 1024)
                logger.info(f"📊 File size: {size_mb:.2f} MB")
            
            # Save to temp file first
            suffix = '.mp4' if media_type == 'video' else '.jpg'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            
            # Download in chunks
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
                    downloaded += len(chunk)
            
            temp_file.close()
            
            file_size_mb = os.path.getsize(temp_file.name) / (1024 * 1024)
            logger.info(f"✅ Downloaded {media_type}: {file_size_mb:.2f} MB")
            
            # Store in CockroachDB buffer and delete local file
            clip_id = self.buffer.store_clip(temp_file.name, media_type, session_id or 'default')
            
            if clip_id:
                logger.info(f"💾 Clip stored in buffer (ID: {clip_id}), local file deleted")
                return clip_id
            else:
                logger.error(f"❌ Failed to store in buffer, deleting local file")
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
                return None
            
        except Exception as e:
            logger.error(f"❌ Error downloading media: {e}")
            return None
    
    def extract_search_keywords(self, headline: str, commentary: str) -> List[str]:
        """
        Use Groq AI to extract meaningful, contextual search terms from news article
        
        Args:
            headline: Article headline
            commentary: AI-generated commentary
            
        Returns:
            List of specific search terms optimized for finding relevant stock footage
        """
        try:
            # Initialize Groq client
            client = Groq(api_key=GROQ_API_KEY)
            
            # Create prompt for extracting visual search terms
            prompt = f"""You are a video editor searching for stock footage for a NEWS VIDEO REEL.

Given this news article:
Headline: {headline}
Commentary: {commentary}

Extract 5 SPECIFIC visual search terms for finding relevant NEWS-RELATED stock videos/photos.

CRITICAL RULES:
1. NEWS CONTEXT ONLY - avoid lifestyle, home, bedroom content
2. Be VISUALLY SPECIFIC (e.g., "construction workers building highway" not "infrastructure")
3. Focus on PUBLIC/PROFESSIONAL settings (e.g., "government building", "factory floor", "city street")
4. NO personal/domestic scenes (no bedrooms, homes, personal items)
5. Think NEWS B-ROLL: protests, conferences, construction sites, technology labs, government buildings

BAD examples (DO NOT USE):
- pillow, bedroom, home decor, kitchen
- person relaxing, lifestyle, wellness

GOOD examples:
- highway construction crane equipment
- government press conference podium
- stock market trading floor
- medical research laboratory
- renewable energy wind turbines

Article topic: {headline}

RESPOND WITH ONLY THE KEYWORDS - NO EXPLANATIONS, NO INTRODUCTION TEXT.
Format: keyword1, keyword2, keyword3, keyword4, keyword5"""

            # Call Groq API
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150
            )
            
            # Extract search terms
            search_terms_text = response.choices[0].message.content.strip()
            
            # Remove any intro text if model still adds it
            if ":" in search_terms_text and search_terms_text.index(":") < 50:
                search_terms_text = search_terms_text.split(":", 1)[-1].strip()
            
            # Remove newlines and split by commas
            search_terms_text = search_terms_text.replace('\n', ',').replace('  ', ' ')
            search_terms = [term.strip() for term in search_terms_text.split(',')]
            
            # Clean and validate - remove empty, too short, or intro phrases
            search_terms = [
                term for term in search_terms 
                if len(term) > 3 
                and not term.lower().startswith(('here', 'these', 'the following'))
                and len(term) < 60  # Reject overly long "sentences"
            ][:5]
            
            logger.info(f"🔑 AI-extracted search terms: {', '.join(search_terms)}")
            return search_terms
            
        except Exception as e:
            logger.warning(f"⚠️ Groq AI extraction failed: {e}, falling back to basic keywords")
            # Fallback to basic keyword extraction
            return self._basic_keyword_extraction(headline, commentary)
    
    def _basic_keyword_extraction(self, headline: str, commentary: str) -> List[str]:
        """
        Fallback: Basic keyword extraction if Groq AI fails
        """
        # Combine headline and commentary
        text = f"{headline} {commentary}".lower()
        
        # Remove common words and extract meaningful keywords
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these',
            'those', 'it', 'its', "it's", 'what', 'which', 'who', 'when', 'where',
            'why', 'how', 'about', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once'
        }
        
        # Split into words
        words = text.replace(',', ' ').replace('.', ' ').replace('!', ' ').replace('?', ' ').split()
        
        # Filter out common words and short words
        keywords = [w for w in words if w not in common_words and len(w) > 3]
        
        # Take top keywords (unique)
        unique_keywords = []
        for keyword in keywords:
            if keyword not in unique_keywords:
                unique_keywords.append(keyword)
            if len(unique_keywords) >= 5:  # Limit to top 5 keywords
                break
        
        # Fallback: use headline words if no good keywords found
        if not unique_keywords:
            unique_keywords = [w for w in headline.split()[:3] if len(w) > 3]
        
        logger.info(f"🔑 Basic keywords: {', '.join(unique_keywords)}")
        return unique_keywords

if __name__ == "__main__":
    # Test Pexels API
    fetcher = PexelsMediaFetcher()
    
    # Test video search
    videos = fetcher.search_videos("technology business", per_page=3)
    print(f"\n✅ Found {len(videos)} videos")
    for i, video in enumerate(videos, 1):
        print(f"{i}. {video['url']} ({video['width']}x{video['height']})")
    
    # Test photo search
    photos = fetcher.search_photos("business meeting", per_page=3)
    print(f"\n✅ Found {len(photos)} photos")
    for i, photo in enumerate(photos, 1):
        print(f"{i}. {photo['url']} ({photo['width']}x{photo['height']})")
