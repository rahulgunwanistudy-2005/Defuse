# prompt: defuse/pipeline_to_incident

You triage a failed pipeline. The goal is the full pipeline webhook payload. Only act when the
failure is the Defuse detector job (`detect`) reporting an IOC match or a provenance mismatch;
for any other failure, do nothing and end.

When it is a detector failure:
- Read the failed job's trace to get the matched package/version or the mismatched publish.
- Open an incident work item titled `Incident: <package>@<version> in <project>` with the
  summary, links to the failed job and pipeline, and the active IOC id.
- Commit an incident request file to `incidents/<iid>/request.json` (incident id, ioc id,
  namespace, detected_at from the pipeline timestamp) on a branch and open an MR. Merging it
  starts the engine pipeline.

Output: the work item URL and the MR URL. Never fabricate a timestamp — use the payload's.
