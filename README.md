# PTTEP Data Engineer Take-Home Exam

## Overview

This project implements data ingestion pipelines in Python for loading structured and semi-structured data into Google BigQuery.

## Technology

* Python
* Google Cloud Storage (GCS)
* Google BigQuery
* pandas
* openpyxl
* pyarrow

## Project Structure

.
├── task1.py
├── task2.py
├── requirements.txt
├── .gitignore
└── README.md

## Task 1

Task 1 processes structured CSV data from Google Cloud Storage and loads the transformed data into BigQuery.

### Source

`gs://pttep-data-engineer-test/de-exam-task1/data_storytelling.csv`

### Destination

* Project: `gcp-test-data-engineer`
* Dataset: `exam_rienthong`
* Table: `task1_data_result`

The pipeline:

1. Downloads the CSV file from GCS.
2. Parses and cleans the source data.
3. Loads the transformed data into BigQuery.


The pipeline handles data cleaning and normalization, including:

* Integer values with embedded commas
* High-precision decimal values
* Multiple timestamp formats
* Boolean normalization
* Holiday name extraction
* Business datetime conversion to Asia/Bangkok
* Load timestamp

### Decimal Column Handling

`decimal_col` is stored as `STRING` because some valid source values exceed BigQuery `NUMERIC` and `BIGNUMERIC` precision and scale limits. Storing them as `STRING` preserves the original valid decimal values without precision loss.

## Task 2

Task 2 processes semi-structured operational data from an Excel file in Google Cloud Storage.

### Source

`gs://pttep-data-engineer-test/de-exam-task2/DE Exam raw data_20250101.xlsx`

The pipeline:

1. Downloads the Excel file from GCS.
2. Reads the `Raw Data` worksheet.
3. Processes monthly blocks and asset columns.
4. Generates one record per asset per calendar day.
5. Excludes the `Reference` column and summary rows.
6. Extracts the `parameter` date from the source filename.
7. Adds the current UTC load timestamp.
8. Saves the processed result as a CSV file.
9. Loads the data into BigQuery.

### Destination

* Project: `gcp-test-data-engineer`
* Dataset: `exam_rienthong`
* Table: `task2_data_result`

### Output Schema

| Column     | BigQuery Type | Description                             |
| ---------- | ------------- | --------------------------------------- |
| date       | DATE          | Calendar date of the operational data   |
| parameter  | DATE          | Date extracted from the source filename |
| asset      | STRING        | Oil/gas asset or equipment              |
| nomination | FLOAT         | Nominated/planned value                 |
| load_ts    | TIMESTAMP     | UTC timestamp when the record is loaded |

Task 2 produces 600 records from the provided source file.

## Setup

Create a Python virtual environment:

python -m venv .venv

Activate the virtual environment on Windows:

.venv\Scripts\Activate.ps1

Install dependencies:

pip install -r requirements.txt

## Google Cloud Credentials

A Google Cloud service account credential file is required to run the pipelines.

Place the credential file in the project directory as:

`key.json`

The credential file is excluded from Git through `.gitignore` and must not be committed to the repository.

## Run

Run Task 1:

python task1.py

Run Task 2:

python task2.py

Both pipelines use `WRITE_TRUNCATE` when loading their respective BigQuery tables.
