"""
Google Cloud Text-to-Speech voice generator
FREE alternative to ElevenLabs with good quality
"""

import os
import json
import tempfile
import logging
import requests
import base64

# Only import google.cloud if not using REST API
try:
    from google.cloud import texttospeech
    HAS_GOOGLE_CLOUD = True
except ImportError:
    HAS_GOOGLE_CLOUD = False

logger = logging.getLogger(__name__)

class GoogleTTSVoice:
    """Generate voice narration using Google Cloud TTS"""
    
    def __init__(self):
        """Initialize Google TTS client"""
        self.client = None
        self.api_key = os.getenv('GOOGLE_TTS_API_KEY')  # Simple API key (best for Render)
        self.use_rest_api = bool(self.api_key)  # Use REST API if API key is available
        
        if not self.use_rest_api:
            self._setup_client()
    
    def _setup_client(self):
        """Set up Google Cloud TTS client with OAuth or Service Account"""
        if not HAS_GOOGLE_CLOUD:
            logger.warning("⚠️  google-cloud-texttospeech not installed. Using REST API only.")
            self.client = None
            return
            
        try:
            # Option 1: Base64-encoded credentials (recommended for Render)
            creds_base64 = os.getenv('GOOGLE_TTS_CREDENTIALS_BASE64')
            if creds_base64:
                logger.info("🔧 Setting up Google TTS with base64-encoded credentials...")
                creds_json = base64.b64decode(creds_base64).decode('utf-8')
                temp_creds = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
                temp_creds.write(creds_json)
                temp_creds.close()
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_creds.name
                logger.info(f"✅ Base64 credentials decoded and written to: {temp_creds.name}")
            
            # Option 2: Check if running on Render with JSON credentials in environment variable
            elif os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
                creds_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
                # Running on Render - write credentials to temp file
                logger.info("🔧 Setting up Google TTS with service account from env variable...")
                temp_creds = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
                temp_creds.write(creds_json)
                temp_creds.close()
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_creds.name
                logger.info(f"✅ Credentials written to: {temp_creds.name}")
            else:
                # Running locally - use Application Default Credentials (ADC)
                # This works if you've run: gcloud auth application-default login
                logger.info("🔧 Using Application Default Credentials (gcloud)...")
            
            self.client = texttospeech.TextToSpeechClient()
            logger.info("✅ Google TTS client initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google TTS: {e}")
            logger.info("ℹ️  To use Google TTS locally, run: gcloud auth application-default login")
            logger.info("ℹ️  For Render, set GOOGLE_TTS_API_KEY env variable")
            self.client = None
    
    def generate_voice(self, text, output_path, voice_name="en-US-Neural2-J"):
        """
        Generate voice narration from text
        
        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
            voice_name: Voice to use (default: Neural2-J - male news anchor)
                       Options:
                       - en-US-Neural2-J (male, news anchor quality)
                       - en-US-Neural2-F (female, warm)
                       - en-US-Neural2-A (male, clear)
                       - en-US-Neural2-C (female, professional)
        
        Returns:
            Path to generated audio file or None if failed
        """
        # Use REST API if API key is available (simpler for Render)
        if self.use_rest_api:
            return self._generate_voice_rest_api(text, output_path, voice_name)
        
        # Otherwise use Python client library
        if not self.client:
            logger.error("❌ Google TTS client not initialized")
            return None
        
        try:
            logger.info(f"🎤 Generating voice with Google TTS ({voice_name})...")
            
            # Set the text input
            synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # Build the voice request
            # Determine gender from voice name
            female_voices = ["C", "E", "F", "G", "H"]
            male_voices = ["A", "D", "I", "J"]
            
            # Extract letter from voice name (e.g., "Neural2-J" -> "J")
            voice_letter = voice_name.split("-")[-1]
            
            if voice_letter in female_voices:
                gender = texttospeech.SsmlVoiceGender.FEMALE
            elif voice_letter in male_voices:
                gender = texttospeech.SsmlVoiceGender.MALE
            else:
                gender = texttospeech.SsmlVoiceGender.NEUTRAL
            
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name=voice_name
            )
            
            # Select the audio file type
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,  # Normal speed
                pitch=0.0,  # Normal pitch
                effects_profile_id=["small-bluetooth-speaker-class-device"]  # Optimize for playback
            )
            
            # Perform the text-to-speech request
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            # Write the response to the output file
            with open(output_path, "wb") as out:
                out.write(response.audio_content)
            
            # Get file size
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ Voice generated: {file_size / 1024:.1f} KB")
            
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Google TTS error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _generate_voice_rest_api(self, text, output_path, voice_name="en-US-Neural2-J"):
        """
        Generate voice using Google Cloud TTS REST API with API key
        Simpler and better for Render deployment
        """
        try:
            logger.info(f"🎤 Generating voice with Google TTS REST API ({voice_name})...")
            
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.api_key}"
            
            payload = {
                "input": {"text": text},
                "voice": {
                    "languageCode": "en-US",
                    "name": voice_name
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": 1.0,
                    "pitch": 0.0,
                    "effectsProfileId": ["small-bluetooth-speaker-class-device"]
                }
            }
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            audio_content = base64.b64decode(result['audioContent'])
            
            # Write audio file
            with open(output_path, 'wb') as f:
                f.write(audio_content)
            
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ Voice generated: {file_size / 1024:.1f} KB")
            
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Google TTS REST API error: {e}")
            import traceback
            traceback.print_exc()
            return None

def test_google_tts():
    """Test Google TTS voice generation"""
    print("\n🎤 Testing Google Cloud Text-to-Speech\n")
    
    tts = GoogleTTSVoice()
    
    if not tts.client:
        print("❌ Google TTS not set up")
        print("\nTo set up Google TTS:")
        print("1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install")
        print("2. Run: gcloud auth application-default login")
        print("3. Enable Cloud Text-to-Speech API in your project")
        return
    
    # Test text
    test_text = """
    Breaking News: Trump Pardons Founder of the Crypto Exchange Binance.
    This bombshell pardon raises eyebrows as Trump grants immunity to the founder of Binance, 
    who admitted to violating anti-money laundering laws. The move has sparked controversy, 
    with critics questioning the timing and motives behind this decision.
    """
    
    output_path = "/tmp/google_tts_test.mp3"
    
    print("📝 Test text:")
    print(test_text[:100] + "...")
    print(f"\n🎤 Generating voice...")
    
    result = tts.generate_voice(test_text, output_path)
    
    if result:
        print(f"\n✅ SUCCESS!")
        print(f"📁 Audio saved to: {result}")
        print(f"📊 File size: {os.path.getsize(result) / 1024:.1f} KB")
        print(f"\n🎧 Play with: afplay {result}")
    else:
        print("\n❌ Failed to generate voice")

if __name__ == "__main__":
    test_google_tts()
