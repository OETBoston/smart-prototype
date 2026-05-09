# Boston CDS Asset Translation System

## Overview

**⚠️ This project is currently in development.**

Boston's SMART Prototype provides a proof-of-concept end-to-end pipeline for automating the management of curbside parking regulations data.

At the core of the prototype is an AI-powered system to automatically translate Boston's existing curb asset data and street signage imagery into standardized [Curb Data Specification (CDS)](https://github.com/openmobilityfoundation/curb-data-specification) format. The goal is to bridge the gap between legacy asset management systems and modern digital curb management by leveraging AI and large language models (LLMs) to interpret and structure curb regulations.

## Project Details

**Partnership:**

- **City of Boston Office of Emerging Technology**
- **Cambridge Systematics**

**Funding:** This work is supported by the U.S. Department of Transportation's SMART Grant program.

## Approach

AT a very high level, this system takes two primary inputs:

1. **Asset Management Data**: Existing streets and curb asset records from Boston's municipal systems
2. **Street Sign Images**: Digital photographs of physical street signs and curb markings

Using AI and geospatial analysis, the system will interpret this data and convert it into CDS-compliant format for modern curb management applications.

## About CDS

The [Curb Data Specification (CDS)](https://github.com/openmobilityfoundation/curb-data-specification) is an open standard developed by the Open Mobility Foundation that helps cities digitally manage curb space and communicate with curb users. CDS provides APIs for:

- **Curbs API**: Digital representation of curb locations and regulations
- **Events API**: Real-time and historic curb usage events
- **Metrics API**: Aggregated statistics on curb utilization

Learn more about CDS at the [official specification repository](https://github.com/openmobilityfoundation/curb-data-specification).

# Boston CDS Asset Translation System

## Overview

**⚠️ This project is currently in development.**

An AI-powered system to automatically translate Boston's existing curb asset data and street signage imagery into standardized [Curb Data Specification (CDS)](https://github.com/openmobilityfoundation/curb-data-specification) format. The goal is to bridge the gap between legacy asset management systems and modern digital curb management by leveraging AI and large language models (LLMs) to interpret and structure curb regulations.

## Project Details

**Partnership:**

- **City of Boston Office of Emerging Technology**
- **Cambridge Systematics**

**Funding:** This work is supported by the U.S. Department of Transportation's SMART Grant program.

## About CDS

The [Curb Data Specification (CDS)](https://github.com/openmobilityfoundation/curb-data-specification) is an open standard developed by the Open Mobility Foundation that helps cities digitally manage curb space and communicate with curb users. CDS provides APIs for:

- **Curbs API**: Digital representation of curb locations and regulations
- **Events API**: Real-time and historic curb usage events
- **Metrics API**: Aggregated statistics on curb utilization

Learn more about CDS at the [official specification repository](https://github.com/openmobilityfoundation/curb-data-specification).

## Approach

The core workflow for the system includes the following steps:

1. Creation of curb geometries from street centerline data.
1. Segmentation of those geometries based on the location of physical assets (including parking signs, fire hydrants, and bus stops).
1. LLM-powered interpretation of digital photographs of street signs and translation into CDS-compliant curb policies.
1. Application of policy information back to the curb segments

Each of these steps can be run independently. Input and output data are managed through a Postgres/PostGIS relational database managment system.

More information is provided in <LINK TO PACKAGES>

# Getting Started

## Environment Setup

This project is developed using the `uv` [package manager](https://docs.astral.sh/uv/#uv) for Python programming environments.
To get started using the tools and pipeline, make sure you have `uv` installed ([instructions](https://docs.astral.sh/uv/getting-started/installation/)) on your system.

To build the required Python environment, clone this repository, and from the project root run:

```sh
uv sync
```

## Environment Variables

The project depends on a couple of important external connections, namely:

- Google Gemini (for sign interpretation tasks)
- A Postgres database server for managing the data

The required environment variables are managed through a `.env` file. To populate them, copy the file `env_template`
to a new file called `.env` at the project root and provide the relevant values. They will be loaded automatically at runtime.

## Database setup

The curb data processing pipeline makes use of a Postgres database. A managed Postgres Instance with the PostGIS extensions
is already set up in Boston's Google Cloud Platform environment. To run the pipeline locally, you should make sure you are able
to connect to this server from your local machine. Contact the Office of Emerging Technology for details.

### Staging Schema

The script located at `/smart-prototype/sql_schema/00_create_staging.sql` contains prerequisite SQL script for
creating the required database schema. A description of the schema can be found [here](docs/staging_database.md)

By default, the schema is called `staging_next` -- as it is designed to provide an isolated environment when running the pipeline
multiple times in succession, which can be renamed to `staging` after inspection.

# Repository Structure

The SMART Protype repo makes use of `uv`'s [workspaces concept](https://docs.astral.sh/uv/concepts/projects/workspaces/)
to manage each of the component analytical packages developed for the prototype. These packages are located at `/smart-prototype/packages/`. Each package contains its
own source code and configuration files located at `/smart_prototype/<package-name>/src/<package_name>`.

There is no need to install packages independently. Running `uv sync` from the project root creates a unified environment
providing access to each package and its dependencies.

# Running Packages in a Pipeline
The SMART Prototype allows for the CDS-creation process to be run in unified pipeline, or one at a time. 

Management of the pipeline is taken care of by the core, `smart_prototype` package (located at `smart-prototype/src/smart_prototype`).

The pipeline is currently capable of running the four core, analytical steps sequentially:
1. `blockface-creator`
1. `curb-segmentater`
1. `sign-reader`
1. `policy-applier`

See [packages](#individual-packages) below for details on these steps.

### Configuration
Within `/src/smart_prototype`, edit the config.yaml file if required. The structure of
this configuration file is simple as it points directly to the individual `config.yaml`
used by each individual processing step, along with a run toggle. 
```yaml
steps:
  <step_name>: # using underscore, not hyphen
    path: "path/to/config.yaml" # Usually within the package source
    run: True # or False. Whether to run this step
   # etc.
``` 

Setting `run` to `False` for all but one step provides a convenient entry point for running
individual processes in sequence (provided the prequisites have been met for each).

Edit each step configuration in the individual package directory as necessary. 

To run the pipeline, from the project root use:

```sh
uv run python /smart-prototype/src/smart_prototype/main.py
```
**Auto Job Discovery (In Development)**
The curb segmenter, sign reader, and policy applier configs each require reference to 
one or more `job_ids` from upstream processes. By setting these `job_id` values to 
`"auto"`, the SMART Prototype pipeline will pass the relevant job ids to each process.
Autodiscovery is only avialable when running the curb segmenter, sign reader, and policy
applier in sequence (i.e. all are set to to `run: True`).

# Individual Packages

Below is a brief description of each package, its upstream requirements, and instructions for running.
**NB:** these are organized logically rather than alphabetically.

Running each step will (generally) create a relevant `job_id` in a corresponding `*_jobs` table in the database that
can be used to link processes together.

## sign-loader

The sign loader ingests data from Boston's [Cartegraph](https://data.boston.gov/dataset/signs-cartegraph)
sign managment system and records information about signs, their locations, links to images, in the database.
Various filters can be configured to determine which signs to upload
(for instance, a single neighborhood, or based on attributes).

Detailed documentation can be found within the package [here](packages/sign-loader/README.md).

### Inputs and Outputs

- **Upstream requirements**: A local copy of the data (csv format) is currently required.
- **Outputs**: Updates `asset_locations`, `signs`, and `images` tables

### Run Instructions

This step is not yet fully integrated into the pipeline, and should be run as follows.

1. Navigate to `smart-prototype/packages/sign-loader/src/sign_loader`.
1. Update the `config.yaml` file with paths for Cartegraph data and additional filters, including a path for geospatial files used to filter the data.
1. Run `uv run python main.py` from the `/src` directory

## blockface-creator

The blockface creator generates the fundamental curb geometries used to construct CDS zones.
It builds a unique line feature for each block in Boston, based on street centerline centerline data.

This process uses data from [MassDOT's 2024 Roadway Inventory](https://gis.data.mass.gov/datasets/MassDOT::road-inventory-2024/explore?location=42.060080%2C-71.715412%2C8), which contained the richest avaialble information for roadway geometries.

**NB**: The blockface creation step redigitizes the direction of each curb line to flow with the direction
of travel in the adjacent lane. This step is important for downstream processes.

Detailed documentation can be found within the package [here](packages/blockface-creator/README.md)

### Inputs and Outputs

- **Upstream requirements**: A local copy of the data (`shp`, `.geojson`, `.parquet` or `.feather`) is currently required.
- **Outputs**: Updates `curb_blockfaces` table

### Run Instructions

Within the package folder, update the `config.yaml` file with paths for roadway centerline data and relevant filters.

This package may be run from the project root using:

```sh
uv run python -m blockface_creator
```

### curb-segmenter

The curb segmentation process uses the locations of parking sign and non-sign asset features to divide up the curb based on estimates of
where different parking rules start and end.

Non-sign features used in segmentation are currently limited to fire hydrants, bus stops, and parking meter zones.
Currently, the non-sign features should be uploaded to the prior to running the curb segmenter.

Detailed documentation can be found within the package [here](packages/curb-segmenter/README.md)

### Inputs and Outputs

- **Upstream requirements**: Blockface creation step, upload of sign and non-sign assets to the database.
- **Outputs**: Updates `curb_segments` table

### Run Instructions

Within the package folder, update the `config.yaml` file with job ids for uploads of signs, fire hydrants, bus stops and parking meters.

This package may be run from the project root using:

```sh
uv run python -m curb_segmenter
```

### sign-reader

The sign reader uses Google Gemini to parse images of parking signs into CDS-compliant policy objects,
along with important metadata such as the direction of arrows. A pre-processor (also Gemini-based) will
first examine whether or not the image is parseable based on whether it contains a parking sign with
legible text. Images that cannot be read are assigned a policy with the "unusable image" activity.

Detailed documentation can be found within the package [here](packages/curb-segmenter/README.md)

### Inputs and Outputs

- **Upstream requirements**: sign-loader
- **Outputs**: Updates `sign_policies` table

### Run Instructions

Within the package folder, update the `config.yaml` with relevant values for the asset `job_id`
for signage data to process (from `sign-loader), as well as settings for Google Gemini settings
and asynchronous API calls.

This package may be run from the project root using:

```sh
uv run python -m sign_reader
```

## policy-applier

The policy applier links parsed curb regulations back to the segmented curb direction,
based on the arrow direction in which the signs are determined to apply. Using common ids
for signs and asset locations, this step iterates over the segmented curbs and identifies
at which segment points each identified policy begins and ends.

**NB**: Currently, the policy applier will attempt to regulate the curb using **all** policies
derived from sign locations recorded by the curb segmenter.

### Inputs and Outputs

- **Upstream requirements**: sign-loader, curb-segmenter, sign-reader. Non-sign assets should be loaded into the database.
- **Outputs**: Updates `curb_segment_policies` table

### Run Instructions

Within the package folder, update the `config.yaml` with relevant curb segmentation `job_id`.

This package may be run from the project root using:

```sh
uv run python -m sign_reader
```

## api-updater

This package manages moving data from the staging database schema to a separate schema
that provides the backend to Boston's CDS Curbs API. The final zones and policies are constructed, deduplicating as needed, and new IDs are assigned.

To ensure consistency over equivalent policies, this step also handles generation of policy descriptions (Gemini-based).

Detailed documentation can be found within the package [here](packages/api-updater/README.md)

The actual API code is hosted in a [smart-curb-api](https://github.com/OETBoston/smart-curb-api) sister repository.
Detailed information on the structure and set up of the API schema can be found there.

### Inputs and Outputs

- **Upstream requirements**: curb-segmenter, policy-applier (including their pre-requisites)
- **Outputs**: Updates all in a API separate database schema

### Run Instructions

Within the package folder, update the `config.yaml` with the `job_ids` for the curb segmenter and
policy applier jobs, as well as the source staging and target API schema for data transfer.

To allow for QAQC, the `api-updater` should normally be run targeting a test schema
(e.g. `public_cds_next`) for testing and \*_not_ the `public_cds` schema, which is used by
production applications.

This package may be run from the project root using:

```sh
uv run python -m api_updater
```

## api-db-rollover

This is a utility package for managing the rollover from a test API database schema to
the production schema.

## curb-utils

This is an interal package containing modules with common utilities used by other SMART Protoype packages, including management of Gemini clients and queries; database connections and queries; file input and output; and logging.

(The `db_utils` module is largely deprecated, but contains some code still currently used for reading from Google Cloud Storage.)

## api-db-rollover

This package is designed to automate the process of rolling over a test API data to the production schema. The business logic is handled by .sql scripts.

### Run Instructions

From the package source folder (`packages/api_db_rollover/src/api_db_rollover`), run:

```sh
uv run python main.py
```



## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for notes on consistent style and tooling for developers of the SMART Grant codebases.git stat

---

_This project supports Boston's Smart City initiatives and the broader goal of making urban curb space more accessible, efficient, and digitally manageable._
