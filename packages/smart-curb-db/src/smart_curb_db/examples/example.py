# Example usage of the smart_curb_db module

# This example demonstrates how to use the SmartCurbDB class to connect to a PostgreSQL
# database, read geospatial and non-geospatial data, and append data to a table.
#
# It requires that the database specified in your .env file has a dataset consistent
# with the cds schema, including tables like curb_zones and curb_policies.
#
# This test script will MODIFY the database by adding a test table and appending data to
# it.

import pandas as pd
from dotenv import load_dotenv
from smart_curb_db import SmartCurbDB

# For testing only, not usually needed.
from sqlalchemy import Column, Float, Integer, MetaData, String, Table

load_dotenv()


def main() -> None:
    # Initialize database connection

    # Connect to the database using a context manager
    # Then test reading a table named curb_zones
    with SmartCurbDB(dbname="smart_curb_db", schema="public") as db:
        # Example: read curb_zones table as a geodataframe
        gdf = db.get_data("curb_zones", geom_col="geometry")

        # Example: read curb_policies as a dataframe
        df = db.get_data("curb_policies")

        # Example: read geodata with a filter
        columns = ["curb_zone_id", "name", "geometry"]
        gdf_filtered = db.get_data(
            "curb_zones",
            geom_col="geometry",
            filter="curb_zone_id = '27c13344-d1b3-5541-a027-3240afe60817'",
            columns=columns,
        )

        # Example: read dataframe with a filter
        columns = ["name", "description"]
        df_filtered = db.get_data(
            "curb_policies", filter="name LIKE 'BOSCDS-%'", columns=columns
        )

    print(f"Curb Zones (type = {type(gdf)}):")
    print(gdf.head())

    print(f"Curb Policies (type = {type(df)}):")
    print(df.head())

    print(f"Filtered Curb Zones (type = {type(gdf_filtered)}):")
    print(gdf_filtered.head())

    print(f"Filtered Curb Policies (type = {type(df_filtered)}):")
    print(df_filtered.head())

    # For testing, create a test table. In practice, tables will already exist.
    create_test_table()

    # Test appending some data
    with SmartCurbDB(dbname="smart_curb_db", schema="public") as db:
        data = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["A", "B", "C"],
                "value": [10.5, 20.75, 30.0],
            }
        )
        db.append_data("test_table", data)

        # Read back the data to verify
        df_test = db.get_data("test_table")
        print("Test Table Data:")
        print(df_test)

        # Now, try to add some bad data to test error handling

        # Bad data type:
        bad_data = pd.DataFrame(
            {
                "id": [4, 5],
                "name": ["D", "E"],
                "value": ["not_a_number", 50.0],  # Invalid data type
            }
        )
        try:
            db.append_data("test_table", bad_data)

        # More robust example of error handling:
        # Other examples are more limited for brevity
        except ValueError as ve:
            print("\n\nCaught ValueError as expected when appending bad datatype:")
            print(ve)
        except ConnectionError as ce:
            print("\n\nCaught ConnectionError as expected when appending bad datatype:")
            print(ce)
        except Exception as e:
            print("\n\nExpected error when appending bad datatype:")
            print(e)

        # Extra column:
        extra_col_data = pd.DataFrame(
            {
                "id": [6],
                "name": ["F"],
                "value": [60.0],
                "extra_col": ["extra"],  # Extra column not in table
            }
        )
        try:
            db.append_data("test_table", extra_col_data)
        except Exception as e:
            print("\n\nExpected error when appending data with extra column:")
            print(e)

        # Missing non-nullable column:
        # (note: add will succeed if missing nullable columns)
        missing_col_data = pd.DataFrame(
            {
                "id": [7],
                # "name" column is missing
                "value": [70.0],
            }
        )
        try:
            db.append_data("test_table", missing_col_data)
        except Exception as e:
            print(
                "\n\nExpected error when appending data with missing "
                + "non-nullable column:"
            )
            print(e)


def create_test_table() -> None:
    # Add a table called test_table, replacing it if it already exists
    # in practice, this will not be needed since tables will already exist
    with SmartCurbDB(dbname="smart_curb_db", schema="public") as db:
        # Drop the table if it exists:
        metadata = MetaData()
        _test_table = Table(
            "test_table",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String, nullable=False),
            Column("value", Float),
        )

        if db.engine is not None:
            metadata.drop_all(db.engine)
            metadata.create_all(db.engine)
        else:
            raise ConnectionError("Database engine is not available.")


if __name__ == "__main__":
    main()
