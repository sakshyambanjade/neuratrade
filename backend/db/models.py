import json
from sqlalchemy import Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"
    id = Column(String, primary_key=True)
    opened_at = Column(Integer, nullable=False)
    closed_at = Column(Integer, nullable=True)
    symbol = Column(String, default="BTCUSDT")
    action = Column(String, nullable=False)  # BUY or SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    size_btc = Column(Float, nullable=False)
    size_usdt = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    pnl_usdt = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    close_reason = Column(String, nullable=True)
    status = Column(String, default="open")  # open | closed | opening
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    indicator_snapshot = Column(Text, nullable=True)  # JSON string
    memories_used = Column(Text, nullable=True)  # JSON array
    brain_memory_id = Column(String, nullable=True)

    def indicator_snapshot_dict(self):
        return json.loads(self.indicator_snapshot or "{}")

    def memories_used_list(self):
        return json.loads(self.memories_used or "[]")


class Candle(Base):
    __tablename__ = "candles"
    ts = Column(Integer, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    source = Column(String, default="binance")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    ts = Column(Integer, primary_key=True)
    cash = Column(Float)
    btc_held = Column(Float)
    total_value = Column(Float)
    daily_pnl = Column(Float)
