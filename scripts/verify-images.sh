#!/bin/sh
set -eu
: "${CI_REGISTRY_IMAGE:?required}"
: "${CI_COMMIT_SHORT_SHA:?required}"
for component in engine web sinkhole; do
  image="$CI_REGISTRY_IMAGE/$component:$CI_COMMIT_SHORT_SHA"
  docker buildx imagetools inspect "$image" --format '{{ json .Provenance.SLSA }}' > "build-evidence/$component-provenance.json"
  docker buildx imagetools inspect "$image" --format '{{ json .SBOM.SPDX }}' > "build-evidence/$component-sbom.json"
  # Empty/null attestations are a build failure, never successful provenance evidence.
  test "$(wc -c < "build-evidence/$component-provenance.json")" -gt 10
  test "$(wc -c < "build-evidence/$component-sbom.json")" -gt 10
done
