from cassandra.cluster import Cluster
from cassandra.util import Date as CassDate
from collections.abc import Mapping
from decimal import Decimal
import datetime
import uuid
import pyarrow as pa, pyarrow.parquet as pq
import pathlib

port = 9042
host = 'localhost'
path_lib=pathlib.Path(__file__).parent

def clean(v):
    if v is None or isinstance(v, (str, int, float, bool, bytes)):
        return v
    if isinstance(v, Mapping):
        return {str(k): clean(x) for k, x in dict(v).items()}
    if isinstance(v, (list, tuple, set)):
        return [clean(x) for x in v]
    if isinstance(v, CassDate):
        return v.date()
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    return str(v)

def export():

    cluster = Cluster([host], port=port)
    conn = cluster.connect()
    my_keyspace = 'shop'

    query=f'''
    select table_name from system_schema.tables where keyspace_name='{my_keyspace}';
    '''

    result=[r.table_name for r in conn.execute(query)]


    for each in result:
        rows = conn.execute(f'SELECT * FROM {my_keyspace}.{each}')
        print(f"Table: {each}")
        pylist = [{k: clean(v) for k, v in r._asdict().items()} for r in rows]
        table = pa.Table.from_pylist(pylist)
    
        pq.write_table(table, f'{path_lib}/{each}.parquet')

    cluster.shutdown()

if __name__ == '__main__':
    print(pathlib.Path(__file__).parent)
    export()