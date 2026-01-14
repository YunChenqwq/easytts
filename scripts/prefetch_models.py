import os
from typing import Iterable

from huggingface_hub import snapshot_download


def prefetch_genie_data(local_dir: str = ".") -> None:
    snapshot_download(
        repo_id="High-Logic/Genie",
        repo_type="model",
        allow_patterns="GenieData/*",
        local_dir=local_dir,
    )


def prefetch_characters(characters: Iterable[str], version: str = "v2ProPlus", local_dir: str = ".") -> None:
    for chara in characters:
        remote_path = f"CharacterModels/{version}/{chara}/*"
        snapshot_download(
            repo_id="High-Logic/Genie",
            repo_type="model",
            allow_patterns=remote_path,
            local_dir=local_dir,
        )


if __name__ == "__main__":
    local_dir = os.getenv("PREFETCH_DIR", ".")
    version = os.getenv("PREFETCH_VERSION", "v2ProPlus")
    chars = [c.strip() for c in os.getenv("PREFETCH_CHARACTERS", "mika,feibi,thirtyseven").split(",") if c.strip()]

    print(f"Prefetch dir: {os.path.abspath(local_dir)}")
    print("Downloading GenieData...")
    prefetch_genie_data(local_dir=local_dir)
    print("Downloading predefined characters...")
    prefetch_characters(chars, version=version, local_dir=local_dir)
    print("Done.")
