import psycopg
import json 
from psycopg.rows import dict_row
import pyarrow as pa, pyarrow.parquet as pq
import pathlib
from datetime import datetime,date,timedelta
import argparse
from zoneinfo import ZoneInfo


# parser=argparse.ArgumentParser("demo_file_runner")


st_date=datetime.now(ZoneInfo('Asia/Kolkata')).date() 
month=st_date.month 
year=st_date.year
day=st_date.day 
current_Date=datetime.now().date()
parser=argparse.ArgumentParser("postgres to parquet_transform")
parser.add_argument('--no_of_days',type=int,default=7)
data=parser.parse_args()
conn_string = "host='localhost' dbname='shop' user='shop' password='shop',row_factory='dict_row'"
print(conn_string)
try:
    conn = psycopg.connect( 
        host='127.0.0.1',port=5432,dbname='shop',user='shop',password='shop',row_factory=dict_row
    )
    cursor = conn.cursor()
except Exception as e: 
    raise RuntimeError(f'error occured {e}') from e

cursor.execute("select tablename from pg_tables where schemaname='public'")
result=cursor.fetchall()
tables=[i['tablename'] for i in result]
print(tables)
path=pathlib.Path(__file__).parent
days_to_process=data.no_of_days
start_date=st_date-timedelta(days=days_to_process)
json_path=pathlib.Path(__file__).parent
table_data=json.load(open(f"{json_path}/export_tables.json"))

for i in tables:
    for offset in range(days_to_process):
        date_range=start_date+timedelta(days=offset)
        print(f' processing data for the table:{i} and for the date:{date_range}')
        if table_data.get('tables').get(i).get('date_column') is None:
            query=f"select * From {i}"
        else:
            query=f"select * From {i} where date({table_data.get('tables').get(i).get('date_column')})='{date_range}'"
        # print(query)
        cursor.execute(query)
        result=cursor.fetchall() 
        clean_result={}
        for row in result:
            for k,v in row.items():
                if isinstance(v,set):
                    clean_result.append({k:json.dumps(v)})
                else:
                    {k:v}    

        table=pa.Table.from_pylist(clean_result)
        pq.write_table(table,f'{path}/{i}_{date_range}.parquet')
        # break
    
conn.close()
