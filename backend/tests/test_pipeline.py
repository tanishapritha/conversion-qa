import pytest
import pandas as pd
from app.pipeline import normalize,detect,reconcile,read_csv,suggest_mapping

def shop(rows, mapping=None):
    frame=pd.DataFrame(rows)
    mapping=mapping or {"order_id":"Order ID","order_date":"Created at","total":"Total","financial_status":"Financial status","source":"UTM source","medium":"UTM medium","campaign":"UTM campaign"}
    return normalize(frame,"shopify",mapping,"orders.csv")[0]

def test_duplicate_order_ids_are_repeated_record_signal():
    rows=[{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}]*2
    result=detect({"shopify":shop(rows)})
    issue=next(x for x in result if x["rule_id"]=="DUPLICATE_ORDER_ID")
    assert issue["affected_records"]==2 and issue["evidence"]["duplicate_ids"]["A"]==2

def test_missing_utm_is_not_called_tracking_failure():
    result=detect({"shopify":shop([{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"","UTM medium":"y","UTM campaign":"z"}])})
    issue=next(x for x in result if x["rule_id"]=="MISSING_UTM")
    assert "does not establish a tracking failure" in issue["description"]

def test_bad_values_and_dates_preserve_originals():
    frame=shop([{"Order ID":"A","Created at":"not-a-date","Total":"invalid","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    rules={x["rule_id"] for x in detect({"shopify":frame})}
    assert {"INVALID_DATE","INVALID_PURCHASE_VALUE"}<=rules
    assert frame.iloc[0]["total_original"]=="invalid"

def test_zero_value_is_not_invalid():
    frame=shop([{"Order ID":"A","Created at":"2026-10-01","Total":"0","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    assert not any(x["rule_id"]=="INVALID_PURCHASE_VALUE" for x in detect({"shopify":frame}))

def test_day_first_date_supported():
    frame=shop([{"Order ID":"A","Created at":"31/10/2026","Total":"10","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    assert pd.notna(frame.iloc[0]["order_date"])

def test_conversion_drop_requires_enough_baseline():
    dates=pd.date_range("2026-10-01",periods=8)
    frame=pd.DataFrame({"date":dates,"conversions":[10]*7+[1],"conversion_value":[100]*8,"campaign":["c"]*8})
    assert any(x["rule_id"]=="CONVERSION_DROP" for x in detect({"google_ads":frame}))
    low=frame.copy();low["conversions"]=[1]*7+[0]
    assert not any(x["rule_id"]=="CONVERSION_DROP" for x in detect({"google_ads":low}))

def test_aggregate_reconciliation_discloses_limitations():
    s=shop([{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    g=pd.DataFrame({"conversions":[2],"conversion_value":[20]})
    result=reconcile({"shopify":s,"google_ads":g})[0]
    assert result["matching_method"]=="Aggregate comparison only"
    assert "not independently verified" in result["status"]

def test_column_suggestions_are_case_and_punctuation_tolerant():
    mapping=suggest_mapping(["Reporting date","Campaign name","All conversions","Conversion value"],"google_ads")
    assert mapping["date"]=="Reporting date" and mapping["conversions"]=="All conversions"

def test_invalid_required_mapping_rejected():
    with pytest.raises(ValueError):
        normalize(pd.DataFrame({"foo":["x"]}),"shopify",{},"bad.csv")

def test_read_csv_empty_header_raises(tmp_path):
    p=tmp_path/"empty.csv";p.write_text("")
    with pytest.raises(ValueError):read_csv(p)
