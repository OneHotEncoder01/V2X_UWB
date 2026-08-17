"""Generate figures from the 2026-07-14 sequenced indoor UWB range tests."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "measurements" / "2026-07-14_indoor_range"

# Figures always land in figures/. To also write them somewhere else (e.g. the
# figures directory of a separate write-up repository), set a path list:
#   V2X_FIGURE_OUT_DIRS=/path/to/other/figures python figures/generate_indoor_range_figures.py
OUT_DIRS = [ROOT / "figures"] + [
    Path(entry)
    for entry in os.environ.get("V2X_FIGURE_OUT_DIRS", "").split(os.pathsep)
    if entry
]

TESTS = [
    (2714, "2,5 m LOS", 300, "v2x_rx_baseline_2714.csv"),
    (2715, "2,5 m TX 90°", 300, "v2x_rx_tx90_2715.csv"),
    (2716, "2,5 m RX 90°", 300, "v2x_rx_rx90_2716.csv"),
    (2717, "2,5 m Körper", 300, "v2x_rx_body_2717.csv"),
    (2718, "2,5 m Glas", 300, "v2x_rx_glass_2718.csv"),
    (2724, "7 m NLOS\nWandecke", 300, "v2x_rx_7m_corner_2724.csv"),
    (2726, "7 m LOS", 300, "v2x_rx_7m_los_2726.csv"),
    (2728, "8 m LOS\nKonfig. A", 300, "v2x_rx_8m_los_2728.csv"),
    (2731, "8 m LOS\nKonfig. A lang", 1000, "v2x_rx_8m_los_r1_2731.csv"),
    (2733, "8 m LOS\nKonfig. B, Lauf 1", 1000, "v2x_rx_8m_los_r2_2733.csv"),
    (2734, "8 m LOS\nKonfig. B, Lauf 2", 1000, "v2x_rx_8m_los_r3_2734.csv"),
    (2735, "8 m Körper", 1000, "v2x_rx_8m_body_2735.csv"),
    (2736, "8 m Erholung", 1000, "v2x_rx_8m_recovery_2736.csv"),
]


def load_rx(path: Path):
    valid_sequences = set()
    rx_errors = 0
    invalid = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            status = row.get("event", row.get("status", ""))
            if status == "valid" and row.get("seq"):
                valid_sequences.add(int(row["seq"]))
            elif status == "rx_error":
                rx_errors += 1
            elif status:
                invalid += 1
    return valid_sequences, rx_errors, invalid


def collect():
    rows = []
    for test_id, label, packets, filename in TESTS:
        sequences, rx_errors, invalid = load_rx(DATA / filename)
        received = len(sequences)
        rows.append(
            {
                "test_id": test_id,
                "label": label,
                "packets": packets,
                "received": received,
                "lost": packets - received,
                "pdr_percent": received / packets * 100,
                "loss_percent": (packets - received) / packets * 100,
                "rx_errors": rx_errors,
                "invalid": invalid,
                "sequences": sequences,
            }
        )
    return rows


def style():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "figure.dpi": 160,
            "savefig.dpi": 300,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
        }
    )


def save(fig, stem):
    for directory in OUT_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
        fig.savefig(directory / f"{stem}.pdf", bbox_inches="tight")
        fig.savefig(directory / f"{stem}.png", bbox_inches="tight")
    plt.close(fig)


def write_summary(rows):
    path = DATA / "indoor_range_summary.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "test_id",
                "label",
                "packets",
                "received",
                "lost",
                "pdr_percent",
                "loss_percent",
                "rx_errors",
                "invalid",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})


def plot_distance_comparison(by_id):
    ids = [2726, 2724, 2731, 2733, 2734]
    labels = [
        "7 m\nLOS",
        "7 m\nNLOS",
        "8 m\nKonfig. A",
        "8 m\nKonfig. B\nLauf 1",
        "8 m\nKonfig. B\nLauf 2",
    ]
    values = [by_id[item]["pdr_percent"] for item in ids]
    colors = ["#2b8cbe", "#d95f0e", "#d95f0e", "#2ca25f", "#2ca25f"]

    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    bars = ax.bar(labels, values, color=colors, edgecolor="#333333", linewidth=0.6)
    ax.set_ylabel("Packet Delivery Ratio [%]")
    ax.set_ylim(0, 108)
    ax.set_title("Empfangsrate an der indoor Reichweitengrenze")
    ax.grid(axis="x", visible=False)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2,
            f"{value:.1f} %",
            ha="center",
            va="bottom",
            fontweight="bold",
        )
    fig.tight_layout()
    save(fig, "indoor_range_pdr")


def plot_blockage_sequence(by_id):
    ids = [2733, 2734, 2735, 2736]
    labels = ["LOS Lauf 1", "LOS Lauf 2", "Körperblockade", "Pfad wieder frei"]
    values = [by_id[item]["pdr_percent"] for item in ids]
    colors = ["#2ca25f", "#2ca25f", "#cb181d", "#fec44f"]

    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    bars = ax.bar(labels, values, color=colors, edgecolor="#333333", linewidth=0.6)
    ax.set_ylabel("Packet Delivery Ratio [%]")
    ax.set_ylim(0, 108)
    ax.set_title("Baseline–Blockade–Erholung bei 8 m")
    ax.grid(axis="x", visible=False)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2,
            f"{value:.1f} %",
            ha="center",
            fontweight="bold",
        )
    fig.tight_layout()
    save(fig, "indoor_body_blockage")


def plot_cumulative(by_id):
    selections = [
        (2726, "7 m LOS", "#2b8cbe"),
        (2724, "7 m NLOS/Wandecke", "#d95f0e"),
        (2733, "8 m LOS, stabile Konfiguration", "#2ca25f"),
        (2736, "8 m nach Körperblockade", "#756bb1"),
    ]
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    for test_id, label, color in selections:
        row = by_id[test_id]
        x = np.arange(1, row["packets"] + 1)
        delivered = np.fromiter(
            (1 if seq in row["sequences"] else 0 for seq in x), dtype=int
        )
        ax.plot(x, np.cumsum(delivered), label=label, color=color, linewidth=2)
    ax.set_xlabel("Gesendete Sequenznummer")
    ax.set_ylabel("Kumulativ empfangene CAMs")
    ax.set_title("Zeitlicher Verlauf ausgewählter Reichweitentests")
    ax.legend(loc="upper left", frameon=True)
    fig.tight_layout()
    save(fig, "indoor_range_cumulative")


def main():
    style()
    rows = collect()
    by_id = {row["test_id"]: row for row in rows}
    write_summary(rows)
    plot_distance_comparison(by_id)
    plot_blockage_sequence(by_id)
    plot_cumulative(by_id)
    print(f"Generated 3 figure pairs and {DATA / 'indoor_range_summary.csv'}")


if __name__ == "__main__":
    main()
