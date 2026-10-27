"""Protected-CI guard: the allowlist must come from the trusted incident artifact."""
import argparse
import json
import subprocess
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--allowlist",type=Path,required=True)
parser.add_argument("--base",required=True)
parser.add_argument("--head",default="HEAD")
args=parser.parse_args()
allowed=set(json.loads(args.allowlist.read_text()))
changed=set(subprocess.run(["git","diff","--name-only",args.base,args.head],
    check=True,capture_output=True,text=True).stdout.splitlines())
if not changed<=allowed:
    raise SystemExit("protected diff guard rejected paths outside the trusted allowlist")
print(f"validated {len(changed)} changed paths")
