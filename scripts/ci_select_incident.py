"""Select exactly one committed incident request; refuse ambiguity rather than guess."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
explicit=os.environ.get("DEFUSE_INCIDENT_REQUEST")
if explicit:
    paths=[explicit]
else:
    before=os.environ.get("CI_COMMIT_BEFORE_SHA","")
    after=os.environ.get("CI_COMMIT_SHA","HEAD")
    if not before or set(before)=={"0"}:
        command=["git","diff-tree","--no-commit-id","--name-only","-r",after]
    else:
        command=["git","diff","--name-only",before,after]
    output=subprocess.run(command,cwd=root,check=True,capture_output=True,text=True).stdout
    paths=[p for p in output.splitlines() if p.startswith("incidents/") and p.endswith("/request.json")]
if len(paths)!=1:
    raise SystemExit("provide exactly one incident request, or set DEFUSE_INCIDENT_REQUEST")
selected=(root/paths[0]).resolve()
if not selected.is_relative_to(root/"incidents") or not selected.is_file():
    raise SystemExit("incident request must be a file under incidents/")
print(selected)
