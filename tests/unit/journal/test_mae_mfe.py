from molido_shared.journal import TradeJournal


def test_mae_mfe_r_fields(tmp_path):
    j = TradeJournal(path=str(tmp_path / "j.jsonl"))
    j.append("fill", ticket="1", side="BUY", entry=1.1000, fill_price=1.1000, mae_r=0.0, mfe_r=0.0)
    j.update_mae_mfe("1", price=1.0990, entry=1.1000, side="BUY", stop_distance=0.0010)
    j.update_mae_mfe("1", price=1.1020, entry=1.1000, side="BUY", stop_distance=0.0010)
    rec = j.append("close", ticket="1", r_multiple=1.5)
    assert rec["mae_r"] == -1.0
    assert rec["mfe_r"] == 2.0
    text = (tmp_path / "j.jsonl").read_text()
    assert "mae_r" in text and "mfe_r" in text
