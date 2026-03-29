from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from data.market.fetcher import (
    fetch_company_info,
    fetch_financial_periods,
    fetch_market_snapshot,
    fetch_price_history,
)
from data.market.schemas import (
    CompanyInfo,
    FinancialPeriod,
    MarketDataBundle,
    MarketSnapshot,
    PriceBar,
)


CACHE_ROOT = Path(__file__).resolve().parents[1] / "cache" / "market"


def _normalize_ticker(ticker: str) -> str:
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("ticker must be a non-empty string.")
    return symbol


def _validate_period_type(period_type: str) -> str:
    normalized = period_type.strip().lower()
    if normalized not in {"annual", "quarterly"}:
        raise ValueError("period_type must be either 'annual' or 'quarterly'.")
    return normalized


def _safe_filename_part(value: str) -> str:
    cleaned = value.strip().replace("/", "_").replace("\\", "_").replace(" ", "_")
    return cleaned or "default"


def _get_ticker_cache_dir(ticker: str) -> Path:
    return CACHE_ROOT / _normalize_ticker(ticker)


def _get_info_cache_path(ticker: str) -> Path:
    return _get_ticker_cache_dir(ticker) / "info.json"


def _get_snapshot_cache_path(ticker: str) -> Path:
    return _get_ticker_cache_dir(ticker) / "snapshot.json"


def _get_price_history_cache_path(ticker: str, period: str, interval: str) -> Path:
    return (
        _get_ticker_cache_dir(ticker)
        / f"price_history_{_safe_filename_part(period)}_{_safe_filename_part(interval)}.json"
    )


def _get_financials_cache_path(ticker: str, period_type: str) -> Path:
    normalized_period_type = _validate_period_type(period_type)
    filename = "annual_financials.json" if normalized_period_type == "annual" else "quarterly_financials.json"
    return _get_ticker_cache_dir(ticker) / filename


def _ensure_cache_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _serialize_for_json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, dict):
        return {key: _serialize_for_json(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_serialize_for_json(item) for item in value]

    return value


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data: Any) -> None:
    _ensure_cache_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(_serialize_for_json(data), file, indent=2, ensure_ascii=False)


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if not isinstance(value, str) or not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None


def _load_or_fetch(
    cache_path: Path,
    fetch_func,
    *fetch_args: Any,
    use_cache: bool = True,
    refresh: bool = False,
) -> Any:
    if use_cache and not refresh:
        cached_data = _read_json(cache_path)
        if cached_data is not None:
            return cached_data

    fresh_data = fetch_func(*fetch_args)

    if use_cache:
        _write_json(cache_path, fresh_data)

    return fresh_data


def _company_info_from_dict(data: dict[str, Any] | None) -> CompanyInfo | None:
    if not data:
        return None

    ticker = data.get("ticker")
    if not ticker:
        return None

    return CompanyInfo(
        ticker=str(ticker),
        company_name=data.get("company_name"),
        sector=data.get("sector"),
        industry=data.get("industry"),
        exchange=data.get("exchange"),
        currency=data.get("currency"),
    )


def _market_snapshot_from_dict(data: dict[str, Any] | None) -> MarketSnapshot | None:
    if not data:
        return None

    return MarketSnapshot(
        current_price=data.get("current_price"),
        market_cap=data.get("market_cap"),
        enterprise_value=data.get("enterprise_value"),
        shares_outstanding=data.get("shares_outstanding"),
        beta=data.get("beta"),
        pe_ratio=data.get("pe_ratio"),
        pb_ratio=data.get("pb_ratio"),
        ps_ratio=data.get("ps_ratio"),
        dividend_yield=data.get("dividend_yield"),
        fifty_two_week_high=data.get("fifty_two_week_high"),
        fifty_two_week_low=data.get("fifty_two_week_low"),
    )


def _price_bar_from_dict(data: dict[str, Any]) -> PriceBar | None:
    bar_date = _parse_iso_date(data.get("date"))
    if bar_date is None:
        return None

    return PriceBar(
        date=bar_date,
        open=data.get("open"),
        high=data.get("high"),
        low=data.get("low"),
        close=data.get("close"),
        volume=data.get("volume"),
    )


def _financial_period_from_dict(data: dict[str, Any]) -> FinancialPeriod | None:
    period_end = _parse_iso_date(data.get("period_end"))
    if period_end is None:
        return None

    return FinancialPeriod(
        period_end=period_end,
        period_type=data.get("period_type") or "annual",
        fiscal_year=data.get("fiscal_year"),
        fiscal_quarter=data.get("fiscal_quarter"),
        revenue=data.get("revenue"),
        gross_profit=data.get("gross_profit"),
        ebit=data.get("ebit"),
        operating_income=data.get("operating_income"),
        net_income=data.get("net_income"),
        depreciation_amortization=data.get("depreciation_amortization"),
        interest_expense=data.get("interest_expense"),
        income_tax_expense=data.get("income_tax_expense"),
        dividends_paid=data.get("dividends_paid"),
        capex=data.get("capex"),
        change_in_nwc=data.get("change_in_nwc"),
        operating_cash_flow=data.get("operating_cash_flow"),
        free_cash_flow=data.get("free_cash_flow"),
        cash=data.get("cash"),
        total_debt=data.get("total_debt"),
        shareholders_equity=data.get("shareholders_equity"),
        shares_outstanding=data.get("shares_outstanding"),
        current_assets=data.get("current_assets"),
        current_liabilities=data.get("current_liabilities"),
    )


def get_company_info(
    ticker: str,
    use_cache: bool = True,
    refresh: bool = False,
) -> CompanyInfo | None:
    cache_path = _get_info_cache_path(ticker)
    raw_data = _load_or_fetch(
        cache_path,
        fetch_company_info,
        _normalize_ticker(ticker),
        use_cache=use_cache,
        refresh=refresh,
    )
    return _company_info_from_dict(raw_data)


def get_market_snapshot(
    ticker: str,
    use_cache: bool = True,
    refresh: bool = False,
) -> MarketSnapshot | None:
    cache_path = _get_snapshot_cache_path(ticker)
    raw_data = _load_or_fetch(
        cache_path,
        fetch_market_snapshot,
        _normalize_ticker(ticker),
        use_cache=use_cache,
        refresh=refresh,
    )
    return _market_snapshot_from_dict(raw_data)


def get_price_history(
    ticker: str,
    period: str = "5y",
    interval: str = "1d",
    use_cache: bool = True,
    refresh: bool = False,
) -> list[PriceBar]:
    cache_path = _get_price_history_cache_path(ticker, period, interval)
    raw_data = _load_or_fetch(
        cache_path,
        fetch_price_history,
        _normalize_ticker(ticker),
        period,
        interval,
        use_cache=use_cache,
        refresh=refresh,
    )

    if not isinstance(raw_data, list):
        return []

    price_bars: list[PriceBar] = []
    for item in raw_data:
        if not isinstance(item, dict):
            continue
        price_bar = _price_bar_from_dict(item)
        if price_bar is not None:
            price_bars.append(price_bar)

    return price_bars


def get_financial_periods(
    ticker: str,
    period_type: str = "annual",
    use_cache: bool = True,
    refresh: bool = False,
) -> list[FinancialPeriod]:
    normalized_period_type = _validate_period_type(period_type)
    cache_path = _get_financials_cache_path(ticker, normalized_period_type)
    raw_data = _load_or_fetch(
        cache_path,
        fetch_financial_periods,
        _normalize_ticker(ticker),
        normalized_period_type,
        use_cache=use_cache,
        refresh=refresh,
    )

    if not isinstance(raw_data, list):
        return []

    financial_periods: list[FinancialPeriod] = []
    for item in raw_data:
        if not isinstance(item, dict):
            continue
        financial_period = _financial_period_from_dict(item)
        if financial_period is not None:
            financial_periods.append(financial_period)

    return financial_periods


def get_market_data_bundle(
    ticker: str,
    price_period: str = "5y",
    price_interval: str = "1d",
    include_annual: bool = True,
    include_quarterly: bool = True,
    use_cache: bool = True,
    refresh: bool = False,
) -> MarketDataBundle:
    company_info = get_company_info(
        ticker=ticker,
        use_cache=use_cache,
        refresh=refresh,
    )
    market_snapshot = get_market_snapshot(
        ticker=ticker,
        use_cache=use_cache,
        refresh=refresh,
    )
    price_history = get_price_history(
        ticker=ticker,
        period=price_period,
        interval=price_interval,
        use_cache=use_cache,
        refresh=refresh,
    )

    annual_financials: list[FinancialPeriod] = []
    if include_annual:
        annual_financials = get_financial_periods(
            ticker=ticker,
            period_type="annual",
            use_cache=use_cache,
            refresh=refresh,
        )

    quarterly_financials: list[FinancialPeriod] = []
    if include_quarterly:
        quarterly_financials = get_financial_periods(
            ticker=ticker,
            period_type="quarterly",
            use_cache=use_cache,
            refresh=refresh,
        )

    return MarketDataBundle(
        company_info=company_info,
        market_snapshot=market_snapshot,
        price_history=price_history,
        annual_financials=annual_financials,
        quarterly_financials=quarterly_financials,
    )
