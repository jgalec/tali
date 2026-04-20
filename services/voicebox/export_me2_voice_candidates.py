import shutil
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parent.parent.parent
SOURCE_AUDIO_ROOT = WORKSPACE / "me2_game_files"
SOURCE_DURATIONS = WORKSPACE / "me2_game_files_durations.txt"
SOURCE_TRANSCRIPTIONS = WORKSPACE / "services" / "whisper" / "output_modal_final" / "transcriptions.txt"
CANDIDATES_ROOT = WORKSPACE / "me2_voice_candidates"


def parse_durations() -> list[dict[str, str | int]]:
    entries = []
    current_folder = None

    for raw in SOURCE_DURATIONS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("- "):
            current_folder = line
            continue

        stem, duration = line[2:].split(": ", 1)
        if "hench_tali" not in stem.lower():
            continue

        minutes, seconds, millis = duration.split(":")
        total_ms = (int(minutes) * 60 + int(seconds)) * 1000 + int(millis)
        entries.append(
            {
                "folder": current_folder,
                "stem": stem,
                "duration": duration,
                "total_ms": total_ms,
            }
        )

    unique_by_stem: dict[str, dict[str, str | int]] = {}
    for entry in entries:
        unique_by_stem.setdefault(str(entry["stem"]), entry)

    return sorted(unique_by_stem.values(), key=lambda item: int(item["total_ms"]), reverse=True)


def parse_transcriptions() -> dict[tuple[str, str], str]:
    entries: dict[tuple[str, str], str] = {}
    current_folder = None

    for raw in SOURCE_TRANSCRIPTIONS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("- "):
            current_folder = line
            continue
        if current_folder is None:
            continue

        head, text = line[2:].split(": ", 1)
        stem = head.rsplit(" (", 1)[0]
        entries[(current_folder, stem)] = text

    return entries


def reset_candidates_root() -> None:
    if CANDIDATES_ROOT.exists():
        shutil.rmtree(CANDIDATES_ROOT)
    CANDIDATES_ROOT.mkdir(parents=True, exist_ok=True)


def copy_audio_files(entries: list[dict[str, str | int]]) -> None:
    for entry in entries:
        folder = str(entry["folder"])
        stem = str(entry["stem"])
        source_dir = SOURCE_AUDIO_ROOT / folder
        matches = [path for path in source_dir.iterdir() if path.is_file() and path.stem == stem]
        if not matches:
            raise FileNotFoundError(f"Missing source audio for {folder}/{stem}")

        destination_dir = CANDIDATES_ROOT / folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(matches[0], destination_dir / matches[0].name)


def write_selection(entries: list[dict[str, str | int]]) -> None:
    output_path = CANDIDATES_ROOT / "selection.txt"
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("Longest unique hench_tali clips copied from me2_game_files\n\n")
        for entry in entries:
            fh.write(f"{entry['folder']}\n")
            fh.write(f"- {entry['stem']}: {entry['duration']}\n\n")


def write_transcriptions(entries: list[dict[str, str | int]], transcriptions: dict[tuple[str, str], str]) -> None:
    output_path = CANDIDATES_ROOT / "transcriptions.txt"
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        last_folder = None
        for entry in entries:
            folder = str(entry["folder"])
            stem = str(entry["stem"])
            duration = str(entry["duration"])
            text = transcriptions.get((folder, stem), "")

            if folder != last_folder:
                if last_folder is not None:
                    fh.write("\n")
                fh.write(folder + "\n")
                last_folder = folder

            fh.write(f"- {stem} ({duration}): {text}\n")


def main() -> None:
    entries = parse_durations()
    transcriptions = parse_transcriptions()

    reset_candidates_root()
    copy_audio_files(entries)
    write_selection(entries)
    write_transcriptions(entries, transcriptions)

    print(
        {
            "copied_files": len(entries),
            "output_dir": str(CANDIDATES_ROOT),
            "transcriptions_file": str(CANDIDATES_ROOT / 'transcriptions.txt'),
        }
    )


if __name__ == "__main__":
    main()
