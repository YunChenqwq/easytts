import os

# Keep resources in the current folder by default.
os.environ.setdefault("GENIE_DATA_DIR", os.path.join(os.getcwd(), "GenieData"))

import genie_tts as genie


def main() -> None:
    # First run may download a predefined character model into ./CharacterModels
    genie.load_predefined_character("mika")

    out_path = os.path.join(os.getcwd(), "output_mika.wav")
    genie.tts(
        character_name="mika",
        text="どうしようかな……やっぱりやりたいかも……！",
        play=False,
        save_path=out_path,
    )
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

