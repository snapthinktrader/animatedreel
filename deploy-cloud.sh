#!/bin/bash
# Deploy video processor to Google Cloud Run

PROJECT_ID="nukkad-foods"
SERVICE_NAME="video-processor"
REGION="asia-south1"  # Mumbai for better latency

# Load environment variables from parent .env file
PARENT_DIR="$(dirname "$(pwd)")"
ENV_FILE="$PARENT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo "📝 Loading environment variables from $ENV_FILE..."
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "⚠️  Warning: .env file not found at $ENV_FILE"
fi

echo "🚀 Deploying Video Processor to Google Cloud Run (Mumbai)..."

# Build and deploy with all required environment variables
gcloud run deploy $SERVICE_NAME \
  --source . \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --memory 4Gi \
  --cpu 2 \
  --timeout 600 \
  --allow-unauthenticated \
  --set-env-vars "COCKROACHDB_URI=$COCKROACHDB_URI,GROQ_API_KEY=$GROQ_API_KEY,PEXEL=$PEXEL,NYT_API_KEY=$NYT_API_KEY,GOOGLE_API_KEY=$GOOGLE_API_KEY"

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
