import pandas as pd
from app.pipeline import normalize,detect,reconcile

def shop(rows):
    mapping={"order_id":"Order ID","order_date":"Created at","total":"Total","financial_status":"Financial status","source":"UTM source","medium":"UTM medium","campaign":"UTM campaign"}
    return normalize(pd.DataFrame(rows),"shopify",mapping,"orders.csv")[0]
def test_duplicate_orders():
    f=shop([{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"},{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    assert any(x["rule_id"]=="DUPLICATE_ORDER_ID" for x in detect({"shopify":f}))
def test_invalid_value_and_date():
    f=shop([{"Order ID":"A","Created at":"not-a-date","Total":"invalid","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    ids={x["rule_id"] for x in detect({"shopify":f})}
    assert {"INVALID_DATE","INVALID_PURCHASE_VALUE"}<=ids
def test_missing_utm_not_failure():
    f=shop([{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"","UTM medium":"y","UTM campaign":"z"}])
    issue=next(x for x in detect({"shopify":f}) if x["rule_id"]=="MISSING_UTM")
    assert "does not establish a tracking failure" in issue["description"]
def test_drop_signal():
    dates=pd.date_range("2026-10-01",periods=8)
    f=pd.DataFrame({"date":dates,"conversions":[10]*7+[1],"conversion_value":[100]*8,"campaign":["c"]*8})
    assert any(x["rule_id"]=="CONVERSION_DROP" for x in detect({"google_ads":f}))
def test_small_baseline_no_signal():
    dates=pd.date_range("2026-10-01",periods=8)
    f=pd.DataFrame({"date":dates,"conversions":[1]*7+[0],"conversion_value":[1]*8,"campaign":["c"]*8})
    assert not any(x["rule_id"]=="CONVERSION_DROP" for x in detect({"google_ads":f}))
def test_reconciliation_label():
    s=shop([{"Order ID":"A","Created at":"2026-10-01","Total":"10","Financial status":"paid","UTM source":"x","UTM medium":"y","UTM campaign":"z"}])
    g=pd.DataFrame({"conversions":[2],"conversion_value":[20]})
    result=reconcile({"shopify":s,"google_ads":g})[0]
    assert result["matching_method"]=="Aggregate comparison only" and "not independently verified" in result["status"]
