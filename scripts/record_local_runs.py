"""Record three fresh stateful model runs; never label these as live GitLab measurements."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"engine"))
from defuse.config import Settings
from defuse.scenario import scenario_ioc
from defuse.workflow import run_incident


async def record(out: Path) -> None:
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix="defuse-evidence-") as scratch:
        for n in range(1,4):
            settings=Settings(database_url=f"sqlite+aiosqlite:///{scratch}/run-{n}.db")
            start=perf_counter()
            run=await run_incident(settings,scenario_ioc(),f"evidence-{n}","defuse-sandbox",scenario=True)
            duration=round((perf_counter()-start)*1000,2)
            if run["status"]!="verified" or len(run["actions"])!=22:
                raise RuntimeError("stateful model run did not complete all actions")
            (out/f"run-{n}.json").write_text(json.dumps(run,indent=2)+"\n")
            results.append({"incident_id":run["incident_id"],"wall_clock_ms":duration,
                "actions":len(run["actions"]),"status":run["status"],"metrics":run["metrics"]})
    summary={"mode":"stateful-local-model","live_gitlab":False,"real_credentials":False,
        "runs":results,"median_wall_clock_ms":median(r["wall_clock_ms"] for r in results)}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=root/"docs/evidence/local-runs")
    asyncio.run(record(parser.parse_args().out))
