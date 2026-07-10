"""
Compare over_air_loss_tx.py and over_air_loss_rx.py CSV logs.
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


SUMMARY_FIELDS = [
    "test_id",
    "rate_hz",
    "tx_attempts",
    "tx_ok",
    "tx_fail",
    "rx_unique",
    "rx_duplicates",
    "lost",
    "loss_pct",
    "first_seq",
    "last_seq",
    "achieved_tx_hz",
]


def truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def read_tx(path, test_id):
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if not row.get("seq"):
                continue
            row_test_id = int(row["test_id"])
            if test_id is not None and row_test_id != test_id:
                continue
            rows.append(
                {
                    "test_id": row_test_id,
                    "rate_hz": row["rate_hz"],
                    "seq": int(row["seq"]),
                    "tx_ok": truthy(row.get("tx_ok")),
                    "elapsed_s": float(row.get("elapsed_s") or 0),
                }
            )
    return rows


def read_rx(path, test_id):
    counts = Counter()
    with Path(path).open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row.get("event") != "valid":
                continue
            if not row.get("seq") or not row.get("test_id"):
                continue
            row_test_id = int(row["test_id"])
            if test_id is not None and row_test_id != test_id:
                continue
            counts[(row_test_id, int(row["seq"]))] += 1
    return counts


def summarize(tx_rows, rx_counts):
    grouped = defaultdict(list)
    for row in tx_rows:
        grouped[(row["test_id"], row["rate_hz"])].append(row)

    summary = []
    for (test_id, rate_hz), rows in grouped.items():
        rows = sorted(rows, key=lambda item: item["seq"])
        ok_rows = [row for row in rows if row["tx_ok"]]
        ok_keys = {(row["test_id"], row["seq"]) for row in ok_rows}
        rx_unique = sum(1 for key in ok_keys if key in rx_counts)
        rx_duplicates = sum(max(0, rx_counts[key] - 1) for key in ok_keys)
        lost = len(ok_rows) - rx_unique
        loss_pct = (100.0 * lost / len(ok_rows)) if ok_rows else 0.0
        elapsed = rows[-1]["elapsed_s"] - rows[0]["elapsed_s"] if len(rows) > 1 else 0
        achieved = (len(rows) - 1) / elapsed if elapsed > 0 else 0

        summary.append(
            {
                "test_id": test_id,
                "rate_hz": rate_hz,
                "tx_attempts": len(rows),
                "tx_ok": len(ok_rows),
                "tx_fail": len(rows) - len(ok_rows),
                "rx_unique": rx_unique,
                "rx_duplicates": rx_duplicates,
                "lost": lost,
                "loss_pct": f"{loss_pct:.3f}",
                "first_seq": rows[0]["seq"] if rows else "",
                "last_seq": rows[-1]["seq"] if rows else "",
                "achieved_tx_hz": f"{achieved:.3f}",
            }
        )

    return sorted(summary, key=lambda row: (int(row["test_id"]), float(row["rate_hz"])))


def write_summary(rows, output):
    with Path(output).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows):
    if not rows:
        print("No matching TX/RX rows found.")
        return

    headers = ["rate", "tx_ok", "rx", "lost", "loss%", "dup", "achieved"]
    print(" | ".join(headers))
    print(" | ".join("-" * len(item) for item in headers))
    for row in rows:
        print(
            f"{row['rate_hz']} | {row['tx_ok']} | {row['rx_unique']} | "
            f"{row['lost']} | {row['loss_pct']} | {row['rx_duplicates']} | "
            f"{row['achieved_tx_hz']}"
        )


def main():
    parser = argparse.ArgumentParser(description="Analyze over-the-air packet loss")
    parser.add_argument("tx_csv")
    parser.add_argument("rx_csv")
    parser.add_argument("--test-id", type=int)
    parser.add_argument("--output", default="over_air_loss_summary.csv")
    args = parser.parse_args()

    tx_rows = read_tx(args.tx_csv, args.test_id)
    rx_counts = read_rx(args.rx_csv, args.test_id)
    rows = summarize(tx_rows, rx_counts)
    write_summary(rows, args.output)
    print_table(rows)
    print(f"\nSummary saved to {args.output}")


if __name__ == "__main__":
    main()
