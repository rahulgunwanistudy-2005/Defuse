"""Verify build digests and in-toto SBOM/provenance in local OCI archives.

This checks artifact integrity and subject binding, not a third-party signature or trust policy.
Archives stay local; the small JSON summary can be included in submission evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def verify(path: Path) -> dict[str, Any]:
    with tarfile.open(path, "r") as archive:

        def read_json(
            name: str, descriptor: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            member = archive.getmember(name)
            if not member.isfile() or member.size > 80 * 1024 * 1024:
                raise ValueError("invalid or oversized OCI metadata")
            file = archive.extractfile(member)
            if file is None:
                raise ValueError("missing OCI metadata")
            raw = file.read()
            if descriptor is not None:
                actual = "sha256:" + hashlib.sha256(raw).hexdigest()
                if actual != descriptor["digest"] or len(raw) != descriptor["size"]:
                    raise ValueError("OCI descriptor integrity check failed")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise TypeError("OCI metadata must be an object")
            return result

        def blob(descriptor: dict[str, Any]) -> dict[str, Any]:
            algorithm, digest = descriptor["digest"].split(":", 1)
            if algorithm != "sha256" or len(digest) != 64:
                raise ValueError("unsupported OCI digest")
            return read_json("blobs/sha256/" + digest, descriptor)

        manifests: list[tuple[dict[str, Any], dict[str, Any]]] = []

        def traverse(index: dict[str, Any]) -> None:
            for descriptor in index["manifests"]:
                item = blob(descriptor)
                if "manifests" in item:
                    traverse(item)
                else:
                    manifests.append((descriptor, item))

        traverse(read_json("index.json"))
        images: dict[str, dict[str, Any]] = {}
        attestations = []
        for descriptor, manifest in manifests:
            if (
                descriptor.get("annotations", {}).get("vnd.docker.reference.type")
                == "attestation-manifest"
                or manifest.get("artifactType")
                == "application/vnd.docker.attestation.manifest.v1+json"
            ):
                attestations.append((descriptor, manifest))
            else:
                config = blob(manifest["config"])
                images[descriptor["digest"]] = {
                    "manifest_digest": descriptor["digest"],
                    "config_digest": manifest["config"]["digest"],
                    "platform": f"{config['os']}/{config['architecture']}",
                    "sbom": False,
                    "provenance": False,
                }
        if not images:
            raise ValueError("archive contains no runnable image")
        for descriptor, manifest in attestations:
            target = manifest.get("subject", {}).get("digest") or descriptor.get(
                "annotations", {}
            ).get("vnd.docker.reference.digest")
            if target not in images:
                raise ValueError("attestation is not bound to an image manifest")
            for layer in manifest["layers"]:
                if layer["mediaType"] != "application/vnd.in-toto+json":
                    continue
                statement = blob(layer)
                subjects = {
                    "sha256:" + item["digest"]["sha256"]
                    for item in statement.get("subject", [])
                    if "sha256" in item.get("digest", {})
                }
                if target not in subjects:
                    raise ValueError("in-toto subject does not match the image")
                predicate = statement.get("predicate", {})
                kind = statement.get("predicateType", "")
                if kind == "https://spdx.dev/Document" and predicate.get("packages"):
                    images[target]["sbom"] = True
                    images[target]["sbom_packages"] = len(predicate["packages"])
                if kind.startswith("https://slsa.dev/provenance/") and predicate:
                    images[target]["provenance"] = True
                    images[target]["provenance_type"] = kind
        if not all(image["sbom"] and image["provenance"] for image in images.values()):
            raise ValueError("every image must have a nonempty SBOM and provenance")
        return {"archive": str(path), "verified": True, "images": list(images.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build-evidence"))
    parser.add_argument(
        "--out", type=Path, default=Path("docs/evidence/docker-builds.json")
    )
    args = parser.parse_args()
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "verification": "OCI descriptor integrity and in-toto subject binding; not signed attestation",
        "components": [
            verify(args.directory / f"{name}.oci.tar")
            for name in ("engine", "web", "sinkhole")
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
