import json,uuid
from fastapi import FastAPI,File,UploadFile,HTTPException,Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import pandas as pd
from .db import Base,engine,get_db,UPLOAD_DIR
from .models import QARun,QAException
from .pipeline import REQUIRED,read_csv,suggest_mapping,normalize,detect,reconcile
Base.metadata.create_all(bind=engine)
app=FastAPI(title="Conversion QA API",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["*"],allow_headers=["*"])
FILES={}
@app.get("/api/health")
def health():return {"status":"ok"}
@app.post("/api/upload")
async def upload(source:str,file:UploadFile=File(...)):
    if source not in REQUIRED:raise HTTPException(400,"Invalid source")
    if not file.filename or not file.filename.lower().endswith(".csv"):raise HTTPException(400,"Upload a CSV file")
    content=await file.read()
    if len(content)>15*1024*1024:raise HTTPException(413,"CSV exceeds 15 MB")
    if not content:raise HTTPException(400,"Uploaded file is empty")
    fid=uuid.uuid4().hex;path=UPLOAD_DIR/(fid+".csv");path.write_bytes(content)
    try:f=read_csv(path)
    except ValueError as exc:path.unlink(missing_ok=True);raise HTTPException(422,str(exc))
    mapping=suggest_mapping(f.columns.tolist(),source);FILES[fid]={"path":path,"source":source,"filename":file.filename,"mapping":mapping}
    return {"file_id":fid,"source":source,"filename":file.filename,"rows":len(f),"columns":f.columns.tolist(),"mapping_suggestion":mapping,"missing_required":[k for k in REQUIRED[source] if k not in mapping],"preview":f.head(8).fillna("").to_dict("records")}
@app.get("/api/upload/{fid}/preview")
def preview(fid:str):
    item=FILES.get(fid)
    if not item:raise HTTPException(404,"Upload not found; upload again.")
    f=read_csv(item["path"])
    return {"rows":len(f),"columns":f.columns.tolist(),"preview":f.head(20).fillna("").to_dict("records"),"mapping":item["mapping"]}
@app.post("/api/upload/{fid}/mapping")
def set_mapping(fid:str,payload:dict):
    item=FILES.get(fid)
    if not item:raise HTTPException(404,"Upload not found")
    mapping=payload.get("mapping",{});f=read_csv(item["path"])
    invalid={k:v for k,v in mapping.items() if v not in f.columns}
    if invalid:raise HTTPException(422,f"Unknown mapped columns: {invalid}")
    missing=[k for k in REQUIRED[item["source"]] if k not in mapping]
    if missing:raise HTTPException(422,f"Missing required mappings: {missing}")
    item["mapping"]=mapping
    return {"file_id":fid,"mapping":mapping,"valid":True}
@app.post("/api/runs")
def create_run(payload:dict,db:Session=Depends(get_db)):
    frames={};meta={}
    for source,fid in payload.get("files",{}).items():
        item=FILES.get(fid)
        if not item or item["source"]!=source:raise HTTPException(422,f"Upload missing or source mismatch: {source}")
        try:
            raw=read_csv(item["path"]);frame,_=normalize(raw,source,payload.get("mappings",{}).get(source,item["mapping"]),item["filename"])
        except (ValueError,KeyError) as exc:raise HTTPException(422,str(exc))
        frames[source]=frame;meta[source]={"filename":item["filename"],"rows":len(raw),"mapping":payload.get("mappings",{}).get(source,item["mapping"])}
    if "shopify" not in frames:raise HTTPException(422,"Shopify orders CSV is required")
    findings=detect(frames);comparison=reconcile(frames)
    all_dates=[]
    for f in frames.values():
        for c in ("date","order_date"):
            if c in f:all_dates.extend(f[c].dropna().tolist())
    run=QARun(records_processed=sum(len(f) for f in frames.values()),files_json=json.dumps(meta),reconciliation_json=json.dumps(comparison))
    if all_dates:run.period_start=str(min(all_dates).date());run.period_end=str(max(all_dates).date())
    db.add(run);db.flush()
    for x in findings:db.add(QAException(run_id=run.id,rule_id=x["rule_id"],title=x["title"],description=x["description"],severity=x["severity"],source=x["source"],campaign=x.get("campaign"),affected_records=x["affected_records"],evidence_json=json.dumps(x["evidence"],default=str),why_it_matters=x["why_it_matters"],recommended_action=x["recommended_action"]))
    db.commit();db.refresh(run)
    return {"run_id":run.id,"records_processed":run.records_processed,"period_start":run.period_start,"period_end":run.period_end,"exception_count":len(findings),"summary":{s:sum(1 for x in findings if x["severity"]==s) for s in ["High","Medium","Low"]},"reconciliation":comparison,"exceptions":findings}
@app.get("/api/runs")
def list_runs(db:Session=Depends(get_db)):
    return [{"id":r.id,"created_at":r.created_at.isoformat(),"records_processed":r.records_processed,"period_start":r.period_start,"period_end":r.period_end,"exception_count":len(r.exceptions)} for r in db.query(QARun).order_by(QARun.created_at.desc()).limit(50)]
@app.get("/api/runs/{rid}")
def get_run(rid:int,db:Session=Depends(get_db)):
    r=db.query(QARun).filter_by(id=rid).first()
    if not r:raise HTTPException(404,"Run not found")
    return {"id":r.id,"created_at":r.created_at.isoformat(),"records_processed":r.records_processed,"period_start":r.period_start,"period_end":r.period_end,"files":json.loads(r.files_json),"exception_count":len(r.exceptions),"summary":{s:sum(e.severity==s for e in r.exceptions) for s in ["High","Medium","Low"]},"reconciliation":json.loads(r.reconciliation_json)}
def as_dict(e):
    return {"id":e.id,"rule_id":e.rule_id,"title":e.title,"description":e.description,"severity":e.severity,"source":e.source,"campaign":e.campaign,"affected_records":e.affected_records,"evidence":json.loads(e.evidence_json),"why_it_matters":e.why_it_matters,"recommended_action":e.recommended_action,"status":e.status}
@app.get("/api/runs/{rid}/exceptions")
def exceptions(rid:int,severity:str|None=None,source:str|None=None,db:Session=Depends(get_db)):
    q=db.query(QAException).filter_by(run_id=rid)
    if severity:q=q.filter_by(severity=severity)
    if source:q=q.filter_by(source=source)
    return [as_dict(e) for e in q]
@app.get("/api/exceptions/{eid}")
def get_exception(eid:int,db:Session=Depends(get_db)):
    e=db.query(QAException).filter_by(id=eid).first()
    if not e:raise HTTPException(404,"Exception not found")
    return as_dict(e)
@app.patch("/api/exceptions/{eid}/status")
def update_status(eid:int,payload:dict,db:Session=Depends(get_db)):
    if payload.get("status") not in {"Open","Investigating","Resolved","Ignored"}:raise HTTPException(422,"Invalid status")
    e=db.query(QAException).filter_by(id=eid).first()
    if not e:raise HTTPException(404,"Exception not found")
    e.status=payload["status"];db.commit();return as_dict(e)
@app.get("/api/runs/{rid}/reconciliation")
def run_reconciliation(rid:int,db:Session=Depends(get_db)):
    r=db.query(QARun).filter_by(id=rid).first()
    if not r:raise HTTPException(404,"Run not found")
    return json.loads(r.reconciliation_json)
@app.get("/api/runs/{rid}/export/{kind}")
def export(rid:int,kind:str,db:Session=Depends(get_db)):
    r=db.query(QARun).filter_by(id=rid).first()
    if not r:raise HTTPException(404,"Run not found")
    if kind=="reconciliation":data=json.loads(r.reconciliation_json)
    elif kind in {"exceptions","invalid-records"}:
        data=[as_dict(e) for e in r.exceptions]
        if kind=="invalid-records":data=[e for e in data if e["rule_id"] in {"INVALID_DATE","INVALID_PURCHASE_VALUE"}]
    else:raise HTTPException(400,"Unknown export type")
    csv=pd.json_normalize(data).to_csv(index=False)
    return StreamingResponse(iter([csv]),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="conversion-qa-{rid}-{kind}.csv"'})
