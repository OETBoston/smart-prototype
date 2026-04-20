

# **Integration Test Setup (BigQuery)**

Integration tests run against **real BigQuery** and require valid Google Cloud authentication.
Tests run only if the necessary environment variables are provided.

---

# **Prerequisites**

### You can authenticate in **either** of two ways:

---

## **Option A — Application Default Credentials (recommended)**

Use your user credentials for local integration tests:

```
gcloud auth application-default login
```

This creates the ADC file here:

```
~/.config/gcloud/application_default_credentials.json
```

---

## **Option B — Service Account JSON (CI or advanced local use)**

If you prefer a service account, provide a `.json` key file that has:

* BigQuery Data Viewer
* BigQuery Data Editor *(if running insert tests)*

Set its path in the `.env` file.

---

# 📦 **Environment Variables Needed**

Integration tests rely on **.env**, not terminal exports.

Your `.env` must define your test project and dataset:

```env
# Project + dataset for integration tests
TEST_GCP_PROJECT_ID="your-gcp-project-id"
TEST_BQ_DATASET_ID="your-dataset-id"
TEST_BQ_TABLE_ID="your-table-name"

# Accessor configuration (used by DataAccessor + BigQueryClient)
DB_ACCESS_ACTIVE_CLIENT=bigquery
DB_ACCESS_ACTIVE_PROFILE=dev
DB_ACCESS_ACTIVE_ENVIRONMENT=dev

# BigQuery profile settings
DB_ACCESS_BIGQUERY_PROFILES__dev__PROJECT_ID="your-gcp-project-id"
DB_ACCESS_BIGQUERY_PROFILES__dev__DEFAULT_DATASET="your-dataset-id"

# Optional — only if using a Service Account JSON instead of ADC
# (leave unset to use gcloud ADC)
# DB_ACCESS_BIGQUERY_PROFILES__dev__CREDENTIALS_PATH="./your-sa-key.json"

# Environment prefix (project.dataset)
DB_ACCESS_ENVIRONMENT_PREFIXES__dev="your-gcp-project-id.your-dataset-id"
```

---

# ▶️ **Running Integration Tests**

Just run:

```bash
uv run pytest -m integration
```

The tests will automatically:

* load `.env`
* initialize the BigQuery client through your real config
* authenticate using ADC or SA JSON (whichever is defined)
* perform live queries and inserts


