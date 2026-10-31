const BASE=(import.meta.env.VITE_API_URL??"http://127.0.0.1:8000").replace(/\\/$/, "");
async function req(path:string,init?:RequestInit){const r=await fetch(BASE+path,init);if(!r.ok){const b=await r.json().catch(()=>({}));throw new Error(b.detail??"Request failed");}return r;}
export async function upload(source:string,file:File){const f=new FormData();f.append("file",file);return(await req("/api/upload?source="+source,{method:"POST",body:f})).json();}
export async function saveMapping(id:string,mapping:Record<string,string>){return(await req("/api/upload/"+id+"/mapping",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mapping})})).json();}
export async function run(files:Record<string,string>,mappings:Record<string,Record<string,string>>){return(await req("/api/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({files,mappings})})).json();}
export async function listRuns(){return(await req("/api/runs")).json();}
export async function getRun(id:number){return(await req("/api/runs/"+id)).json();}
export async function listExceptions(id:number){return(await req("/api/runs/"+id+"/exceptions")).json();}
export async function setStatus(id:number,status:string){return(await req("/api/exceptions/"+id+"/status",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})})).json();}
export async function exportReport(id:number,kind:string){const r=await req("/api/runs/"+id+"/export/"+kind);const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="conversion-qa-"+id+"-"+kind+".csv";a.click();URL.revokeObjectURL(url);}
