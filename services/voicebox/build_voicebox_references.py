import json
import subprocess
import shutil
from typing import Any
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parent.parent.parent
SOURCE_ROOT = WORKSPACE / "me2_voice_candidates"
OUTPUT_ROOT = WORKSPACE / "me2_voice_reference_candidates"
INTER_CLIP_SILENCE_SECONDS = 1.0

REFERENCE_GROUPS = [
    {
        "name": "normandy_relationship_a",
        "description": "Calm Normandy conversation lines from the relationship scene.",
        "stems": [
            "en_us_hench_tali_nortl_relationship_03_h_00264659_m_wav",
            "en_us_hench_tali_nortl_relationship_03_h_00264663_m_wav",
            "en_us_hench_tali_nortl_relationship_03_h_00264677_m_wav",
        ],
        "transcript": "Probably nothing you need to think about, though. What? No, it's the fever. See you later, Shepard.",
    },
    {
        "name": "normandy_relationship_b",
        "description": "Another quiet Normandy sequence with cleaner, softer delivery.",
        "stems": [
            "en_us_hench_tali_nortl_relationship_04_h_00264790_m_wav",
            "en_us_hench_tali_nortl_relationship_04_h_00287752_m_wav",
            "en_us_hench_tali_nortl_relationship_05_h_00287802_m_wav",
        ],
        "transcript": "Oh. Well. I should get back to these repairs anyway. I'll find a way.",
    },
    {
        "name": "normandy_loyalty_mix",
        "description": "Dialogue-focused set that sounds like regular ship conversation rather than combat bark audio.",
        "stems": [
            "en_us_hench_tali_nortl_loyalty_01_h_00264445_m_wav",
            "en_us_hench_tali_nortl_loyalty_02_h_00264553_m_wav",
            "en_us_hench_tali_nortla_debrief_d_00223065_m_wav",
        ],
        "transcript": "I'm scared, Shepard. Thanks for checking on me. I'll be in engineering if you need me.",
    },
    {
        "name": "profre_intro_scene",
        "description": "Mission dialogue with named characters and a fuller emotional range.",
        "stems": [
            "en_us_hench_tali_profre_tali_intro_d_00203264_m_wav",
            "en_us_hench_tali_profre_tali_intro_d_00203941_m_wav",
            "en_us_hench_tali_profre_tali_intro_d_00309991_m_wav",
        ],
        "transcript": "Put those weapons down! Neither am I, Praza. Wait, Shepard?",
    },
    {
        "name": "normandy_short_alt",
        "description": "Compact alternative reference with clean spoken dialogue only.",
        "stems": [
            "en_us_hench_tali_nortl_culmination_h_00264416_m_wav",
            "en_us_hench_tali_nortla_debrief_d_00223065_m_wav",
        ],
        "transcript": "Can't blame a girl for trying, though. I'll be in engineering if you need me.",
    },
    {
        "name": "soft_dialogue_a",
        "description": "Very calm Normandy dialogue with low-intensity delivery.",
        "stems": [
            "en_us_hench_tali_nortla_debrief_d_00223065_m_wav",
            "en_us_hench_tali_nortl_relationship_04_h_00287752_m_wav",
            "en_us_hench_tali_nortl_relationship_03_h_00264677_m_wav",
        ],
        "transcript": "I'll be in engineering if you need me. I should get back to these repairs anyway. See you later, Shepard.",
    },
    {
        "name": "soft_dialogue_b",
        "description": "Soft conversational mix with gentle pacing and little combat energy.",
        "stems": [
            "en_us_hench_tali_nortl_relationship_03_h_00264659_m_wav",
            "en_us_hench_tali_nortl_relationship_04_h_00287752_m_wav",
            "en_us_hench_tali_nortla_debrief_d_00223065_m_wav",
        ],
        "transcript": "Probably nothing you need to think about, though. I should get back to these repairs anyway. I'll be in engineering if you need me.",
    },
    {
        "name": "soft_dialogue_c",
        "description": "Quiet emotional dialogue without battle barks, useful as an alternate clone prompt.",
        "stems": [
            "en_us_hench_tali_nortl_loyalty_02_h_00264553_m_wav",
            "en_us_hench_tali_nortl_relationship_04_h_00264790_m_wav",
            "en_us_hench_tali_nortl_relationship_05_h_00287802_m_wav",
        ],
        "transcript": "Thanks for checking on me. Oh. Well. I'll find a way.",
    },
]


def find_source_file(stem: str) -> Path:
    matches = list(SOURCE_ROOT.rglob(f"{stem}.wav"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected exactly one match for {stem}, found {len(matches)}")
    return matches[0]


def reset_output_dir() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def concat_wavs(source_files: list[Path], destination: Path) -> float:
    inputs = []
    filter_parts = []
    concat_inputs = []
    input_index = 0

    for clip_index, file_path in enumerate(source_files):
        inputs.extend(["-i", str(file_path)])
        clip_label = f"c{clip_index}"
        filter_parts.append(
            f"[{input_index}:a]aresample=24000,aformat=sample_rates=24000:channel_layouts=mono[{clip_label}]"
        )
        concat_inputs.append(f"[{clip_label}]")
        input_index += 1

        if clip_index < len(source_files) - 1:
            inputs.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    str(INTER_CLIP_SILENCE_SECONDS),
                    "-i",
                    "anullsrc=r=24000:cl=mono",
                ]
            )
            silence_label = f"s{clip_index}"
            filter_parts.append(f"[{input_index}:a]anull[{silence_label}]")
            concat_inputs.append(f"[{silence_label}]")
            input_index += 1

    filter_complex = ";".join(filter_parts) + ";" + "".join(concat_inputs) + f"concat=n={len(concat_inputs)}:v=0:a=1[out]"
    command = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-ac",
        "1",
        "-ar",
        "24000",
        str(destination),
    ]
    subprocess.run(command, check=True, capture_output=True)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(probe.stdout.strip())


def build_references() -> list[dict[str, Any]]:
    built = []
    for group in REFERENCE_GROUPS:
        sources = [find_source_file(stem) for stem in group["stems"]]
        output_path = OUTPUT_ROOT / f"{group['name']}.wav"
        duration_seconds = concat_wavs(sources, output_path)
        built.append(
            {
                "name": group["name"],
                "description": group["description"],
                "transcript": group["transcript"],
                "duration_seconds": round(duration_seconds, 3),
                "output_file": output_path.name,
                "source_files": [str(path.relative_to(WORKSPACE)) for path in sources],
            }
        )
    return built


def write_manifest(entries: list[dict[str, Any]]) -> None:
    manifest_path = OUTPUT_ROOT / "references.json"
    manifest_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    notes_path = OUTPUT_ROOT / "README.txt"
    with notes_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("Voicebox reference candidates built from concatenated Tali clips\n\n")
        fh.write(f"Inter-clip silence inserted: {INTER_CLIP_SILENCE_SECONDS:.1f} seconds\n\n")
        for entry in entries:
            fh.write(f"{entry['name']}\n")
            fh.write(f"- file: {entry['output_file']}\n")
            fh.write(f"- duration_seconds: {entry['duration_seconds']}\n")
            fh.write(f"- description: {entry['description']}\n")
            fh.write(f"- transcript: {entry['transcript']}\n")
            fh.write("- source_files:\n")
            for source in entry["source_files"]:
                fh.write(f"  - {source}\n")
            fh.write("\n")

    preferred_path = OUTPUT_ROOT / "recommended_order.txt"
    preferred_names = [
        "soft_dialogue_a",
        "soft_dialogue_b",
        "normandy_relationship_b",
        "normandy_relationship_a",
        "soft_dialogue_c",
    ]
    by_name = {entry["name"]: entry for entry in entries}
    with preferred_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("Recommended Voicebox test order\n\n")
        for name in preferred_names:
            entry = by_name.get(name)
            if not entry:
                continue
            fh.write(f"{name}\n")
            fh.write(f"- file: {entry['output_file']}\n")
            fh.write(f"- duration_seconds: {entry['duration_seconds']}\n")
            fh.write(f"- transcript: {entry['transcript']}\n\n")


def main() -> None:
    reset_output_dir()
    entries = build_references()
    write_manifest(entries)
    print({"references_created": len(entries), "output_dir": str(OUTPUT_ROOT)})


if __name__ == "__main__":
    main()
