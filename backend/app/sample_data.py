from pathlib import Path
import pandas as pd
OUT=Path(__file__).resolve().parents[2]/"sample_data"
def generate():
    OUT.mkdir(exist_ok=True);dates=pd.date_range("2026-10-01",periods=14)
    ga=[];meta=[]
    for i,d in enumerate(dates):
        n=12 if i<12 else (3 if i==12 else 2)
        ga.append({"Date":d.strftime("%Y-%m-%d"),"Campaign":"Shopping US","Conversions":n,"Conversion value":n*85})
        meta.append({"Reporting date":d.strftime("%d/%m/%Y"),"Campaign name":"Meta Prospecting","Purchases":max(1,n-2),"Purchase conversion value":max(1,n-2)*82})
    orders=[]
    for i in range(1,61):
        d=dates[(i-1)%12]
        orders.append({"Order ID":f"NS-{i:04d}","Created at":d.strftime("%Y-%m-%d"),"Total":round(60+(i%9)*11.5,2),"Financial status":"paid","UTM source":"google" if i%2 else "meta","UTM medium":"paid","UTM campaign":"Shopping US" if i%2 else "Meta Prospecting"})
    orders += [
      {"Order ID":"NS-0004","Created at":"2026-10-04","Total":"138","Financial status":"paid","UTM source":"","UTM medium":"paid","UTM campaign":"Shopping US"},
      {"Order ID":"NS-0061","Created at":"2026-10-09","Total":"bad-value","Financial status":"paid","UTM source":"google","UTM medium":"","UTM campaign":""},
      {"Order ID":"NS-0062","Created at":"not-a-date","Total":"99","Financial status":"paid","UTM source":"","UTM medium":"","UTM campaign":""},
      {"Order ID":"NS-0063","Created at":"2026-10-10","Total":"-20","Financial status":"refunded","UTM source":"meta","UTM medium":"paid","UTM campaign":"Meta Prospecting"},
      {"Order ID":"NS-0064","Created at":"2026-10-11","Total":"120","Financial status":"cancelled","UTM source":"","UTM medium":"","UTM campaign":""},
      {"Order ID":"NS-0065","Created at":"2026-10-12","Total":"50","Financial status":"test","UTM source":"","UTM medium":"","UTM campaign":""}]
    pd.DataFrame(ga).to_csv(OUT/"google_ads.csv",index=False);pd.DataFrame(meta).to_csv(OUT/"meta_ads.csv",index=False);pd.DataFrame(orders).to_csv(OUT/"shopify_orders.csv",index=False)
    print("Generated fictional Northstar Outdoor CSV exports in",OUT)
if __name__=="__main__":generate()
