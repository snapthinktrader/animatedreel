# Final Architecture: Cloud Run + CockroachDB + Render

## ✅ Current Deployment Status

**Deploying to Google Cloud Run (Mumbai - asia-south1)**
- Service: `video-processor`
- Memory: 2 GB RAM
- CPU: 2 vCPUs  
- Timeout: 600 seconds (10 minutes)
- Region: Mumbai (asia-south1) for low latency from India

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    RENDER (512 MB RAM)                      │
│                    Orchestrator Only                        │
├─────────────────────────────────────────────────────────────┤
│ 1. Fetch NYT articles                                       │
│ 2. Generate voice (Google TTS)                              │
│ 3. Extract keywords (Groq AI)                               │
│ 4. Search Pexels for video URLs                             │
│ 5. Send URLs to Cloud Run ────────┐                         │
│ 6. Wait for video_id              │                         │
│ 7. Download from CockroachDB      │                         │
│ 8. Add text & anchor overlays     │                         │
│ 9. Add voice narration            │                         │
│ 10. Save final reel to CockroachDB│                         │
│ 11. Sleep 12 minutes              │                         │
└───────────────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────┐
│            GOOGLE CLOUD RUN (2 GB RAM)                      │
│            Video Processor - Mumbai                         │
├─────────────────────────────────────────────────────────────┤
│ 1. Receive 6 video URLs                                     │
│ 2. Download all clips                                       │
│ 3. Resize to 9:16 portrait (1080x1920)                      │
│ 4. Concatenate clips                                        │
│ 5. Chunk if >8 MB (6 MB chunks)                             │
│ 6. Store in CockroachDB ──────┐                             │
│ 7. Return video_id            │                             │
└───────────────────────────────┼─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│            COCKROACHDB (5 GB FREE)                          │
│            All Video Storage                                │
├─────────────────────────────────────────────────────────────┤
│ Tables:                                                      │
│ - processed_videos: Main video metadata                     │
│ - processed_video_chunks: Large file chunks (>8 MB)         │
│ - final_reels: Completed reels with overlays                │
│ - temp_clips: Temporary buffer (auto-cleanup)               │
│ - temp_clip_chunks: Temp chunks (auto-cleanup)              │
└─────────────────────────────────────────────────────────────┘
```

## Cost Breakdown (Monthly)

### Render
- **Plan**: Starter ($7/month)
- **Usage**: 24/7 orchestration
- **RAM**: 512 MB (enough for lightweight tasks)

### Google Cloud Run
- **Free Tier**: 2 million requests, 360,000 GB-seconds
- **Usage per reel**: ~30-60 seconds @ 2 GB = 60-120 GB-seconds
- **Monthly reels**: 3,600 reels (1 every 12 min)
- **Monthly GB-seconds**: ~250,000 GB-seconds
- **Cost**: **FREE** (within free tier!) 🎉

### CockroachDB
- **Plan**: Free tier (5 GB storage)
- **Usage**: ~2-3 GB for videos (auto-cleanup old videos)
- **Cost**: **FREE** 🎉

### **Total Monthly Cost: $7** 🎉

## Next Steps After Deployment

1. **Wait for deployment** (3-5 minutes)
2. **Get Cloud Run URL** from deployment output
3. **Update Render** environment variable:
   ```
   CLOUD_PROCESSOR_URL=https://video-processor-<hash>-el.a.run.app
   ```
4. **Update** `generate_and_save_reels.py` to use lightweight creator
5. **Deploy to Render**
6. **Monitor** - no more memory crashes!

## Benefits

✅ **No More Memory Crashes** - Heavy processing on 2 GB Cloud Run
✅ **Zero Storage Cost** - Using free CockroachDB 
✅ **Low Latency** - Mumbai region for Indian users
✅ **Free Cloud Run** - Within free tier limits
✅ **Scalable** - Cloud Run auto-scales if needed
✅ **Reliable** - Google's infrastructure

## Files Created

1. `main.py` - Cloud Run service (renamed from cloud_video_processor.py)
2. `requirements.txt` - Python dependencies for Cloud Run
3. `lightweight_reel_creator.py` - Render's lightweight orchestrator
4. `deploy-cloud.sh` - Deployment script
5. `.gcloudignore` - Ignore unnecessary files

## Monitoring

**Check Cloud Run logs:**
```bash
gcloud run services logs read video-processor \
  --region asia-south1 \
  --project nukkad-foods \
  --limit 100
```

**Check service status:**
```bash
gcloud run services describe video-processor \
  --region asia-south1 \
  --project nukkad-foods
```
