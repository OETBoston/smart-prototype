⚙️ Setting a Non-Standard BigQuery Profile

Your system uses Pydantic to check for configuration settings in a specific order: Environment Variables, then a config.toml file, then internal defaults.

Option 1: Using an Environment Variable (Recommended)

The easiest method is to set the ACTIVE_PROFILE environment variable in your consuming project to the name of the profile you want to use (e.g., staging, testing).

    Identify the Profile: Ensure the desired profile (e.g., "staging") is defined within the dependency's configuration.

    Set the Environment Variable: Set the ACTIVE_PROFILE variable to match that profile name.

Example (Bash/Linux/macOS):
Bash

# This tells the accessor to look up the profile named 'staging' 
export ACTIVE_PROFILE=staging

Example (Windows Command Prompt):
Bash

set ACTIVE_PROFILE=staging

Option 2: Using a config.toml File

If you don't want to use environment variables, you can place a config.toml file in the root directory of your main project.

    Create the File: Create a file named config.toml in your main project's root folder.

    Define the Profile: In this file, define your non-standard profile under the bigquery_profiles section and set the active_profile.

config.toml Example:
Ini, TOML

# Set the desired profile to be used
active_profile = "testing"

[bigquery_profiles.testing]
# This profile will automatically be loaded by your BigQueryClient.initialize()
credentials_path = "/path/to/your/test/account.json"
project_id = "my-test-gcp-project"



alternatively, it'll use your default profile, so you can just run (on a mac):
gcloud auth application-default login