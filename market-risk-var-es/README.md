# Market risk VaR and Expected Shortfall

One-day Value at Risk (VaR) and Expected Shortfall (ES) for a small constant-weight portfolio, with the two standard coverage backtests: Kupiec unconditional coverage, and Christoffersen independence and conditional coverage.

This is a personal methodology demo for interviews. It is not a risk system, not a limit framework, and not investment advice. It is not affiliated with any employer. The numbers come from a recorded file of public ETF prices. Nothing here is private market data or a proprietary model.

## Quick start

```bash
cd market-risk-var-es
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

market-risk                        # or: python -m market_risk
python -m pytest
```

Python 3.10 or newer. The default command needs no network access.

## What it calculates

For a chosen confidence level (95% and 99% by default) and a trailing window (250 sessions by default):

- Historical VaR and historical ES on the portfolio's simple returns.
- Parametric (variance-covariance) VaR and ES under a Gaussian model.
- A rolling backtest of each VaR model, scored only on sessions that the forecast did not see.
- Kupiec's unconditional coverage test, Christoffersen's independence test, and the conditional coverage test.
- A single-position VaR table, so the gap between the sum of standalone VaRs and the portfolio VaR is visible. That gap is not an Euler allocation.

Losses are positive. A VaR of 1.18% on a 1,000,000 book is a loss threshold of 11,800. A negative VaR means the threshold outcome is a gain.

## Methodology

### Portfolio

Each column of the price file is a positive price. The engine uses close-to-close simple returns

```text
R(i, t) = P(i, t) / P(i, t-1) - 1
```

labeled on session `t`. A Monday row is the return from the previous session in the file, which is usually Friday. That is the usual "1-day" market-risk convention: one session ahead, close to close.

Weights are constant and must sum to 1. A negative weight is a short. The portfolio return is the weighted sum of simple returns, which is the right aggregation for a book that is back to those weights at each session. Log returns are not additive across names, so they are not used.

The current risk estimate uses the last `window` returns and applies to the next session. Each backtest forecast for session `t` uses only `returns[t - window : t]`.

### Historical VaR

```text
VaR(c) = - quantile(R_p, 1 - c)
```

The quantile is Hyndman-Fan type 7, which is NumPy's linear quantile and the default in R. Every session in the window has equal weight. There is no volatility scaling and no exponential decay.

### Parametric VaR

Asset sample means and the sample covariance `Sigma` (divisor `n - 1`) give

```text
mu_p    = w' mu
sigma_p = sqrt(w' Sigma w)
VaR(c)  = -(mu_p + sigma_p * invPhi(1 - c))
```

For constant weights, `sigma_p` matches the sample volatility of the portfolio return series. `--zero-mean` sets `mu_p` to 0 and still estimates `Sigma` around the sample means. That is the short-horizon "z times sigma" form. The default keeps the sample mean. On a one-day equity book the mean is small next to a 99% quantile, and the report shows both the mean and the VaR so the effect is easy to see.

On a standard normal, the formulas return the usual figures: 95% VaR 1.645 and ES 2.063; 99% VaR 2.326 and ES 2.665.

### Expected Shortfall

Historical ES is Acerbi's average of the empirical tail. With returns ordered `R(1) <= ... <= R(n)`, `alpha = 1 - c`, `u = n * alpha`, and `k = floor(u)`:

```text
ES(c) = -1/u * (sum of R(1)..R(k) + (u - k) * R(k+1))
```

When `u` is an integer this is the average of the worst `u` returns, written as a loss. A value of `u` that misses an integer only by binary rounding is treated as that integer.

This tail average and the type 7 VaR quantile are related estimators, not the same order statistic. On the sample book, ES is above VaR at both printed confidences. The tests check the tail formula on hand-built samples rather than assuming the two estimators coincide.

Gaussian ES is the mean loss beyond the Gaussian quantile:

```text
ES(c) = -mu_p + sigma_p * phi(invPhi(1 - c)) / (1 - c)
```

### Backtests

An exception (a hit) occurs when the realized simple return is strictly below minus the VaR forecast. A tie is not a hit.

Let `x` be the number of hits in `n` out-of-sample sessions, `p = x / n`, and `alpha = 1 - c`.

Kupiec's proportion-of-failures statistic (unconditional coverage) is

```text
LR_uc = -2 * ln( L(alpha) / L(p) )
```

referred to chi-square with 1 degree of freedom. The null is that the hit rate equals `alpha`. `0 * ln(0)` is taken as 0, so a sample with no hits still has a finite statistic.

Christoffersen's independence test treats hits as a two-state Markov chain. `pi01` is the hit probability after a quiet session, `pi11` is the hit probability after a hit, and `pi` is the single probability used when those two are forced equal:

```text
LR_ind = -2 * ln( L(pi) / L(pi01, pi11) )
```

also chi-square with 1 degree of freedom. A state that never occurs is left out of both likelihoods, so a sample with no hits does not reject independence.

Conditional coverage adds the two statistics:

```text
LR_cc = LR_uc + LR_ind
```

referred to chi-square with 2 degrees of freedom. Coverage is computed on all `n` hits. Independence is computed on the `n - 1` transitions. That is the original decomposition.

The null is rejected when the p-value is below the significance level (default 5%). A rejection says the data disagree with that null. The exception rate next to `alpha` shows the direction: a higher rate means the VaR was crossed more often than the confidence level claims.

## Sample portfolio and data

| Ticker | Weight | Role in the demo book |
| --- | --- | --- |
| SPY | 35% | US equity |
| EFA | 20% | Developed markets outside the US |
| EEM | 10% | Emerging markets equity |
| AGG | 25% | US aggregate bonds |
| GLD | 10% | Gold |

The weights are an illustrative fully invested book, not a recommendation.

Prices live in [`data/sample_prices.csv`](data/sample_prices.csv). They are dividend- and split-adjusted closes for the sessions from 4 January 2016 through 30 October 2026 (2,723 sessions present for every ticker), recorded from the public Yahoo Finance chart endpoint on 15 November 2026 and rounded to 6 decimal places. Adjusted closes are a total-return approximation. Yahoo can revise an adjusted series later; this file is a frozen snapshot. The engine, the tests, and CI read the file and do not download anything.

The date column is `YYYY-MM-DD`. To use another book, pass a CSV with the same layout and weights that match the columns and sum to 1:

```bash
python -m market_risk --prices my_prices.csv --weights SPY=0.60,AGG=0.40 --confidence 0.99
```

## Install, run, and test

```bash
cd market-risk-var-es
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Run the default report (95% and 99%, window of 250, portfolio value 1,000,000):

```bash
market-risk
python -m market_risk
```

Other entry points:

```bash
python -m market_risk --confidence 0.99 --window 250 --portfolio-value 1000000
python -m market_risk --zero-mean
python -m market_risk --weights SPY=0.60,EFA=0.15,EEM=0.05,AGG=0.15,GLD=0.05
```

Tests:

```bash
python -m pytest
```

The tests include hand-computed quantiles, the Gaussian ES against a truncated normal expectation, hand-computed Kupiec and Christoffersen likelihood ratios, and a check that a shock to the last session changes the current estimate without changing earlier forecasts.

GitHub Actions runs those tests from [`.github/workflows/market-risk-var-es.yml`](../.github/workflows/market-risk-var-es.yml) on Python 3.12. The workflow is path-filtered to this folder and that workflow file, and its working directory is `market-risk-var-es`, so it does not install or run the other folders in the repository.

From code:

```python
from market_risk import (
    SAMPLE_WEIGHTS,
    historical_var_return,
    load_prices,
    portfolio_returns,
    simple_returns,
)
from market_risk.portfolio import align_weights

prices = load_prices("data/sample_prices.csv")
weights = align_weights(prices.columns, SAMPLE_WEIGHTS)
returns = portfolio_returns(simple_returns(prices), weights)
print(historical_var_return(returns.iloc[-250:], 0.99))
```

## Reading the sample report

The current estimate below uses 3 November 2025 through 30 October 2026. The backtest is a different object: it re-estimates every session from 30 December 2016 through 30 October 2026, so the 2020 drawdown is inside the backtest and outside the current window. The current number is not a stressed VaR.

On this run, 95% historical and Gaussian VaR are almost the same (about 1.18% and 1.17%). Historical ES is higher than Gaussian ES (1.64% versus 1.48%), which is the heavier sample tail. Kupiec does not reject either 95% model at the 5% level. Independence does reject: a hit is more likely after a hit than after a quiet session. Conditional coverage rejects because of that clustering. An unconditional 250-day window has no volatility dynamics, so clustered hits are the expected failure mode.

At 99%, both models are crossed more often than 1% (1.54% historical, 2.39% Gaussian, against 24.72 expected exceptions). Kupiec rejects both. The Gaussian model is further off, which is what a thin-tailed distribution does in a far equity tail. The current 99% historical quantile is also coarse: a 250-day window has about 2.5 expected tail observations.

`Sum minus portfolio` is positive for both methods. Holding each ETF weight on its own and adding those VaRs overstates the book, because the five series do not move together one for one. That comparison is not a capital allocation.

## Example output

This is the default `market-risk` report for the recorded sample.

```text
market-risk-var-es 0.1.0
One-day (close-to-close) Value at Risk and Expected Shortfall

Portfolio value: 1,000,000.00
Weights: SPY 35.00%, EFA 20.00%, EEM 10.00%, AGG 25.00%, GLD 10.00%
Prices: 2016-01-04 to 2026-10-30 (2,723 sessions)
Simple returns: 2,722
Current estimate: last 250 returns, 2025-11-03 to 2026-10-30, applied to the next session
Parametric model: Gaussian variance-covariance using the sample mean and the sample covariance (divisor n - 1).
Backtest: rolling window of 250 returns. Each forecast uses only earlier sessions.
Exception: realized simple return < -VaR. A tie is not an exception.
Hypothesis tests are evaluated at the 5% significance level.
Losses are positive numbers. A negative VaR means the threshold outcome is a gain.

Estimation window, descriptive
Portfolio mean: 0.0340% per session
Portfolio volatility: 0.7342% per session (sample, divisor n - 1)
Annualized volatility, sqrt(252) of that session volatility, descriptive only: 11.66%

Asset volatility per session
Asset  Volatility
SPY    0.8071%
EFA    1.0034%
EEM    1.6161%
AGG    0.2561%
GLD    1.8027%

Correlation, estimation window
             SPY     EFA     EEM     AGG     GLD
SPY         1.00    0.79    0.77    0.39    0.40
EFA         0.79    1.00    0.79    0.52    0.50
EEM         0.77    0.79    1.00    0.37    0.48
AGG         0.39    0.52    0.37    1.00    0.25
GLD         0.40    0.50    0.48    0.25    1.00

Confidence 95.00%
Method      VaR return  VaR amount  ES return  ES amount
Historical  1.18%       11,817.37   1.64%      16,391.69
Parametric  1.17%       11,736.84   1.48%      14,804.92
The window has about 12.5 expected tail observations at this confidence.

Single-position VaR, each weight held on its own over the same window. This is not an Euler allocation. The rows do not sum to portfolio VaR.
Position             Historical VaR  Parametric VaR
SPY                  4,957.35        4,476.26
EFA                  3,087.47        3,192.21
EEM                  2,733.00        2,597.90
AGG                  1,028.29        1,054.57
GLD                  3,142.71        2,962.40
Sum                  14,948.81       14,283.36
Portfolio            11,817.37       11,736.84
Sum minus portfolio  3,131.44        2,546.52

Historical VaR backtest
Out of sample: 2016-12-30 to 2026-10-30 (2,472 sessions)
Exceptions: 143 (5.78%), expected 123.60 (5.00%). The rate is above the model tail probability.
Transitions: n00=2,202 n01=127 n10=126 n11=16
P(hit)=0.0579  P(hit | no hit)=0.0545  P(hit | hit)=0.1127
Kupiec unconditional coverage: LR=3.058  df=1  p-value=0.0803  decision=not rejected
  H0: the exception rate equals the model tail probability
Christoffersen independence: LR=6.704  df=1  p-value=0.0096  decision=rejected
  H0: exceptions are independent over time
Christoffersen conditional coverage: LR=9.762  df=2  p-value=0.0076  decision=rejected
  H0: coverage is correct and exceptions are independent

Parametric VaR backtest
Out of sample: 2016-12-30 to 2026-10-30 (2,472 sessions)
Exceptions: 129 (5.22%), expected 123.60 (5.00%). The rate is above the model tail probability.
Transitions: n00=2,230 n01=113 n10=112 n11=16
P(hit)=0.0522  P(hit | no hit)=0.0482  P(hit | hit)=0.1250
Kupiec unconditional coverage: LR=0.245  df=1  p-value=0.6206  decision=not rejected
  H0: the exception rate equals the model tail probability
Christoffersen independence: LR=10.807  df=1  p-value=0.0010  decision=rejected
  H0: exceptions are independent over time
Christoffersen conditional coverage: LR=11.052  df=2  p-value=0.0040  decision=rejected
  H0: coverage is correct and exceptions are independent

Confidence 99.00%
Method      VaR return  VaR amount  ES return  ES amount
Historical  1.90%       19,000.42   2.19%      21,908.08
Parametric  1.67%       16,740.63   1.92%      19,228.72
Note: the window has about 2.5 expected tail observations at this confidence, so the historical quantile is coarse.

Single-position VaR, each weight held on its own over the same window. This is not an Euler allocation. The rows do not sum to portfolio VaR.
Position             Historical VaR  Parametric VaR
SPY                  6,228.31        6,401.29
EFA                  4,764.71        4,559.90
EEM                  4,312.00        3,699.26
AGG                  1,600.81        1,490.87
GLD                  4,251.27        4,190.90
Sum                  21,157.09       20,342.22
Portfolio            19,000.42       16,740.63
Sum minus portfolio  2,156.67        3,601.59

Historical VaR backtest
Out of sample: 2016-12-30 to 2026-10-30 (2,472 sessions)
Exceptions: 38 (1.54%), expected 24.72 (1.00%). The rate is above the model tail probability.
Transitions: n00=2,398 n01=35 n10=35 n11=3
P(hit)=0.0154  P(hit | no hit)=0.0144  P(hit | hit)=0.0789
Kupiec unconditional coverage: LR=6.190  df=1  p-value=0.0128  decision=rejected
  H0: the exception rate equals the model tail probability
Christoffersen independence: LR=5.305  df=1  p-value=0.0213  decision=rejected
  H0: exceptions are independent over time
Christoffersen conditional coverage: LR=11.495  df=2  p-value=0.0032  decision=rejected
  H0: coverage is correct and exceptions are independent

Parametric VaR backtest
Out of sample: 2016-12-30 to 2026-10-30 (2,472 sessions)
Exceptions: 59 (2.39%), expected 24.72 (1.00%). The rate is above the model tail probability.
Transitions: n00=2,360 n01=52 n10=52 n11=7
P(hit)=0.0239  P(hit | no hit)=0.0216  P(hit | hit)=0.1186
Kupiec unconditional coverage: LR=34.574  df=1  p-value=4.10e-09  decision=rejected
  H0: the exception rate equals the model tail probability
Christoffersen independence: LR=12.398  df=1  p-value=0.0004  decision=rejected
  H0: exceptions are independent over time
Christoffersen conditional coverage: LR=46.972  df=2  p-value=6.31e-11  decision=rejected
  H0: coverage is correct and exceptions are independent

Personal methodology demo on public market data. Not a risk limit. Not investment advice.
```

## Layout

```text
market-risk-var-es/
  pyproject.toml
  data/sample_prices.csv
  src/market_risk/
    cli.py            command line
    portfolio.py      prices, weights, covariance
    risk.py           historical and Gaussian VaR and ES
    backtest.py       rolling hits, Kupiec, Christoffersen
    analysis.py       wires the current estimate to the backtest
    report.py         text report
  tests/
```

## Limitations

The horizon is one session. A 10-day figure is not produced. Square-root-of-time scaling is omitted because it needs i.i.d. returns, which the independence test on this sample already argues against.

The book is linear and constant-mix. There is no full revaluation, no options, no financing, no transaction costs, and no liquidity horizon. Bond and equity risk enter only through the ETF's own price history.

Historical VaR and ES weight each day in the window equally. There is no GARCH filter, no exponentially weighted covariance, and no volatility-scaled historical simulation.

The parametric model is an unconditional Gaussian on that window. Real equity returns are skewed and heavier tailed. Gaussian VaR at 99% is often too small for that reason, and Gaussian ES uses the same distribution, so it does not repair the assumption.

A 99% historical quantile on 250 sessions is a noisy order statistic. The report says so when the window holds fewer than five expected tail points.

The backtest scores VaR exceptions. It does not score the size of the losses beyond VaR, so it is not an ES backtest. The Kupiec and Christoffersen p-values are asymptotic chi-square approximations and are rough when exceptions are scarce.

`Sum minus portfolio` can be negative. VaR is not subadditive in general. A negative gap would be printed as it is.

The price file is a frozen public adjusted-close snapshot. It can differ from a vendor extract taken on another day.

This is a personal interview demo. It is not investment advice, not a trading signal, and not affiliated with any employer.

## References

- Kupiec, P. (1995). *Techniques for Verifying the Accuracy of Risk Measurement Models.* Journal of Derivatives, 3(2), 73–84.
- Christoffersen, P. (1998). *Evaluating Interval Forecasts.* International Economic Review, 39(4), 841–862.
- Acerbi, C. and Tasche, D. (2002). *On the coherence of expected shortfall.* Journal of Banking & Finance, 26(7), 1487–1503.
- Hyndman, R. and Fan, Y. (1996). *Sample quantiles in statistical packages.* The American Statistician, 50(4), 361–365.
