import numpy as np
import pandas as pd


def calculate_portfolio_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.07,
    periods_per_year: int = 252,
) -> dict:
    """
    Calculate portfolio performance and risk metrics.

    Parameters
    ----------
    portfolio_returns : pd.Series
        Portfolio periodic returns (daily preferred).

    benchmark_returns : pd.Series
        Benchmark periodic returns aligned to the same dates.

    risk_free_rate : float
        Annual risk-free rate as decimal. Example: 0.07 = 7%

    periods_per_year : int
        252 for daily returns, 12 for monthly returns.

    Returns
    -------
    dict
        Portfolio metrics including return, risk, CAPM, and drawdown stats.
    """

    # ----------------------------------
    # Clean and align series
    # ----------------------------------
    df = pd.concat(
        [portfolio_returns, benchmark_returns],
        axis=1,
        join="inner",
    ).dropna()

    if len(df) < 2:
        raise ValueError(
            "Not enough return observations to calculate metrics."
        )

    portfolio_returns = df.iloc[:, 0]
    benchmark_returns = df.iloc[:, 1]

    # ----------------------------------
    # Annualized returns
    # ----------------------------------
    annual_portfolio_return = portfolio_returns.mean() * periods_per_year
    annual_benchmark_return = benchmark_returns.mean() * periods_per_year

    # ----------------------------------
    # Standard deviation (volatility)
    # ----------------------------------
    std_dev = portfolio_returns.std(ddof=1) * np.sqrt(periods_per_year)

    # ----------------------------------
    # Sharpe ratio
    # ----------------------------------
    excess_return = annual_portfolio_return - risk_free_rate
    sharpe_ratio = excess_return / std_dev if std_dev > 0 else np.nan

    # ----------------------------------
    # Sortino ratio
    # ----------------------------------
    downside_returns = portfolio_returns[portfolio_returns < 0]
    if len(downside_returns) > 0:
        downside_deviation = (
            downside_returns.std(ddof=1) * np.sqrt(periods_per_year)
        )
        sortino_ratio = (
            excess_return / downside_deviation
            if downside_deviation > 0
            else np.nan
        )
    else:
        sortino_ratio = np.nan

    # ----------------------------------
    # Beta
    # ----------------------------------
    benchmark_variance = benchmark_returns.var(ddof=1)
    if benchmark_variance > 0:
        covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
        beta = covariance / benchmark_variance
    else:
        beta = np.nan

    # ----------------------------------
    # Jensen alpha
    # ----------------------------------
    if not np.isnan(beta):
        alpha = annual_portfolio_return - (
            risk_free_rate
            + beta * (annual_benchmark_return - risk_free_rate)
        )
    else:
        alpha = np.nan

    jensen_alpha = alpha

    # ----------------------------------
    # Treynor ratio
    # ----------------------------------
    treynor_ratio = (
        excess_return / beta
        if (not np.isnan(beta) and beta != 0)
        else np.nan
    )

    # ----------------------------------
    # Maximum drawdown
    # ----------------------------------
    cumulative = (1 + portfolio_returns).cumprod()
    rolling_peak = cumulative.cummax()
    drawdown_series = (cumulative - rolling_peak) / rolling_peak
    max_drawdown = float(drawdown_series.min())   # negative value

    # ----------------------------------
    # Calmar ratio  (annualised return / |max drawdown|)
    # ----------------------------------
    calmar_ratio = (
        annual_portfolio_return / abs(max_drawdown)
        if max_drawdown != 0
        else np.nan
    )

    # ----------------------------------
    # Information ratio  (active return / tracking error)
    # ----------------------------------
    active_returns = portfolio_returns - benchmark_returns
    tracking_error = active_returns.std(ddof=1) * np.sqrt(periods_per_year)
    active_return_annualized = active_returns.mean() * periods_per_year
    information_ratio = (
        active_return_annualized / tracking_error
        if tracking_error > 0
        else np.nan
    )

    # ----------------------------------
    # Build output
    # ----------------------------------
    def _round(val, decimals=4):
        return round(float(val), decimals) if not np.isnan(val) else None

    return {
        "annual_portfolio_return": _round(annual_portfolio_return * 100, 2),
        "annual_benchmark_return": _round(annual_benchmark_return * 100, 2),
        "std_dev":                 _round(std_dev * 100, 2),
        "sharpe":                  _round(sharpe_ratio),
        "sortino":                 _round(sortino_ratio),
        "beta":                    _round(beta),
        "alpha":                   _round(alpha * 100, 2),
        "jensen_alpha":            _round(jensen_alpha * 100, 2),
        "treynor":                 _round(treynor_ratio),
        # --- new metrics ---
        "max_drawdown":            _round(max_drawdown * 100, 2),   # % (negative)
        "calmar_ratio":            _round(calmar_ratio),
        "information_ratio":       _round(information_ratio),
    }