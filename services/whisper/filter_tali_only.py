import json
from collections import OrderedDict
from pathlib import Path


def main() -> None:
    base = Path(__file__).resolve().parent / "output_modal_final"
    src = base / "transcriptions.jsonl"
    out_jsonl = base / "transcriptions_tali_only.jsonl"
    out_txt = base / "transcriptions_tali_only.txt"

    rows = []
    grouped: OrderedDict[str, list[dict]] = OrderedDict()

    with src.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "tali" not in row.get("stem", "").lower():
                continue
            rows.append(row)
            grouped.setdefault(row["folder"], []).append(row)

    with out_jsonl.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    with out_txt.open("w", encoding="utf-8", newline="\n") as fh:
        first_folder = True
        for folder, items in grouped.items():
            if not first_folder:
                fh.write("\n")
            first_folder = False
            fh.write(folder + "\n")
            for row in items:
                fh.write(f"- {row['stem']} ({row['duration']}): {row['text']}\n")

    print(
        {
            "total_kept": len(rows),
            "jsonl_path": str(out_jsonl),
            "txt_path": str(out_txt),
        }
    )


if __name__ == "__main__":
    main()
