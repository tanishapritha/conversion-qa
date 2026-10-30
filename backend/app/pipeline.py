from __future__ import annotations
from pathlib import Path
import re
import pandas as pd

REQUIRED = {
 "google_ads": {"date":["date","day","reporting date"],"campaign":["campaign","campaign name"],"conversions":["conversions","all conversions","results"],"conversion_value":["conversion value","conv value","purchase conversion value"]},
 "meta_ads": {"date":["date","reporting date","day"],"campaign":["campaign","campaign name","ad set name"],"purchases":["purchases","website purchases","results"],"purchase_value":["purchase conversion value","purchase value","website purchase conversion value"]},
 "shopify": {"order_id":["order id","name","order","id"],"order_date":["created at","order date","date"],"total":["total","total price","current total price"],"financial_status":["financial status","payment status","status"]},
}
OPTIONAL={"shopify":{"source":["utm source","source","first click source"],"medium":["utm medium","medium"],"campaign":["utm campaign","campaign"]}}
def clean_header(v): return re.sub(r"[^a-z0-9]+"," ",str(v).strip().lower()).strip()
def suggest_mapping(columns,source):
    normalized={clean_header(c):c for c in columns}
    result={}
    for field,aliases in {**REQUIRED[source],**OPTIONAL.get(source,{})}.items():
        for alias in aliases:
            if alias in normalized:
                result[field]=normalized[alias];break
    return result
def read_csv(path:Path):
    try: frame=pd.read_csv(path,dtype=str,keep_default_na=False)
    except pd.errors.EmptyDataError as exc: raise ValueError("CSV is empty and has no header row.") from exc
    except Exception as exc: raise ValueError(f"Could not parse CSV: {exc}") from exc
    if frame.columns.duplicated().any(): raise ValueError(f"Duplicate column headers: {frame.columns[frame.columns.duplicated()].tolist()}")
    return frame
def normalize(frame,source,mapping,filename):
    missing=[f for f in REQUIRED[source] if f not in mapping or mapping[f] not in frame.columns]
    if missing: raise ValueError(f"Missing required mappings for: {', '.join(missing)}")
    out=pd.DataFrame({"source_file":filename,"source_row":range(2,len(frame)+2)})
    for field,col in mapping.items():
        if col in frame.columns: out[field]=frame[col].astype(str).str.strip()
    date_field="order_date" if source=="shopify" else "date"
    raw=out[date_field].copy()
    # mixed=True preserves support for both ISO and common day-first platform exports.
    out[date_field]=pd.to_datetime(raw,errors="coerce",utc=True,format="mixed",dayfirst=False)
    # Explicit day-first retry for values that remained invalid.
    invalid=out[date_field].isna()
    if invalid.any():
        out.loc[invalid,date_field]=pd.to_datetime(raw[invalid],errors="coerce",utc=True,format="mixed",dayfirst=True)
    out[date_field+"_original"]=raw
    numeric={"total"} if source=="shopify" else ({"conversions","conversion_value"} if source=="google_ads" else {"purchases","purchase_value"})
    for field in numeric:
        raw=out[field].copy()
        cleaned=raw.str.replace(r"[^0-9.\-]","",regex=True)
        out[field]=pd.to_numeric(cleaned,errors="coerce")
        out[field+"_original"]=raw
    for field in OPTIONAL.get(source,{}):
        if field not in out: out[field]=""
    return out,[]
def make_issue(rule_id,title,description,severity,source,records,why,action,evidence=None):
    return {"rule_id":rule_id,"title":title,"description":description,"severity":severity,"source":source,"campaign":None,"affected_records":len(records),"evidence":evidence or {"records":records},"why_it_matters":why,"recommended_action":action}
def detect(frames,drop_threshold=.5):
    findings=[];shop=frames.get("shopify")
    if shop is not None:
        dup=shop[shop.order_id.duplicated(keep=False)]
        if not dup.empty:
            records=dup[["order_id","source_row","total","financial_status"]].to_dict("records")
            findings.append(make_issue("DUPLICATE_ORDER_ID","Repeated order IDs",f"{dup.order_id.nunique()} order IDs occur in {len(dup)} rows. This is not proof of duplicate purchases.","High","shopify",records,"Repeated records may inflate reported order and revenue totals.","Inspect each order ID in Shopify; compare timestamps, values and statuses.",{"duplicate_ids":dup.order_id.value_counts().to_dict(),"records":records}))
        for field in ("source","medium","campaign"):
            rows=shop[shop[field].astype(str).str.strip().eq("")]
            if not rows.empty:
                records=rows[["order_id","source_row",field]].to_dict("records")
                findings.append(make_issue("MISSING_UTM",f"Missing {field} information",f"{len(rows)} orders have no {field} value in the upload. This does not establish a tracking failure.","Medium","shopify",records,"Available attribution context is incomplete.","Check the store's order attribution details and the export's source fields.",{"missing_field":field,"records":records}))
        invalid=shop[shop.total.isna()|shop.total.lt(0)]
        if not invalid.empty:
            rec=invalid[["order_id","source_row","total_original","total"]].to_dict("records")
            findings.append(make_issue("INVALID_PURCHASE_VALUE","Missing or invalid purchase values",f"{len(invalid)} orders have a missing, non-numeric or negative total.","High","shopify",rec,"Invalid amounts can distort revenue summaries.","Verify the original order export and total/currency columns."))
        bad=shop[shop.order_date.isna()]
        if not bad.empty:
            rec=bad[["order_id","source_row","order_date_original"]].to_dict("records")
            findings.append(make_issue("INVALID_DATE","Invalid order dates",f"{len(bad)} order dates could not be parsed.","Medium","shopify",rec,"These records cannot be reliably assigned to reporting periods.","Verify date format and timezone conventions."))
        status=shop.financial_status.str.lower()
        for label,mask in [("Cancelled",status.str.contains("cancel",na=False)),("Refunded",status.str.contains("refund",na=False)),("Test",status.str.contains("test",na=False))]:
            rows=shop[mask]
            if not rows.empty:
                rec=rows[["order_id","source_row","financial_status","total"]].to_dict("records")
                findings.append(make_issue("EXCLUDED_ORDER_CANDIDATE",f"{label} orders to review",f"{len(rows)} orders have a status indicating {label.lower()}. They remain in the uploaded dataset.","Medium","shopify",rec,"These records may need distinct revenue treatment.","Confirm the reporting policy before including or excluding these orders.",{"status_group":label,"records":rec}))
    for source,metric in [("google_ads","conversions"),("meta_ads","purchases")]:
        f=frames.get(source)
        if f is None or f.empty: continue
        valid=f.dropna(subset=["date"])
        if valid.empty: continue
        daily=valid.groupby(valid.date.dt.date)[metric].sum(min_count=1).sort_index()
        for i in range(7,len(daily)):
            baseline=daily.iloc[i-7:i];mean=float(baseline.mean());current=float(daily.iloc[i])
            if mean>=2 and current<=mean*(1-drop_threshold):
                rec=[{"date":str(daily.index[i]),"current":current,"baseline_daily_average":round(mean,3),"drop_percent":round((1-current/mean)*100,2),"baseline_days":7,"threshold_percent":drop_threshold*100}]
                findings.append(make_issue("CONVERSION_DROP","Unusual conversion drop",f"{source} reported {current:g} {metric} on {daily.index[i]}, {rec[0]['drop_percent']}% below the preceding seven-day average.","High",source,rec,"A drop can reflect demand, spend, site issues, reporting changes or lag; it is not proof of broken tracking.","Check spend and delivery, checkout health, tag diagnostics and reporting delays.",{"records":rec}))
    return findings
def reconcile(frames):
    shop=frames.get("shopify")
    if shop is None:return []
    eligible=shop[~shop.financial_status.str.lower().str.contains("cancel|test",na=False)]
    orders=int(eligible.order_id.nunique());revenue=float(eligible.total.sum(skipna=True));result=[]
    for source,metric,value_field in [("google_ads","conversions","conversion_value"),("meta_ads","purchases","purchase_value")]:
        f=frames.get(source)
        if f is None:continue
        conversions=float(f[metric].sum(skipna=True));value=float(f[value_field].sum(skipna=True))
        result.append({"platform":source,"platform_conversions":conversions,"available_shopify_orders":orders,"conversion_difference":conversions-orders,"platform_conversion_value":value,"comparable_shopify_revenue":revenue,"value_difference":value-revenue,"matching_method":"Aggregate comparison only","status":"Aggregate discrepancy — attribution not independently verified","limitations":["No shared transaction identifier used for row-level matching.","Attribution windows and conversion lag are not modeled.","Currency and timezone comparability require operator verification.","Cancelled and test orders omitted from basic order count; refunded orders remain included."]})
    return result
