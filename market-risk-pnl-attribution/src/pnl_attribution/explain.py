"""Session P&L split and a stated-beta factor attribution.

The dollar identities do not divide. With decimal arithmetic they are exact
when the products fit in the default precision (28 significant digits).

Let ``dp = p_end - p_start`` and ``dq = q_end - q_start``.

```text
market   = q_start * dp
position = dq * dp
model    = market + position
residual = 0                        if no reported session P&L is supplied
residual = reported - model         if one is supplied
session  = model + residual

cash     = dq * p_start
mv       = q_end * p_end - q_start * p_start
mv - cash = model
```

The position term is the P&L on the quantity that was added or removed,
assuming that change was dealt at the start price. There is no trade tape.
``cash`` is the start-price value of that quantity change. It moves market
value and it is not, by itself, P&L.

Factor dollars use opening market value ``mv0 = q_start * p_start`` and the
stated inputs ``beta`` and ``f``:

```text
factor_k = mv0 * beta_k * f_k
specific = market - sum(factor_k)
```

So factor contributions plus the specific residual equal market P&L. They
are not a regression, and they do not include position P&L.

The returns printed beside that split are

```text
actual          = dp / p_start
predicted       = sum(beta_k * f_k)
residual_return = actual - predicted
```

When the division is exact, ``specific = mv0 * residual_return``. When it is
not, the last digits of that product can differ from ``specific``. The dollar
plug is the identity the totals use.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pnl_attribution.book import Book, FactorReturn, Loading, Position, betas_by_instrument, make_book
from pnl_attribution.version import __version__


@dataclass(frozen=True)
class InstrumentExplain:
    """P&L explain for one instrument. Amounts are decimals, gain positive."""

    instrument: str
    qty_start: Decimal
    qty_end: Decimal
    price_start: Decimal
    price_end: Decimal
    market_pnl: Decimal
    position_pnl: Decimal
    residual_pnl: Decimal
    session_pnl: Decimal
    market_value_change: Decimal
    cash_at_start: Decimal
    actual_return: Decimal
    predicted_return: Decimal
    factor_pnl: tuple[tuple[str, Decimal], ...]
    specific_pnl: Decimal
    reported_supplied: bool

    @property
    def residual_return(self) -> Decimal:
        """Price return the stated betas do not explain. Not the dollar residual."""
        return self.actual_return - self.predicted_return


@dataclass(frozen=True)
class ExplainResult:
    """Book-level explain. Totals are sums of the instrument rows."""

    version: str
    session: str
    currency: str
    factors: tuple[FactorReturn, ...]
    loadings: tuple[Loading, ...]
    instruments: tuple[InstrumentExplain, ...]

    def _sum(self, field: str) -> Decimal:
        return sum((getattr(row, field) for row in self.instruments), Decimal(0))

    @property
    def market_pnl(self) -> Decimal:
        return self._sum("market_pnl")

    @property
    def position_pnl(self) -> Decimal:
        return self._sum("position_pnl")

    @property
    def residual_pnl(self) -> Decimal:
        return self._sum("residual_pnl")

    @property
    def session_pnl(self) -> Decimal:
        return self._sum("session_pnl")

    @property
    def market_value_change(self) -> Decimal:
        return self._sum("market_value_change")

    @property
    def cash_at_start(self) -> Decimal:
        return self._sum("cash_at_start")

    @property
    def specific_pnl(self) -> Decimal:
        return self._sum("specific_pnl")

    @property
    def uses_reported_pnl(self) -> bool:
        return any(row.reported_supplied for row in self.instruments)

    def factor_totals(self) -> tuple[tuple[str, Decimal], ...]:
        """Sum of each factor's dollar contribution, in factor-file order."""
        if not self.instruments:
            return tuple((factor.factor, Decimal(0)) for factor in self.factors)
        width = len(self.instruments[0].factor_pnl)
        totals: list[tuple[str, Decimal]] = []
        for index in range(width):
            name = self.instruments[0].factor_pnl[index][0]
            total = sum((row.factor_pnl[index][1] for row in self.instruments), Decimal(0))
            totals.append((name, total))
        return tuple(totals)


def explain_book(book: Book) -> ExplainResult:
    """Explain one session. The result rows follow the position order."""
    book = make_book(
        book.positions,
        book.factors,
        book.loadings,
        session=book.session,
        currency=book.currency,
    )
    grouped = betas_by_instrument(book)
    rows = tuple(_explain_position(position, book, grouped[position.instrument]) for position in book.positions)
    return ExplainResult(
        version=__version__,
        session=book.session,
        currency=book.currency,
        factors=book.factors,
        loadings=book.loadings,
        instruments=rows,
    )


def _explain_position(
    position: Position,
    book: Book,
    loadings: tuple[Loading, ...],
) -> InstrumentExplain:
    qty_start = _decimal(position.qty_start)
    qty_end = _decimal(position.qty_end)
    price_start = _decimal(position.price_start)
    price_end = _decimal(position.price_end)
    delta_price = price_end - price_start
    delta_qty = qty_end - qty_start
    market = _unsigned_zero(qty_start * delta_price)
    position_pnl = _unsigned_zero(delta_qty * delta_price)
    model = market + position_pnl
    if position.reported_pnl is None:
        residual = Decimal(0)
        session = _unsigned_zero(model)
        reported_supplied = False
    else:
        session = _unsigned_zero(_decimal(position.reported_pnl))
        residual = _unsigned_zero(session - model)
        reported_supplied = True

    betas = {loading.factor: _decimal(loading.beta) for loading in loadings}
    opening_value = qty_start * price_start
    predicted = Decimal(0)
    contributions: list[tuple[str, Decimal]] = []
    for factor in book.factors:
        beta = betas.get(factor.factor, Decimal(0))
        simple_return = _decimal(factor.simple_return)
        if factor.factor in betas:
            predicted += beta * simple_return
        contributions.append((factor.factor, _unsigned_zero(opening_value * beta * simple_return)))
    specific = _unsigned_zero(market - sum((amount for _, amount in contributions), Decimal(0)))
    return InstrumentExplain(
        instrument=position.instrument,
        qty_start=qty_start,
        qty_end=qty_end,
        price_start=price_start,
        price_end=price_end,
        market_pnl=market,
        position_pnl=position_pnl,
        residual_pnl=residual,
        session_pnl=session,
        market_value_change=_unsigned_zero(qty_end * price_end - qty_start * price_start),
        cash_at_start=_unsigned_zero(delta_qty * price_start),
        actual_return=_unsigned_zero(delta_price / price_start),
        predicted_return=_unsigned_zero(predicted),
        factor_pnl=tuple(contributions),
        specific_pnl=specific,
        reported_supplied=reported_supplied,
    )


def _decimal(value: Decimal | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _unsigned_zero(value: Decimal) -> Decimal:
    """Map a signed zero to ``0``.

    Decimal keeps a sign on zero, so a short quantity times a zero beta prints
    as ``-0.00``. The value is still zero.
    """
    if value.is_zero():
        return Decimal(0)
    return value
