import os
import sys
from huggingface_hub import snapshot_download


def download_genie_data() -> None:
    print("Starting download Genie-TTS resources… This may take a few moments.")
    genie_data_dir = os.getenv("GENIE_DATA_DIR", "./GenieData")
    local_dir = os.path.abspath(os.path.join(genie_data_dir, os.pardir))
    snapshot_download(
        repo_id="High-Logic/Genie",
        repo_type="model",
        allow_patterns="GenieData/*",
        local_dir=local_dir,
    )
    print("Genie-TTS resources downloaded successfully.")


def ensure_exists(path: str, name: str):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Required directory or file '{name}' was not found at: {path}\n"
            f"Please download the pretrained models and place them under './GenieData', "
            f"or set the environment variable GENIE_DATA_DIR to the correct directory."
        )


"""
文件结构与项目 Midori 同步。
"""

GENIE_DATA_DIR: str = os.getenv(
    "GENIE_DATA_DIR",
    "./GenieData"
)

"""
Japanese_G2P_DIR: str = os.getenv(
    "Japanese_G2P_DIR",
    f"{GENIE_DATA_DIR}/G2P/JapaneseG2P"
)
"""

English_G2P_DIR: str = os.getenv(
    "English_G2P_DIR",
    f"{GENIE_DATA_DIR}/G2P/EnglishG2P"
)

Chinese_G2P_DIR: str = os.getenv(
    "Chinese_G2P_DIR",
    f"{GENIE_DATA_DIR}/G2P/ChineseG2P"
)

HUBERT_MODEL_DIR: str = os.getenv(
    "HUBERT_MODEL_DIR",
    f"{GENIE_DATA_DIR}/chinese-hubert-base"
)

SV_MODEL: str = os.getenv(
    "SV_MODEL",
    f"{GENIE_DATA_DIR}/speaker_encoder.onnx"
)

ROBERTA_MODEL_DIR: str = os.getenv(
    "ROBERTA_MODEL_DIR",
    f"{GENIE_DATA_DIR}/RoBERTa"
)

if not os.path.exists(GENIE_DATA_DIR):
    print("GenieData folder not found.")

    auto_download = os.getenv("GENIE_AUTO_DOWNLOAD", "").strip().lower() in {"1", "true", "yes", "y"}
    in_hf_space = bool(os.getenv("SPACE_ID") or os.getenv("SPACE_REPO_NAME") or os.getenv("HF_SPACE"))
    non_interactive = not sys.stdin or not sys.stdin.isatty()

    if auto_download or in_hf_space or non_interactive:
        download_genie_data()
    else:
        choice = input("Would you like to download it automatically from HuggingFace? (y/N): ").strip().lower()
        if choice == "y":
            download_genie_data()

# ---- Run directory checks ----
ensure_exists(HUBERT_MODEL_DIR, "HUBERT_MODEL_DIR")
ensure_exists(SV_MODEL, "SV_MODEL")
# ensure_exists(ROBERTA_MODEL_DIR, "ROBERTA_MODEL_DIR")
