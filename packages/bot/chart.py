import io
from datetime import date

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def render_stats_chart(
    daily: list[tuple[date, int]],
    by_group: list[tuple[str, int]],
    period: str,
    topic: str | None = None,
) -> bytes:
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8, 6), height_ratios=[2, 1], constrained_layout=True
    )

    dates = [d.strftime("%m-%d") for d, _ in daily]
    counts = [c for _, c in daily]
    ax1.bar(dates, counts, color="#c0392b")
    ax1.set_ylabel("victims")
    step = max(1, len(dates) // 10)
    ax1.set_xticks(range(0, len(dates), step))
    ax1.set_xticklabels(dates[::step], rotation=45, ha="right")

    groups = by_group[:5]
    if groups:
        names = [g for g, _ in groups][::-1]
        values = [c for _, c in groups][::-1]
        ax2.barh(names, values, color="#e67e22")
    ax2.set_xlabel("victims")

    scope = topic or "Thailand"
    fig.suptitle(f"Ransomware victims — {scope} — last {period}")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return buf.getvalue()
