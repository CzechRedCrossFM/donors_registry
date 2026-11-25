"""Fetch private award artwork into the identical path in web and email images."""

import os
from pathlib import Path

from azure.identity import ManagedIdentityCredential
from azure.storage.blob import ContainerClient


def sync_assets():
    root = Path("/app/registry/static")
    counts = {"stamps": 0, "signatures": 0}
    with ManagedIdentityCredential(
        client_id=os.environ["AZURE_CLIENT_ID"]
    ) as credential:
        with ContainerClient.from_container_url(
            os.environ["ASSET_CONTAINER_URL"], credential
        ) as container:
            for blob in container.list_blobs():
                parts = blob.name.split("/")
                if (
                    len(parts) != 2
                    or parts[0] not in counts
                    or not parts[1].endswith(".png")
                ):
                    raise ValueError("Assets must be stamps/*.png or signatures/*.png")
                path = root / parts[0] / parts[1]
                path.write_bytes(container.download_blob(blob.name).readall())
                counts[parts[0]] += 1
    if not all(counts.values()):
        raise ValueError("At least one stamp and signature are required")


if __name__ == "__main__":
    sync_assets()
