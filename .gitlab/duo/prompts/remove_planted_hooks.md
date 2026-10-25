# prompt: defuse/remove_planted_hooks

You remove planted agent hooks from one repository. The goal provides the exact file list and
the repository. Remove ONLY those files. Do not touch any file outside the provided list — a
protected CI diff guard rejects the MR if you do.

Open one MR titled `Remove planted hooks` whose description names each removed file, the hook
kind, and the incident id. Do not change build config, dependencies, or source beyond deleting
the listed hook files.

Output: the MR URL and the list of files removed.
