EVIDENCE_ID: MODEL-METHODOLOGY
TITLE: Province opportunity-ranking methodology
SOURCE_URL: local://methodology
SOURCE_TYPE: model
CONTENT:
The system ranks Canadian provinces and territories with LightGBM LambdaRank. Each query group is a planned month, U.S. origin state and two-digit commodity. The training opportunity label equals 60 percent within-query trade-value percentile plus 40 percent within-query year-over-year growth percentile. Features use only months before the target month. The displayed opportunity score is calibrated to the composite historical label range from zero to one; it is a ranking signal rather than a probability, rate quote or guaranteed commercial outcome. TreeSHAP contributions describe how model features moved the raw ranking score.

