"""Stable codes and human-readable labels used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Province:
    raw_code: str
    postal_code: str
    name: str


PROVINCES: tuple[Province, ...] = (
    Province("XA", "AB", "Alberta"),
    Province("XC", "BC", "British Columbia"),
    Province("XM", "MB", "Manitoba"),
    Province("XB", "NB", "New Brunswick"),
    Province("XW", "NL", "Newfoundland and Labrador"),
    Province("XT", "NT", "Northwest Territories"),
    Province("XN", "NS", "Nova Scotia"),
    Province("XV", "NU", "Nunavut"),
    Province("XO", "ON", "Ontario"),
    Province("XP", "PE", "Prince Edward Island"),
    Province("XQ", "QC", "Quebec"),
    Province("XS", "SK", "Saskatchewan"),
    Province("XY", "YT", "Yukon"),
)

PROVINCE_BY_RAW = {province.raw_code: province for province in PROVINCES}
PROVINCE_BY_POSTAL = {province.postal_code: province for province in PROVINCES}
PROVINCE_NAME_BY_RAW = {province.raw_code: province.name for province in PROVINCES}
VALID_PROVINCE_CODES = tuple(PROVINCE_BY_RAW)

US_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
STATE_CODE_BY_NAME = {name.casefold(): code for code, name in US_STATE_NAMES.items()}

MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# These aliases only resolve common natural-language phrases to BTS 2-digit HS chapters.
# They do not imply that every item in the chapter has identical handling requirements.
COMMODITY_ALIASES: dict[str, str] = {
    "automotive_parts": "87",
    "automotive parts": "87",
    "auto parts": "87",
    "vehicle parts": "87",
    "vehicles": "87",
    "cars": "87",
    "汽车零部件": "87",
    "汽车配件": "87",
    "汽车": "87",
    "machinery": "84",
    "机械": "84",
    "electrical machinery": "85",
    "electronics": "85",
    "电子产品": "85",
    "电气设备": "85",
    "plastics": "39",
    "塑料": "39",
    "pharmaceuticals": "30",
    "药品": "30",
    "furniture": "94",
    "家具": "94",
    "iron and steel": "72",
    "钢铁": "72",
    "chemicals": "38",
    "化工品": "38",
    "produce": "07",
    "vegetables": "07",
    "蔬菜": "07",
    "fruit": "08",
    "水果": "08",
}

BTS_COUNTRY_CANADA = "1220"
BTS_TRADE_EXPORT = "1"
BTS_MODE_TRUCK = "5"

FEATURE_LABELS: dict[str, str] = {
    "value_lag_1": "上月贸易额",
    "value_lag_2": "前第2个月贸易额",
    "value_lag_3": "前第3个月贸易额",
    "rolling_3_mean": "近3个月平均贸易额",
    "rolling_6_mean": "近6个月平均贸易额",
    "rolling_12_mean": "近12个月平均贸易额",
    "rolling_3_growth": "近3个月增长趋势",
    "recent_yoy_growth": "近期同比增长",
    "rolling_6_volatility": "近6个月波动",
    "nonzero_ratio_12": "近12个月活跃度",
    "route_share_12": "州-商品在该省的历史份额",
    "commodity_province_share_12": "商品在该省的全国份额",
    "state_province_share_12": "起点州与该省的历史匹配",
    "seasonality_index": "计划月份季节性",
    "origin_state_code": "美国起点州",
    "commodity_code_encoded": "商品类别",
    "province_code": "加拿大省/地区",
    "planning_month": "计划月份",
}

