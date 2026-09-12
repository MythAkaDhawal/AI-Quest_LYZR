import time
import polars as pl

SEVERITY_HIGH = {"FATAL", "ERROR", "EXCEPTION", "TRACEBACK", "PANIC"}
FATAL_TOKENS = r"(?i)\b(FATAL|PANIC)\b"
ERROR_TOKENS = r"(?i)\b(ERROR|EXCEPTION|TRACEBACK)\b"


def build_log_frame(raw: str) -> pl.DataFrame:
    lines = raw.splitlines()
    if not lines:
        return pl.DataFrame({"line_no": pl.Series([], dtype=pl.Int64), "raw": pl.Series([], dtype=pl.String)})
    return pl.DataFrame({"line_no": range(len(lines)), "raw": lines})


def tag_severity(df: pl.DataFrame) -> pl.DataFrame:
    if df.height == 0:
        return df.with_columns(pl.Series("severity", [], dtype=pl.String))
    return df.with_columns(
        pl.when(pl.col("raw").str.contains(FATAL_TOKENS))
        .then(pl.lit("FATAL"))
        .when(pl.col("raw").str.contains(ERROR_TOKENS))
        .then(pl.lit("ERROR"))
        .otherwise(pl.lit("NOISE"))
        .alias("severity")
    )


def find_crash_anchor(tagged: pl.DataFrame) -> int | None:
    if tagged.height == 0:
        return None
    fatal_rows = tagged.filter(pl.col("severity") == "FATAL")
    if fatal_rows.height > 0:
        return fatal_rows["line_no"][0]
    error_rows = tagged.filter(pl.col("severity") == "ERROR")
    if error_rows.height > 0:
        return error_rows["line_no"][0]
    return None


def prune_context(full_df: pl.DataFrame, anchor: int, window: int) -> pl.DataFrame:
    lo, hi = max(0, anchor - window), anchor + window
    return full_df.filter((pl.col("line_no") >= lo) & (pl.col("line_no") <= hi))


def preprocess(raw_log: str, window: int = 10) -> dict:
    t0 = time.perf_counter()
    full_df = build_log_frame(raw_log)
    tagged = tag_severity(full_df)
    anchor = find_crash_anchor(tagged)

    if anchor is None:
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "context": None,
            "severity": None,
            "preprocessing_ms": elapsed,
            "estimated_prompt_tokens": 0,
        }

    severity = tagged.filter(pl.col("line_no") == anchor)["severity"][0]
    context_df = prune_context(full_df, anchor, window)
    context_str = "\n".join(context_df["raw"].to_list())
    elapsed = (time.perf_counter() - t0) * 1000

    return {
        "context": context_str,
        "severity": severity,
        "preprocessing_ms": elapsed,
        "estimated_prompt_tokens": len(context_str) // 4,
    }
