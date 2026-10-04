import boto3 
from pathlib import Path
from datetime import datetime


client=boto3.client("s3", region_name="us-east-1")

shop_dir=Path(__file__).parent

parquet_files=sorted(shop_dir.glob("*.parquet"))

path='s3://myshopraw/raw/shop/'

print(f"Found {len(parquet_files)} parquet files to upload.")
for i in parquet_files:
    print(f"Uploading {i.name} to S3...")
    path=i.name.split(".")[0]
    client.upload_file(str(i),"myshopraw", f"raw/shop/{path}/{datetime.now().strftime('%Y-%m-%d')}+{i.name}")
