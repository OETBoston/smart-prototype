# Smart Curb Sign Reader

The Sign Reader package uses Google Gemini to parse sign images into CDS policy objects.
It leverages Pydantic data models that restrict outputs to CDS-specific structures and
values. It also includes a preprocessor to determine if a sign contains a usuable image,
(also using Gemini). Images that are not usable are assigned a special policy with
`activity: "unusable image"`.

This repository also contain a lightweight web application for exploring results after
running the Sign Reader.

## Usage

To run the sign reader itself from the project root (`smart-prototype/`), run

```sh
uv run python -m sign_reader
```

After running the sign reader and populating the Postgres Database with policies,
the accompanying Streamlit web app can be used to assess the policies generated for each
image read by the process. To run the app from the project root, use:

```sh
uv run streamlit run packages/sign-reader/src/sign_reader/app.py
```

## Configuration

Runtime behavior is controlled through a YAML configuration file.
See the [default config file](./src/sign_reader/config.yaml) for details.

## Resuming After Failure

If repeated queries to Gemini hang, you can resume processing signs by simply restarting
the sign reader. As long as the config option `re_process` is set to `False`, the process
will automatically skip any sign images that have already been processed. Note that
a new sign reader `job_id` will be generated.
