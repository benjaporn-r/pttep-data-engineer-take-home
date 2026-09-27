import pandas as pd
import calendar
from datetime import datetime, timezone
from google.cloud import storage
from google.cloud import bigquery
import re
import logging


PROJECT_ID = 'gcp-test-data-engineer'
DATASET_ID = 'exam_rienthong'
TABLE_ID = 'task2_data_result'
BUCKET_NAME = 'pttep-data-engineer-test'
BLOB_NAME = 'de-exam-task2/DE Exam raw data_20250101.xlsx'
LOCAL_FILE = 'DE Exam raw data_20250101.xlsx'


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def download_raw_file():
    try:
        storage_client = storage.Client.from_service_account_json('key.json')
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(BLOB_NAME)
        blob.download_to_filename(LOCAL_FILE)

        logger.info('Downloaded: %s', LOCAL_FILE)

    except Exception:
        logger.exception('Failed to download raw file from GCS')
        raise

def transform_data(df):
    # Monthly blocks start at column 1 and are 6 columns apart in the raw sheet.
    START_COLUMN = 1
    BLOCK_SIZE = 6

    assets = [
        'Prod_Well_A',
        'Pressure_Tx',
        'Gas_Flow',
        'Temp_Sensor_1',
        'Inject_Pump_B'
    ]

    result = []

    for start in range(
        START_COLUMN,
        START_COLUMN + 4 * BLOCK_SIZE,
        BLOCK_SIZE
    ):
        block_date = pd.Timestamp(df.iloc[0, start])

        days_in_month = calendar.monthrange(
            block_date.year,
            block_date.month
        )[1]

        for i, asset in enumerate(assets):
            temp = pd.DataFrame({
                'date': pd.date_range(
                    start=block_date.replace(day=1),
                    periods=days_in_month,
                    freq='D'
                ),
                'asset': asset,
                'nomination': df.iloc[
                    2:2 + days_in_month,
                    start + i
                ].values
            })

            result.append(temp)

    result = pd.concat(result, ignore_index=True)

    parameter_str = re.search(
        r'_(\d{8})\.xlsx$',
        LOCAL_FILE
    ).group(1)

    result['parameter'] = pd.to_datetime(parameter_str)
    result['date'] = result['date'].dt.date
    result['parameter'] = result['parameter'].dt.date

    result['nomination'] = pd.to_numeric(
        result['nomination'],
        errors='coerce'
    ).astype(float)

    result['load_ts'] = datetime.now(timezone.utc)

    return result[
        ['date', 'parameter', 'asset', 'nomination', 'load_ts']
    ]


def validate_data(result):
    if result.empty:
        raise ValueError('Transformed result is empty')

    if result['nomination'].isna().any():
        raise ValueError(
            'Nomination contains values that could not be converted to numeric'
        )


def load_to_bigquery(result):
    try:
        bigquery_client = bigquery.Client.from_service_account_json('key.json')
        table_ref = f'{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}'

        job_config = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField('date', 'DATE'),
                bigquery.SchemaField('parameter', 'DATE'),
                bigquery.SchemaField('asset', 'STRING'),
                bigquery.SchemaField('nomination', 'FLOAT'),
                bigquery.SchemaField('load_ts', 'TIMESTAMP'),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )

        job = bigquery_client.load_table_from_dataframe(
            result,
            table_ref,
            job_config=job_config
        )

        job.result()

        logger.info(
            'Loaded %d rows into %s',
            len(result),
            table_ref
        )

    except Exception:
        logger.exception('Failed to load data into BigQuery')
        raise


def main():
    logger.info('Starting Task 2 pipeline')

    download_raw_file()

    df = pd.read_excel(
        LOCAL_FILE,
        sheet_name='Raw Data',
        header=None,
        skiprows=11
    )

    result = transform_data(df)

    validate_data(result)

    logger.info('Transformation completed: %d rows', len(result))

    print(result.head(5).to_string(index=False))

    result.to_csv(
        'task2_data_result.csv',
        index=False
    )

    logger.info('CSV saved: task2_data_result.csv')

    load_to_bigquery(result)

    logger.info('Task 2 pipeline completed successfully')


if __name__ == '__main__':
    main()

