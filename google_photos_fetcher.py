"""
Google Custom Search API Integration
Fetches images from across the web using Google Custom Search (Image Search)
"""

import os
import requests
import tempfile
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

logger = logging.getLogger(__name__)

# Google Custom Search API
GOOGLE_API_KEY = os.getenv('GOOGLE_CUSTOM_SEARCH_API_KEY', '')
GOOGLE_SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID', '')
GOOGLE_CUSTOM_SEARCH_API = "https://www.googleapis.com/customsearch/v1"

class GoogleImageSearchFetcher:
    """Fetch images from web using Google Custom Search API"""
    
    def __init__(self):
        """Initialize Google Custom Search fetcher"""
        self.api_key = GOOGLE_API_KEY
        self.search_engine_id = GOOGLE_SEARCH_ENGINE_ID
        
        if not self.api_key:
            logger.warning("⚠️ Google Custom Search API key not set - image search disabled")
            logger.info("Get a free API key at: https://developers.google.com/custom-search/v1/overview")
        
        if not self.search_engine_id:
            logger.warning("⚠️ Google Search Engine ID not set - using default image search")
            # Use a generic search engine ID that searches images (you need to create one)
            logger.info("Create Search Engine at: https://programmablesearchengine.google.com/")
    
    def search_photos(self, query: str, per_page: int = 5, orientation: str = 'portrait') -> List[Dict]:
        """
        Search for images using Google Custom Search API
        
        Args:
            query: Search query
            per_page: Number of results (max 10 per request on free tier)
            orientation: Photo orientation preference (portrait, landscape, square)
            
        Returns:
            List of photo dictionaries with URLs
        """
        try:
            if not self.api_key:
                logger.warning("⚠️ No Google API key - skipping Google Image search")
                return []
            
            logger.info(f"� Searching Google Images for: '{query}'")
            
            # Prepare search parameters
            params = {
                'key': self.api_key,
                'cx': self.search_engine_id or '017576662512468239146:omuauf_lfve',  # Generic image search
                'q': query,
                'searchType': 'image',
                'num': min(per_page, 10),  # Max 10 per request
                'imgSize': 'large',  # large, medium, or small
                'safe': 'active',  # Safe search
                'fileType': 'jpg,png',
                'rights': 'cc_publicdomain,cc_attribute,cc_sharealike'  # Try to get reusable images
            }
            
            # Add orientation filter if specified
            if orientation == 'portrait':
                params['imgType'] = 'photo'
                # Note: Custom Search doesn't have direct portrait/landscape filter
                # We'll filter by aspect ratio after fetching
            
            response = requests.get(
                GOOGLE_CUSTOM_SEARCH_API,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Google Custom Search API error: {response.status_code}")
                if response.status_code == 403:
                    logger.error("API key invalid or quota exceeded")
                    logger.error(f"Response: {response.text[:200]}")
                return []
            
            data = response.json()
            items = data.get('items', [])
            
            if not items:
                logger.warning(f"⚠️ No images found on Google for: '{query}'")
                return []
            
            logger.info(f"✅ Found {len(items)} images from Google")
            
            # Extract photo URLs and metadata
            photo_list = []
            for item in items:
                # Get image metadata
                image_meta = item.get('image', {})
                width = image_meta.get('width', 0)
                height = image_meta.get('height', 0)
                
                # Filter by orientation if needed
                if orientation == 'portrait' and width >= height:
                    continue  # Skip landscape images when looking for portrait
                elif orientation == 'landscape' and height >= width:
                    continue  # Skip portrait when looking for landscape
                
                photo_list.append({
                    'id': item.get('link', '').split('/')[-1],  # Use filename as ID
                    'url': item.get('link'),  # Direct image URL
                    'original': item.get('link'),
                    'thumb': image_meta.get('thumbnailLink'),
                    'width': width,
                    'height': height,
                    'title': item.get('title', ''),
                    'source_page': item.get('image', {}).get('contextLink', ''),
                    'source': 'google_images',
                    'mime_type': item.get('mime', 'image/jpeg')
                })
            
            logger.info(f"✅ Filtered to {len(photo_list)} {orientation} images")
            return photo_list
            
        except Exception as e:
            logger.error(f"❌ Error searching Google Images: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def download_photo(self, url: str) -> Optional[str]:
        """
        Download photo from URL
        
        Args:
            url: Photo URL
            
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            logger.info(f"📥 Downloading image from Google search...")
            
            # Add headers to avoid bot detection
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://www.google.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            
            if response.status_code != 200:
                logger.error(f"❌ Download failed: {response.status_code}")
                return None
            
            # Detect file extension from content-type
            content_type = response.headers.get('Content-Type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                ext = '.jpg'  # Default
            
            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            
            # Download in chunks
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            
            temp_file.close()
            
            file_size_mb = os.path.getsize(temp_file.name) / (1024 * 1024)
            logger.info(f"✅ Downloaded image: {file_size_mb:.2f} MB")
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"❌ Error downloading image: {e}")
            return None

if __name__ == "__main__":
    # Test Google Custom Search API
    logging.basicConfig(level=logging.INFO)
    
    fetcher = GoogleImageSearchFetcher()
    
    if not fetcher.api_key:
        print("\n⚠️ Setup Required:")
        print("1. Get a free API key: https://developers.google.com/custom-search/v1/overview")
        print("2. Create a Search Engine: https://programmablesearchengine.google.com/")
        print("3. Add to .env:")
        print("   GOOGLE_CUSTOM_SEARCH_API_KEY=your_key_here")
        print("   GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id")
    else:
        # Test photo search
        photos = fetcher.search_photos("business technology", per_page=5, orientation='portrait')
        
        if photos:
            print(f"\n✅ Found {len(photos)} images:")
            for i, photo in enumerate(photos, 1):
                print(f"\n{i}. {photo['title'][:50]}...")
                print(f"   Size: {photo['width']}x{photo['height']}")
                print(f"   URL: {photo['url'][:80]}...")
            
            # Test download
            if photos:
                print(f"\n📥 Testing download...")
                path = fetcher.download_photo(photos[0]['url'])
                if path:
                    print(f"✅ Downloaded to: {path}")
        else:
            print("\n❌ No images found")
