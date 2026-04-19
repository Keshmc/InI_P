param(
    [string]$ProjectId = "financial-news-analyzer-489418",
    [string]$ServiceName = "news-analyzer",
    [string]$Region = "europe-west1",
    [string]$Memory = "2Gi",
    [string]$Cpu = "2",
    [string]$JobName = "news-analyzer-trends-job",
    [string]$SchedulerJobName = "news-analyzer-trends-daily",
    [string]$SchedulerSchedule = "0 6 * * *"
)

Write-Host "=== Google Cloud Deployment Script ===" -ForegroundColor Green

Write-Host "Step 1: Checking gcloud CLI..." -ForegroundColor Yellow
gcloud --version

Write-Host "`nStep 2: Setting project..." -ForegroundColor Yellow
gcloud config set project $ProjectId

Write-Host "`nStep 3: Enabling required APIs..." -ForegroundColor Yellow
gcloud services enable containerregistry.googleapis.com run.googleapis.com cloudbuild.googleapis.com compute.googleapis.com cloudscheduler.googleapis.com --quiet

Write-Host "`nStep 4: Building Docker image with Cloud Build..." -ForegroundColor Yellow
Write-Host "Image: gcr.io/$ProjectId/$ServiceName"
gcloud builds submit --tag "gcr.io/$ProjectId/$ServiceName" --quiet

Write-Host "`nStep 5: Deploying web app to Cloud Run (scheduler disabled)..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --image "gcr.io/$ProjectId/$ServiceName" `
    --platform managed `
    --region $Region `
    --memory $Memory `
    --cpu $Cpu `
    --allow-unauthenticated `
    --quiet `
    --set-env-vars "CONFIG_PATH=/app/config.yaml,NEWS_ANALYZER_LONG_TERM_TRENDS_ENABLED=false"

Write-Host "`nStep 6: Deploying Cloud Run Job for trend collection..." -ForegroundColor Yellow
gcloud run jobs deploy $JobName `
    --image "gcr.io/$ProjectId/$ServiceName" `
    --region $Region `
    --memory $Memory `
    --cpu $Cpu `
    --task-timeout 3600 `
    --command "python" `
    --args "src/news_analyzer/run_trends_job.py" `
    --set-env-vars "CONFIG_PATH=/app/config.yaml" `
    --quiet

Write-Host "`nStep 7: Setting up Cloud Scheduler (daily at $SchedulerSchedule UTC)..." -ForegroundColor Yellow
$ProjectNumber = gcloud projects describe $ProjectId --format "value(projectNumber)"
$ComputeSA = "$ProjectNumber-compute@developer.gserviceaccount.com"
Write-Host "Using service account: $ComputeSA" -ForegroundColor Cyan

Write-Host "Granting run.invoker to $ComputeSA..." -ForegroundColor Cyan
gcloud run jobs add-iam-policy-binding $JobName `
    --region $Region `
    --member "serviceAccount:$ComputeSA" `
    --role "roles/run.invoker" `
    --quiet 2>$null

$JobUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$JobName`:run"
$ExistingScheduler = powershell.exe -Command "gcloud scheduler jobs list --location $Region --format 'value(name)' 2>`$null" | Where-Object { $_ -match $SchedulerJobName }
if ($ExistingScheduler) {
    Write-Host "Updating existing scheduler job..." -ForegroundColor Cyan
    gcloud scheduler jobs update http $SchedulerJobName `
        --location $Region `
        --schedule $SchedulerSchedule `
        --uri $JobUri `
        --message-body "{}" `
        --oauth-service-account-email $ComputeSA `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
        --quiet
} else {
    Write-Host "Creating new scheduler job..." -ForegroundColor Cyan
    gcloud scheduler jobs create http $SchedulerJobName `
        --location $Region `
        --schedule $SchedulerSchedule `
        --uri $JobUri `
        --message-body "{}" `
        --oauth-service-account-email $ComputeSA `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
        --quiet
}

Write-Host "`nStep 8: Getting service URL..." -ForegroundColor Yellow
$ServiceUrl = gcloud run services describe $ServiceName `
    --platform managed `
    --region $Region `
    --format "value(status.url)"

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Green
Write-Host "Trend Job:   $JobName (runs daily at $SchedulerSchedule UTC)" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Write-Host "`nUseful commands:" -ForegroundColor Yellow
Write-Host "View web logs:  gcloud run logs read $ServiceName --region=$Region --limit=50"
Write-Host "View job logs:  gcloud run jobs logs read $JobName --region=$Region --limit=50"
Write-Host "Run job now:    gcloud run jobs execute $JobName --region=$Region"
Write-Host "List scheduler: gcloud scheduler jobs list --location=$Region"
