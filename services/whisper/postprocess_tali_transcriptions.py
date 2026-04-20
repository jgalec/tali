import json
import re
from collections import OrderedDict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent / "output_modal_final"
SOURCE_JSONL = BASE_DIR / "transcriptions_tali_only.jsonl"
CLEAN_JSONL = BASE_DIR / "transcriptions_tali_only_clean.jsonl"
CLEAN_TXT = BASE_DIR / "transcriptions_tali_only_clean.txt"
REVIEW_JSONL = BASE_DIR / "transcriptions_tali_only_review.jsonl"
REVIEW_TXT = BASE_DIR / "transcriptions_tali_only_review.txt"


EXACT_REPLACEMENTS = {
    "Disabling the MEX systems.": "Disabling the mech systems.",
    "draining their shields.": "Draining their shields.",
    "Combat thrown away.": "Combat drone away!",
    "Combat throne ready.": "Combat drone ready.",
}

STEM_REPLACEMENTS = {
    "en_us_hench_tali_ss_global_hench_tali_00285242_m_wav": "Garrus is down.",
    "en_us_hench_tali_ss_global_hench_tali_00285255_m_wav": "Kasumi's down.",
    "en_us_hench_tali_ss_global_hench_tali_00289268_m_wav": "The Krogan's back up!",
    "en_us_hench_tali_ss_global_hench_tali_00331255_m_wav": "Disabling the Mech systems.",
    "en_us_hench_tali_ss_global_hench_tali_00331271_m_wav": "Combat drone away.",
    "en_us_hench_tali_ss_global_hench_tali_00331272_m_wav": "Combat drone away.",
    "en_us_hench_tali_ss_global_hench_tali_00331274_m_wav": "Combat drone ready.",
    "en_us_hench_tali_ss_global_hench_tali_00332275_m_wav": "Allied fire!",
    "en_us_hench_tali_ss_global_hench_tali_00334310_m_wav": "Suppressing fire!",
}

WORD_REPLACEMENTS = {
    r"\btally\b": "Tali",
    r"\baquarian\b": "Quarian",
    r"\bquarry\b": "Quarian",
    r"\bshepard\b": "Shepard",
    r"\bchatika\b": "Chatika",
    r"\bgeth\b": "Geth",
}

REVIEW_PATTERNS = {
    r"\btally\b": "auto-corrected character name",
    r"\baquarian\b": "auto-corrected species name",
    r"\bquarry\b": "auto-corrected species name",
}


def normalize_text(stem: str, text: str) -> tuple[str, list[str]]:
    cleaned = text.strip()
    changes: list[str] = []

    stem_replacement = STEM_REPLACEMENTS.get(stem)
    if stem_replacement is not None and stem_replacement != cleaned:
        changes.append(f'stem override: "{cleaned}" -> "{stem_replacement}"')
        cleaned = stem_replacement

    replacement = EXACT_REPLACEMENTS.get(cleaned)
    if replacement is not None and replacement != cleaned:
        changes.append(f'exact: "{cleaned}" -> "{replacement}"')
        cleaned = replacement

    for pattern, replacement in WORD_REPLACEMENTS.items():
        updated = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        if updated != cleaned:
            changes.append(f'regex: /{pattern}/ -> "{replacement}"')
            cleaned = updated

    return cleaned, changes


def collect_review_flags(original_text: str) -> list[str]:
    lowered = original_text.lower()
    flags = []
    for pattern, reason in REVIEW_PATTERNS.items():
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            flags.append(reason)
    return sorted(set(flags))


def write_grouped_text(rows: list[dict], output_path: Path) -> None:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        grouped.setdefault(row["folder"], []).append(row)

    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        first_folder = True
        for folder, items in grouped.items():
            if not first_folder:
                fh.write("\n")
            first_folder = False
            fh.write(folder + "\n")
            for row in items:
                fh.write(f"- {row['stem']} ({row['duration']}): {row['text']}\n")


def write_review_text(rows: list[dict], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            reasons = "; ".join(row["review_flags"])
            changes = "; ".join(row["cleaning_changes"])
            fh.write(f"{row['folder']}\n")
            fh.write(f"- stem: {row['stem']}\n")
            fh.write(f"- original: {row['text_original']}\n")
            fh.write(f"- clean: {row['text']}\n")
            fh.write(f"- review: {reasons or 'none'}\n")
            fh.write(f"- changes: {changes or 'none'}\n\n")


def main() -> None:
    clean_rows: list[dict] = []
    review_rows: list[dict] = []

    with SOURCE_JSONL.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            row = json.loads(line)
            original_text = row["text"]
            cleaned_text, changes = normalize_text(row["stem"], original_text)
            review_flags = collect_review_flags(original_text)

            clean_row = dict(row)
            clean_row["text_original"] = original_text
            clean_row["text"] = cleaned_text
            clean_row["cleaning_changes"] = changes
            clean_row["review_flags"] = review_flags
            clean_rows.append(clean_row)

            if changes or review_flags:
                review_rows.append(clean_row)

    with CLEAN_JSONL.open("w", encoding="utf-8", newline="\n") as fh:
        for row in clean_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    with REVIEW_JSONL.open("w", encoding="utf-8", newline="\n") as fh:
        for row in review_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_grouped_text(clean_rows, CLEAN_TXT)
    write_review_text(review_rows, REVIEW_TXT)

    print(
        {
            "total_rows": len(clean_rows),
            "changed_rows": sum(1 for row in clean_rows if row["cleaning_changes"]),
            "review_rows": len(review_rows),
            "clean_jsonl": str(CLEAN_JSONL),
            "clean_txt": str(CLEAN_TXT),
            "review_jsonl": str(REVIEW_JSONL),
            "review_txt": str(REVIEW_TXT),
        }
    )


if __name__ == "__main__":
    main()
