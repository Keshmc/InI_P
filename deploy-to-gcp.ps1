param(
    [string]$ProjectId = "financial-news-analyzer-489418",
    [string]$ServiceName = "news-analyzer",
    [string]$Region = "europe-west1",
    [string]$Memory = "2Gi",
    [string]$Cpu = "2"
)

Write-Host "=== Google Cloud Deployment Script ===" -ForegroundColor Green

Write-Host "Step 1: Checking gcloud CLI..." -ForegroundColor Yellow
gcloud --version

Write-Host "`nStep 2: Setting project..." -ForegroundColor Yellow
gcloud config set project $ProjectId

Write-Host "`nStep 3: Enabling required APIs..." -ForegroundColor Yellow
gcloud services enable containerregistry.googleapis.com run.googleapis.com cloudbuild.googleapis.com compute.googleapis.com --quiet

Write-Host "`nStep 4: Building Docker image with Cloud Build..." -ForegroundColor Yellow
Write-Host "Image: gcr.io/$ProjectId/$ServiceName"
gcloud builds submit --tag "gcr.io/$ProjectId/$ServiceName" --quiet

Write-Host "`nStep 5: Deploying to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --image "gcr.io/$ProjectId/$ServiceName" `
    --platform managed `
    --region $Region `
    --memory $Memory `
    --cpu $Cpu `
    --allow-unauthenticated `
    --quiet `
    --set-env-vars "CONFIG_PATH=/app/config.yaml"

Write-Host "`nStep 6: Getting service URL..." -ForegroundColor Yellow
$ServiceUrl = gcloud run services describe $ServiceName `
    --platform managed `
    --region $Region `
    --format "value(status.url)"

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Write-Host "`nUseful commands:" -ForegroundColor Yellow
Write-Host "View logs: gcloud run logs read $ServiceName --region=$Region --limit=50"
Write-Host "Stream logs: gcloud run logs read $ServiceName --region=$Region --limit=50 --follow"
