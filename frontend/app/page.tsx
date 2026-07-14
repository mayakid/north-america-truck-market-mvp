"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const EXAMPLE_QUERY =
  "Michigan（密歇根州）的中型卡车承运商，计划10月运输汽车零部件到加拿大，请推荐市场。";

const SERIES_COLORS = ["#ff6b3d", "#0e7c72", "#3366cc", "#c48a18", "#8657c7"];

type FeatureContribution = {
  feature: string;
  label: string;
  value: number | string | null;
  contribution: number;
  direction: "positive" | "negative";
};

type Evidence = {
  evidence_id: string;
  title: string;
  excerpt: string;
  source_url: string;
  source_type: "BTS" | "model" | "system";
};

type MarketRecommendation = {
  rank: number;
  province_code: string;
  province_postal_code: string;
  province_name: string;
  opportunity_score: number;
  raw_ranker_score: number;
  latest_3m_trade_value_usd: number;
  latest_12m_trade_value_usd: number;
  recent_yoy_growth: number | null;
  cold_start: boolean;
  shap_contributions: FeatureContribution[];
  evidence: Evidence[];
  explanation: string | null;
};

type TrendPoint = {
  month: string;
  trade_value_usd: number;
  rolling_3m_trade_value_usd: number;
  yoy_growth: number | null;
};

type MarketTrend = {
  province_code: string;
  province_postal_code: string;
  province_name: string;
  source_scope: "origin_state_commodity" | "national_commodity_fallback";
  points: TrendPoint[];
};

type PortStatistic = {
  port_code: string;
  port_name: string | null;
  province_codes: string[];
  latest_12m_trade_value_usd: number;
  yoy_growth: number | null;
  preferred_port_match: boolean;
  caveat: string;
};

type ParsedRequest = {
  origin_state: string;
  commodity: string;
  commodity_code: string;
  country: "Canada";
  month: number;
  year: number | null;
  fleet_size: "small" | "medium" | "large" | null;
  preferred_port: string | null;
};

type RecommendationResponse = {
  request: ParsedRequest;
  resolved_planning_date: string;
  data_cutoff: string;
  recommendations: MarketRecommendation[];
  market_trends: MarketTrend[];
  auxiliary_ports: PortStatistic[];
  methodology: Record<string, string>;
  limitations: string[];
  generated_summary: string | null;
  retrieval_backend: string;
  model_version: string;
};

type HealthResponse = {
  status: "ok" | "degraded";
  model_ready: boolean;
  deepseek_configured: boolean;
};

type TrendMetric =
  | "trade_value_usd"
  | "rolling_3m_trade_value_usd"
  | "yoy_growth";

function formatUsd(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (absolute >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${Math.round(value).toLocaleString("zh-CN")}`;
}

function formatPercent(value: number | null, digits = 1): string {
  if (value === null || !Number.isFinite(value)) return "暂无同比";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

function formatMonth(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return `${String(date.getFullYear()).slice(2)}.${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function formatDate(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return `${date.getFullYear()}年${date.getMonth() + 1}月`;
}

function fleetLabel(value: ParsedRequest["fleet_size"]): string {
  return value ? { small: "小型车队", medium: "中型车队", large: "大型车队" }[value] : "未指定车队";
}

function trendMetricLabel(metric: TrendMetric): string {
  if (metric === "trade_value_usd") return "月度贸易规模";
  if (metric === "rolling_3m_trade_value_usd") return "近3月滚动规模";
  return "同比变化";
}

function trendValue(value: number, metric: TrendMetric): string {
  return metric === "yoy_growth" ? formatPercent(value) : formatUsd(value);
}

function compactLabel(value: string, max = 15): string {
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function uniqueEvidence(recommendations: MarketRecommendation[]): Evidence[] {
  const seen = new Set<string>();
  return recommendations.flatMap((item) => item.evidence).filter((item) => {
    if (seen.has(item.evidence_id)) return false;
    seen.add(item.evidence_id);
    return true;
  });
}

export default function Home() {
  const [query, setQuery] = useState(EXAMPLE_QUERY);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCode, setSelectedCode] = useState("");
  const [trendMetric, setTrendMetric] = useState<TrendMetric>(
    "rolling_3m_trade_value_usd",
  );
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/health", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: HealthResponse | null) => {
        if (active) setHealth(payload);
      })
      .catch(() => {
        if (active) setHealth(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedMarket = useMemo(
    () =>
      result?.recommendations.find((item) => item.province_code === selectedCode) ??
      result?.recommendations[0] ??
      null,
    [result, selectedCode],
  );

  const trendData = useMemo(() => {
    if (!result?.market_trends.length) return [];
    return result.market_trends[0].points.map((point, index) => {
      const row: Record<string, string | number | null> = { month: point.month };
      result.market_trends.forEach((series) => {
        row[series.province_code] = series.points[index]?.[trendMetric] ?? null;
      });
      return row;
    });
  }, [result, trendMetric]);

  const provinceNameByCode = useMemo(
    () =>
      Object.fromEntries(
        result?.recommendations.map((item) => [item.province_code, item.province_name]) ?? [],
      ),
    [result],
  );

  const evidence = useMemo(
    () => (result ? uniqueEvidence(result.recommendations) : []),
    [result],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (cleanQuery.length < 3) {
      setError("请补充出发州、商品和计划月份。");
      return;
    }

    setLoading(true);
    setError(null);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 120_000);

    try {
      const response = await fetch("/api/recommend", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: cleanQuery }),
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          payload.message ?? payload.detail ?? "暂时无法生成建议，请检查输入后重试。",
        );
      }
      const recommendation = payload as RecommendationResponse;
      setResult(recommendation);
      setSelectedCode(recommendation.recommendations[0]?.province_code ?? "");
      window.requestAnimationFrame(() => {
        document.getElementById("analysis-results")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    } catch (caught) {
      const message =
        caught instanceof DOMException && caught.name === "AbortError"
          ? "分析等待时间过长，请稍后重试。"
          : caught instanceof Error
            ? caught.message
            : "暂时无法生成建议，请稍后重试。";
      setError(message);
    } finally {
      window.clearTimeout(timeout);
      setLoading(false);
    }
  }

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="北境市场雷达首页">
          <span className="brand-mark" aria-hidden="true">N</span>
          <span>
            <strong>北境市场雷达</strong>
            <small>Canada Truck Market Intelligence</small>
          </span>
        </a>
        <div className={`service-status ${health?.model_ready ? "is-online" : ""}`}>
          <span aria-hidden="true" />
          {health?.model_ready ? "模型在线" : "等待模型服务"}
        </div>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span>01</span> 美国出口加拿大 · 卡车运输</p>
          <h1>
            把运输需求，
            <em>变成可解释的市场路线图。</em>
          </h1>
          <p className="hero-lead">
            输入出发州、商品和计划月份，系统会给出加拿大省/地区 Top 5、DeepSeek
            建议、真实历史趋势与模型依据。
          </p>
          <div className="scope-strip" aria-label="分析范围">
            <span>13 个候选省/地区</span>
            <span>60% 规模 + 40% 同比</span>
            <span>口岸独立辅助</span>
          </div>
        </div>

        <form className="query-panel" onSubmit={submit}>
          <div className="panel-kicker">
            <span>智能分析台</span>
            <span className="live-dot">BTS DATA</span>
          </div>
          <label htmlFor="market-query">描述你的运输计划</label>
          <textarea
            id="market-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={5}
            maxLength={4000}
            placeholder="例如：密歇根州，汽车零部件，计划10月通过卡车出口到加拿大……"
          />
          <div className="query-actions">
            <button
              className="example-button"
              type="button"
              onClick={() => setQuery(EXAMPLE_QUERY)}
            >
              填入示例
            </button>
            <button className="submit-button" type="submit" disabled={loading}>
              {loading ? "正在分析真实数据…" : "生成市场建议"}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <p className="privacy-note">DeepSeek 密钥仅在服务器端使用，不会进入浏览器。</p>
          {error ? <p className="error-message" role="alert">{error}</p> : null}
        </form>
      </section>

      {!result && !loading ? (
        <section className="preview-band" aria-label="分析内容预览">
          <div className="preview-copy">
            <p className="section-number">分析输出 / 04</p>
            <h2>每一个建议，都能沿着数据往回看。</h2>
            <p>提交需求后，这里将绘制真实 Top 5 排名、24 个月趋势、SHAP 因素与口岸辅助图。</p>
          </div>
          <div className="empty-chart" role="img" aria-label="等待真实数据的趋势图区域">
            <div className="empty-chart-grid" />
            <div className="empty-chart-message">
              <span>WAITING FOR QUERY</span>
              <strong>趋势图将在分析后生成</strong>
              <small>不展示模拟或装饰性数据</small>
            </div>
          </div>
        </section>
      ) : null}

      {loading ? (
        <section className="loading-stage" aria-live="polite" aria-busy="true">
          <div className="loading-orbit" aria-hidden="true"><span /></div>
          <div>
            <p className="section-number">模型分析中</p>
            <h2>正在解析需求并计算 13 个候选市场</h2>
            <p>完成后将一次性显示建议、趋势和证据，不使用模拟进度。</p>
          </div>
        </section>
      ) : null}

      {result ? (
        <div className="results" id="analysis-results">
          <section className="result-intro">
            <div>
              <p className="section-number">智能结论 / {formatDate(result.data_cutoff)} 数据</p>
              <h2>{result.request.origin_state} · HS {result.request.commodity_code} 的加拿大机会</h2>
            </div>
            <div className="request-facts" aria-label="已解析需求">
              <span>{result.request.commodity}</span>
              <span>{formatDate(result.resolved_planning_date)}计划</span>
              <span>{fleetLabel(result.request.fleet_size)}</span>
            </div>
          </section>

          <section className="summary-card">
            <div className="summary-label">
              <span>DEEPSEEK</span>
              <strong>决策摘要</strong>
            </div>
            <div className="summary-copy">
              {result.generated_summary ?? "模型已完成排序，请结合下方市场解释和限制条件判断。"}
            </div>
          </section>

          <section className="content-section">
            <div className="section-heading">
              <div>
                <p className="section-number">市场排序 / 01</p>
                <h2>加拿大省/地区 Top 5</h2>
              </div>
              <p>机会分是校准后的排序信号，不代表成功概率。</p>
            </div>

            <div className="ranking-layout">
              <div className="chart-card ranking-chart" role="img" aria-label="Top 5 市场机会分条形图">
                <ResponsiveContainer width="100%" height={310}>
                  <BarChart
                    data={result.recommendations}
                    layout="vertical"
                    margin={{ top: 12, right: 22, bottom: 8, left: 6 }}
                  >
                    <CartesianGrid stroke="#d9ddd7" strokeDasharray="3 5" horizontal={false} />
                    <XAxis
                      type="number"
                      domain={[0, 1]}
                      tickFormatter={(value) => `${Math.round(value * 100)}`}
                      tick={{ fill: "#64716b", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="province_postal_code"
                      width={42}
                      tick={{ fill: "#182721", fontWeight: 700, fontSize: 13 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      cursor={{ fill: "rgba(14,124,114,0.06)" }}
                      formatter={(value) => [`${(Number(value) * 100).toFixed(1)} 分`, "机会分"]}
                      labelFormatter={(_, items) => items[0]?.payload?.province_name ?? ""}
                      contentStyle={{ borderRadius: 12, border: "1px solid #d6ddd7" }}
                    />
                    <Bar dataKey="opportunity_score" radius={[0, 8, 8, 0]} barSize={24}>
                      {result.recommendations.map((item, index) => (
                        <Cell
                          key={item.province_code}
                          fill={SERIES_COLORS[index]}
                          opacity={!selectedMarket || selectedMarket.province_code === item.province_code ? 1 : 0.5}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <span className="axis-caption">机会分 × 100</span>
              </div>

              <div className="market-list" aria-label="Top 5 市场明细">
                {result.recommendations.map((item, index) => (
                  <button
                    className={`market-card ${selectedMarket?.province_code === item.province_code ? "is-selected" : ""}`}
                    key={item.province_code}
                    type="button"
                    onClick={() => setSelectedCode(item.province_code)}
                    aria-pressed={selectedMarket?.province_code === item.province_code}
                  >
                    <span className="market-rank">0{item.rank}</span>
                    <span className="market-name">
                      <strong>{item.province_name}</strong>
                      <small>{item.province_postal_code} · 近12月 {formatUsd(item.latest_12m_trade_value_usd)}</small>
                    </span>
                    <span className={`growth-pill ${(item.recent_yoy_growth ?? 0) < 0 ? "is-negative" : ""}`}>
                      {formatPercent(item.recent_yoy_growth)}
                    </span>
                    <span className="market-score">{(item.opportunity_score * 100).toFixed(1)}</span>
                    <span className="market-color" style={{ background: SERIES_COLORS[index] }} aria-hidden="true" />
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="content-section trend-section">
            <div className="section-heading trend-heading">
              <div>
                <p className="section-number">历史趋势 / 02</p>
                <h2>24 个月市场变化过程</h2>
              </div>
              <div className="metric-switch" role="group" aria-label="趋势指标">
                {([
                  ["trade_value_usd", "月度规模"],
                  ["rolling_3m_trade_value_usd", "3月滚动"],
                  ["yoy_growth", "同比"],
                ] as const).map(([metric, label]) => (
                  <button
                    type="button"
                    key={metric}
                    className={trendMetric === metric ? "is-active" : ""}
                    onClick={() => setTrendMetric(metric)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="chart-card trend-chart" role="img" aria-label={`${trendMetricLabel(trendMetric)}折线图`}>
              {result.market_trends[0]?.source_scope === "national_commodity_fallback" ? (
                <div className="fallback-notice">该州＋商品缺少历史，图表使用全美该商品的省级历史回退。</div>
              ) : null}
              <ResponsiveContainer width="100%" height={390}>
                <LineChart data={trendData} margin={{ top: 24, right: 22, left: 8, bottom: 8 }}>
                  <CartesianGrid stroke="#d9ddd7" strokeDasharray="3 5" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tickFormatter={formatMonth}
                    minTickGap={34}
                    tick={{ fill: "#64716b", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tickFormatter={(value) => trendValue(Number(value), trendMetric)}
                    tick={{ fill: "#64716b", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={64}
                  />
                  {trendMetric === "yoy_growth" ? <ReferenceLine y={0} stroke="#65736c" /> : null}
                  <Tooltip
                    formatter={(value, name) => [
                      trendValue(Number(value), trendMetric),
                      provinceNameByCode[String(name)] ?? String(name),
                    ]}
                    labelFormatter={(label) => formatDate(String(label))}
                    contentStyle={{ borderRadius: 12, border: "1px solid #d6ddd7" }}
                  />
                  <Legend
                    formatter={(code) => provinceNameByCode[String(code)] ?? String(code)}
                    wrapperStyle={{ paddingTop: 16, fontSize: 12 }}
                  />
                  {result.market_trends.map((series, index) => (
                    <Line
                      key={series.province_code}
                      type="monotone"
                      dataKey={series.province_code}
                      stroke={SERIES_COLORS[index]}
                      strokeWidth={selectedMarket?.province_code === series.province_code ? 3.5 : 2}
                      strokeOpacity={
                        !selectedMarket || selectedMarket.province_code === series.province_code ? 1 : 0.45
                      }
                      dot={false}
                      activeDot={{ r: 5, strokeWidth: 2, fill: "#fff" }}
                      connectNulls={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              <p className="chart-footnote">
                仅使用 BTS Table 2 的“美国出口加拿大、卡车运输、州＋HS2＋省/地区”月度记录；口岸数据未并入此图。
              </p>
            </div>
          </section>

          <section className="content-section evidence-section">
            <div className="section-heading">
              <div>
                <p className="section-number">模型依据 / 03</p>
                <h2>{selectedMarket?.province_name ?? "首选市场"} 为什么进入推荐</h2>
              </div>
              <p>点击上方任一市场，可切换解释和影响因素。</p>
            </div>

            <div className="explain-layout">
              <article className="explanation-card">
                <div className="explanation-score">
                  <span>RANK {String(selectedMarket?.rank ?? 1).padStart(2, "0")}</span>
                  <strong>{((selectedMarket?.opportunity_score ?? 0) * 100).toFixed(1)}</strong>
                  <small>机会分</small>
                </div>
                <div>
                  <p>{selectedMarket?.explanation ?? "当前未返回逐市场文字解释，请参考趋势和模型因素。"}</p>
                  <dl className="market-metrics">
                    <div><dt>近3月规模</dt><dd>{formatUsd(selectedMarket?.latest_3m_trade_value_usd ?? 0)}</dd></div>
                    <div><dt>近12月规模</dt><dd>{formatUsd(selectedMarket?.latest_12m_trade_value_usd ?? 0)}</dd></div>
                    <div><dt>近期同比</dt><dd>{formatPercent(selectedMarket?.recent_yoy_growth ?? null)}</dd></div>
                  </dl>
                </div>
              </article>

              <div className="chart-card shap-card">
                <div className="chart-title-row">
                  <div>
                    <strong>SHAP 影响因素</strong>
                    <span>向右推动排名，向左压低排名</span>
                  </div>
                  <div className="direction-key"><i /> 正向 <i /> 负向</div>
                </div>
                {selectedMarket?.shap_contributions.length ? (
                  <ResponsiveContainer width="100%" height={310}>
                    <BarChart
                      data={selectedMarket.shap_contributions.slice(0, 8)}
                      layout="vertical"
                      margin={{ top: 16, right: 18, left: 10, bottom: 8 }}
                    >
                      <CartesianGrid stroke="#d9ddd7" strokeDasharray="3 5" horizontal={false} />
                      <XAxis type="number" tick={{ fill: "#64716b", fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis
                        type="category"
                        dataKey="label"
                        width={116}
                        tickFormatter={(value) => compactLabel(String(value), 10)}
                        tick={{ fill: "#263630", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <ReferenceLine x={0} stroke="#65736c" />
                      <Tooltip
                        formatter={(value) => [Number(value).toFixed(4), "SHAP 贡献"]}
                        labelFormatter={(label) => String(label)}
                        contentStyle={{ borderRadius: 12, border: "1px solid #d6ddd7" }}
                      />
                      <Bar dataKey="contribution" radius={[5, 5, 5, 5]} barSize={16}>
                        {selectedMarket.shap_contributions.slice(0, 8).map((item) => (
                          <Cell
                            key={item.feature}
                            fill={item.direction === "positive" ? "#0e7c72" : "#ff6b3d"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="no-chart-data">本次未返回 SHAP 明细，排序结果仍保留。</div>
                )}
              </div>
            </div>
          </section>

          <section className="content-section process-section">
            <div className="section-heading">
              <div>
                <p className="section-number">计算过程 / 04</p>
                <h2>从一句需求到 Top 5</h2>
              </div>
            </div>
            <ol className="process-flow">
              <li><span>01</span><strong>需求解析</strong><p>{result.methodology.parser ?? "结构化解析"}识别州、商品与月份</p></li>
              <li><span>02</span><strong>候选构建</strong><p>固定评估 13 个加拿大省与地区</p></li>
              <li><span>03</span><strong>机会排序</strong><p>60% 规模分位数 + 40% 同比增长分位数</p></li>
              <li><span>04</span><strong>证据解释</strong><p>{result.methodology.explanation ?? "解释模型"}结合历史证据生成建议</p></li>
            </ol>
          </section>

          <section className="content-section port-section">
            <div className="section-heading">
              <div>
                <p className="section-number">口岸辅助 / 独立统计</p>
                <h2>相关口岸规模参考</h2>
              </div>
              <p>不是“州＋商品＋省＋口岸”的联合估计。</p>
            </div>
            {result.auxiliary_ports.length ? (
              <div className="port-layout">
                <div className="chart-card port-chart" role="img" aria-label="独立口岸近12月贸易规模条形图">
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart
                      data={result.auxiliary_ports.slice(0, 7)}
                      layout="vertical"
                      margin={{ top: 12, right: 18, bottom: 8, left: 8 }}
                    >
                      <CartesianGrid stroke="#d9ddd7" strokeDasharray="3 5" horizontal={false} />
                      <XAxis
                        type="number"
                        tickFormatter={(value) => formatUsd(Number(value))}
                        tick={{ fill: "#64716b", fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="port_name"
                        width={120}
                        tickFormatter={(value) => compactLabel(String(value ?? "未知口岸"), 12)}
                        tick={{ fill: "#263630", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        formatter={(value) => [formatUsd(Number(value)), "近12月规模"]}
                        labelFormatter={(label) => String(label ?? "未知口岸")}
                        contentStyle={{ borderRadius: 12, border: "1px solid #d6ddd7" }}
                      />
                      <Bar dataKey="latest_12m_trade_value_usd" fill="#182721" radius={[0, 8, 8, 0]} barSize={20} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <aside className="port-caveat">
                  <span>范围边界</span>
                  <h3>口岸只用来辅助运营判断</h3>
                  <p>{result.auxiliary_ports[0].caveat}</p>
                  <ul>
                    {result.auxiliary_ports.slice(0, 3).map((port) => (
                      <li key={port.port_code}>
                        <strong>{port.port_name ?? port.port_code}</strong>
                        <span>{formatPercent(port.yoy_growth)}</span>
                      </li>
                    ))}
                  </ul>
                </aside>
              </div>
            ) : (
              <div className="empty-port">
                当前模型包未返回口岸辅助数据；省级 Top 5 与趋势不受影响，也不会用缺失口岸数据补推联合统计。
              </div>
            )}
          </section>

          <section className="content-section source-section">
            <div className="section-heading">
              <div>
                <p className="section-number">证据与边界</p>
                <h2>建议从哪里来，也在哪里停止</h2>
              </div>
            </div>
            <div className="source-layout">
              <div className="evidence-list">
                {evidence.slice(0, 5).map((item) => {
                  const isLink = /^https?:\/\//i.test(item.source_url);
                  const content = (
                    <>
                      <span>{item.source_type}</span>
                      <strong>{item.title}</strong>
                      <p>{item.excerpt}</p>
                    </>
                  );
                  return isLink ? (
                    <a key={item.evidence_id} href={item.source_url} target="_blank" rel="noreferrer">
                      {content}
                    </a>
                  ) : (
                    <article key={item.evidence_id}>{content}</article>
                  );
                })}
              </div>
              <details className="limitations" open>
                <summary>使用限制与风险提示 <span>{result.limitations.length}</span></summary>
                <ul>
                  {result.limitations.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </details>
            </div>
          </section>
        </div>
      ) : null}

      <footer>
        <span>北境市场雷达 · 数据驱动的跨境卡车市场机会建议</span>
        <span>范围：美国出口加拿大 · 卡车 · BTS 月度历史</span>
      </footer>
    </main>
  );
}
