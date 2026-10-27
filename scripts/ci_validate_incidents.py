"""CI boundary for every committed IOC and incident request."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"engine"))
from defuse.model.ioc import IOCSet
from defuse.workflow import IncidentRequest

root=Path(__file__).resolve().parents[1]
for path in sorted((root/"incidents").glob("**/*.json")):
    model=IOCSet if path.name=="ioc.json" else IncidentRequest if path.name=="request.json" else None
    if model:
        model.model_validate_json(path.read_text())
        print(f"validated {path.relative_to(root)}")
