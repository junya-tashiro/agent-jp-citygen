"""Invoke the unchanged GUI compiler without starting a browser or server."""
import json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def compile_roads(request):
    result=subprocess.run(['node',str(ROOT/'city_generator/roads.mjs')],input=json.dumps(request),text=True,capture_output=True)
    try: data=json.loads(result.stdout)
    except ValueError: raise ValueError('Road compiler failed: '+result.stderr) from None
    if not data.get('valid'):raise ValueError('\n'.join(data.get('errors',[])))
    return data
