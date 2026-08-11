from datetime import date, timedelta

from packages.bot.chart import render_stats_chart


def test_render_stats_chart_returns_png():
    daily = [(date(2026, 8, 4) + timedelta(days=i), i % 3) for i in range(7)]
    png = render_stats_chart(daily, [("lockbit", 4), ("alphv", 2)], "7d")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 1000


def test_render_stats_chart_handles_empty_groups():
    daily = [(date(2026, 8, 10), 0)]
    png = render_stats_chart(daily, [], "7d", topic="manufacturing")
    assert png.startswith(b"\x89PNG")
