import json
from pathlib import Path


def main() -> None:
    src = Path(__file__).resolve().parent / "output_modal_final" / "transcriptions_tali_only_review.jsonl"
    out = Path(__file__).resolve().parent / "output_modal_final" / "transcriptions_tali_only_review_minimal.txt"

    rows = [json.loads(line) for line in src.open("r", encoding="utf-8") if line.strip()]

    selected = []
    seen = set()
    for row in rows:
        if not row.get("review_flags"):
            continue
        stem = row["stem"]
        if stem in seen:
            continue
        seen.add(stem)
        selected.append(row)

    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for row in selected:
            fh.write(f"{row['stem']}\n")
            fh.write(f"- original: {row['text_original']}\n")
            fh.write(f"- clean: {row['text']}\n")
            fh.write(f"- review: {'; '.join(row['review_flags'])}\n\n")

    print({"count": len(selected), "path": str(out)})


if __name__ == "__main__":
    main()
