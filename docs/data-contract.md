# 数据契约

## 1. 自然语言输入

必填字段：

| 字段 | 类型 | 规则 |
|---|---|---|
| `origin_state` | 两位字符串 | 有效美国州/地区代码；名称会规范化 |
| `commodity` | 字符串 | 必须能解析为 HS2 商品章 |
| `commodity_code` | 两位数字字符串 | 由商品文本解析或直接提供 |
| `country` | 字符串 | 本版本只接受 `Canada` |
| `month` | 1–12 整数 | 计划月份 |

可选字段：`year`、`fleet_size`、`hazmat_capable`、`hazmat_required`、`preferred_port` 和 `language`。

缺少任一必填字段会返回非法输入，不会猜测。若显式请求 Mexico，也会拒绝，因为当前训练范围只覆盖加拿大。

## 2. BTS Table 2 主训练表

官方 current-format Table 2 的粒度为美国州、HS2 商品、加拿大省/地区和月份。输入必须至少包含：

```text
COUNTRY, TRDTYPE, DISAGMOT, USASTATE, COMMODITY2,
CANPROV, VALUE, YEAR, MONTH
```

当前官方月度文件使用 `COMMODITY2/YEAR/MONTH`；管道同时兼容归档格式中的
`COMMODITY/STATYR/STATMO`，并统一规范化为内部字段。

硬过滤条件：

```text
COUNTRY == "1220"
TRDTYPE == "1"
DISAGMOT == "5"
CANPROV in 13 known province/territory codes
```

规范化输出：

| 字段 | 类型 | 含义 |
|---|---|---|
| `date` | 月初日期 | 统计月份 |
| `origin_state` | 字符串 | 美国起点州 |
| `commodity_code` | 两位字符串 | HS2 商品章 |
| `province_code` | 字符串 | BTS 加拿大省/地区原始码，如 `XO` |
| `value` | 非负浮点数 | 当月贸易额（美元） |

同一主键的多行会求和。无效州代码、无效商品代码、未知省区和无效日期会过滤。

## 3. BTS Table 1 口岸辅助表

Table 1 的粒度为美国州、加拿大省/地区、海关口岸和月份，不含商品。输入必须至少包含：

```text
COUNTRY, TRDTYPE, DISAGMOT, USASTATE, CANPROV,
DEPE, VALUE, YEAR, MONTH
```

采用与主表相同的加拿大、出口、卡车硬过滤，输出：

```text
date, origin_state, province_code, port_code, value
```

禁止把它与 Table 2 拼成“州＋商品＋省＋口岸”的联合观测。响应中的 `auxiliary_ports` 仅表达独立的州/省/口岸历史规模。

## 4. 候选与标签

每个查询组定义为：

```text
target_month + origin_state + commodity_code
```

每组固定产生 13 个已知加拿大省/地区候选。连续真实标签在查询组内计算：

```text
opportunity_label = 0.60 * rank_pct(current_month_trade_value)
                  + 0.40 * rank_pct(current_month_yoy_growth)
```

LambdaRank 使用的相关性等级是：

```text
relevance = clip(floor(opportunity_label * 5), 0, 4)
```

所有模型特征只使用目标月份之前的数据。目标月贸易额和目标月同比增长只用于标签，不进入特征。

## 5. 推荐输出

每个 Top-5 市场包含：

- 排名、省区原始码、邮政缩写和名称；
- 校准后的机会信号与原始 ranker 分数；
- 最近 3/12 个月历史贸易规模、近期同比趋势和冷启动标记；
- TreeSHAP 特征贡献；
- 来源绑定证据与受约束解释。

顶层输出同时包含计划日期解析结果、数据截止日、方法信息、独立口岸辅助统计、检索后端、模型版本和限制说明。

顶层 `market_trends` 与 Top 5 按省区码一一对应，每个序列默认返回最近 24 个完整日历月：

```text
province_code, province_postal_code, province_name, source_scope,
points[month, trade_value_usd, rolling_3m_trade_value_usd, yoy_growth]
```

缺失月份以 0 贸易额补齐；上年同月为 0 或不存在时，`yoy_growth` 返回 `null`，不会输出 NaN/Infinity。趋势只使用 Table 2。若请求州＋商品没有历史，排序和趋势会共同回退为全美该商品的省级历史，并把 `source_scope` 标为 `national_commodity_fallback`；口岸数据始终不进入趋势序列。
