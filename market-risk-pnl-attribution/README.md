# Market risk P&L attribution

One session of linear P&L for a small snapshot book, split into the market move on the opening quantity and the P&L from a quantity change, then a stated-beta factor split of the market piece.

This is a personal methodology demo for interviews. It is not a P&L system, not a limit framework, and not investment advice. It is not affiliated with any employer. The book, the prices, and the factor returns are synthetic. Nothing here is private market data or a proprietary model.

See also [market-risk-var-es](../market-risk-var-es/), which estimates a distribution of returns and backtests VaR. This project does not estimate a distribution. It explains one session. See also [market-risk-streaming-lake](../market-risk-streaming-lake/). That pipeline's session P&L is the latest quantity times the price change, and its README notes that a production explain would split the size change from the market move. This project is that split, on its own snapshot. Neither sibling is imported, and neither has to be installed.

## Quick start

```bash
cd market-risk-pnl-attribution
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

pnl-attribution                    # or: python -m pnl_attribution
python -m pytest
python -m ruff check --select E4,E7,E9,F src tests
```

Python 3.10 or newer. The default command needs no network access, no API key, and no other folder in this repository.

## What it calculates

For one labeled session, on each instrument:

- Market P&L: the price move on the quantity held at the start.
- Position P&L: the price move on the quantity that was added or removed, assuming that change was dealt at the start price.
- Residual: the gap between an optional reported session P&L and those two terms. On the shipped book the column is absent, so the residual is 0.
- A factor split of market P&L only. Each stated beta times the stated factor simple return, scaled by opening market value. The part of market P&L the betas do not explain is specific P&L.

Two adding-up rules are exact in decimal arithmetic, for values that fit in the default precision of 28 significant digits:

```text
session P&L = market P&L + position P&L + residual
market P&L  = sum of factor P&L + specific P&L
```

Factor P&L does not add up to session P&L. Position P&L sits outside it.

A gain is positive. A negative quantity is a short. Prices are positive USD amounts. There is one currency and no conversion.

## Methodology

The inputs are two snapshots and a set of stated factor moves. There is no trade tape, no path inside the session, and no estimated regression.

Let `dp = p_end - p_start` and `dq = q_end - q_start`.

```text
market   = q_start * dp
position = dq * dp
model    = market + position

residual = 0                        if no reported session P&L is supplied
residual = reported - model         if one is supplied
session  = model + residual
```

Dealing the quantity change at the start price is an assumption, not a fact about a market. A trade tape would replace `p_start` in the position term with the trade price. This demo does not take one.

The same assumption separates P&L from cash:

```text
cash = dq * p_start
mv   = q_end * p_end - q_start * p_start
mv - cash = model
```

`cash` is the start-price value of the quantity change. It changes market value. It is not, by itself, P&L. Session P&L equals `mv - cash` plus the residual.

When the residual is 0, session P&L is also `q_end * dp`. That is the "latest quantity times the price change" figure. The split shows how much of it came from the opening quantity and how much from the quantity change.

A constant-mix book is the special case `q_end = q_start` on every name. Position P&L is then 0, and session P&L equals market P&L when the residual is 0. The shipped book is a snapshot: some names are unchanged, one grows, one opens, and one closes.

### Factor split

Opening market value is `mv0 = q_start * p_start`. For each stated loading,

```text
factor_k = mv0 * beta_k * f_k
specific = market - sum(factor_k)
```

`f_k` is the factor's simple return, an input. `beta_k` is an input. Nothing here fits a beta, shrinks one, or reads a history. An instrument may load on more than one factor. An instrument with no loading has specific P&L equal to its market P&L. A beta may be negative. A factor return is not clipped.

The returns printed next to the dollars are a reading aid:

```text
actual          = dp / p_start
predicted       = sum(beta_k * f_k)
residual_return = actual - predicted
```

When `dp / p_start` is an exact decimal, `specific = mv0 * residual_return`. When it is not, the last digits of that product can differ from `specific`. The dollar plug above is the identity the totals use. A price move from 3 to 4 is the test case for the inexact division. The sample file uses divisions that are exact, so both agree on the shipped book.

Factor dollars are scaled by opening market value. A new position has `mv0 = 0`, so every factor dollar is 0 even if the residual return is not. A position that is closed by the end still has factor P&L, because the market term uses the opening quantity. Under the start-price assumption that factor P&L is offset in session P&L by the position term, and the session total is 0.

Arithmetic is decimal, not binary floating point. CSV values are parsed as exact decimal strings, so `0.1` is `0.1`. A Python `float` passed into `make_book` is rejected. Amounts in the report are rounded half-even to cents for display. The shipped figures are already exact cents, so the printed table adds up. The identities in the tests are on the unrounded decimals.

## Sample book

The session label is `2026-06-12`. It is a label, not a calendar lookup. Prices and factor returns are invented. `EQ`, `RT`, and `FX` are names for a toy equity factor, a toy rates factor, and a toy FX factor. `RT` is not a yield and not a curve. `FX` is not a currency conversion. Every price is already a positive USD amount, including the FX name.

| Factor | Simple return |
| --- | ---: |
| EQ | 1% |
| RT | 0.5% |
| FX | -2% |

| Instrument | Start qty | End qty | Start px | End px | Betas | What it is there for |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| SYN-EQ-A | 1,000 | 1,000 | 100 | 101 | EQ 1 | Held. The price return equals the EQ factor, so specific P&L is 0. |
| SYN-EQ-B | 500 | 700 | 40 | 40.8 | EQ 1, RT 0.5 | Size increases. Two loadings, and the price return is not that mix. |
| SYN-RT-A | 2,000 | 2,000 | 100 | 100.5 | RT 0.5 | Held. Half of the RT factor, so half of the market P&L is specific. |
| SYN-FX-A | -10,000 | -10,000 | 1.25 | 1.20 | FX 1 | Short, held. The price falls by more than the FX factor. |
| SYN-EQ-C | 0 | 250 | 80 | 81.6 | EQ 1 | Opens from zero. Market P&L and factor P&L are 0. |
| SYN-RT-B | 400 | 0 | 50 | 49 | RT 1 | Closes. Dealt at the start price, so session P&L is 0. |
| SYN-FX-B | 1,000 | 1,500 | 2 | 2 | FX 1 | Price does not move. Quantity does. Session P&L is 0. |

On this book:

- SYN-EQ-A market P&L is 1,000, all of it EQ. Position P&L is 0.
- SYN-EQ-B market P&L is 400, of which EQ is 200, RT is 50, and specific is 150. The extra 200 units add position P&L of 160. Session P&L is 560. The 160 is not in the factor table.
- SYN-FX-A is a short whose price fell, so market P&L is a gain of 500. FX explains 250 and specific explains 250.
- SYN-EQ-C earns 400 in the position column. Its residual return is 1% and its specific P&L is 0, because the opening market value is 0.
- SYN-RT-B market P&L is -400 and position P&L is +400, so the session is 0. The factor table still shows RT 100 and specific -500. Those explain the market term, which the close then offsets.
- SYN-FX-B has market P&L 0 and position P&L 0. The FX factor contributes -40 and specific contributes +40. The factor said the price should fall. It did not. The two dollars offset, and the session is still 0.

Totals: market 2,500, position 960, residual 0, session 3,460. Factor dollars are EQ 1,200, RT 650, FX 210, and specific 440, which sum to 2,500. Cash at the start price is 9,000. The market-value change is 12,460. Change minus cash is 3,460, the session P&L.

An optional `reported_pnl` column on the position file replaces the model session P&L for that row. The residual is then `reported - market - position`. The shipped file omits the column. A ledger figure, a fee, or a one-cent difference would go there. This demo does not invent one.

```csv
instrument,qty_start,qty_end,price_start,price_end,reported_pnl
SYN-EQ-A,1000,1000,100,101,999.50
```

That row would keep market P&L at 1,000 and print a residual of -0.50.

## Install, run, and test

```bash
cd market-risk-pnl-attribution
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

There are no runtime dependencies beyond Python. The `dev` extra is pytest and ruff.

Run the shipped snapshot:

```bash
pnl-attribution
python -m pnl_attribution
```

Other entry points:

```bash
python -m pnl_attribution --session 2026-06-12
python -m pnl_attribution \
  --positions data/positions.csv \
  --factors data/factors.csv \
  --loadings data/loadings.csv
```

`--session` changes the label only. It does not reprice the book.

Tests and the lint check CI runs:

```bash
python -m pytest
python -m ruff check --select E4,E7,E9,F src tests
```

The tests include the two dollar identities, hand-computed market / position / factor figures, the new, closed, flat, and short cases, a reported P&L residual, and a price move from 3 to 4 where the return division is not exact and the dollar plug still holds. They also check that the example below matches the default report.

GitHub Actions runs those commands from [`.github/workflows/market-risk-pnl-attribution.yml`](../.github/workflows/market-risk-pnl-attribution.yml) on Python 3.12. The workflow is path-filtered to this folder and that workflow file, and its working directory is `market-risk-pnl-attribution`, so it does not install or run the other folders in the repository.

From code:

```python
from pnl_attribution import explain_book, load_sample_book
from pnl_attribution.report import format_report

result = explain_book(load_sample_book())
print(result.session_pnl)
print(format_report(result))
```

To explain another book, build it with `make_book` or point `load_book` at three CSV files with the columns above. Quantities and prices are `Decimal` or `int`. A binary float is rejected.

## Example output

This is the default `pnl-attribution` report for the synthetic snapshot.

```text
market-risk-pnl-attribution 0.1.0
Session P&L explain for a linear snapshot book

Session label: 2026-06-12
Currency: USD
Book: 7 instruments
Data: synthetic snapshot. No market download.

Session P&L = market P&L + position P&L + residual.
Market P&L = start quantity x (end price - start price).
Position P&L = quantity change x (end price - start price).
Quantity changes are dealt at the start price. There is no trade tape.
No reported session P&L was supplied. Residual is 0, and session P&L is market P&L + position P&L.
Factor P&L = opening market value x stated beta x stated factor simple return. The betas are inputs, not a fitted model.
Factor P&L + specific P&L = market P&L. Position P&L is outside that sum.
A gain is positive. Prices are positive USD amounts. Short quantities are allowed.
Factor names are labels. Nothing here treats a factor as a yield, a curve, or a currency conversion.

Factor simple returns
These returns are inputs. They are not estimated from the instrument prices.
Factor  Return
EQ       1.00%
RT       0.50%
FX      -2.00%

Stated betas
A missing instrument here has no factor loading. Its market P&L is specific.
Instrument  Factor  Beta
SYN-EQ-A    EQ       1.0
SYN-EQ-B    EQ       1.0
SYN-EQ-B    RT       0.5
SYN-RT-A    RT       0.5
SYN-FX-A    FX       1.0
SYN-EQ-C    EQ       1.0
SYN-RT-B    RT       1.0
SYN-FX-B    FX       1.0

Instrument P&L
Instrument   Qty start     Qty end  Px start  Px end    Market  Position  Residual   Session
SYN-EQ-A      1,000.00    1,000.00    100.00  101.00  1,000.00      0.00      0.00  1,000.00
SYN-EQ-B        500.00      700.00     40.00   40.80    400.00    160.00      0.00    560.00
SYN-RT-A      2,000.00    2,000.00    100.00  100.50  1,000.00      0.00      0.00  1,000.00
SYN-FX-A    -10,000.00  -10,000.00      1.25    1.20    500.00      0.00      0.00    500.00
SYN-EQ-C          0.00      250.00     80.00   81.60      0.00    400.00      0.00    400.00
SYN-RT-B        400.00        0.00     50.00   49.00   -400.00    400.00      0.00      0.00
SYN-FX-B      1,000.00    1,500.00      2.00    2.00      0.00      0.00      0.00      0.00

Session identity
Market + position + residual = session P&L.
Component      Amount
Market       2,500.00
Position       960.00
Residual         0.00
Session P&L  3,460.00

Market value and cash
Cash is the quantity change times the start price.
Buying units at the start price changes market value and does not, by itself, create P&L.
Market-value change minus cash equals market P&L + position P&L.
Session P&L equals that sum plus the residual.
Component                   Amount
Market-value change      12,460.00
Cash at the start price   9,000.00
Change minus cash         3,460.00
Market + position         3,460.00

Factor attribution of market P&L
Each contribution is opening market value x beta x factor simple return.
The rows below sum to market P&L. They do not sum to session P&L.
Component     Amount
EQ          1,200.00
RT            650.00
FX            210.00
Specific      440.00
Market P&L  2,500.00

Instrument factor split
A zero means the opening market value, the beta, or the factor return produced zero.
A new position has opening market value zero, so every factor dollar is zero.
Instrument    Market        EQ      RT      FX  Specific
SYN-EQ-A    1,000.00  1,000.00    0.00    0.00      0.00
SYN-EQ-B      400.00    200.00   50.00    0.00    150.00
SYN-RT-A    1,000.00      0.00  500.00    0.00    500.00
SYN-FX-A      500.00      0.00    0.00  250.00    250.00
SYN-EQ-C        0.00      0.00    0.00    0.00      0.00
SYN-RT-B     -400.00      0.00  100.00    0.00   -500.00
SYN-FX-B        0.00      0.00    0.00  -40.00     40.00

Price returns
Actual is the instrument simple return. Predicted is the sum of beta x factor return.
Specific P&L equals opening market value times the residual return when that division is exact.
The dollar identity does not depend on the division. A new position can show a residual return and specific P&L of 0.
Instrument  Actual  Predicted  Residual return
SYN-EQ-A     1.00%      1.00%            0.00%
SYN-EQ-B     2.00%      1.25%            0.75%
SYN-RT-A     0.50%      0.25%            0.25%
SYN-FX-A    -4.00%     -2.00%           -2.00%
SYN-EQ-C     2.00%      1.00%            1.00%
SYN-RT-B    -2.00%      0.50%           -2.50%
SYN-FX-B     0.00%     -2.00%            2.00%

Personal interview demo on synthetic data. Not a production risk system. Not investment advice. Not affiliated with any employer.
```

## Layout

```text
market-risk-pnl-attribution/
  pyproject.toml
  data/positions.csv    synthetic snapshot
  data/factors.csv      stated factor simple returns
  data/loadings.csv     stated betas
  src/pnl_attribution/
    book.py             load and validate the snapshot
    explain.py          market, position, residual, factor dollars
    report.py           text report
    cli.py              pnl-attribution
  tests/
```

## Limitations

The horizon is one session and two snapshots. There is no path inside the session, no financing, and no fee unless it is supplied as a reported P&L. The position term assumes the quantity change was dealt at the start price.

The book is linear. There is no full revaluation, no options, no convexity, no time decay, and no curve. Bond and FX risk enter only as a stated beta on a named price factor. This is not a Brinson attribution against a benchmark, and it is not an Euler allocation of a risk measure.

The factor model is whatever betas and factor returns the files contain. It is not fitted, not shrunk, and not a claim that those factors caused the price. Specific P&L is the remainder of market P&L. It will be large when the stated model is a poor description of the price, which is the point of printing it.

A new position has no factor P&L. A close at the start price has session P&L of 0 and can still show factor P&L on the market term. Reading the factor table as a split of session P&L would double-count or miss the position term. The report says the factor rows sum to market P&L.

Quantities may be negative. Prices may not. A factor return below -100% is accepted, because a factor return is an input and not itself a price.

Dollar arithmetic uses decimal numbers at the default precision of 28 significant digits. The shipped book is far inside that. A product of longer inputs can round in the last place, and then an algebraic identity can miss by a unit in that place.

The report rounds displayed amounts and percents to two decimal places, half to even. The tests check the unrounded decimals. On this snapshot the two agree.

This is a personal interview demo. It is not investment advice, not a trading signal, and not affiliated with any employer.
