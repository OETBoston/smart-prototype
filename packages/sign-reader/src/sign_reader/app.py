"""
app.py

Main entry point for the Sign Reader Visualizer Streamlit application.

"""

import json
import logging
import os
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from curb_utils.db_utils import SmartCurbDB
from dotenv import load_dotenv
from google.cloud import storage
from streamlit_pdf_viewer import pdf_viewer

repo_root = Path(__file__).resolve().parents[4]  # …/smart-prototype
sys.path.append(str(repo_root))

IMAGE_UNAVAILABLE_PATH = Path(__file__).resolve().parent / "image_unavailable.jfif"

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Setup Page Config
st.set_page_config(page_title="Sign Reader Viewer", layout="wide")
st.title("Sign Reader Viewer")


def get_image_unavailable_bytes() -> bytes:
    try:
        return IMAGE_UNAVAILABLE_PATH.read_bytes()
    except Exception:
        return None


def get_image_from_gs(
    bucket_path: str, cache_dir: str = Path(__file__).resolve().parent / "cached_images"
) -> bytes:
    """
    Fetch image bytes from Google Cloud Storage with local caching.

    Args:
        bucket_path (str): The gs:// URI.
        cache_dir (str): Local directory to store downloaded images.

    Returns:
        bytes: The image data.
    """
    try:
        # 1. Parse the URI
        parsed = urlparse(bucket_path)
        if parsed.scheme != "gs":
            return None

        bucket_name = parsed.netloc
        blob_name = parsed.path.lstrip("/")

        # 2. Ensure cache directory exists
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        # 3. Construct a safe local filename
        safe_filename = f"{bucket_name}_{blob_name.replace('/', '_')}"
        local_path = os.path.join(cache_dir, safe_filename)

        # 4. Check if we already have it locally
        if os.path.exists(local_path):
            # print(f"Loading from cache: {local_path}") # Debugging
            with open(local_path, "rb") as f:
                return f.read()

        # 5. If not cached, download from GCS
        # print(f"Downloading from GCS: {bucket_path}") # Debugging
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        image_bytes = blob.download_as_bytes()

        # 6. Save to local cache for next time
        with open(local_path, "wb") as f:
            f.write(image_bytes)

        return image_bytes

    except Exception as e:
        print(f"Error fetching {bucket_path}: {e}")
        return None


def get_image_from_url(url: str) -> bytes:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        return response.content
    except Exception as e:
        print(f"Error fetching image: {e}")
        return None


def get_pdf_from_url(url: str) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()

        return response.content
    except Exception as e:
        print(f"Error fetching PDF: {e}")
        return None


@st.cache_data()
def load_data(dbname="cds", schema="staging", sign_reader_job_id=None) -> pd.DataFrame:
    logger.info(f"Connecting to {dbname}.{schema}...")
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        sign_policies = db.get_data(
            "sign_policies",
            columns=["sign_id", "policy_json", "policy_arrow"],
            filter=f"job_id = '{sign_reader_job_id}'" if sign_reader_job_id else None,
        )
        signs = db.get_data("signs", columns=["sign_id", "sign_location_id"])
        asset_locations = db.get_data(
            "asset_locations",
            columns=["asset_location_id", "location"],
            geom_col="location",
        )
        images = db.get_data("images", columns=["sign_id", "uri"])

    signs_w_images = signs.merge(images, on="sign_id", how="left")
    data = sign_policies.merge(signs_w_images, on="sign_id", how="left").merge(
        asset_locations,
        left_on="sign_location_id",
        right_on="asset_location_id",
        how="left",
    )

    # Convert UUIDs to strings
    data = data.astype(
        {col: str for col in ["sign_id", "sign_location_id", "asset_location_id"]}
    )

    return data


@st.cache_data()
def load_jobs(dbname="cds", schema="staging") -> pd.DataFrame:
    logger.info(f"Connecting to {dbname}.{schema}...")
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        jobs = db.get_data(
            "sign_reader_jobs",
            columns=[
                "job_id",
                "job_timestamp",
                "job_name",
                "job_description",
                "model_settings",
                "system_instruction",
                "prompt",
            ],
        )

    jobs = jobs.sort_values(by="job_timestamp", ascending=False).reset_index(drop=True)

    # Convert UUIDs to strings
    jobs = jobs.astype({col: str for col in ["job_id"]})

    return jobs


# Initialize session state
if "record_index" not in st.session_state:
    st.session_state.record_index = 0

# Sidebar Configuration
st.sidebar.header("Data Source Settings")

# Schema Selection
schema_option = st.sidebar.selectbox("Select Schema", options=["staging", "staging_next"], index=0)

jobs_df = load_jobs(schema=schema_option)

# Initialize job_id as None
job_id = None

if not jobs_df.empty:
    formatted_ts = pd.to_datetime(jobs_df["job_timestamp"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    jobs_df["display_label"] = (
        "["
        + jobs_df["job_id"].str[:8]
        + "] "
        + jobs_df["job_name"].fillna("Unnamed")
        + " | "
        + formatted_ts
    )

    # Job Selection Dropdown
    selected_job_label = st.sidebar.selectbox(
        "Select Sign Reader Job",
        options=jobs_df["display_label"].tolist(),
        index=None,
        placeholder="Choose a job...",
    )

    # Only extract details if a selection was made
    if selected_job_label:
        # Extract selected job details
        job_info = jobs_df[jobs_df["display_label"] == selected_job_label].iloc[0]
        job_id = job_info["job_id"]

        st.sidebar.divider()
        st.sidebar.subheader("Job Details")

        # Larger Description
        if job_info["job_description"]:
            st.sidebar.markdown(f"### Description\n{job_info['job_description']}")
        else:
            st.sidebar.info("No description available.")

        # Model Settings (JSON)
        st.sidebar.markdown("### Model Settings")
        if pd.notnull(job_info["model_settings"]):
            with st.sidebar.expander("View JSON", expanded=True):
                st.json(job_info["model_settings"])
        else:
            st.sidebar.warning("Empty model settings")

        # 3. System Instruction & Prompt
        st.sidebar.markdown("### LLM Configuration")

        # System Instruction
        if pd.notnull(job_info.get("system_instruction")):
            with st.sidebar.expander("📝 System Instruction", expanded=False):
                st.write(job_info["system_instruction"])
        else:
            st.sidebar.caption("No system instruction found.")

        # Prompt
        if pd.notnull(job_info.get("prompt")):
            with st.sidebar.expander("💬 User Prompt", expanded=False):
                st.write(job_info["prompt"])
        else:
            st.sidebar.caption("No prompt found.")

        st.sidebar.divider()
    else:
        st.sidebar.info("Please select a job to see details.")
else:
    st.sidebar.warning("No jobs found in this schema.")


if job_id:
    df = load_data(schema=schema_option, sign_reader_job_id=job_id)

    if not df.empty:
        record = df.iloc[st.session_state.record_index]

        if "location" in df.columns:
            df["lat"] = df["location"].apply(lambda g: g.y if g else None)
            df["lon"] = df["location"].apply(lambda g: g.x if g else None)

        # Navigation Controls

        col_nav1, col_nav2, col_nav3, col_nav4, col_nav5, col_nav6 = st.columns(
            [1, 1, 1, 3, 1, 1]
        )

        n = len(df)

        with col_nav1:
            if st.button("⏪ -10"):
                st.session_state.record_index = (st.session_state.record_index - 10) % n

        with col_nav2:
            if st.button("⬅️ Prev"):
                st.session_state.record_index = (st.session_state.record_index - 1) % n

        with col_nav3:
            if st.button("🎲 Random"):
                st.session_state.record_index = random.randint(0, n - 1)

        with col_nav5:
            if st.button("Next ➡️"):
                st.session_state.record_index = (st.session_state.record_index + 1) % n

        with col_nav6:
            if st.button("+10 ⏩"):
                st.session_state.record_index = (st.session_state.record_index + 10) % n

        # Get current record
        record = df.iloc[st.session_state.record_index]

        with col_nav4:
            # Centered record and Sign ID display
            st.markdown(
                f"<div style='text-align: center; line-height: 1.2;'>"
                f"<strong>"
                f"Record {st.session_state.record_index + 1} of {len(df)}"
                f"</strong><br>"
                f"<code style='font-size: 0.8em;'>{record['sign_id']}</code>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # image and policy json side by side
        col_img, col_json = st.columns([1, 1])

        with col_img:
            st.subheader("Sign Image")

            uri = record.get("uri")
            is_valid_uri = pd.notnull(uri) and uri != ""
            img_bytes = None
            is_pdf = str(uri).lower().endswith(".pdf") if is_valid_uri else False

            if is_valid_uri:
                try:
                    if uri.startswith("gs://"):
                        img_bytes = get_image_from_gs(uri)
                    elif is_pdf:
                        img_bytes = get_pdf_from_url(uri)
                    else:
                        img_bytes = get_image_from_url(uri)
                except Exception as e:
                    st.error(f"Error loading source: {e}")

            if img_bytes:
                if is_pdf:
                    pdf_viewer(img_bytes)
                else:
                    st.image(img_bytes, width="stretch")
            else:
                placeholder = get_image_unavailable_bytes()
                if placeholder:
                    st.image(placeholder, width="stretch")

                if not is_valid_uri:
                    st.info("No URI provided.")
                else:
                    st.warning("Image could not be retrieved.")

            # Wide Map using PyDeck
            st.subheader("Location")
            if pd.notnull(record["lat"]):
                # 1. Define the initial view centered on the sign's location
                view_state = pdk.ViewState(
                    latitude=record["lat"], longitude=record["lon"], zoom=18, pitch=0
                )

                # 2. Layer for ALL points (Green)
                all_points_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=df,
                    get_position="[lon, lat]",
                    get_color="[0, 200, 0, 150]",
                    get_radius=3,
                )

                # 3. Layer for the SELECTED point (Red)
                selected_point_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([record.to_dict()]),
                    get_position="[lon, lat]",
                    get_color="[255, 0, 0, 255]",
                    get_radius=6,
                )

                # 4. OpenStreetMap Background
                base_layer = pdk.Layer(
                    "TileLayer",
                    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    attribution="OpenStreetMap",
                )

                # 5. Render
                st.pydeck_chart(
                    pdk.Deck(
                        initial_view_state=view_state,
                        layers=[base_layer, all_points_layer, selected_point_layer],
                        map_style=None,
                    )
                )
            else:
                st.warning("No coordinates available for this record.")

        with col_json:
            st.subheader("Policy Details")

            # 1. Display Policy Arrow
            arrow_val = record.get("policy_arrow", "N/A")
            st.markdown(f"**Policy Arrow Direction:** `{arrow_val}`")

            # 2. Display Policy JSON on screen
            st.json(record["policy_json"])

            # 3. Prepare JSON for download
            json_string = json.dumps(record["policy_json"], indent=4)
            filename = f"sign_{record['sign_id']}_policy.json"

            # 4. Add the Download Button
            st.download_button(
                label="📥 Download Policy JSON",
                data=json_string,
                file_name=filename,
                mime="application/json",
            )
    else:
        st.info(
            f"The job **{job_id[:8]}** was found, "
            f"but it contains no sign records in the `{schema_option}` schema."
        )
else:
    st.info("Please select a Job ID from the sidebar to visualize sign data.")
