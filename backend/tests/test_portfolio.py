from services import portfolio_service as ps
from db.database import init_db, SessionLocal
from db import models


def setup_function(_):
    init_db()
    with SessionLocal() as db:
        db.query(models.Trade).delete()
        db.query(models.PortfolioSnapshot).delete()
        db.commit()


def test_open_and_close_trade():
    with SessionLocal() as db:
        snap = ps.current_portfolio(db, price=50000)
        decision = type("D", (), {"confidence": 1.0, "reasoning": "test"})()
        trade = ps.open_position(db, price=50000, decision=decision, indicators={}, brain_id="")
        assert trade is not None
        closed = ps.close_position(db, price=51000, reason="tp")
        assert closed is not None
        assert closed.pnl_usdt != 0
