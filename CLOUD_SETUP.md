# Google Cloud Run + Render Hybrid Architecture

## Overview
Split the workload between two services:
- **Google Cloud Run**: Heavy video processing (2GB RAM, pay-per-use)
- **Render**: Orchestration, overlays, database (512 MB RAM, $7/month)

## Benefits
✅ **Cost Effective**: Cloud Run only charges when processing (seconds of usage)
✅ **Scalable**: Cloud Run auto-scales, handles any video size
✅ **Memory Efficient**: Render stays under 512 MB limit
✅ **Reliable**: No more memory crashes

## Architecture Flow

```
Render Worker (512 MB RAM):
1. Fetch NYT articles
2. Generate voice with Google TTS
3. Search Pexels for video URLs
4. Send URLs to Cloud Run ──────┐
5. Wait for processed video     │
6. Download result              │
7. Add overlays (text, anchor)  │
8. Add voice narration          │
9. Save to CockroachDB          │
10. Sleep 12 minutes            │
                                │
                                ▼
Google Cloud Run (2GB RAM):
1. Receive video URLs
2. Download all clips
3. Resize to 9:16 portrait
4. Concatenate clips
5. Upload to Cloud Storage
6. Return URL to Render ────────┘
```

## Setup Instructions

### 1. Create Google Cloud Project

```bash
# Install Google Cloud SDK
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Login and create project
gcloud auth login
gcloud projects create animatedreel-processor
gcloud config set project animatedreel-processor

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### 2. Create Google Cloud Storage Bucket

```bash
# Create bucket for processed videos
gsutil mb -l us-central1 gs://animatedreel-videos

# Make bucket public (or use signed URLs)
gsutil iam ch allUsers:objectViewer gs://animatedreel-videos
```

### 3. Deploy Video Processor to Cloud Run

```bash
cd /Users/mahendrabahubali/Desktop/QPost/animatedreel

# Deploy (will build and deploy automatically)
gcloud run deploy video-processor \
  --source . \
  --dockerfile Dockerfile.cloud \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --max-instances 3 \
  --allow-unauthenticated \
  --set-env-vars GCS_BUCKET=animatedreel-videos

# Get service URL
gcloud run services describe video-processor \
  --region us-central1 \
  --format 'value(status.url)'
```

### 4. Update Render Environment Variables

Add to Render dashboard:
```
CLOUD_PROCESSOR_URL=https://video-processor-<hash>-uc.a.run.app
```

### 5. Update Render Code

Replace `AnimatedReelCreator` with `LightweightReelCreator`:

```python
# In generate_and_save_reels.py
from lightweight_reel_creator import LightweightReelCreator

# Change:
creator = AnimatedReelCreator()

# To:
creator = LightweightReelCreator()
```

## Cost Estimate

### Google Cloud Run
- **Free tier**: 2 million requests/month, 360,000 GB-seconds
- **Video processing**: ~30 seconds per reel @ 2GB RAM
  - 30s × 2GB = 60 GB-seconds per reel
  - Cost: ~$0.004 per reel
  - Monthly (1 reel every 12 min = ~3,600 reels): **$14.40/month**

### Google Cloud Storage
- **Free tier**: 5 GB storage, 1 GB egress
- **Storage**: 100 videos @ 20 MB = 2 GB
- **Egress**: 3,600 downloads @ 20 MB = 72 GB
  - Cost: **~$9/month**

### Total Monthly Cost
- Render: $7
- Cloud Run: $14.40
- Cloud Storage: $9
- **Total: ~$30/month** (vs trying to make 512 MB work)

## Alternative: Use Existing Cloud Services

Instead of Cloud Run, use:

1. **Shotstack API** (Video editing as a service)
   - $49/month for unlimited renders
   - No infrastructure management
   - https://shotstack.io

2. **Cloudinary** (Media processing)
   - Video transformations
   - $99/month for advanced features
   - https://cloudinary.com

3. **FFmpeg Lambda Layer** (AWS)
   - Process on AWS Lambda
   - Similar to Cloud Run pricing

## Recommended: Start with Cloud Run

✅ Most control over processing
✅ Transparent costs
✅ Easy to debug
✅ Can optimize further if needed

## Next Steps

1. Set up Google Cloud account
2. Deploy video processor
3. Update Render service
4. Test with one reel
5. Monitor costs and performance
