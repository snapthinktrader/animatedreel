"""
Professional News Anchor Overlay System
Adds a news anchor presentation to animated reels
"""

import os
import random
from PIL import Image, ImageDraw, ImageFont
try:
    from moviepy.editor import ImageClip, CompositeVideoClip
except ImportError:
    from moviepy import ImageClip, CompositeVideoClip
import numpy as np

# US-based female news anchor names
FEMALE_ANCHOR_NAMES = [
    "Sarah Mitchell",
    "Jessica Thompson", 
    "Emily Rodriguez",
    "Rachel Anderson",
    "Amanda Williams",
    "Lauren Davis",
    "Michelle Carter",
    "Jennifer Martinez",
    "Ashley Taylor",
    "Samantha Brooks",
    "Nicole Patterson",
    "Christina Hayes",
    "Melissa Cooper",
    "Rebecca Morgan",
    "Stephanie Collins"
]

class AnchorOverlaySystem:
    """Creates professional news anchor overlays for reels"""
    
    def __init__(self):
        self.anchor_image_path = "/Users/mahendrabahubali/Desktop/QPost/WhatsApp Image 2025-10-25 at 07.04.58.jpeg"
        self.used_names = set()
        
    def get_unique_anchor_name(self):
        """Get a unique US-based female anchor name"""
        # Fixed anchor name
        return "Rachel Anderson"
    
    def create_voice_speaker_icon(self, size=40):
        """Create an animated voice/speaker icon"""
        icon = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon)
        
        # Draw speaker icon
        # Speaker cone
        draw.polygon([
            (5, size//3),
            (5, 2*size//3),
            (size//3, 2*size//3),
            (size//2, size-5),
            (size//2, 5),
            (size//3, size//3)
        ], fill='white', outline='white')
        
        # Sound waves
        for i in range(3):
            offset = size//2 + 10 + (i * 8)
            wave_size = 8 + (i * 4)
            draw.arc([offset, size//2 - wave_size//2, offset + wave_size, size//2 + wave_size//2], 
                    -60, 60, fill='white', width=3)
        
        return icon
    
    def create_anchor_overlay(self, video_width=1080, video_height=1920, headline_height=180):
        """
        Create the anchor overlay composite image
        
        Args:
            video_width: Width of the video (default 1080)
            video_height: Height of the video (default 1920)
            headline_height: Height of headline area to match (default 180)
        
        Returns:
            PIL Image with anchor overlay
        """
        # Get unique anchor name
        anchor_name = self.get_unique_anchor_name()
        
        # Create transparent overlay (increased size)
        overlay_width = 550  # Increased from 450
        overlay_height = headline_height + 60  # Increased from +20
        overlay = Image.new('RGBA', (overlay_width, overlay_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Load and process anchor image
        try:
            anchor_img = Image.open(self.anchor_image_path).convert('RGBA')
            
            # Resize anchor to fit height (keep aspect ratio)
            anchor_height = headline_height - 20  # Increased from -40 for larger photo
            aspect_ratio = anchor_img.width / anchor_img.height
            anchor_width = int(anchor_height * aspect_ratio)
            anchor_img = anchor_img.resize((anchor_width, anchor_height), Image.Resampling.LANCZOS)
            
            # Make circular/rounded
            mask = Image.new('L', (anchor_width, anchor_height), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, anchor_width, anchor_height], fill=255)
            
            # Create circular anchor image
            circular_anchor = Image.new('RGBA', (anchor_width, anchor_height), (0, 0, 0, 0))
            circular_anchor.paste(anchor_img, (0, 0))
            circular_anchor.putalpha(mask)
            
            # Add white border around anchor
            border_img = Image.new('RGBA', (anchor_width + 8, anchor_height + 8), (255, 255, 255, 255))
            border_mask = Image.new('L', (anchor_width + 8, anchor_height + 8), 0)
            border_draw = ImageDraw.Draw(border_mask)
            border_draw.ellipse([0, 0, anchor_width + 8, anchor_height + 8], fill=255)
            border_img.putalpha(border_mask)
            
            # Composite anchor on the right side
            anchor_x = overlay_width - anchor_width - 30
            anchor_y = 20
            overlay.paste(border_img, (anchor_x - 4, anchor_y - 4), border_img)
            overlay.paste(circular_anchor, (anchor_x, anchor_y), circular_anchor)
            
        except Exception as e:
            print(f"⚠️  Could not load anchor image: {e}")
            # Continue without anchor photo
            anchor_x = overlay_width - 100
            anchor_y = 20
        
        # Create semi-transparent background for text
        text_bg = Image.new('RGBA', (overlay_width - anchor_width - 80, overlay_height), (0, 0, 0, 180))
        overlay.paste(text_bg, (20, 0), text_bg)
        
        # Add text elements
        try:
            # Try to use a nice font (increased sizes)
            title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 38)  # Increased from 32
            subtitle_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26)  # Increased from 22
            org_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)  # Increased from 20
        except:
            # Fallback to default
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
            org_font = ImageFont.load_default()
        
        # Draw anchor name
        draw.text((35, 30), anchor_name, font=title_font, fill='white')
        
        # Draw title
        draw.text((35, 75), "Senior News Reporter", font=subtitle_font, fill='#FFD700')  # Gold color
        
        # Draw organization
        draw.text((35, 110), "Forexyy Newsroom", font=org_font, fill='#CCCCCC')
        
        # Add voice speaker icon (larger)
        speaker_icon = self.create_voice_speaker_icon(size=42)  # Increased from 35
        overlay.paste(speaker_icon, (35, 150), speaker_icon)  # Adjusted position
        
        # Add "LIVE" indicator (larger)
        draw.rectangle([85, 155, 145, 178], fill='#FF0000')  # Increased size
        try:
            live_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)  # Increased from 16
        except:
            live_font = ImageFont.load_default()
        draw.text((92, 157), "LIVE", font=live_font, fill='white')  # Adjusted position
        
        return overlay, anchor_name
    
    def add_to_video_clip(self, video_clip, headline_height=180):
        """
        Add anchor overlay to a video clip
        
        Args:
            video_clip: MoviePy VideoClip
            headline_height: Height to match with headline (default 180)
        
        Returns:
            VideoClip with anchor overlay
        """
        # Get video dimensions
        video_width, video_height = video_clip.size
        
        # Create overlay image
        overlay_img, anchor_name = self.create_anchor_overlay(
            video_width=video_width,
            video_height=video_height,
            headline_height=headline_height
        )
        
        # Convert PIL image to numpy array
        overlay_array = np.array(overlay_img)
        
        # Create ImageClip from overlay
        overlay_clip = ImageClip(overlay_array, duration=video_clip.duration)
        
        # Position on LEFT SIDE, BELOW headline (y = headline_height + 20)
        x_position = 20  # Left side with 20px margin
        y_position = headline_height + 20  # Below headline
        
        overlay_clip = overlay_clip.with_position((x_position, y_position))
        
        # Composite video with overlay
        final_clip = CompositeVideoClip([video_clip, overlay_clip])
        
        print(f"✅ Added anchor overlay: {anchor_name}")
        
        return final_clip, anchor_name


# Test function
if __name__ == "__main__":
    print("🎬 Testing Anchor Overlay System")
    
    anchor_system = AnchorOverlaySystem()
    
    # Test 1: Generate unique names
    print("\n📝 Testing unique name generation:")
    for i in range(5):
        name = anchor_system.get_unique_anchor_name()
        print(f"   {i+1}. {name}")
    
    # Test 2: Create overlay image
    print("\n🎨 Creating anchor overlay image...")
    try:
        overlay_img, anchor_name = anchor_system.create_anchor_overlay()
        print(f"✅ Created overlay for: {anchor_name}")
        print(f"   Size: {overlay_img.size}")
        
        # Save test image
        test_path = "/Users/mahendrabahubali/Desktop/test_anchor_overlay.png"
        overlay_img.save(test_path)
        print(f"💾 Saved test overlay to: {test_path}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
