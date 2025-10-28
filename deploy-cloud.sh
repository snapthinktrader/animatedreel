#!/bin/bash
# Deploy video processor to Google Cloud Run

PROJECT_ID="nukkad-foods"
SERVICE_NAME="video-processor"
REGION="asia-south1"  # Mumbai for better latency

# CockroachDB connection string
COCKROACHDB_URI="postgresql://snap:zY7iXb69bunWURtTeASzhg@backinsta-17456.j77.aws-ap-south-1.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full"

echo "🚀 Deploying Video Processor to Google Cloud Run (Mumbai)..."

# Build and deploy (will auto-detect main.py)
gcloud run deploy $SERVICE_NAME \
  --source . \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --memory 4Gi \
  --cpu 2 \
  --timeout 600 \
  --allow-unauthenticated \
  --set-env-vars COCKROACHDB_URI="$COCKROACHDB_URI"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Getting service URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --project $PROJECT_ID \
  --format 'value(status.url)')

echo "📡 Service URL: $SERVICE_URL"
echo ""
echo "Add this to Render environment variables:"
echo "CLOUD_PROCESSOR_URL=$SERVICE_URL"
