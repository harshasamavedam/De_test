import duckdb as duck
import pathlib

def read_data_from_s3(folder_path): 
    # Connect to DuckDB
    con = duck.connect()

    # Read Parquet files from S3
    query = f"""
        SELECT *
        FROM read_parquet('s3://myshopraw/raw/shop/{folder_path}/*.parquet')
        limit 10
    """
    df = con.execute(query).fetchdf()

    return df

print("Reading data from S3...")
# df = read_data_from_s3()
for each in (list((pathlib.Path(__file__).parent).glob("*.parquet"))):
    print(f"reading data from s3 for {each.name}...")
    df=read_data_from_s3(each.name.split(".")[0])
    print(f"Data read from S3 for {each.name}:")
    print(df.head(2))


