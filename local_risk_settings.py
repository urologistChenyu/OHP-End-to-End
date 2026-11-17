"""Optional probability post-processing; frozen inference outputs are never modified."""
from __future__ import annotations
import csv
import hashlib
import html
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SOFTWARE_VERSION = "1.1.0"
DEFAULT_THRESHOLD = 0.3530539465287861
DEVELOPMENT_PREVALENCE = 114 / 296
EPSILON = 1e-12


def number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number, not a boolean.")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric.") from None
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite.")
    return value


def probability(value: Any, label: str = "Probability", *, interior: bool = False) -> float:
    value = number(value, label)
    if not (0 < value < 1 if interior else 0 <= value <= 1):
        raise ValueError(f"{label} must be {'strictly between 0 and 1' if interior else 'between 0 and 1'}.")
    return value


def logit(p: float) -> float:
    p = min(max(probability(p), EPSILON), 1 - EPSILON)
    return math.log(p) - math.log1p(-p)


def sigmoid(x: float) -> float:
    x = number(x, "Log odds")
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    t = math.exp(x)
    return t / (1 + t)


@dataclass(frozen=True)
class LocalSettings:
    mode: str = "none"
    threshold: float = DEFAULT_THRESHOLD
    intercept: float = 0.0
    local_prevalence: float | None = None
    source_prevalence: float = DEVELOPMENT_PREVALENCE

    def __post_init__(self) -> None:
        if self.mode not in {"none", "intercept", "prevalence"}:
            raise ValueError("Unknown adjustment mode.")
        object.__setattr__(self, "threshold", probability(self.threshold, "Decision threshold", interior=True))
        object.__setattr__(self, "intercept", number(self.intercept, "Intercept"))
        object.__setattr__(self, "source_prevalence", probability(self.source_prevalence, "Source prevalence", interior=True))
        if self.mode == "prevalence":
            object.__setattr__(self, "local_prevalence", probability(self.local_prevalence, "Local prevalence", interior=True))

    @property
    def offset(self) -> float:
        if self.mode == "intercept":
            return float(self.intercept)
        if self.mode == "prevalence":
            return logit(float(self.local_prevalence)) - logit(self.source_prevalence)
        return 0.0

    def adjust(self, raw: float) -> float:
        p = probability(raw, "Raw probability")
        # Identity is exact, including the endpoints and the default threshold.
        if self.offset == 0:
            return p
        return sigmoid(logit(p) + self.offset)

    def describe(self) -> str:
        return {
            "none": "Original model probability",
            "intercept": "Local intercept adjustment",
            "prevalence": "Prevalence-based adjustment (assumption-dependent)",
        }[self.mode]


def fit_intercept(probabilities: Iterable[Any], outcomes: Iterable[Any]) -> dict[str, Any]:
    ps = [probability(x) for x in probabilities]
    ys = [number(y, "OHP outcome") for y in outcomes]
    if len(ps) != len(ys) or len(ps) < 2:
        raise ValueError("Provide at least two paired probabilities and outcomes.")
    if any(y not in (0, 1) for y in ys):
        raise ValueError("OHP outcomes must be 0 or 1.")
    events = int(sum(ys))
    if not 0 < events < len(ys):
        raise ValueError("The calibration data must contain both OHP-positive and OHP-negative cases.")
    lps = [logit(p) for p in ps]
    lo, hi = -80.0, 80.0
    for _ in range(160):
        a = (lo + hi) / 2
        if sum(sigmoid(x + a) for x in lps) > events:
            hi = a
        else:
            lo = a
    a = (lo + hi) / 2
    fitted = [sigmoid(x + a) for x in lps]
    return {
        "intercept": a, "n": len(ps), "events": events,
        "observed_prevalence": events / len(ps),
        "mean_adjusted_probability": sum(fitted) / len(ps),
        "clipped_endpoint_probabilities": sum(p in (0, 1) for p in ps),
        "method": "Logistic intercept-only maximum likelihood; logit(raw probability) is an offset and slope is fixed at one",
        "evaluation": "Fit summary only; not an independent performance evaluation",
    }


def calibration_csv(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        pc = next((x for x in ("fusion_prob", "raw_probability", "probability") if x in fields), None)
        yc = next((x for x in ("OHP", "ohp", "label", "outcome") if x in fields), None)
        if pc is None or yc is None:
            raise ValueError("CSV requires fusion_prob (or raw_probability) and OHP columns with outcomes 0/1.")
        rows = list(reader)
    id_column = next((x for x in ("patient_id", "ID", "case_id") if x in fields), None)
    if id_column:
        ids = [r[id_column].strip() for r in rows]
        if any(not x for x in ids) or len(set(ids)) != len(ids):
            raise ValueError("Calibration case identifiers must be non-empty and unique.")
    result = fit_intercept((r[pc] for r in rows), (r[yc] for r in rows))
    result.update(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), probability_column=pc, outcome_column=yc)
    return result


def local_rows(rows: Iterable[dict[str, Any]], settings: LocalSettings) -> list[dict[str, Any]]:
    result, seen = [], set()
    for row in rows:
        cid = str(row.get("patient_id", row.get("ID", ""))).strip()
        if not cid or cid in seen:
            raise ValueError("Prediction case identifiers must be non-empty and unique.")
        seen.add(cid)
        raw = probability(row.get("fusion_prob", row.get("raw_probability")), f"Probability for {cid}")
        raw_class = int(raw >= DEFAULT_THRESHOLD)
        if "pred_primary" in row and number(row["pred_primary"], "Original classification") != raw_class:
            raise ValueError(f"Original probability and default classification disagree for case {cid}.")
        p = settings.adjust(raw)
        result.append({
            "patient_id": cid,
            "raw_probability": raw,
            "raw_pred_default": raw_class,
            "configured_probability": p,
            "configured_threshold": settings.threshold,
            "configured_pred": int(p >= settings.threshold),
            "adjustment_mode": settings.mode,
            "log_odds_offset": settings.offset,
        })
    if not result:
        raise ValueError("Load a completed batch before exporting local settings.")
    return result


def export_local_settings(output: str | Path, settings: LocalSettings, *, fit: dict[str, Any] | None = None) -> dict[str, Any]:
    output = Path(output)
    predictions = output / "patient_predictions.csv"
    raw_bytes = predictions.read_bytes()
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    with predictions.open(newline="", encoding="utf-8-sig") as stream:
        result = local_rows(list(csv.DictReader(stream)), settings)
    mode_note = "Prevalence-only adjustment assumes stable class-conditional predictor distributions and appropriate source probabilities; local validation is required." if settings.mode == "prevalence" else "An intercept update addresses mean risk; it does not estimate a calibration slope or demonstrate clinical benefit."
    manifest = {
        "software_version": SOFTWARE_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_predictions_file": predictions.name,
        "source_predictions_sha256": source_hash,
        "default_threshold": DEFAULT_THRESHOLD,
        "settings": asdict(settings), "effective_log_odds_offset": settings.offset,
        "cases": len(result), "calibration_fit": fit,
        "note": mode_note,
        "scope": "Optional post-processing; original predictions, branch contributions, model weights and original run manifest are unchanged. Clinical performance of these optional settings was not evaluated in the original cohorts.",
    }
    folder = output / "local_settings"
    folder.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    csv_path = folder / f"local_predictions_{stamp}.csv"
    with csv_path.open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    manifest["export_predictions_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    json_path = csv_path.with_suffix(".json")
    json_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    headers = "".join(f"<th>{html.escape(c)}</th>" for c in result[0])
    cells = "".join("<tr>" + "".join(f"<td>{html.escape(format(v, '.6f') if isinstance(v, float) else str(v))}</td>" for v in r.values()) + "</tr>" for r in result)
    report_path = csv_path.with_suffix(".html")
    report_path.write_text("<!doctype html><html lang='en'><meta charset='utf-8'><title>OHP local settings</title><style>body{font:14px Segoe UI,Arial;margin:30px;color:#243b53}h1{color:#1f4e8c}table{border-collapse:collapse}td,th{border:1px solid #ccd6e3;padding:8px;text-align:right}th{background:#e8eef8}.note{max-width:1000px;line-height:1.5}</style><h1>OHP local settings</h1><p>" + html.escape(settings.describe()) + "</p><p class='note'>" + html.escape(manifest["scope"]) + "</p><p class='note'>" + html.escape(mode_note) + "</p><table><thead><tr>" + headers + "</tr></thead><tbody>" + cells + "</tbody></table></html>", encoding="utf-8")
    if hashlib.sha256(predictions.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("Source predictions changed while the optional export was being written.")
    return {"csv": str(csv_path), "json": str(json_path), "html": str(report_path), "cases": len(result), "source_unchanged": True}
