# sinkhole

Tiny FastAPI service that records simulator beacons (a canary id and the *names* of readable CI
variables — never values). Verification queries `/beacons?window=120` and passes only if the
count is zero, proving the contained worm stopped calling home.

Run: `uvicorn sinkhole.app:app --port 8080`. Deployed as a Cloud Run service in `infra/`.
