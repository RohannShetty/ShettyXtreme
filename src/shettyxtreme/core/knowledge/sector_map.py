"""Curated symbol→sector map (D12: pure data, no external imports).

Static sector classification for NSE symbols used by the risk heat map's
sectoral exposure dimension. Fyers instrument master has no sector field,
so this curated dict is the source of truth for v1.

Pattern mirrors core/knowledge/lexicons.py — pure data, no imports.
"""
from __future__ import annotations

# Symbol → sector mapping. Covers NIFTY/BANKNIFTY indices + common F&O names.
# Unknown symbols get "Unknown" via the aggregator (honesty rule — never fake).
SYMBOL_SECTOR: dict[str, str] = {
    # Indices
    "NIFTY": "Index",
    "BANKNIFTY": "Index",
    "FINNIFTY": "Index",
    "MIDCPNIFTY": "Index",
    "NIFTYNXT50": "Index",
    # Banking & Financial
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "KOTAKBANK": "Banking",
    "AXISBANK": "Banking",
    "INDUSINDBK": "Banking",
    "FEDERALBNK": "Banking",
    "BANDHANBNK": "Banking",
    "PNB": "Banking",
    "IDFCFIRSTB": "Banking",
    "AUBANK": "Banking",
    "BAJFINANCE": "Financial Services",
    "BAJAJFINSV": "Financial Services",
    "HDFCLIFE": "Financial Services",
    "SBILIFE": "Financial Services",
    "ICICIPRULI": "Financial Services",
    "BAJAJHLDNG": "Financial Services",
    "CHOLAFIN": "Financial Services",
    "MUTHOOTFIN": "Financial Services",
    "MANAPPURAM": "Financial Services",
    "HDFCAMC": "Financial Services",
    # IT
    "INFY": "IT",
    "TCS": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "LTIM": "IT",
    "MPHASIS": "IT",
    "PERSISTENT": "IT",
    "COFORGE": "IT",
    # Oil & Gas / Energy
    "RELIANCE": "Oil & Gas",
    "ONGC": "Oil & Gas",
    "IOC": "Oil & Gas",
    "BPCL": "Oil & Gas",
    "HINDPETRO": "Oil & Gas",
    "GAIL": "Oil & Gas",
    "PETRONET": "Oil & Gas",
    "ATGL": "Oil & Gas",
    "TATAPOWER": "Power",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "ADANIGREEN": "Power",
    "ADANIENSOL": "Power",
    # Auto
    "MARUTI": "Auto",
    "TATAMOTORS": "Auto",
    "M&M": "Auto",
    "BAJAJ-AUTO": "Auto",
    "HEROMOTOCO": "Auto",
    "EICHERMOT": "Auto",
    "TVSMOTOR": "Auto",
    "ASHOKLEY": "Auto",
    "SONACOMS": "Auto",
    # Metals & Mining
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "VEDL": "Metals",
    "NMDC": "Metals",
    "NATIONALUM": "Metals",
    "JINDALSTEL": "Metals",
    "HINDCOPPER": "Metals",
    # Pharma & Healthcare
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "AUROPHARMA": "Pharma",
    "LUPIN": "Pharma",
    "TORNTPHARM": "Pharma",
    "ALKEM": "Pharma",
    "IPCALAB": "Pharma",
    # FMCG / Consumer
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "DABUR": "FMCG",
    "MARICO": "FMCG",
    "GODREJCP": "FMCG",
    "EMAMILTD": "FMCG",
    "TATACONSUM": "FMCG",
    # Cement & Building
    "ULTRACEMCO": "Cement",
    "GRASIM": "Cement",
    "SHREECEM": "Cement",
    "ACC": "Cement",
    "AMBUJACEM": "Cement",
    # Infrastructure & Construction
    "LT": "Infrastructure",
    "ADANIPORTS": "Infrastructure",
    "ADANIENT": "Conglomerate",
    "IRCTC": "Infrastructure",
    # Telecom
    "BHARTIARTL": "Telecom",
    "IDEA": "Telecom",
    # Realty
    "DLF": "Realty",
    "GODREJPROP": "Realty",
    "OBEROIRLTY": "Realty",
    "PRESTIGE": "Realty",
    # Chemicals & Others
    "PIDILITIND": "Chemicals",
    "UPL": "Chemicals",
    "DEEPAKNTR": "Chemicals",
    "SRF": "Chemicals",
    "ATUL": "Chemicals",
    # Defence & Aerospace
    "HAL": "Defence",
    "BEL": "Defence",
    "BDL": "Defence",
    "COCHINSHIP": "Defence",
    # Media & Entertainment
    "ZEEL": "Media",
    "PVRINOX": "Media",
    # Retail / Consumer Discretionary
    "TRENT": "Retail",
    "DMART": "Retail",
    "PAGEIND": "Consumer",
    # Logistics
    "DELHIVERY": "Logistics",
}


def get_sector(symbol: str) -> str:
    """Return the sector for a symbol, or 'Unknown' if not mapped."""
    return SYMBOL_SECTOR.get(symbol.upper(), "Unknown")
