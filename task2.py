import pandas as pd
import calendar
from datetime import datetime, timezone
from google.cloud import storage
from google.cloud import bigquery
import re


# =========================
# Configuration
# =========================

PROJECT_ID = 'gcp-test-data-engineer'
DATASET_ID = 'exam_rienthong'
TABLE_ID = 'task2_data_result'

BUCKET_NAME = 'pttep-data-engineer-test'
BLOB_NAME = 'de-exam-task2/DE Exam raw data_20250101.xlsx'
LOCAL_FILE = 'DE Exam raw data_20250101.xlsx'


# =========================
# Download raw file from GCS
# =========================

storage_client = storage.Client.from_service_account_json('key.json')

bucket = storage_client.bucket(BUCKET_NAME)
blob = bucket.blob(BLOB_NAME)

blob.download_to_filename(LOCAL_FILE)

print('Downloaded:', LOCAL_FILE)


# =========================
# Read raw Excel
# =========================

df = pd.read_excel(
    LOCAL_FILE,
    sheet_name='Raw Data',
    header=None,
    skiprows=11
)


# =========================
# Transform data
# =========================

starts = [1, 7, 13, 19]

assets = [
    'Prod_Well_A',
    'Pressure_Tx',
    'Gas_Flow',
    'Temp_Sensor_1',
    'Inject_Pump_B'
]

result = []

for start in starts:

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

result = result[
    ['date', 'parameter', 'asset', 'nomination', 'load_ts']
]

# =========================
# Check result
# =========================

print(result.head(5).to_string(index=False))

print('\nDTYPES:')
print(result.dtypes)

print('\nSHAPE:', result.shape)


# =========================
# Save processed CSV
# =========================

result.to_csv(
    'task2_data_result.csv',
    index=False
)

print('\nCSV saved: task2_data_result.csv')


# =========================
# Load data into BigQuery
# =========================

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

print(f'Loaded {len(result)} rows into {table_ref}')