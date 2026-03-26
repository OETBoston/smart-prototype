# Example usage of the smart_curb_db module

# This example demonstrates how to use the SmartCurbDB class to connect to a PostgreSQL
# database and append data to a staging table with a UUID4
#
# This example was tested on the live staging database hosted in GCP.
#

import uuid

import pandas as pd
from dotenv import load_dotenv
from smart_curb_db import SmartCurbDB

load_dotenv()


def main() -> None:
    # Add a record to the table asset_jobs
    with SmartCurbDB(dbname="cds", schema="staging") as db:
        data = pd.DataFrame(
            {
                "job_id": [uuid.uuid4().hex],
                "job_name": ["TEST Job"],
                "job_description": ["This is a test job"],
            }
        )
        db.append_data("asset_jobs", data)


if __name__ == "__main__":
    main()
