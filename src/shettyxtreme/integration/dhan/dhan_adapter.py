"""DhanHQ adapter - Dhan's full data and trading capabilities.

DUAL PATH architecture:
1. DATA PATH (DIRECT via DhanHQ-py):
   - Live WebSocket market feed (ticker/quote/depth/200-level)
   - Historical data (5 years intraday at 1/5/15/25/60 min)
   - Daily candles since inception with OI
   - Expired options historical data (rolling)
   - Options chain data
   - Positions, holdings, funds, tradebook

2. EXECUTION PATH (via OpenAlgo - primary / DhanHQ direct for Dhan-specific):
   - Standard orders through OpenAlgo's multi-broker abstraction
   - Dhan-specific orders (AMO, CO, BO) via DhanHQ direct

Reference: https://github.com/dhan-oss/DhanHQ-py v2.3.0-rc1
"""

import asyncio
from datetime import datetime, date
from typing import Any, Callable, Optional

# Exchange segment mapping
EXCHANGE_MAP = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "MCX": "MCX",
    "IDX": "IDX_I",
}


class DhanAdapter:
    """Adapter wrapping DhanHQ-py for full Dhan data and trading.

    Provides:
    - Historical data (5yr intraday, daily since inception, expired options)
    - Live WebSocket feed (ticker, quote, 200-level depth)
    - Options chain data
    - Account info (positions, holdings, funds)
    - Dhan-specific order types (AMO, etc.)
    """

    broker_name = "dhan"

    def __init__(self, client_id: str = "", access_token: str = "",
                 data_dir: str = "data"):
        self.client_id = client_id
        self.access_token = access_token
        self._dhanhq = None
        self._ws_connected = False

    def _init_dhanhq(self):
        """Lazy init DhanHQ client."""
        if self._dhanhq is None:
            from dhanhq import dhanhq
            self._dhanhq = dhanhq.DhanHQ(
                client_id=self.client_id,
                access_token=self.access_token,
            )
        return self._dhanhq

    # ------------------------------------------------------------------
    # HISTORICAL DATA (5 years intraday + daily since inception)
    # ------------------------------------------------------------------

    async def get_intraday_bars(self, symbol: str, exchange: str,
                                inst_type: str,
                                from_date: str, to_date: str,
                                interval: int = 1, oi: bool = False) -> dict:
        """Fetch intraday minute candles (up to 5 years).

        Args:
            interval: 1, 5, 15, 25, or 60 minutes
            inst_type: EQUITY | OPTIDX | OPTSTK | FUTIDX | FUTSTK
            oi: include open interest for derivatives
        """
        dhan = self._init_dhanhq()
        return dhan.historical_data.intraday_minute_data(
            security_id=symbol,
            exchange_segment=EXCHANGE_MAP.get(exchange, exchange),
            instrument_type=inst_type,
            from_date=from_date, to_date=to_date,
            interval=interval, oi=oi,
        )

    async def get_daily_bars(self, symbol: str, exchange: str,
                             inst_type: str,
                             from_date: str, to_date: str,
                             oi: bool = False) -> dict:
        """Fetch daily candles since inception."""
        dhan = self._init_dhanhq()
        return dhan.historical_data.historical_daily_data(
            security_id=symbol,
            exchange_segment=EXCHANGE_MAP.get(exchange, exchange),
            instrument_type=inst_type,
            from_date=from_date, to_date=to_date, oi=oi,
        )

    async def get_expired_options(self, underlying: str, exchange: str,
                                  expiry_flag: str, expiry_code: int,
                                  strike: str, option_type: str,
                                  fields: list, from_date: str, to_date: str,
                                  interval: int = 1) -> dict:
        """Fetch expired options historical data (rolling basis)."""
        dhan = self._init_dhanhq()
        return dhan.historical_data.expired_options_data(
            security_id=underlying,
            exchange_segment=EXCHANGE_MAP.get(exchange, exchange),
            instrument_type="OPTIDX",
            expiry_flag=expiry_flag, expiry_code=expiry_code,
            strike=strike, drv_option_type=option_type,
            required_data=fields,
            from_date=from_date, to_date=to_date,
            interval=interval,
        )

    # ------------------------------------------------------------------
    # MARKET DATA (REST - ticker, quote, depth)
    # ------------------------------------------------------------------

    async def get_ltp(self, securities: dict) -> dict:
        """Get latest traded prices.

        Args:
            securities: {"NSE_EQ": [11536], "NSE_FNO": [49081, 49082]}
        """
        dhan = self._init_dhanhq()
        return dhan.market_feed.ticker_data(securities)

    async def get_quotes(self, securities: dict) -> dict:
        """Get full quotes with market depth."""
        dhan = self._init_dhanhq()
        return dhan.market_feed.quote_data(securities)

    async def get_ohlc(self, securities: dict) -> dict:
        """Get OHLC + LTP for instruments."""
        dhan = self._init_dhanhq()
        return dhan.market_feed.ohlc_data(securities)

    # ------------------------------------------------------------------
    # LIVE WEBSOCKET FEED (real-time ticks with 200-level depth)
    # ------------------------------------------------------------------

    async def connect_websocket(self, instruments: dict,
                                on_tick: Optional[Callable] = None):
        """Connect to DhanHQ live market feed WebSocket.

        Supports: Ticker(15), Quote(17), Depth(19), Full(21) request codes.
        200-level full market depth available via Depth or Full modes.
        """
        from dhanhq.marketfeed import MarketFeed as DhanWSFeed

        self._ws_connected = True

        def _run():
            feed = DhanWSFeed(
                dhan_context=self._init_dhanhq(),
                instruments=instruments,
                on_ticks=on_tick,
            )
            feed.run_forever()

        await asyncio.get_event_loop().run_in_executor(None, _run)

    # ------------------------------------------------------------------
    # OPTIONS CHAIN
    # ------------------------------------------------------------------

    async def get_option_chain(self, symbol: str, exchange: str = "NFO",
                               expiry: Optional[str] = None) -> dict:
        """Fetch options chain data for a symbol/expiry."""
        dhan = self._init_dhanhq()
        return dhan.option_chain.get_option_chain(
            underlying_scrip=symbol,
            exchange_segment=EXCHANGE_MAP.get(exchange, exchange),
            expiry=expiry or "",
        )

    # ------------------------------------------------------------------
    # ACCOUNT / PORTFOLIO
    # ------------------------------------------------------------------

    async def get_positions(self) -> list:
        """Get current open positions from Dhan."""
        dhan = self._init_dhanhq()
        result = dhan.portfolio.get_positions()
        return result.get("data", []) if isinstance(result, dict) else []

    async def get_holdings(self) -> list:
        """Get delivery holdings from Dhan."""
        dhan = self._init_dhanhq()
        result = dhan.portfolio.get_holdings()
        return result.get("data", []) if isinstance(result, dict) else []

    async def get_funds(self) -> dict:
        """Get fund limits and margin details."""
        dhan = self._init_dhanhq()
        result = dhan.funds.get_fund_limits()
        return result.get("data", {}) if isinstance(result, dict) else {}

    async def get_tradebook(self) -> list:
        """Get today's tradebook."""
        dhan = self._init_dhanhq()
        result = dhan.portfolio.get_tradebook()
        return result.get("data", []) if isinstance(result, dict) else []

    # ------------------------------------------------------------------
    # DHAN-SPECIFIC ORDERS (AMO, etc.)
    # ------------------------------------------------------------------

    async def place_dhan_order(self, symbol: str, exchange: str,
                               side: str, order_type: str, quantity: int,
                               price: float = 0, trigger_price: float = 0,
                               product: str = "INTRADAY",
                               after_market: bool = False) -> dict:
        """Place order via DhanHQ for Dhan-specific order types.

        For standard orders, use OpenAlgoAdapter.place_order().
        This is for Dhan-specific features like AMO.
        """
        dhan = self._init_dhanhq()
        return dhan.order.place_order(
            security_id=symbol,
            exchange_segment=EXCHANGE_MAP.get(exchange, exchange),
            transaction_type=side.upper(),
            quantity=quantity,
            order_type=order_type.upper(),
            price=price if price > 0 else 0,
            trigger_price=trigger_price if trigger_price > 0 else 0,
            product_type=product,
            after_market_order=after_market,
        )

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        try:
            self._init_dhanhq()
            return True
        except Exception:
            return False

    async def disconnect(self):
        self._ws_connected = False

    async def is_connected(self) -> bool:
        return self._dhanhq is not None
