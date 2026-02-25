#!/usr/bin/env python3
"""
将 IBKR Activity Statement 导出的 CSV 转换为 TradingView Portfolio 导入格式。

支持：
- 股票交易（买入/卖出）
- 存款（Deposit）
- 取款（Withdrawal）
- 股息（Dividend）
- 代扣税（Taxes and fees）

用法：
  python3 convert.py <activity_statement1.csv> [activity_statement2.csv ...] \\
      --flex <flex1.csv> [flex2.csv ...] \\
      -o output.csv

  --flex 文件用于补充 Symbol → 交易所 映射（可选，但推荐提供）
"""

import csv
import sys
import argparse
import io

# IBKR 交易所代码 → TradingView 前缀
EXCHANGE_MAP = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "AMEX": "AMEX",
    "SEHK": "HKEX",
    "ARCA": "AMEX",
}

TV_FIELDNAMES = ["Symbol", "Side", "Qty", "Fill Price", "Commission", "Closing Time"]


def build_symbol_exchange_map(flex_files):
    """从 Flex Query 文件构建 Symbol → TradingView 前缀 的映射表。"""
    mapping = {}
    for filepath in flex_files:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("Symbol", "").strip()
                ex = row.get("ListingExchange", "").strip()
                if sym and ex and sym not in mapping:
                    tv_ex = EXCHANGE_MAP.get(ex, ex)
                    mapping[sym] = tv_ex
    return mapping


def get_tv_symbol(symbol, currency, symbol_exchange_map):
    """根据 symbol、货币和映射表，返回 TradingView 格式的 Symbol。
    HKD 计价视为港股（HKEX），USD 计价从映射表查找，找不到默认 NASDAQ。
    """
    if currency == "HKD":
        return f"HKEX:{symbol}"
    exchange = symbol_exchange_map.get(symbol, "NASDAQ")
    return f"{exchange}:{symbol}"


def parse_activity_statement(filepath):
    """解析 IBKR Activity Statement CSV，按 section 分组返回数据。

    返回 dict：{section_name: [{"field1": val, ...}, ...]}

    注意：IBKR 某些 section（如 "交易"）的 header 中存在重复字段名（如 "代码" 出现两次）。
    为避免 dict 覆盖，重复的字段名会加上 "_2"、"_3" 后缀。
    """
    sections = {}
    current_section = None
    current_headers = None

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            section = row[0].strip()
            row_type = row[1].strip()

            if row_type == "Header":
                current_section = section
                raw_headers = row[2:]
                # 处理重复字段名：第二次出现的加 "_2" 后缀
                seen_headers = {}
                deduped = []
                for h in raw_headers:
                    if h in seen_headers:
                        seen_headers[h] += 1
                        deduped.append(f"{h}_{seen_headers[h]}")
                    else:
                        seen_headers[h] = 1
                        deduped.append(h)
                current_headers = deduped
                if section not in sections:
                    sections[section] = []
            elif row_type == "Data" and current_section == section and current_headers:
                data = row[2:]
                # 补齐或截断到 header 长度
                while len(data) < len(current_headers):
                    data.append("")
                record = dict(zip(current_headers, data))
                sections[section].append(record)

    return sections


def convert_trades(records, symbol_exchange_map):
    """将交易记录转换为 TradingView 格式。"""
    rows = []
    for r in records:
        if r.get("DataDiscriminator") != "Order":
            continue
        if r.get("资产分类") != "股票":
            continue

        symbol = r["代码"].strip()
        currency = r["货币"].strip()
        tv_symbol = get_tv_symbol(symbol, currency, symbol_exchange_map)

        qty_raw = float(r["数量"])
        side = "Buy" if qty_raw > 0 else "Sell"
        qty = abs(qty_raw)
        price = r["交易价格"].strip()
        commission = abs(float(r["佣金/税"])) if r["佣金/税"].strip() else ""

        # 日期格式："2025-08-14, 11:32:43" → "2025-08-14 11:32:43"
        dt = r["日期/时间"].strip().replace(", ", " ")

        rows.append({
            "Symbol": tv_symbol,
            "Side": side,
            "Qty": qty,
            "Fill Price": price,
            "Commission": commission,
            "Closing Time": dt,
        })
    return rows


def convert_cash_transactions(records, side_label):
    """将存款/取款记录转换为 TradingView $CASH 格式。
    side_label: 'Deposit' 或 'Withdrawal'
    正数金额 → Deposit，负数金额 → Withdrawal
    """
    rows = []
    for r in records:
        # 跳过汇总行
        desc = r.get("描述", "").strip()
        if not desc:
            continue
        amount_str = r.get("金额", "").strip()
        if not amount_str:
            continue
        amount = float(amount_str)

        if amount > 0:
            side = "Deposit"
        else:
            side = "Withdrawal"
            amount = abs(amount)

        dt = r.get("结算日期", "").strip()
        if dt:
            dt += " 0:00:00"

        rows.append({
            "Symbol": "$CASH",
            "Side": side,
            "Qty": amount,
            "Fill Price": "",
            "Commission": "",
            "Closing Time": dt,
        })
    return rows


def convert_dividends(records):
    """将股息记录转换为 TradingView $CASH Dividend 格式。"""
    rows = []
    for r in records:
        desc = r.get("描述", "").strip()
        if not desc:
            continue
        amount_str = r.get("金额", "").strip()
        if not amount_str:
            continue
        amount = float(amount_str)
        if amount <= 0:
            continue

        dt = r.get("日期", "").strip()
        if dt:
            dt += " 0:00:00"

        rows.append({
            "Symbol": "$CASH",
            "Side": "Dividend",
            "Qty": amount,
            "Fill Price": "",
            "Commission": "",
            "Closing Time": dt,
        })
    return rows


def convert_taxes(records):
    """将代扣税记录转换为 TradingView $CASH Taxes and fees 格式。"""
    rows = []
    for r in records:
        desc = r.get("描述", "").strip()
        if not desc:
            continue
        amount_str = r.get("金额", "").strip()
        if not amount_str:
            continue
        amount = float(amount_str)
        if amount >= 0:
            continue  # 代扣税应为负数

        dt = r.get("日期", "").strip()
        if dt:
            dt += " 0:00:00"

        rows.append({
            "Symbol": "$CASH",
            "Side": "Taxes and fees",
            "Qty": abs(amount),
            "Fill Price": "",
            "Commission": "",
            "Closing Time": dt,
        })
    return rows


def process_activity_statement(filepath, symbol_exchange_map):
    """处理单个 Activity Statement 文件，返回所有转换后的行。"""
    sections = parse_activity_statement(filepath)
    rows = []

    rows += convert_trades(sections.get("交易", []), symbol_exchange_map)
    rows += convert_cash_transactions(sections.get("存款和取款", []), "")
    rows += convert_dividends(sections.get("股息", []))
    rows += convert_taxes(sections.get("代扣税", []))

    return rows


def main():
    parser = argparse.ArgumentParser(description="IBKR Activity Statement → TradingView Portfolio CSV 转换器")
    parser.add_argument("inputs", nargs="+", help="IBKR Activity Statement CSV 文件路径")
    parser.add_argument("--flex", nargs="*", default=[], metavar="FLEX_CSV",
                        help="IBKR Flex Query CSV 文件（用于补充交易所映射）")
    parser.add_argument("-o", "--output", default="output.csv", help="输出文件路径（默认：output.csv）")
    args = parser.parse_args()

    symbol_exchange_map = build_symbol_exchange_map(args.flex)
    print(f"交易所映射：{len(symbol_exchange_map)} 个 Symbol")

    all_rows = []
    for filepath in args.inputs:
        rows = process_activity_statement(filepath, symbol_exchange_map)
        trades = sum(1 for r in rows if r["Side"] in ("Buy", "Sell"))
        cash = sum(1 for r in rows if r["Side"] not in ("Buy", "Sell"))
        print(f"  {filepath}: {trades} 笔交易 + {cash} 笔现金记录")
        all_rows.extend(rows)

    # 去重（两个 Activity Statement 时间段可能有重叠）
    seen = set()
    deduped = []
    for r in all_rows:
        key = (r["Symbol"], r["Side"], r["Qty"], r["Fill Price"], r["Closing Time"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # 按时间排序
    deduped.sort(key=lambda r: r["Closing Time"] or "")

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(deduped)

    print(f"\n完成！共 {len(deduped)} 条记录 → {args.output}")


if __name__ == "__main__":
    main()
