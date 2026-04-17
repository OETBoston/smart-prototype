import unittest
from unittest.mock import MagicMock, patch

from data_utils.accessor import BigQueryClient, BigQueryProfile

ACCESSOR_MODULE = "data_utils.accessor"


class TestBigQueryClientInit(unittest.TestCase):
    @patch(f"{ACCESSOR_MODULE}.os.path.exists", return_value=False)
    @patch(f"{ACCESSOR_MODULE}.AppSettings")
    @patch(f"{ACCESSOR_MODULE}.bigquery.Client")
    def test_01_init_falls_back_to_adc(
        self, MockBqClient, MockAppSettings, MockPathExists
    ):
        """Tests fallback when AppSettings provides no specific credentials."""

        MockAppSettings.return_value.bigquery_profiles = {}
        MockAppSettings.return_value.active_profile = "default"
        client_wrapper = BigQueryClient.initialize()
        MockBqClient.assert_called_once_with()
        MockPathExists.assert_not_called()
        self.assertIsInstance(client_wrapper, BigQueryClient)

    @patch(f"{ACCESSOR_MODULE}.os.path.exists", return_value=True)
    @patch(f"{ACCESSOR_MODULE}.AppSettings")
    @patch(f"{ACCESSOR_MODULE}.service_account.Credentials.from_service_account_file")
    @patch(f"{ACCESSOR_MODULE}.bigquery.Client")
    def test_02_init_uses_explicit_profile(
        self, MockBqClient, MockCredsFromFile, MockAppSettings, MockPathExists
    ):
        """Tests priority given to an explicit credentials_path from the config."""

        MOCK_PROFILE_CONFIG = {
            "bigquery_profiles": {
                "test_profile": BigQueryProfile(
                    credentials_path="/path/to/creds.json",
                    project_id="test-project-from-toml",
                    # default_dataset is None by default
                )
            }
        }

        # ARRANGE: Mock Pydantic to return the explicit profile and make it active
        mock_settings = MagicMock(
            active_profile="test_profile",
            bigquery_profiles=MOCK_PROFILE_CONFIG["bigquery_profiles"],
        )
        MockAppSettings.return_value = mock_settings

        # Setup mock credentials object
        mock_creds = MagicMock(project_id="creds-project-id")
        MockCredsFromFile.return_value = mock_creds

        # ACT: Initialize
        client_wrapper = BigQueryClient.initialize()

        # ASSERT
        # 1. Check that the credential file path was checked and used
        MockPathExists.assert_called_once_with("/path/to/creds.json")
        MockCredsFromFile.assert_called_once_with("/path/to/creds.json")

        # 2. Check that the BQ client used the credentials and project ID/Dataset
        MockBqClient.assert_called_once_with(
            credentials=mock_creds,
            project="test-project-from-toml",
            default_dataset=None,
        )
        self.assertIsInstance(client_wrapper, BigQueryClient)
