# Demo script (video, under 2:55)

Show real GitLab UI for every claim (pipeline graph, MRs, work items), not only the console.

| Time | Beat | Shows |
| --- | --- | --- |
| 0:00 | Three numbers | 23% on dev machines; 2–7 min between orgs; "one order is safe". |
| 0:20 | A routine push infects the sandbox | GitLab pipeline on app-a; the console Live view fills in as SSE events arrive: loader@1.0.3, infected job, runner, host, readable secrets, the rogue strings@2.4.1 with no matching commit, the planted hook, the watcher. |
| 0:45 | Naive revoke-everything | Replay view, naive side: the sentinel directory shreds; the revocation handler and the dead-man's switch both fire. |
| 1:05 | Reset; paste the advisory | A worm-advisory work item; advisory-intake opens the IOC MR; merging it starts the engine. Exposure Map appears (d3-force, epidemic generations). |
| 1:45 | The child containment pipeline runs | GitLab pipeline graph reads as the plan (isolate → preserve → eradicate → rotate → quarantine → rebuild → verify). Plan view highlights the C1 "isolate before revoke" edge. The watcher never fires. |
| 2:25 | Metrics, record, policy MR | Record view timings; the postmortem work item and the policy MR (ignore-scripts, variable scope tightening). |
| 2:45 | Security Standard mapping + repo link | The lifecycle table; the public repo and the live console URL. |

Narration notes: no copyrighted music; every number on screen traces to a stored metric or a
cited source; never round a timing for effect.
