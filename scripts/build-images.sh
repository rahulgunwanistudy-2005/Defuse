#!/bin/sh
# BuildKit creates SBOM and provenance attestations as part of each image build.
set -eu
export BUILDX_METADATA_PROVENANCE=max
: "${IMAGE_PREFIX:=defuse}"
: "${IMAGE_TAG:=local}"
: "${BUILD_OUTPUT:=--load}"
mkdir -p build-evidence
for component in engine web sinkhole; do
  if [ "$BUILD_OUTPUT" = oci ]; then
    # A classic local Docker image store cannot retain attestation manifest lists.
    # Keep the complete OCI archive, then load an identical runnable build separately.
    docker buildx build --output "type=oci,dest=build-evidence/$component.oci.tar" \
      --sbom=true --provenance=mode=max \
      --metadata-file "build-evidence/$component.json" \
      -t "$IMAGE_PREFIX/$component:$IMAGE_TAG" "$component"
    docker buildx build --load --sbom=false --provenance=false \
      --metadata-file "build-evidence/$component-runtime.json" \
      -t "$IMAGE_PREFIX/$component:$IMAGE_TAG" "$component"
  else
    docker buildx build "$BUILD_OUTPUT" --sbom=true --provenance=mode=max \
      --metadata-file "build-evidence/$component.json" \
      -t "$IMAGE_PREFIX/$component:$IMAGE_TAG" "$component"
  fi
done
