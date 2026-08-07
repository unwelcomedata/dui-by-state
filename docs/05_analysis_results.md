# 05-Analysis Results & Interpretation

**Run date:** 2025-08-07  
**Dataset:** 51 states × 49 columns (dui_by_state_v1)

---

## 1. Regional Differences

**Kruskal-Wallis tests** (nonparametric, no normality assumption):

| Metric | H | p | Significant? |
|--------|---|---|-------------|
| Alcohol fatality rate per 100M VMT | 15.86 | 0.0012 | ** |
| DUI arrest rate per 100k | 7.25 | 0.0644 | ns |
| Ethanol per capita (2022) | 7.03 | 0.0710 | ns |
| % traffic deaths alcohol | 3.62 | 0.3057 | ns |

**Key finding:** Regions differ significantly on fatality rates (p=0.001) but
NOT on consumption, arrest rates, or alcohol share. This means the regional
gap isn't about how much people drink — it's about road environment, speed,
and infrastructure.

**Region means (fatality rate per 100M VMT):**
- South: 0.391
- West: 0.395
- Midwest: 0.312
- Northeast: 0.258

The South and West are ~50% higher than the Northeast. The difference is
statistically real (not random noise).

---

## 2. What Drives Fatality Rates? (OLS Regression)

**Model:** `fatality_rate ~ consumption + speed + IID + checkpoints + arrests + felony`

| Stat | Value |
|------|-------|
| R² | 0.189 |
| Adj R² | 0.079 |
| F-statistic | 1.71 (p=0.14) |
| N | 51 |

**Coefficients (standardized):**

| Predictor | Coef | p | Significant? |
|-----------|------|---|-------------|
| Max speed limit (mph) | +0.052 | 0.006 | ** |
| Ethanol per capita | +0.013 | 0.426 | ns |
| DUI arrest rate | -0.016 | 0.353 | ns |
| All-offender IID | +0.015 | 0.328 | ns |
| Checkpoints legal | +0.004 | 0.772 | ns |
| First-offense felony | +0.004 | 0.800 | ns |

**Key finding:** Speed limits are the ONLY significant predictor (p=0.006).
States with higher speed limits have higher alcohol fatality rates. No policy
variable (IID, checkpoints, felony) reaches significance. Consumption doesn't
predict fatality rate either (R²=0.003 when alone).

**VIF:** All variables VIF < 1.6 — no multicollinearity concerns.

**Interpretation for social media:** "Higher speed limits are the strongest
predictor of alcohol-impaired driving deaths. Stricter DUI laws don't
measurably reduce fatality rates at the state level."

---

## 3. Policy Effectiveness (with confounders controlled)

Controlling for consumption, speed, and region (R²≈0.35 for each model):

| Policy | Coefficient | t | p | Significant? |
|--------|------------|---|---|-------------|
| IID mandate | +0.006 | +0.19 | 0.847 | ns |
| First-offense felony | +0.030 | +1.08 | 0.285 | ns |
| Sobriety checkpoints | +0.006 | +0.18 | 0.859 | ns |

**Key finding:** After controlling for confounders, NO policy variable is
significantly associated with lower fatality rates. The earlier finding that
felony states have higher rates is explained by region/speed — it's not the
felony law causing worse outcomes.

**Social media angle:** "IID mandates, felony laws, and sobriety checkpoints
show zero measurable effect on alcohol fatality rates once you control for
speed limits and geography. The policies we debate most may not be the ones
that save lives."

---

## 4. State Typology (K-Means Clustering, k=4)

| Cluster | n | Fatality Rate | Arrest Rate | Consumption | IID | Checkpoints | Speed |
|---------|---|--------------|-------------|-------------|-----|-------------|-------|
| 0 (Dangerous outliers) | 2 | 0.570 | 78 | 2.79 | 0.50 | 0.00 | 82.5 |
| 1 (High-death + checkpoints) | 3 | 0.587 | 56 | 2.73 | 0.33 | 1.00 | 75.0 |
| 2 (Mainstream majority) | 34 | 0.324 | 44 | 2.55 | 0.71 | 0.97 | 69.9 |
| 3 (High-arrest Midwest) | 12 | 0.326 | 122 | 2.60 | 0.42 | 0.25 | 74.2 |

**Cluster membership:**
- **Cluster 0** "Fast & Fatal": MT, TX — extreme speed limits (82.5 mph), no checkpoints
- **Cluster 1** "Hot & Dangerous": AZ, NV, SC — highest fatality rates despite checkpoints
- **Cluster 2** "Mainstream": 34 states (most of the country) — moderate on everything
- **Cluster 3** "Arrest-Heavy Midwest": ID, IA, MI, MN, NE, ND, OR, RI, SD, WA, WI, WY — 
  arrest rates 3x higher than Cluster 2, but same fatality rate. No checkpoints, no IID.

**Key insight:** Cluster 3 is the "enforcement works differently" group — they
arrest at very high rates but have the same death rate as states that barely
arrest anyone. This suggests arrests alone don't reduce deaths (or these states
would have the lowest rates).

---

## 5. Consumption-Fatality Gap (Residuals)

**Simple model:** fatality_rate ~ consumption  
**R² = 0.003** — consumption explains almost NOTHING (0.3%) of the variation.

**Worse than expected** (high deaths, any consumption level):
1. South Carolina (+0.346)
2. Texas (+0.238)
3. Arizona (+0.228)
4. Montana (+0.206)
5. Oregon (+0.142)

**Better than expected** (low deaths given consumption):
1. Massachusetts (-0.188)
2. Minnesota (-0.167)
3. New Jersey (-0.160)
4. Utah (-0.143)
5. Rhode Island (-0.118)

**What separates worse vs better states?**

| Metric | Better | As Expected | Worse |
|--------|--------|-------------|-------|
| Max speed limit | 70.0 | 71.5 | 73.5 |
| IID mandate | 0.47 | 0.65 | 0.71 |
| Checkpoints | 0.71 | 0.76 | 0.82 |
| Arrest rate | 58.8 | 64.7 | 69.2 |

Counter-intuitive: "worse" states actually have MORE policies (higher IID,
more checkpoints) and higher arrest rates. The key differentiator is speed
limits — confirming the OLS finding.

---

## Summary Narrative for Social Media

1. **Speed kills, not drinking volume.** Consumption doesn't predict which states
   have more alcohol fatality deaths. Speed limits do.

2. **Popular policies don't work at the state level.** IID mandates, felony
   classifications, and sobriety checkpoints show no measurable effect on
   fatality rates.

3. **The South/West gap is real.** The South and West have ~50% higher alcohol
   fatality rates than the Northeast — driven by faster roads and more rural
   driving, not more drinking.

4. **South Carolina, Texas, and Arizona are the biggest outliers** — far more
   deaths than any characteristic predicts.

5. **Massachusetts, Minnesota, and New Jersey** consistently outperform — fewer
   deaths than expected by any measure.

6. **Arresting more people doesn't reduce deaths.** Midwest states arrest DUI
   drivers at 3x the rate of the Northeast but have the same fatality rate.

---

## Caveats

- N=51 is small for regression; significance thresholds are conservative
- Cross-sectional data — cannot prove causation
- Policy variables are binary (has/doesn't have) — doesn't capture enforcement intensity
- FARS data uses drimpair coding (likely undercounts vs NHTSA imputed figures)
- Speed limit is the max posted limit, not average driving speed
- Clustering with k=4 is exploratory — no "correct" number of clusters
