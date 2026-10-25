# Contract fixtures

Each file is a recorded-shape GitLab API response, keyed by `METHOD path?query`. They are
synthetic (hand-written from the GitLab REST reference, see `docs/decisions.md` D4) until
`defuse fixtures record` replaces them with scrubbed recordings from a live sandbox.

`routes.json` maps request keys to the file that answers them. The contract test replays them
through an httpx MockTransport and asserts the collector reproduces the sandbox infection.
