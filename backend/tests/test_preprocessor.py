from backend.core.preprocessor import preprocess, build_log_frame, tag_severity, find_crash_anchor


def test_build_log_frame():
    raw = "line1\nline2\nline3"
    df = build_log_frame(raw)
    assert df.height == 3
    assert df["line_no"].to_list() == [0, 1, 2]
    assert df["raw"].to_list() == ["line1", "line2", "line3"]


def test_tag_severity():
    raw = "2026-09-08 INFO ok\n2026-09-08 ERROR OutOfMemory\n2026-09-08 FATAL KernelPanic"
    df = build_log_frame(raw)
    tagged = tag_severity(df)
    assert tagged["severity"].to_list() == ["NOISE", "ERROR", "FATAL"]


def test_find_crash_anchor_prefers_fatal():
    raw = "INFO start\nERROR minor error\nFATAL critical crash\nERROR after crash"
    df = build_log_frame(raw)
    tagged = tag_severity(df)
    anchor = find_crash_anchor(tagged)
    assert anchor == 2


def test_preprocess_prunes_context_with_window():
    lines = [f"2026-09-08 INFO line {i}" for i in range(30)]
    lines[15] = "2026-09-08 FATAL NullPointerException at line 15"
    raw_log = "\n".join(lines)

    res = preprocess(raw_log, window=5)
    assert res["severity"] == "FATAL"
    assert res["context"] is not None
    ctx_lines = res["context"].splitlines()
    assert len(ctx_lines) == 11  # 5 before + anchor + 5 after
    assert "FATAL NullPointerException" in res["context"]


def test_preprocess_no_errors():
    raw_log = "INFO start\nINFO running\nINFO done"
    res = preprocess(raw_log, window=10)
    assert res["context"] is None
    assert res["severity"] is None
