from huggingface_hub import snapshot_download
import os
from typing import Dict

CHARA_LANG: Dict[str, str] = {
    "mika": "Japanese",
    "feibi": "Chinese",
    "thirtyseven": "English",
}
CHARA_ALIAS_MAP: Dict[str, str] = {
    "mika": "mika",
    "misono mika": "mika",
    "淵坩隆雑": "mika",
    "隆雑": "mika",
    "みその みか": "mika",
    "feibi": "feibi",
    "憩曳": "feibi",
    "37": "thirtyseven",
    "thirtyseven": "thirtyseven",
}


def download_chara(chara: str, version: str = "v2ProPlus") -> str:
    local_dir = os.path.join("CharacterModels", version, chara)
    if os.path.exists(local_dir):
        print(f"Model for '{chara}' already exists locally. Skipping download.")
        return local_dir

    print(f"Starting download of model for character '{chara}'. This may take a few moments...")
    remote_path = f"CharacterModels/{version}/{chara}/*"
    snapshot_download(
        repo_id="High-Logic/Genie",
        repo_type="model",
        allow_patterns=remote_path,
        local_dir=".",
    )
    print(f"All model files for '{chara}' have been downloaded to '{os.path.abspath(local_dir)}'.")
    return local_dir
