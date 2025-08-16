# 🚀 TradeTracker API - Google Cloud Deployment Guide

This guide will help you deploy your FastAPI backend to Google Cloud Platform's free tier using Cloud Run.

## 📋 Prerequisites

1. **Google Cloud Account**: Sign up at [cloud.google.com](https://cloud.google.com)
2. **Google Cloud CLI**: Install from [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)
3. **Docker**: Install from [docker.com](https://docker.com)

## 🔧 Setup Steps

### 1. Install and Configure Google Cloud CLI

```bash
# Install gcloud CLI (if not already installed)
# Follow instructions at: https://cloud.google.com/sdk/docs/install

# Authenticate with Google Cloud
gcloud auth login

# Set your project ID
gcloud config set project YOUR_PROJECT_ID
```

### 2. Enable Required APIs

```bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### 3. Configure Firebase Service Account

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select your project
3. Go to Project Settings > Service Accounts
4. Generate new private key
5. Download the JSON file
6. Place it in the `backend/` directory as `firebase-service-account.json`

## 🐳 Local Docker Testing

Before deploying, test locally:

### Option 1: Use Build Scripts (Recommended)

#### For Linux/Mac:
```bash
# Make executable and run
chmod +x build-docker.sh
./build-docker.sh
```

#### For Windows:
```cmd
# Run the build script
build-docker.bat
```

### Option 2: Manual Build

```bash
# Build the image
docker build -t tradetracker-api .

# Run locally
docker run -p 8000:8000 -v $(pwd)/firebase-service-account.json:/app/firebase-service-account.json tradetracker-api

# Or use docker-compose
docker-compose up --build
```

### Option 3: Alternative Dockerfile (if main fails)

If you encounter Rust compilation issues:

```bash
# Use alternative Dockerfile with pre-compiled wheels
docker build -f Dockerfile.alternative -t tradetracker-api .
```

## 🚀 Deploy to Google Cloud

### Option 1: Use the Deployment Script (Recommended)

#### For Linux/Mac:
```bash
# Edit the script to set your PROJECT_ID
nano deploy-gcp.sh

# Make executable and run
chmod +x deploy-gcp.sh
./deploy-gcp.sh
```

#### For Windows:
```cmd
# Edit the script to set your PROJECT_ID
notepad deploy-gcp.bat

# Run the script
deploy-gcp.bat
```

### Option 2: Manual Deployment

```bash
# Build and push image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/tradetracker-api .

# Deploy to Cloud Run
gcloud run deploy tradetracker-api \
    --image gcr.io/YOUR_PROJECT_ID/tradetracker-api \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --port 8000 \
    --memory 512Mi \
    --cpu 1 \
    --max-instances 10 \
    --min-instances 0
```

## ⚙️ Configuration

### Environment Variables

The following environment variables are automatically set:

- `FIREBASE_SERVICE_ACCOUNT_PATH`: Path to Firebase service account JSON
- `PORT`: Port number (8000)

### Resource Limits (Free Tier Optimized)

- **Memory**: 512 MiB
- **CPU**: 1 vCPU
- **Max Instances**: 10
- **Min Instances**: 0 (scales to zero when not in use)
- **Timeout**: 300 seconds
- **Concurrency**: 80 requests per instance

## 🔍 Monitoring and Logs

### View Logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=tradetracker-api" --limit=50
```

### Monitor Performance
- Go to [Cloud Run Console](https://console.cloud.google.com/run)
- Select your service
- View metrics, logs, and performance data

## 💰 Cost Optimization

### Free Tier Benefits
- **Cloud Run**: 2 million requests per month
- **Cloud Build**: 120 build-minutes per day
- **Container Registry**: 0.5 GB storage

### Cost-Saving Tips
1. **Scale to Zero**: Service automatically scales down when not in use
2. **Optimize Image Size**: Multi-stage Docker build reduces storage costs
3. **Monitor Usage**: Set up billing alerts to avoid unexpected charges

## 🚨 Troubleshooting

### Common Issues

1. **Authentication Errors**
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Build Failures**
   - Check Dockerfile syntax
   - Ensure all files are present
   - Verify requirements.txt

3. **Runtime Errors**
   - Check Cloud Run logs
   - Verify Firebase service account path
   - Check environment variables

### Health Check
Your service includes a health endpoint at `/health` that returns:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00"
}
```

## 🔄 Updating the Service

To update your deployed service:

```bash
# Rebuild and redeploy
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/tradetracker-api .
gcloud run deploy tradetracker-api --image gcr.io/YOUR_PROJECT_ID/tradetracker-api --region us-central1
```

## 📚 Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Build Documentation](https://cloud.google.com/cloud-build/docs)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
- [Google Cloud Free Tier](https://cloud.google.com/free)

## 🆘 Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review Cloud Run logs
3. Verify your configuration
4. Check Google Cloud status page

---

**Happy Deploying! 🎉**
