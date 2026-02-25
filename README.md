# ibkr2tv

Convert Interactive Brokers (IBKR) trade history to TradingView Portfolio import format.

## Background

TradingView Portfolio supports importing trades via CSV, but IBKR's export formats don't match directly. This script parses IBKR's **Activity Statement** CSV export and converts it into the format TradingView expects.

IBKR limits Flex Query exports to 365 days, so you may need multiple files to cover your full history. This script accepts multiple input files and deduplicates overlapping records automatically.

## Supported Record Types

| IBKR Source | TradingView Side |
|-------------|-----------------|
| Stock trades (buy) | `Buy` |
| Stock trades (sell) | `Sell` |
| Deposits & Withdrawals (positive) | `$CASH Deposit` |
| Deposits & Withdrawals (negative) | `$CASH Withdrawal` |
| Dividends | `$CASH Dividend` |
| Withholding tax | `$CASH Taxes and fees` |

## Supported Exchanges

| IBKR Exchange | TradingView Prefix |
|---------------|--------------------|
| NASDAQ | `NASDAQ:` |
| NYSE | `NYSE:` |
| AMEX / ARCA | `AMEX:` |
| SEHK (Hong Kong) | `HKEX:` |

## Requirements

- Python 3.6+
- No third-party dependencies

## How to Export from IBKR

### Activity Statement (required)

1. Log in to IBKR Client Portal
2. Go to **Performance & Reports → Statements**
3. Select **Activity** statement type
4. Choose your date range (up to 365 days per export)
5. Select **CSV** format and download
6. Repeat for additional date ranges if needed

> **Note:** IBKR exports Activity Statements in your account's display language. The script currently supports **Chinese (Simplified)** language exports. If your IBKR interface is in English, the section names will differ and the script will need to be updated accordingly.

### Flex Query (optional, recommended)

Flex Query exports provide exchange information (`ListingExchange`) used to correctly prefix US stock symbols. Without it, all USD-denominated stocks default to `NASDAQ:`.

1. Go to **Performance & Reports → Flex Queries**
2. Create a new **Trade Confirmation** flex query
3. Include at minimum: `Symbol`, `ListingExchange`, `AssetClass`
4. Export as CSV for the same date ranges as your Activity Statements

## Usage

```bash
python3 convert.py <activity_statement.csv> [more_statements.csv ...] \
    [--flex <flex_query.csv> [more_flex.csv ...]] \
    [-o output.csv]
```

### Examples

Single file:
```bash
python3 convert.py data/activity_2025.csv -o output.csv
```

Multiple files with exchange mapping:
```bash
python3 convert.py \
    data/activity_2024-11_2025-11.csv \
    data/activity_2025-11_2026-02.csv \
    --flex data/flex_2024-11_2025-11.csv data/flex_2025-11_2026-02.csv \
    -o output.csv
```

### Arguments

| Argument | Description |
|----------|-------------|
| `inputs` | One or more IBKR Activity Statement CSV files |
| `--flex` | One or more IBKR Flex Query CSV files (for exchange mapping) |
| `-o` | Output file path (default: `output.csv`) |

## Importing to TradingView

1. Open [TradingView Portfolio](https://www.tradingview.com/portfolio/)
2. Click **Import trades**
3. Upload the generated `output.csv`

## Known Limitations

- **Language**: Activity Statement exports must be in **Chinese (Simplified)**. Other languages are not currently supported.
- **HKD deposits via FX conversion**: If you funded your account in HKD and converted to USD via IBKR's FX exchange, this appears as a `USD.HKD` trade in Flex Query but is not recorded in Activity Statement's deposit section. You will need to add this deposit manually in TradingView.
- **Currencies**: All commissions are included as-is regardless of currency (e.g., HKD commissions for HK stocks). TradingView does not distinguish commission currencies.

## License

MIT
