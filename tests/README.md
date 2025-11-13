Integration Test Setup (BigQuery)

Integration tests require live GCP credentials to verify connectivity. These tests will only run if the necessary environment variables are set.

Prerequisites

A Google Cloud Service Account key file (.json) with BigQuery Data Viewer permissions for the test project.

Your local environment must have the project and key readily accessible.

Running Integration Tests Securely

Before running, set the following environment variables in your terminal session (replace the placeholder values with your actual GCP details).

DO NOT COMMIT THESE VALUES TO GIT.

# 1. Your real GCP Project ID
export TEST_GCP_PROJECT_ID="your-gcp-project-id"

# 2. The specific dataset the test will query (Must exist and contain tables)
export TEST_BQ_DATASET_ID="your-dataset-id"

# 3. The ABSOLUTE path to your downloaded Service Account key file (the .json)
export REAL_CREDS_PATH="/Users/yourname/secrets/my-ci-key.json"

# Run the integration tests
uv run pytest -m integration
