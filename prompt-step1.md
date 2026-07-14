
项目名：基于北美跨境贸易数据的卡车线路机会推荐系统

输入：从用户自然语言中输入中找到承运商画像和运输需求（美国起点州，商品类型，目标国家，计划月份），对应成结构化输入，若是不全则视为非法输入，需要补全信息。

输出：输出最值得关注的加拿大跨境市场Top 5，以及推荐依据。

skill加载：recommendation- engine（已配置，仅在推荐系统任务核心算法建设中执行）、scikit-learn-best-practices（已配置，仅在评估阶段（试验规范）中执行，其余时间不考虑）

开源算法：LightGBM LambdaRank（用户输入：货物类型、美国起点州、加拿大或墨西哥方向、出发月份、可选：承运商规模、HazMat能力、偏好口岸 系统输出：推荐的 Top-5 跨境线路或口岸、机会评分、历史货运规模、增长趋势、推荐原因）

公开数据集：BTS TransBorder Freight Data（时间粒度：月；对本任务的作用：训练标签和市场趋势）

整个项目最终目标：LightGBM负责算推荐，LightRAG负责找依据，大模型API负责理解问题和生成解释。

最终方案执行架构如下：用户自然语言输入 -> 大模型提取结构化条件(州、商品、国家、月份、承运能力) -> 业务规则过滤候选市场 -> LightGBM LGBMRanker推荐算法排序 -> Top 5市场＋分数＋SHAP特征贡献 -> LightRAG检索相关行业资料 -> 大模型生成带依据的推荐解释

例：用户问：我是Michigan的中型承运商，主要运输汽车零部件，10月份有哪些加拿大市场值得关注？
   step-1: Parse提取
{
  "origin_state": "MI",
  "commodity": "automotive_parts",
  "country": "Canada",
  "month": 10,
  "fleet_size": "medium"
}
   step-2:LightGBM LGBMRanker推荐算法
1. Ontario   0.91
2. Quebec    0.68
3. Manitoba  0.42
    step-3:SHAP提供数值依据：
Ontario:
近3个月贸易额          +0.31
Michigan匹配           +0.24
汽车商品历史份额       +0.19
10月季节性             +0.08
市场波动               -0.04
  step-3:LightRAG再检索(待完善，目前考虑到的是对应商品代码说明等)
  step-4: 最后大模型生成：Ontario排名第一，主要因为Michigan—Ontario汽车相关贸易规模较高，近三个月市场表现稳定，并符合该商品的季节性特征。该结果反映市场机会，不代表实时运价或口岸等待时间。

评估指标：统计precision, recall, F1 等或者你觉得比较能体现情况的其他指标







