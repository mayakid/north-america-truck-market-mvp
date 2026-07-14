from __future__ import annotations

import pandas as pd

from crossborder_recommender.trends import market_trend_series


def test_market_trends_use_national_fallback_and_preserve_zero_months(
    synthetic_history,
):
    trends = market_trend_series(
        synthetic_history,
        origin_state="AK",
        commodity_code="87",
        province_codes=["XO"],
        months=18,
    )

    assert len(trends) == 1
    assert trends[0].source_scope == "national_commodity_fallback"
    assert len(trends[0].points) == 18
    assert all(point.trade_value_usd >= 0 for point in trends[0].points)
    assert all(point.rolling_3m_trade_value_usd >= 0 for point in trends[0].points)
    assert pd.Timestamp(trends[0].points[-1].month) == synthetic_history["date"].max()
