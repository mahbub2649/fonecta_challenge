#!/usr/bin/env python3
"""Draw the README's charts into docs/images/, from the scores in the README's tables.

    python3 tools/make_charts.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e7e6e1"
COLOURS = {"2026 season": "#2a78d6", "2025 season": "#eb6834"}
MARKERS = {"2026 season": "o", "2025 season": "s"}

STEPS = ["Package\nbaseline", "LightGBM", "+ TabICLv2,\nstricter rule", "+ all past\ndays", "+ history\ntransformers"]
SCORES = {"2026 season": [54.49, 67.66, 67.98, 68.30, 68.62], "2025 season": [53.23, 65.67, 66.05, 66.17, 66.27]}
WRONG = {"2026 season": [224, 389, 317, 308, 292], "2025 season": [249, 445, 329, 323, 311]}
ALL_DAYS = [0, 0.25, 0.5, 1.0]
ALL_DAYS_SCORES = {"2026 season": [67.88, 68.01, 68.15, 68.30], "2025 season": [66.01, 66.14, 66.12, 66.17]}
SHARES = [0, 0.10, 0.15, 0.20, 0.25, 0.30]
SHARE_SCORES = {"2026 season": [68.30, 68.52, 68.54, 68.60, 68.53, 68.77], "2025 season": [66.17, 66.25, 66.29, 66.27, 66.05, 65.97]}
SHARE_WRONG = {"2026 season": [308, 299, 295, 292, 293, 284], "2025 season": [323, 318, 315, 308, 308, 301]}


def draw(ax, xs, series, title, ylabel, xlabel="", label_at=(-1,), fmt="{:.2f}"):
    frame = pd.DataFrame([(x, name, v) for name, values in series.items() for x, v in zip(xs, values)], columns=["x", "season", "value"])
    sns.lineplot(data=frame, x="x", y="value", hue="season", style="season", markers=MARKERS, dashes=False, palette=COLOURS, linewidth=2,
                 markersize=9, markeredgecolor=SURFACE, markeredgewidth=1.5, sort=False, legend=False, ax=ax)
    ax.set_title(title, loc="left", color=INK, fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=11)
    ax.set_xlabel(xlabel, color=MUTED, fontsize=11)
    ax.tick_params(colors=MUTED, labelsize=10, length=0)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=1)
    sns.despine(ax=ax, left=True)
    low, high = min(min(v) for v in series.values()), max(max(v) for v in series.values())
    gap = (high - low) * 0.09
    for name, values in series.items():
        above = values[-1] == max(v[-1] for v in series.values())
        for i in label_at:
            # The first point sits at the foot of a steep line, so its label goes to the side. A low label on a peak needs extra room.
            offset, align = ((-11, -4), "right") if i == 0 and len(label_at) > 1 else ((0, 10 if above else -26 if i == 1 else -17), "center")
            ax.annotate(fmt.format(values[i]), (xs[i], values[i]), xytext=offset, textcoords="offset points", ha=align, color=INK, fontsize=10, fontweight="bold")
    ax.set_ylim(low - gap * 1.6, high + gap * 1.6)


def legend(fig):
    handles = [plt.Line2D([], [], color=COLOURS[n], marker=MARKERS[n], markersize=9, linewidth=2, markeredgecolor=SURFACE, label=n) for n in COLOURS]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.012, 0.99), ncol=2, frameon=False, fontsize=11, labelcolor=INK, handletextpad=0.5, columnspacing=1.6)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote {OUT / name}")


def main():
    sns.set_theme(style="whitegrid", rc={"axes.facecolor": SURFACE, "figure.facecolor": SURFACE})

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.9))
    xs = list(range(len(STEPS)))
    draw(axes[0], xs, SCORES, "Score rose at every step", "Score (0 to 100)", label_at=(0, -1))
    draw(axes[1], xs, WRONG, "Wrong calls rose with LightGBM, then fell", "Wrong open or closed calls", label_at=(0, 1, -1), fmt="{:.0f}")
    for ax in axes:
        ax.set_xticks(xs, STEPS)
        ax.set_xlim(-0.6, len(STEPS) - 0.65)
    legend(fig)
    fig.tight_layout(rect=(0, 0, 1, 0.93), w_pad=3)
    save(fig, "score_progress.png")

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6))
    draw(axes[0], ALL_DAYS, ALL_DAYS_SCORES, "More weight on all past days", "Score (0 to 100)", "Weight on the extra days")
    draw(axes[1], SHARES, SHARE_SCORES, "Transformer share: score", "Score (0 to 100)", "Share of the blend")
    draw(axes[2], SHARES, SHARE_WRONG, "Transformer share: wrong calls", "Wrong open or closed calls", "Share of the blend", fmt="{:.0f}")
    axes[0].set_xticks(ALL_DAYS)
    for ax in axes[1:]:
        ax.set_xticks(SHARES)
        ax.axvline(0.20, color=MUTED, linewidth=1, linestyle=(0, (3, 3)), zorder=0)
    axes[1].annotate("Our choice: 0.20", (0.20, 67.4), xytext=(-6, 0), textcoords="offset points", ha="right", color=MUTED, fontsize=10)
    axes[2].annotate("Our choice: 0.20", (0.20, 282), xytext=(-6, 0), textcoords="offset points", ha="right", color=MUTED, fontsize=10)
    legend(fig)
    fig.tight_layout(rect=(0, 0, 1, 0.93), w_pad=3)
    save(fig, "weight_tests.png")


if __name__ == "__main__":
    main()
