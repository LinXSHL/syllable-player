from pathlib import Path

from core.mfa import _read_phone_tier, _validate_and_label_intervals


TEXTGRID = '''File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0
xmax = 0.3
tiers? <exists>
size = 1
item []:
    item [1]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 0.3
        intervals: size = 3
        intervals [1]:
            xmin = 0
            xmax = 0.05
            text = "sil"
        intervals [2]:
            xmin = 0.05
            xmax = 0.18
            text = "eh"
        intervals [3]:
            xmin = 0.18
            xmax = 0.3
            text = "v"
'''


def test_textgrid_phone_tier_and_candidate_validation(tmp_path: Path) -> None:
    path = tmp_path / "word.TextGrid"
    path.write_text(TEXTGRID, encoding="utf-8")
    raw = _read_phone_tier(path)
    intervals, selected = _validate_and_label_intervals(raw, [("EH1", "V")])
    assert selected == ("EH1", "V")
    assert [(x.arpa, x.start_ms, x.end_ms) for x in intervals] == [
        ("EH1", 50.0, 180.0), ("V", 180.0, 300.0)
    ]
