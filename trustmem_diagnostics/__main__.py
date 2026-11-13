import argparse
import json

from .sap import diagnose

p=argparse.ArgumentParser(description='Read-only stage diagnostics; no model calls')
p.add_argument('--original',required=True)
p.add_argument('--continuation',required=True)
p.add_argument('--output',required=True)
args=p.parse_args()
print(json.dumps(diagnose(args.original,args.continuation,args.output),ensure_ascii=False))
