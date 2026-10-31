from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

# Canonical fields expected from each source. The user maps their CSV columns
# to these names before normalization.
REQUIRED = {
    "shopify": ["order_id", "order_date", "total"],
    "google_ads": ["date", "campaign", "conversions", "conversion_value"],
    "meta_ads": ["date", "campaign", "conversions", "conversion_value"],
}

ALIASES = {
    "order_id": ["order id", "name", "order name", "order number", "id"],
    "order_date": ["created at", "created", "order date", "date", "processed at"],
    "total": ["total", "total price", "amount", "purchase value", "order value"],
    "financial_status": ["financial status", "payment status", "status"],
    "source": ["utm source", "source"],
    "medium": ["utm medium", "medium"],
    "campaign": ["utm campaign", "campaign name", "campaign"],
    "date": ["date", "day", "reporting date", "start date"],
    "conversions": ["conversions", "all conversions", "purchases", "results"],
    "conversion_value": ["conversion value", "conv. value", "purchase conversion value", "value"],
    "spend": ["spend", "cost", "amount spent"],
    "clicks": ["clicks", "link clicks"],
    "impressions": ["impressions"],
}

def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

def read_csv(path: str | Path) -> pd.DataFrame:
    """Read a CSV with encoding fallbacks and useful validation errors."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError("CSV file is empty or does not exist.")
    try:
        frame = pd.read_csv(path)
    except UnicodeDecodeError:
        frame = pd.read_csv(path, encoding="latin-1")
    except pd.errors.EmptyDataError as exc:
        raise ValueError("CSV file has no header or data.") from exc
    if frame.empty and len(frame.columns) == 0:
        raise ValueError("CSV file has no columns.")
    if len(frame.columns) == 0:
        raise ValueError("CSV file has no header row.")
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame

def suggest_mapping(columns: list[str], source: str) -> dict[str, str]:
    """Suggest canonical-field -> uploaded-column mappings."""
    if source not in REQUIRED:
        raise ValueError(f"Unsupported source: {source}")
    normalized = {_key(column): column for column in columns}
    mapping: dict[str, str] = {}
    fields = list(dict.fromkeys(REQUIRED[source] + (
        ["financial_status", "source", "medium", "campaign"]
        if source == "shopify" else ["spend", "clicks", "impressions"]
    )))
    for field in fields:
        candidates = ALIASES.get(field, [field.replace("_", " ")])
        for candidate in candidates:
            found = normalized.get(_key(candidate))
            if found is not None:
                mapping[field] = found
                break
    return mapping

def _parse_dates(values: pd.Series) -> pd.Series:
    # Try normal parsing first, then day-first parsing for values such as 31/10/2026.
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    missing = parsed.isna() & values.notna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(values.loc[missing], errors="coerce", dayfirst=True)
    return parsed

def normalize(
    frame: pd.DataFrame,
    source: str,
    mapping: dict[str, str],
    filename: str = "",
) -> tuple[pd.DataFrame, list[dict]]:
    """Convert a mapped source CSV into canonical columns without discarding originals."""
    if source not in REQUIRED:
        raise ValueError(f"Unsupported source: {source}")
    missing = [field for field in REQUIRED[source] if field not in mapping]
    if missing:
        raise ValueError(f"Missing required mappings for {source}: {missing}")
    invalid = {field: column for field, column in mapping.items() if column not in frame.columns}
    if invalid:
        raise ValueError(f"Mapped columns do not exist in CSV: {invalid}")

    result = pd.DataFrame(index=frame.index)
    for field, column in mapping.items():
        result[field] = frame[column]
    result["source_file"] = filename
    if source == "shopify":
        result["order_id"] = result["order_id"].astype("string").str.strip()
        result["order_date_original"] = result["order_date"]
        result["date"] = _parse_dates(result["order_date"])
        result["order_date"] = result["date"]
        result["total_original"] = result["total"]
        result["total"] = pd.to_numeric(
            result["total"].astype("string").str.replace(r"[^0-9.\-]", "", regex=True),
            errors="coerce",
        )
    else:
        result["date_original"] = result["date"]
        result["date"] = _parse_dates(result["date"])
        for field in ("conversions", "conversion_value", "spend", "clicks", "impressions"):
            if field in result:
                result[field + "_original"] = result[field]
                result[field] = pd.to_numeric(
                    result[field].astype("string").str.replace(r"[^0-9.\-]", "", regex=True),
                    errors="coerce",
                )
        if "campaign" in result:
            result["campaign"] = result["campaign"].astype("string").str.strip()
    result["source_type"] = source
    return result.reset_index(drop=True), []

def _finding(rule_id: str, title: str, description: str, severity: str,
             source: str, affected: int, evidence: dict, why: str, action: str,
             campaign: str | None = None) -> dict:
    return {
        "rule_id": rule_id, "title": title, "description": description,
        "severity": severity, "source": source, "campaign": campaign,
        "affected_records": int(affected), "evidence": evidence,
        "why_it_matters": why, "recommended_action": action,
    }

def detect(frames: dict[str, pd.DataFrame]) -> list[dict]:
    """Run deterministic data-quality and trend checks over normalized inputs."""
    findings: list[dict] = []
    shop = frames.get("shopify")
    if shop is not None:
        if "order_id" in shop:
            ids = shop["order_id"].dropna().astype(str)
            counts = ids.value_counts()
            duplicates = counts[counts > 1]
            if not duplicates.empty:
                findings.append(_finding(
                    "DUPLICATE_ORDER_ID", "Repeated Shopify order IDs",
                    "The same order ID appears more than once in the uploaded Shopify data.",
                    "High", "shopify", int(duplicates.sum()),
                    {"duplicate_ids": duplicates.to_dict()},
                    "Repeated rows can inflate order counts and revenue totals.",
                    "Inspect the repeated order IDs and confirm whether they are duplicate exports or legitimate line-level records.",
                ))
        utm_fields = [field for field in ("source", "medium", "campaign") if field in shop]
        if utm_fields:
            missing_mask = shop[utm_fields].isna().any(axis=1)
            for field in utm_fields:
                missing_mask |= shop[field].astype("string").str.strip().eq("").fillna(False)
            count = int(missing_mask.sum())
            if count:
                findings.append(_finding(
                    "MISSING_UTM", "Missing UTM values",
                    "Some Shopify orders have one or more blank UTM fields. This does not establish a tracking failure; orders may be direct, organic, referral, or unattributed.",
                    "Medium", "shopify", count,
                    {"missing_by_field": {
                        field: int(shop[field].isna().sum() + shop[field].astype("string").str.strip().eq("").fillna(False).sum())
                        for field in utm_fields
                    }},
                    "Incomplete campaign metadata limits campaign-level attribution.",
                    "Review landing-page tagging and attribution rules; do not automatically classify these orders as paid-media failures.",
                ))
        if "total" in shop:
            invalid = shop["total"].isna()
            count = int(invalid.sum())
            if count:
                findings.append(_finding(
                    "INVALID_PURCHASE_VALUE", "Invalid purchase values",
                    "Some order totals could not be parsed as numeric values.",
                    "High", "shopify", count,
                    {"rows": shop.index[invalid].tolist()[:100],
                     "original_values": shop.loc[invalid, "total_original"].astype(str).tolist()[:100]},
                    "Invalid values can distort revenue and average-order-value calculations.",
                    "Review the original CSV values, currency symbols, and export formatting.",
                ))
        if "date" in shop:
            invalid = shop["date"].isna()
            count = int(invalid.sum())
            if count:
                findings.append(_finding(
                    "INVALID_DATE", "Invalid order dates",
                    "Some Shopify order dates could not be parsed.",
                    "Medium", "shopify", count,
                    {"rows": shop.index[invalid].tolist()[:100],
                     "original_values": shop.loc[invalid, "order_date_original"].astype(str).tolist()[:100]},
                    "Rows with invalid dates cannot be reliably assigned to a reporting period.",
                    "Correct the source date values or confirm the export's date format.",
                ))
        if "financial_status" in shop:
            status = shop["financial_status"].astype("string").str.lower().str.strip()
            flagged = status.str.contains(r"cancel|refund|test|void", na=False)
            count = int(flagged.sum())
            if count:
                findings.append(_finding(
                    "ORDER_STATUS_REVIEW", "Cancelled, refunded, or test orders",
                    "Orders with statuses suggesting cancellation, refund, void, or test activity need review.",
                    "Low", "shopify", count,
                    {"status_counts": status[flagged].value_counts().to_dict()},
                    "These records may need to be excluded from a paid conversion comparison depending on the reporting definition.",
                    "Confirm the business's order inclusion policy before excluding or adjusting these records.",
                ))

    # Detect an unusual drop only when there are at least seven baseline days.
    for source in ("google_ads", "meta_ads"):
        frame = frames.get(source)
        if frame is None or not {"date", "conversions"}.issubset(frame.columns):
            continue
        daily = frame.dropna(subset=["date"]).groupby(frame["date"].dt.date)["conversions"].sum().sort_index()
        if len(daily) < 8:
            continue
        baseline = daily.iloc[:-1]
        latest = float(daily.iloc[-1])
        mean = float(baseline.mean())
        if mean >= 5 and latest <= mean * 0.5:
            findings.append(_finding(
                "CONVERSION_DROP", "Unusual daily conversion drop",
                f"Latest reported conversions ({latest:g}) are at least 50% below the preceding {len(baseline)}-day average ({mean:.1f}). This is a signal for investigation, not proof of a tracking outage.",
                "High", source, 1,
                {"daily_conversions": {str(k): float(v) for k, v in daily.items()},
                 "baseline_days": len(baseline), "baseline_average": mean, "latest": latest},
                "A sharp drop may indicate a performance change, reporting delay, budget change, or measurement issue.",
                "Check platform delivery, spend, landing pages, conversion actions, and reporting lag before concluding that tracking is broken.",
            ))
    return findings

def reconcile(frames: dict[str, pd.DataFrame]) -> list[dict]:
    """Compare aggregate totals only; this does not perform order-level attribution."""
    shop = frames.get("shopify")
    if shop is None:
        return []
    shop_orders = int(shop["order_id"].nunique()) if "order_id" in shop else int(len(shop))
    shop_revenue = float(shop["total"].fillna(0).sum()) if "total" in shop else 0.0
    results = []
    for source in ("google_ads", "meta_ads"):
        frame = frames.get(source)
        if frame is None:
            continue
        conversions = float(frame["conversions"].fillna(0).sum()) if "conversions" in frame else 0.0
        value = float(frame["conversion_value"].fillna(0).sum()) if "conversion_value" in frame else 0.0
        results.append({
            "platform": source,
            "shopify_orders": shop_orders,
            "platform_conversions": conversions,
            "order_difference": round(shop_orders - conversions, 2),
            "shopify_revenue": round(shop_revenue, 2),
            "platform_conversion_value": round(value, 2),
            "value_difference": round(shop_revenue - value, 2),
            "matching_method": "Aggregate comparison only",
            "status": "Aggregate discrepancy; not independently verified at order level",
            "limitations": "Totals may differ because of attribution windows, time zones, consent, currency, cancellations, refunds, modeled conversions, and platform counting rules. This is not order-level matching.",
        })
    return results
