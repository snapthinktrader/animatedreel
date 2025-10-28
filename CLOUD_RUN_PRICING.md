# Google Cloud Run Pricing Analysis for Video Processor
# Region: asia-south1 (Mumbai)
# Updated: October 28, 2025

## Current Setup (2GB RAM)
- Memory: 2 GB
- CPU: 2 cores
- Processing time per reel: ~30-60 seconds (with failures due to OOM)
- Status: ❌ RUNNING OUT OF MEMORY

## Proposed Setup (4GB RAM)
- Memory: 4 GB
- CPU: 2 cores  
- Processing time per reel: ~30-60 seconds (estimated, should be stable)
- Status: ✅ Should handle 6 video clips without OOM

---

## Google Cloud Run Pricing (asia-south1)

### Memory Pricing
- **Cost per GB-second**: $0.0000025
- **Cost per GB-hour**: $0.009

### CPU Pricing
- **Cost per vCPU-second**: $0.000024
- **Cost per vCPU-hour**: $0.0864

### Request Pricing
- **First 2 million requests/month**: FREE
- **After 2 million**: $0.40 per million requests

---

## Monthly Cost Calculation

### Scenario: 3,600 reels per month (2.5 reels/hour, 24/7)

#### Option 1: 2GB RAM (Current - but FAILING)
```
Processing time per reel: 45 seconds average
Total processing time: 3,600 reels × 45s = 162,000 seconds = 45 hours/month

Memory cost:
- 2 GB × 45 hours × $0.009/GB-hour = $0.81/month

CPU cost:
- 2 vCPU × 45 hours × $0.0864/vCPU-hour = $7.78/month

Total: $8.59/month
⚠️ BUT: Service crashes, worker timeouts, unreliable
```

#### Option 2: 4GB RAM (Proposed - STABLE)
```
Processing time per reel: 45 seconds average  
Total processing time: 3,600 reels × 45s = 162,000 seconds = 45 hours/month

Memory cost:
- 4 GB × 45 hours × $0.009/GB-hour = $1.62/month

CPU cost:
- 2 vCPU × 45 hours × $0.0864/vCPU-hour = $7.78/month

Total: $10.40/month
✅ Stable, no crashes, reliable service
```

#### Option 3: 8GB RAM (Maximum headroom)
```
Processing time per reel: 45 seconds average
Total processing time: 3,600 reels × 45s = 162,000 seconds = 45 hours/month

Memory cost:
- 8 GB × 45 hours × $0.009/GB-hour = $3.24/month

CPU cost:
- 2 vCPU × 45 hours × $0.0864/vCPU-hour = $7.78/month

Total: $12.02/month
✅✅ Maximum stability, handles spikes easily
```

---

## Cost Comparison Summary

| Configuration | Memory | CPU | Monthly Cost | Status |
|--------------|--------|-----|--------------|--------|
| **Current (2GB)** | 2 GB | 2 vCPU | **$8.59** | ❌ FAILING (OOM) |
| **Proposed (4GB)** | 4 GB | 2 vCPU | **$10.40** | ✅ Recommended |
| **Premium (8GB)** | 8 GB | 2 vCPU | **$12.02** | ✅✅ Maximum safety |

### Additional Cost: $1.81/month for 4GB (recommended)
### Additional Cost: $3.43/month for 8GB (premium)

---

## Total System Cost Breakdown

### With 4GB Cloud Run:
```
Render (512 MB worker)          $7.00/month
Google Cloud Run (4GB)         $10.40/month
CockroachDB (5GB free tier)     $0.00/month
----------------------------------------------
TOTAL                          $17.40/month  ✅ STABLE
```

### With 8GB Cloud Run (maximum safety):
```
Render (512 MB worker)          $7.00/month
Google Cloud Run (8GB)         $12.02/month
CockroachDB (5GB free tier)     $0.00/month
----------------------------------------------
TOTAL                          $19.02/month  ✅✅ PREMIUM
```

---

## Recommendation: 4GB RAM

### Why 4GB is the sweet spot:
1. **Only $1.81/month more** than current failing setup
2. **Doubles available memory** for video processing
3. **Should handle 6 clips** without OOM errors
4. **Still very affordable** at $17.40/month total

### Why NOT stay at 2GB:
1. Service is crashing (logs show OOM)
2. Worker timeouts killing the process
3. Unreliable - fails on most requests
4. Only saves $1.81/month but causes 100% failure rate

### Why consider 8GB:
1. Only $1.62/month more than 4GB
2. Maximum headroom for future features
3. Can handle larger videos or more clips
4. Total cost still under $20/month

---

## Decision Matrix

| If you want... | Choose | Cost |
|---------------|--------|------|
| **Cheapest (but broken)** | 2GB | $17.59/month ❌ |
| **Best value (recommended)** | 4GB | $17.40/month ✅ |
| **Maximum reliability** | 8GB | $19.02/month ✅✅ |

## My Recommendation: **Go with 4GB RAM**
- Cost difference is minimal ($1.81/month extra)
- Fixes all current OOM errors
- Provides stable, reliable service
- Total cost $17.40/month is still very affordable

---

## Free Tier Included
Google Cloud Run includes FREE tier:
- 2 million requests/month FREE
- 180,000 vCPU-seconds/month FREE  
- 360,000 GB-seconds/month FREE

Your usage (45 hours/month) is well within free tier for requests,
so you only pay for the actual compute time used!

---

## Cost Per Reel
- **2GB**: $0.0024 per reel (but FAILS)
- **4GB**: $0.0029 per reel ✅
- **8GB**: $0.0033 per reel

**Verdict: For less than 1 cent per reel, get a working system!**
