import csv
import re
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from google.cloud import storage


PROJECT_ID = "gcp-test-data-engineer"
DATASET_ID = "exam_rienthong"
TABLE_ID = "task1_data_result"
FULL_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

FILE_NAME = "data_storytelling.csv"
BUCKET_NAME = "pttep-data-engineer-test"
BLOB_NAME = "de-exam-task1/data_storytelling.csv"

BQ_SCHEMA = [
    bigquery.SchemaField("row_id", "INTEGER"),
    bigquery.SchemaField("integer_col", "INTEGER"),
    bigquery.SchemaField("decimal_col", "STRING"),
    bigquery.SchemaField("timestamp_col", "TIMESTAMP"),
    bigquery.SchemaField("boolean_col", "BOOL"),
    bigquery.SchemaField("holiday_name", "STRING"),
    bigquery.SchemaField("business_datetime", "TIMESTAMP"),
    bigquery.SchemaField("created_datetime", "TIMESTAMP"),
]

BOOLEAN_VALUES = {
    "true",
    "false",
    "yes",
    "no",
    "ok",
    "1",
    "0",
    "-",
    "unknown",
    "maybe",
    "2",
}

HOLIDAY_NAMES = [
    "Makha Bucha Day",
    "Labour Day",
    "Chulalongkorn Day",
    "King's Birthday",
    "King Bhumibol Memorial Day",
    "Songkran Festival",
    "Constitution Day",
    "Royal Ploughing Ceremony",
    "Queen's Birthday",
    "New Year's Day",
    "Buddhist Lent",
    "Christmas Day",
]

HOLIDAY_ALIASES = {
    "makha bucha": "Makha Bucha Day",
}

BKK = ZoneInfo("Asia/Bangkok")
UTC = ZoneInfo("UTC")


logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def create_business_datetime(value):
    if value is None:
        return None

    return value.replace(tzinfo=BKK)


def looks_like_timestamp(value):
    value = value.strip()

    patterns = [
        r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$",
        r"^\d{2}/\d{2}/\d{4}$",
        r"^\d{2}-[A-Za-z]{3}-\d{2}$",
        r"^\d{14}$",
    ]

    invalid_timestamp_values = {
        "unknown",
        "not a date",
        "invalid timestamp",
    }

    if value.lower() in invalid_timestamp_values:
        return True

    return any(re.match(pattern, value) for pattern in patterns)


def parse_row(row):
    # In the case of 5 columns
    # Structure:
    # integer, decimal, timestamp, boolean, holiday
    if len(row) == 5:
        return {
            "integer_col": row[0].strip(),
            "decimal_col": row[1].strip(),
            "timestamp_col": row[2].strip(),
            "boolean_col": row[3].strip(),
            "holiday_name": row[4].strip(),
        }

    # More than 5 columns may indicate an unquoted comma
    # inside integer_col or holiday_name.
    timestamp_index = None

    for i, value in enumerate(row):
        if looks_like_timestamp(value):
            timestamp_index = i
            break

    # Timestamp at index 3 indicates that integer_col contains
    # an unquoted comma, e.g. 261,180.
    if timestamp_index == 3:
        integer_col = row[0] + "," + row[1]
        decimal_col = row[2]
        boolean_col = row[4]
        holiday_name = ",".join(row[5:]).strip()

        return {
            "integer_col": integer_col.strip(),
            "decimal_col": decimal_col.strip(),
            "timestamp_col": row[3].strip(),
            "boolean_col": boolean_col.strip(),
            "holiday_name": holiday_name,
        }

    # Timestamp is at index 2,
    # indicating that the extra comma is in holiday_name.
    elif timestamp_index == 2:
        integer_col = row[0]
        decimal_col = row[1]
        boolean_col = row[3]
        holiday_name = ",".join(row[4:]).strip()

        return {
            "integer_col": integer_col.strip(),
            "decimal_col": decimal_col.strip(),
            "timestamp_col": row[2].strip(),
            "boolean_col": boolean_col.strip(),
            "holiday_name": holiday_name,
        }

    # Timestamp is invalid or blank
    else:
        boolean_index = None

        for i, value in enumerate(row):
            if value.strip().lower() in BOOLEAN_VALUES:
                boolean_index = i
                break

        if boolean_index == 3:
            # integer, decimal, timestamp, boolean, holiday...
            integer_col = row[0]
            decimal_col = row[1]
            timestamp_col = row[2]
            boolean_col = row[3]
            holiday_name = ",".join(row[4:]).strip()

        elif boolean_index == 4:
            # integer, integer_part, decimal, timestamp, boolean, holiday...
            integer_col = row[0] + "," + row[1]
            decimal_col = row[2]
            timestamp_col = row[3]
            boolean_col = row[4]
            holiday_name = ",".join(row[5:]).strip()

        else:
            raise ValueError(f"Cannot determine row structure: {row}")

        return {
            "integer_col": integer_col.strip(),
            "decimal_col": decimal_col.strip(),
            "timestamp_col": timestamp_col.strip(),
            "boolean_col": boolean_col.strip(),
            "holiday_name": holiday_name,
        }


def clean_integer(value):
    value = value.strip()

    if value == "":
        return None

    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def clean_boolean(value):
    value = value.strip().lower()

    if value == "":
        return None

    if value in {"true", "yes", "ok", "1"}:
        return True

    if value in {"false", "no", "0"}:
        return False

    if value == "-":
        return None

    logger.warning("Unrecognized boolean value: %r",value)

    return None


def clean_decimal(value):
    value = value.strip()

    if value == "":
        return None

    try:
        Decimal(value)
        return value
    except InvalidOperation:
        return None


def clean_timestamp(value):
    value = value.strip()

    if value == "":
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%d-%b-%y",
        "%Y%m%d%H%M%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


def clean_holiday(value):
    value = value.strip()

    if value == "":
        return None

    value_lower = value.lower()

    # Check known short forms
    for alias, holiday_name in HOLIDAY_ALIASES.items():
        if alias in value_lower:
            return holiday_name

    # Find canonical holiday names in the sentence
    matches = []

    for holiday in HOLIDAY_NAMES:
        position = value_lower.find(holiday.lower())

        if position != -1:
            matches.append((position, holiday))

    if not matches:
        return None

    # If multiple holidays appear, use the first one in the sentence
    matches.sort(key=lambda item: item[0])

    return matches[0][1]


def download_raw_data():
    try:
        client = storage.Client.from_service_account_json("key.json")
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(BLOB_NAME)
        blob.download_to_filename(FILE_NAME)

        logger.info("Downloaded: %s", FILE_NAME)

    except Exception:
        logger.exception("Failed to download raw file from GCS")
        raise


def read_raw_data():
    rows = []
    created_datetime = datetime.now(UTC)

    with open(FILE_NAME,"r",encoding="utf-8-sig",newline="") as file:
        reader = csv.reader(file)

        next(reader)

        for line_number, row in enumerate(reader, start=2):
            parsed = parse_row(row)

            parsed["row_id"] = line_number - 1

            parsed["integer_col"] = clean_integer(parsed["integer_col"])

            parsed["decimal_col"] = clean_decimal(parsed["decimal_col"])

            parsed["timestamp_col"] = clean_timestamp(parsed["timestamp_col"])

            parsed["boolean_col"] = clean_boolean(parsed["boolean_col"])

            parsed["holiday_name"] = clean_holiday(parsed["holiday_name"])

            parsed["business_datetime"] = create_business_datetime(parsed["timestamp_col"])

            parsed["created_datetime"] = created_datetime

            rows.append(parsed)

    return rows


def validate_data(rows):
    if not rows:
        raise ValueError("No rows were parsed from the raw file")

    row_ids = [row["row_id"] for row in rows]

    if len(row_ids) != len(set(row_ids)):
        raise ValueError("Duplicate row_id found")

    logger.info("Validation completed: %d rows",len(rows))


def load_to_bigquery(rows):
    try:
        client = bigquery.Client.from_service_account_json("key.json")

        json_rows = []

        for row in rows:
            row_copy = row.copy()

            for column in [
                "timestamp_col",
                "business_datetime",
                "created_datetime",
            ]:
                if row_copy[column] is not None:
                    row_copy[column] = row_copy[column].isoformat()

            json_rows.append(row_copy)

        job_config = bigquery.LoadJobConfig(schema=BQ_SCHEMA,write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,)

        job = client.load_table_from_json(json_rows,FULL_TABLE_ID,job_config=job_config,)

        job.result()

        table = client.get_table(FULL_TABLE_ID)

        logger.info("Loaded %d rows into %s", table.num_rows,FULL_TABLE_ID)

    except Exception:
        logger.exception("Failed to load data into BigQuery")
        raise


def main():
    logger.info("Starting Task 1 pipeline")

    download_raw_data()

    rows = read_raw_data()

    logger.info("Parsed %d rows",len(rows))

    validate_data(rows)

    load_to_bigquery(rows)

    logger.info("Task 1 pipeline completed successfully")


if __name__ == "__main__":
    main()