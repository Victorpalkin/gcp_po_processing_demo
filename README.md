# PO Processing Prototype

Purchase Order extraction powered by Google Cloud Document AI Custom Extractor with GenAI.

Users upload POs (scans/PDFs/images), the app extracts structured data, users review/correct, then "send" (mock). Uploaded files stored in GCS, extraction results stored in BigQuery. Admins configure extraction fields and manage processors via the Document AI API.

## Architecture

| Layer   | Technology                                      |
|---------|-------------------------------------------------|
| UI      | Streamlit (multi-page, custom-styled)           |
| Doc AI  | Custom Extractor with GenAI (zero-shot)         |
| Files   | Google Cloud Storage                            |
| Results | BigQuery                                        |
| Auth    | Identity-Aware Proxy on Cloud Run               |
| Deploy  | Cloud Run from source (Python buildpack)        |

## Setup

### Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Python 3.11+

### Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  documentai.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com
```

### Create Resources

```bash
export PROJECT_ID=$(gcloud config get-value project)

# GCS bucket
gsutil mb -l us-central1 gs://${PROJECT_ID}-po-uploads

# BigQuery dataset and table
bq mk --dataset ${PROJECT_ID}:po_processing
bq mk --table ${PROJECT_ID}:po_processing.extractions \
  id:STRING,filename:STRING,gcs_uri:STRING,processor_name:STRING,processor_display_name:STRING,status:STRING,extracted_data:JSON,reviewed_data:JSON,confidence:FLOAT,created_at:TIMESTAMP,reviewed_at:TIMESTAMP,sent_at:TIMESTAMP
```

### Service Account

```bash
gcloud iam service-accounts create po-processing-sa

for ROLE in roles/documentai.apiUser roles/storage.objectAdmin roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member=serviceAccount:po-processing-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --role=$ROLE
done
```

### Local Development

```bash
pip install -r requirements.txt

export PROJECT_ID=your-gcp-project
export DOCAI_LOCATION=us
export GCS_BUCKET=${PROJECT_ID}-po-uploads
export BQ_DATASET=po_processing

streamlit run app.py
```

The app will be available at http://localhost:8501.

### Deploy to Cloud Run

```bash
gcloud run deploy po-processing \
  --source . \
  --region us-central1 \
  --set-env-vars PROJECT_ID=$PROJECT_ID,DOCAI_LOCATION=us,GCS_BUCKET=${PROJECT_ID}-po-uploads,BQ_DATASET=po_processing \
  --service-account po-processing-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --memory 1Gi
```

Configure IAP via the GCP Console for authentication.

## Pages

- **Home** (`app.py`) — Dashboard with stats and recent activity
- **Process** (`pages/1_Process.py`) — Select processor, upload documents, extract data
- **Review** (`pages/2_Review.py`) — Edit extracted fields, send
- **History** (`pages/3_History.py`) — Browse past extractions with filters
- **Admin** (`pages/4_Admin.py`) — Create and manage Document AI processors

## Field Configuration Tips

- Use descriptive `description` fields when creating processors — they drive zero-shot extraction accuracy
- Example: instead of "vendor", use "The name of the vendor or supplier company on the purchase order"
- The `type` field supports "Extract" (from document text) and "Derive" (computed/inferred)
- Mark fields as `required` to ensure they appear in every extraction

## Environment Variables

| Variable        | Description                        |
|-----------------|------------------------------------|
| `PROJECT_ID`    | GCP project ID                     |
| `DOCAI_LOCATION`| Document AI API location (e.g. us) |
| `GCS_BUCKET`    | GCS bucket for file uploads        |
| `BQ_DATASET`    | BigQuery dataset name              |
