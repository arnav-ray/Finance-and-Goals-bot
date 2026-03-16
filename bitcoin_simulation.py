import numpy as np
import pandas as pd

def simulate_bitcoin_price(days=120, initial_price=60000, volatility=0.04, drift=0.0005):
    """
    Simulates Bitcoin price using Geometric Brownian Motion.
    """
    np.random.seed(42)  # For reproducibility
    # daily_returns are log returns
    daily_returns = np.random.normal(drift, volatility, days)
    # price = P0 * exp(sum(r))
    price_series = initial_price * np.exp(np.cumsum(daily_returns))
    return price_series

def main():
    # 1. Simulate 90 days of data to ensure we have SMAs for the last 60 days
    total_days = 90
    prices = simulate_bitcoin_price(days=total_days)

    # Create a DataFrame
    days_range = pd.date_range(start='2023-01-01', periods=total_days)
    df = pd.DataFrame({'Date': days_range, 'Price': prices})

    # 2. Calculate Moving Averages
    df['SMA7'] = df['Price'].rolling(window=7).mean()
    df['SMA30'] = df['Price'].rolling(window=30).mean()

    # 3. Implement 'Golden Cross' trading algorithm for the last 60 days
    ledger_df = df.iloc[-60:].copy().reset_index(drop=True)

    cash = 10000.0
    btc_holdings = 0.0
    initial_cash = cash

    print(f"{'Day':<3} | {'Date':<10} | {'Price':<10} | {'SMA7':<10} | {'SMA30':<10} | {'Action':<6} | {'Portfolio Value':<15}")
    print("-" * 85)

    for i in range(len(ledger_df)):
        row = ledger_df.iloc[i]
        day = i + 1
        date_str = row['Date'].strftime('%Y-%m-%d')
        price = row['Price']
        sma7 = row['SMA7']
        sma30 = row['SMA30']
        action = "-"

        # Check for Golden Cross (SMA7 > SMA30)
        if not np.isnan(sma7) and not np.isnan(sma30):
            if sma7 > sma30 and btc_holdings == 0:
                # Buy
                btc_holdings = cash / price
                cash = 0
                action = "BUY"
            elif sma7 < sma30 and btc_holdings > 0:
                # Sell
                cash = btc_holdings * price
                btc_holdings = 0
                action = "SELL"

        current_val = cash + (btc_holdings * price)

        # Formatting for NaN values
        sma7_str = f"{sma7:10.2f}" if not np.isnan(sma7) else f"{'NaN':>10}"
        sma30_str = f"{sma30:10.2f}" if not np.isnan(sma30) else f"{'NaN':>10}"

        print(f"{day:<3} | {date_str} | {price:10.2f} | {sma7_str} | {sma30_str} | {action:<6} | {current_val:15.2f}")

    final_val = cash + (btc_holdings * ledger_df.iloc[-1]['Price'])
    return_pct = ((final_val - initial_cash) / initial_cash) * 100

    print("-" * 85)
    print(f"Initial Portfolio: ${initial_cash:,.2f}")
    print(f"Final Portfolio Value: ${final_val:,.2f}")
    print(f"Total Return: {return_pct:.2f}%")

if __name__ == "__main__":
    main()
