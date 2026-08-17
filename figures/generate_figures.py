"""
Generates figures from the received-message database cam_messages.sqlite3.
Run from the project root:  venv/bin/python figures/generate_figures.py
Output: figures/*.pdf (vector, ready for LaTeX) + figures/*.png (preview)

Note: comments and figure labels in this script are in German.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Ellipse
import numpy as np
from scipy.stats import chi2

# ── Stil ───────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
})

ACCENT  = "#0f766e"
ORANGE  = "#b45309"
GREY    = "#64748b"
LIGHT   = "#e2e8f0"
OUT_DIR = Path(__file__).parent
DB_PATH = Path(__file__).parent.parent / "cam_messages.sqlite3"


def save(fig, name):
    fig.savefig(OUT_DIR / f"{name}.pdf")
    fig.savefig(OUT_DIR / f"{name}.png")
    print(f"  gespeichert: {name}.pdf / .png")
    plt.close(fig)


# ── Daten laden ────────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute("""
    SELECT received_at, latitude, longitude, altitude_m,
           speed_mps, heading_deg, generation_delta_time,
           length(raw_hex)/2
    FROM messages_cammessage
    ORDER BY received_at
""")
rows = cur.fetchall()
con.close()

times  = [datetime.fromisoformat(r[0]) for r in rows]
lats   = np.array([r[1] for r in rows], dtype=float)
lons   = np.array([r[2] for r in rows], dtype=float)
alts   = np.array([r[3] if r[3] is not None else np.nan for r in rows])
gdts   = np.array([r[6] for r in rows], dtype=int)
sizes  = np.array([r[7] for r in rows], dtype=int)

# Sitzungen erkennen (Lücke > 30 s)
gaps = np.array([(times[i+1]-times[i]).total_seconds() for i in range(len(times)-1)])
breaks = np.where(gaps > 30)[0]
session_ids = np.zeros(len(times), dtype=int)
for i, b in enumerate(breaks):
    session_ids[b+1:] = i+1

# Sitzung 4 (Index 3) — 335 Nachrichten, Hauptauswertung
S4    = session_ids == 3
t4    = [t for t, m in zip(times, S4) if m]
lats4 = lats[S4]
lons4 = lons[S4]
alts4 = alts[S4]
gdts4 = gdts[S4]

# Ankunftszeitabstände für Sitzung 4
iat4   = np.array([(t4[i+1]-t4[i]).total_seconds() for i in range(len(t4)-1)])
t4_rel = np.array([(t - t4[0]).total_seconds() for t in t4])

# Umrechnung Lat/Lon → lokale Meter (Flacherd-Näherung)
lat0  = lats4.mean()
lon0  = lons4.mean()
LON_M = 111_320.0 * np.cos(np.radians(lat0))
LAT_M = 111_320.0
x4 = (lons4 - lon0) * LON_M
y4 = (lats4 - lat0) * LAT_M


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 1 — GPS-Positionsstreuung mit 95-%-Konfidenzellipse
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 1 — GPS-Positionsstreuung")

cov             = np.cov(x4, y4)
eigval, eigvec  = np.linalg.eigh(cov)
order           = eigval.argsort()[::-1]
eigval, eigvec  = eigval[order], eigvec[:, order]
angle           = np.degrees(np.arctan2(*eigvec[:, 0][::-1]))
scale           = np.sqrt(chi2.ppf(0.95, df=2))
w, h            = 2 * scale * np.sqrt(eigval)

fig, ax = plt.subplots(figsize=(5.5, 5))
ax.scatter(x4, y4, s=14, alpha=0.55, color=ACCENT, linewidths=0, zorder=3)
ax.scatter([0], [0], marker="+", s=120, color=ORANGE, linewidths=1.8,
           zorder=5, label="Mittlere Position")
ellipse = Ellipse(xy=(0, 0), width=w, height=h, angle=angle,
                  edgecolor=ORANGE, facecolor="none", linewidth=1.5,
                  linestyle="--", zorder=4, label="95-%-Konfidenzellipse")
ax.add_patch(ellipse)
ax.set_aspect("equal")
ax.set_xlabel("Östlicher Versatz (m)")
ax.set_ylabel("Nördlicher Versatz (m)")
ax.set_title("GPS-Positionsstreuung — stationärer Empfänger (n = 335)")
ax.legend(frameon=False, fontsize=10)

r   = np.sqrt(x4**2 + y4**2)
cep = np.percentile(r, 50)
ax.annotate(f"CEP₅₀ = {cep*100:.0f} cm",
            xy=(cep, 0), xytext=(cep + 0.3, 0.5), fontsize=9,
            arrowprops=dict(arrowstyle="->", color=GREY, lw=0.9), color=GREY)

save(fig, "abb1_gps_streuung")


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 2 — Höhenverlauf (Sitzung 4)
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 2 — Höhenverlauf")

mean_alt = np.nanmean(alts4)
std_alt  = np.nanstd(alts4)

fig, ax = plt.subplots(figsize=(7, 3.2))
ax.plot(t4_rel, alts4, color=ACCENT, linewidth=1.2, zorder=3)
ax.fill_between(t4_rel, alts4, mean_alt, alpha=0.12, color=ACCENT)
ax.axhline(mean_alt, color=ORANGE, linewidth=1.0, linestyle="--",
           label=f"Mittelwert = {mean_alt:.1f} m")
ax.set_xlabel("Zeit in der Sitzung (s)")
ax.set_ylabel("Höhe (m, WGS-84)")
ax.set_title("Vom GPS gemeldete Höhe — stationär (Sitzung 4)")
ax.legend(frameon=False, fontsize=10)
ax.annotate(f"σ = {std_alt:.2f} m", xy=(0.98, 0.08),
            xycoords="axes fraction", ha="right", fontsize=9, color=GREY)

save(fig, "abb2_hoehe")


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 3 — Ankunftszeitabstand (Sitzung 4)
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 3 — Ankunftszeitabstand")

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.hist(iat4[iat4 < 10], bins=30,
        color=ACCENT, edgecolor="white", linewidth=0.4)
ax.axvline(np.median(iat4), color=ORANGE, linewidth=1.4, linestyle="--",
           label=f"Median = {np.median(iat4):.2f} s")
ax.axvline(np.mean(iat4),   color=ORANGE, linewidth=1.4, linestyle=":",
           label=f"Mittelwert = {np.mean(iat4):.2f} s")
ax.set_xlabel("Ankunftszeitabstand (s)")
ax.set_ylabel("Anzahl")
ax.set_title("CAM-Ankunftszeitabstand (Sitzung 4, n = 334 Intervalle)")
ax.legend(frameon=False, fontsize=10)
ax.annotate(f"σ = {iat4.std():.2f} s", xy=(0.98, 0.88),
            xycoords="axes fraction", ha="right", fontsize=9, color=GREY)

save(fig, "abb3_ankunftszeit")


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 4 — Nutzlastkodierungsgröße (Vergleich)
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 4 — Nutzlastkodierungsgrößen")

json_bytes = len((
    '{"generationDeltaTime":12345,"latitude":48.8350074,'
    '"longitude":10.1035437,"altitude_m":448.1,"speed_mps":0.0,'
    '"heading_deg":null,"drive_direction":"unavailable"}'
).encode())

beschriftungen = [
    "ASN.1 UPER\n(dieses Projekt)",
    "JSON\n(gleiche Felder)",
    "ASN.1 BER\n(unkodiert, gesch.)",
]
werte   = [35, json_bytes, 58]
farben  = [ACCENT, ORANGE, GREY]

fig, ax = plt.subplots(figsize=(5, 3.5))
balken  = ax.bar(beschriftungen, werte, color=farben, width=0.5, zorder=3)
ax.set_ylabel("Kodierte Größe (Bytes)")
ax.set_title("Vergleich der CAM-Nutzlastkodierung")
ax.set_ylim(0, max(werte) * 1.25)
for b, v in zip(balken, werte):
    ax.text(b.get_x() + b.get_width()/2, v + 1.5, str(v),
            ha="center", va="bottom", fontsize=11, fontweight="bold")
ax.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
ax.set_axisbelow(True)

save(fig, "abb4_nutzlastgroesse")


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 5 — generationDeltaTime über die Zeit (Überlaufverhalten)
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 5 — generationDeltaTime")

fig, ax = plt.subplots(figsize=(7, 3.2))
ax.plot(t4_rel, gdts4, color=ACCENT, linewidth=0.9, zorder=3)
ax.set_xlabel("Zeit in der Sitzung (s)")
ax.set_ylabel("generationDeltaTime")
ax.set_title("ITS-Zeitstempelfeld (mod 65 536) — Sitzung 4")
ax.axhline(0,     color=LIGHT, linewidth=0.7, zorder=0)
ax.axhline(65535, color=LIGHT, linewidth=0.7, zorder=0)

überläufe = np.where(np.diff(gdts4) < -30000)[0]
if len(überläufe):
    ax.annotate("Überlauf\n(mod 65 536)",
                xy=(t4_rel[überläufe[0]+1], gdts4[überläufe[0]+1]),
                xytext=(t4_rel[überläufe[0]+1] + 10, 15000),
                fontsize=9, color=GREY,
                arrowprops=dict(arrowstyle="->", color=GREY, lw=0.9))

save(fig, "abb5_zeitstempel")


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 6 — Nachrichten pro Testsitzung
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 6 — Nachrichten pro Sitzung")

sitzungs_labels  = ["19. Jun\n11:18", "23. Jun\n09:01", "23. Jun\n10:05", "26. Jun\n02:55"]
sitzungs_anzahl  = [int((session_ids == i).sum()) for i in range(4)]
sitzungs_dauer   = []
for i in range(4):
    ts = [t for t, m in zip(times, session_ids == i) if m]
    sitzungs_dauer.append((ts[-1]-ts[0]).total_seconds())

fig, ax1 = plt.subplots(figsize=(6, 3.5))
ax2 = ax1.twinx()
balken = ax1.bar(sitzungs_labels, sitzungs_anzahl, color=ACCENT, alpha=0.85,
                 width=0.5, zorder=3)
ax2.plot(sitzungs_labels, sitzungs_dauer, "o--", color=ORANGE,
         linewidth=1.4, markersize=6, label="Dauer (s)")
ax1.set_ylabel("Empfangene Nachrichten", color=ACCENT)
ax2.set_ylabel("Sitzungsdauer (s)", color=ORANGE)
ax1.set_title("Empfangene CAM-Nachrichten pro Testsitzung")
ax1.tick_params(axis="y", labelcolor=ACCENT)
ax2.tick_params(axis="y", labelcolor=ORANGE)
for b, v in zip(balken, sitzungs_anzahl):
    ax1.text(b.get_x() + b.get_width()/2, v + 3, str(v),
             ha="center", va="bottom", fontsize=10, fontweight="bold", color=ACCENT)
ax1.yaxis.grid(True, linestyle="--", alpha=0.3, zorder=0)
ax1.set_axisbelow(True)
ax2.spines["top"].set_visible(False)

save(fig, "abb6_sitzungen")


# ══════════════════════════════════════════════════════════════════════════════
# Abbildung 7 — Kumulierte Nachrichtenanzahl (Sitzung 4)
# ══════════════════════════════════════════════════════════════════════════════
print("Abbildung 7 — Kumulierte Nachrichten")

idealrate = 1 / np.median(iat4)

fig, ax = plt.subplots(figsize=(7, 3.2))
ax.plot(t4_rel, np.arange(1, len(t4)+1), color=ACCENT, linewidth=1.4,
        label="Empfangen", zorder=3)
ideal = t4_rel * idealrate
ax.plot(t4_rel, ideal, "--", color=ORANGE, linewidth=1.2,
        label=f"Ideal ({idealrate:.2f} Nachr./s)", zorder=2)
ax.fill_between(t4_rel, np.arange(1, len(t4)+1), ideal,
                alpha=0.1, color=GREY)
ax.set_xlabel("Zeit in der Sitzung (s)")
ax.set_ylabel("Kumulierte Nachrichten")
ax.set_title("Kumulierte empfangene CAM-Nachrichten — Sitzung 4")
ax.legend(frameon=False, fontsize=10)

save(fig, "abb7_kumuliert")


print("\nFertig — alle Abbildungen gespeichert in figures/")
