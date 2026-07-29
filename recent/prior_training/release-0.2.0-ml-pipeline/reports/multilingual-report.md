# Multilingual Report (engineering)

**Languages:** zh / en / hi / id (synthetic generator + rules + student training)

**Status:** Pipeline exercised on synthetic data only. Per-language Precision/Recall/F1 on a frozen real test set is **pending**.

| Language | Train/Val/Test coverage | Formal metrics |
|----------|-------------------------|----------------|
| zh | Synthetic templates | Pending real labels |
| en | Synthetic templates | Pending real labels |
| hi | Synthetic templates + Hindi normalizer unit tests | Pending real labels |
| id | Synthetic templates | Pending real labels |

Hindi combining marks preserved in `TextNormalizer` unit tests (JVM).
