import urllib.request, json, time, sys, os
EK="YOUR_ETHERSCAN_V2_KEY"
V2="https://api.etherscan.io/v2/api"
def get(url):
    for _ in range(4):
        try: return json.load(urllib.request.urlopen(url,timeout=60))
        except Exception as e:
            sys.stderr.write(f"retry {e}\n"); time.sleep(2)
    return None
def fetch_source(addr,label):
    u=f"{V2}?chainid=1&module=contract&action=getsourcecode&address={addr}&apikey={EK}"
    d=get(u)
    if not d or d.get('status')!='1':
        print(f"{label} {addr}: NOT VERIFIED / err: {str(d)[:200]}"); return
    r=d['result'][0]
    name=r.get('ContractName','?'); impl=r.get('Implementation','')
    print(f"{label} {addr}: name={name} proxy={r.get('Proxy')} impl={impl} compiler={r.get('CompilerVersion','')}")
    src=r.get('SourceCode','')
    outdir=f"src/{label}_{name}"
    os.makedirs(outdir,exist_ok=True)
    # handle multi-file json
    if src.startswith('{'):
        s=src
        if s.startswith('{{'): s=s[1:-1]
        try:
            j=json.loads(s)
            files=j.get('sources',j)
            for path,content in files.items():
                safe=path.replace('/','__')
                open(f"{outdir}/{safe}",'w').write(content.get('content','') if isinstance(content,dict) else str(content))
            print(f"   -> {len(files)} files to {outdir}")
        except Exception as e:
            open(f"{outdir}/raw.txt",'w').write(src); print(f"   json parse fail {e}, raw saved")
    else:
        open(f"{outdir}/{name}.sol",'w').write(src); print(f"   -> single file to {outdir}")
for addr,label in [
  ("0xcb9ab119be270f58d40e3d57d1ecc82bd479d59f","comptroller_impl"),
  ("0xbd6f5add9b7a6eb151933cb4efd50be4eca71451","oracle"),
  ("0x7e8844ea4c211a69ad9308ba0b6cdb3ea0bb2b05","cerc20delegate"),
  ("0xAB1c342C7bf5Ec5F02ADEA1c2270670bCa144CbB","unitroller"),
]:
    fetch_source(addr,label)
