# Smart Curb Sign Reader

This repository contains two main entry points:

1. **A Streamlit web application** for interactive usage
2. **A batch-processing script (`main.py`)** for automated runs

The project uses **[uv](https://github.com/astral-sh/uv)** for fast Python dependency and environment management.

---


## Prerequisites

* Python **3.13+**
* `uv` installed

Install `uv` (if you don’t have it yet):

```bash
pip install uv
```


## Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/OETBoston/smart-curb-sign-reader
cd smart-curb-sign-reader
uv sync
```

This will:

* Create a virtual environment
* Install all dependencies defined in `pyproject.toml`

---


## Environment Variables

This project relies on environment variables. To get started:

1.  **Copy the template file** to create your local environment file:
    ```bash
    cp .env.template .env
    ```
2.  **Open `.env`** and fill in the required credentials, including the Gemini API key and 
GCP Postgres Staging Database credentials (username and password).

3.  **Note:** The `.env` file is ignored by git and should never be committed.

## Usage

This project uses `uv` for seamless environment management. You do not need to manually activate a virtual environment; `uv run` handles it automatically.


### 1. Running the Streamlit App (`app.py`)

To launch the Streamlit application:

```bash
uv run streamlit run app.py
```

Once started, Streamlit will print a local URL (usually `http://localhost:8501`) that you can open in your browser.


The application provides four flexible ways to source images for analysis. Each option is designed for a specific testing or production workflow:

![streamlit_options_screenshot.png](assets/streamlit_options_screenshot.png)

| Option | Input Method | Behavior |
| :--- | :--- | :--- |
| **Option 1** | **Local Upload** | Upload an image (`.jpg`, `.png`) directly from your computer. The file is automatically staged to GCS before processing. |
| **Option 2** | **Image URL** | Paste a direct link to a hosted image. The app will fetch the bytes and analyze them via the Gemini API. |
| **Option 3** | **Random (Local File)** | Randomly selects a URI from your local `urls.txt` file. Ideal for quick benchmarking against a known dataset. |
| **Option 4** | **Random (GCP Database)** | Connects to the GCP Postgres staging table and pulls a random unprocessed image. This automatically creates a new `job_id` for tracking. |


---

### 2. Running Batch Processing (`main.py`)

`main.py` processes image URIs using the Gemini API. You must specify an input source using either a local text file or by pulling records from the Google Cloud Postgres database.
And it supports optional configuration flag like temperature.

#### 2.1 Option A: Local Text File
Create a `.txt` file (for example, `urls.txt`) with one image URI per line:

```text
https://example.com/image1.jpg
https://example.com/image2.jpg
https://example.com/image3.jpg
```
Run the command using the `--file` flag:

```bash
uv run python main.py --file urls.txt
```

#### 2.2 Option B: Database Fetch
To pull image URIs directly from the Google Cloud Postgres table instead of using a local file, use the `--db` flag:

```bash
uv run python main.py --db
```
Optional: To process a specific batch, filter by specific asset job ID (this requires the `--db` flag):
```bash
uv run python main.py --db --job-id "YOUR_ASSET_JOB_UUID_HERE"
```

#### 2.3 Temperature Configuration
You can optionally specify a temperature to control model creativity:

```bash
# Run with default settings (temperature = 0)
uv run python main.py --db
uv run python main.py --file urls.txt

# Run with a custom temperature (e.g., 0.7 for more creative reasoning)
uv run python main.py --db --temperature 0.7
uv run python main.py --file urls.txt --temperature 0.7
```

#### 2.4 Argument Details

| Argument | Type | Description                                                                 |
| :--- | :--- |:----------------------------------------------------------------------------|
| `--file` | `string` | Path to a local text file containing image URIs (one per line).             |
| `--db` | `flag` | Triggers a fetch from the Google Cloud Postgres staging table.              |
| `--job-id` | `uuid` | Filters database records by a specific asset Job UUID. **Requires `--db`.** |
| `--temperature` | `float` | (Optional, default to 0.0) Controls the randomness of the Gemini output. Use 0.0 for consistent extraction and higher values (up to 2.0) for more varied responses.|
