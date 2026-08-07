# YouTube DUI Body Cam Content — Feasibility Assessment

**Date:** 2025-08-07  
**Status:** Feasible with caveats. Recommend hybrid approach.

---

## Research Question

Can we quantify DUI body cam content volume on YouTube by state to
explore whether "perception" (viral body cam DUI content) correlates
with actual DUI fatality rates?

---

## Approaches Evaluated

### 1. YouTube Data API v3 — Search Counts

**Method:** Query `search.list` for "DUI body cam [state]" for each state and
capture `pageInfo.totalResults`.

**Constraints:**
- Default quota: 10,000 units/day (each search = 100 units → 100 queries/day max)
- `totalResults` is an **unreliable estimate** — Google explicitly notes it may be
  inflated and inconsistent between requests
- No geographic metadata on videos; state must be inferred from title/description
- Would need 51 queries (one per state) — fits in one day's quota easily
- Results limited to 500 items max per query (pagination caps)

**Verdict:** Usable as a rough ordinal ranking (state A has "more" content than
state B) but NOT as precise counts. Good enough for a perception proxy if
normalized carefully.

**Implementation plan:**
```python
# 51 queries × 100 units = 5,100 units (well within daily quota)
for state in states:
    query = f"DUI body cam {state_name}"
    results = youtube.search().list(q=query, type='video', part='snippet',
                                    maxResults=1, order='relevance').execute()
    count = results['pageInfo']['totalResults']  # rough estimate
```

### 2. Google Trends — YouTube Search Volume by State

**Method:** Use Google Trends filtered to YouTube Search for terms like "DUI body cam",
"DUI arrest body camera", etc. and get relative interest by state.

**Pros:**
- Free, no API key needed (pytrends library)
- Gives relative search interest (0–100 scale) by U.S. state
- Reflects viewer DEMAND, not supply — complementary angle
- Can compare multiple queries and time ranges

**Cons:**
- Relative scale only (not absolute counts)
- Low-volume terms may return no data for many states
- Requires pytrends or manual export from trends.google.com

**Verdict:** Best signal for "which states' residents are most interested in
DUI body cam content." Easier and more reliable than API counts.

### 3. Manual Survey / Channel Analysis

**Method:** Identify top 10-20 DUI body cam YouTube channels, manually code
their videos by state mentioned in title/description.

**Pros:**
- Most accurate state attribution
- Can capture view counts, engagement, channel size
- Small sample but defensible methodology

**Cons:**
- Time-intensive (manual work)
- Small N — may miss long-tail content
- Subjective channel selection

**Verdict:** Best for a focused deep-dive if the broader data shows promise.
Not scalable for initial exploration.

---

## Recommended Hybrid Approach

1. **Google Trends (YouTube filter)** — Get relative search interest by state
   for "DUI body cam", "drunk driving arrest", "DUI stop body camera"
   - Tool: `pytrends` or manual CSV export from trends.google.com
   - Effort: Low (1 hour)
   - Output: 51 rows with relative interest score

2. **YouTube API top-level counts** — Get estimated video count per state
   using `search.list` with state name in query
   - Tool: YouTube Data API v3 (need Google Cloud API key)
   - Effort: Medium (2 hours with API setup)
   - Output: 51 rows with estimated result counts

3. **Compare both signals to actual DUI data** — Scatter/correlation:
   - YouTube supply (API counts) vs fatality rate
   - YouTube demand (Trends) vs fatality rate
   - Test hypothesis: states with more body cam content ≠ states with more DUI deaths

---

## Data Quality Caveats

- YouTube `totalResults` is an estimate, not exact
- State inference from video titles is imperfect (some videos don't mention state)
- Google Trends relative scores are normalized — a score of 50 doesn't mean half of 100
- Body cam DUI content skews toward states with: (a) proactive FOIA/release laws,
  (b) popular channels based there, (c) viral incidents
- Correlation ≠ causation: high YouTube presence may reflect media culture, not DUI prevalence

---

## Next Steps

- [ ] Set up Google Cloud project + enable YouTube Data API v3
- [ ] Run Google Trends export for YouTube-filtered "DUI body cam" by state
- [ ] Execute 51 API queries and save raw results
- [ ] Merge with master dataset and compute correlations
- [ ] Visualize: perception (YouTube) vs reality (fatality rate) scatter

---

## Dependencies

```
google-api-python-client    # YouTube Data API
pytrends                    # Google Trends (unofficial)
```

## Budget

- YouTube API: Free tier (10,000 units/day) sufficient
- Google Trends: Free
- Estimated total time: 3-4 hours for complete data collection + analysis
