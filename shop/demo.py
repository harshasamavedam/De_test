import json  
import pathlib 


loc=pathlib.Path(__file__).parent
print(f'{loc}\export_tables.json')

data=json.load(open(f'{loc}\export_tables.json'))
print(data)