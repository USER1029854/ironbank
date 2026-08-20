import urllib.request, json, time
from keccak import sel
EK="YOUR_ETHERSCAN_V2_KEY"; V2="https://api.etherscan.io/v2/api"
COMP="0xAB1c342C7bf5Ec5F02ADEA1c2270670bCa144CbB"
_last=[0.0]
def call(to,data):
    for _ in range(6):
        dt=time.time()-_last[0]
        if dt<0.45: time.sleep(0.45-dt)
        _last[0]=time.time()
        u=f"{V2}?chainid=1&module=proxy&action=eth_call&to={to}&data=0x{data}&tag=latest&apikey={EK}"
        try:
            d=json.load(urllib.request.urlopen(u,timeout=30)); r=d.get('result','')
            if isinstance(r,str) and 'rate limit' in r: time.sleep(1);continue
            return r
        except Exception: time.sleep(0.7)
    return None
def w1(to,fn):  # first word only
    r=call(to,sel(fn))
    if not r or len(r)<66: return None
    return int(r[2:66],16)
def w1arg(to,fn,a):
    r=call(to,sel(fn)+a[2:].rjust(64,'0'))
    if not r or len(r)<66: return None
    return int(r[2:66],16)
om=json.load(open("data/oracle_map.json"))
order=["iWETH","iDAI","iMIM","iLINK","iYFI","iSNX","iWBTC","iUSDT","iUSDC","iSUSHI","iGBP","iEUR","EURS","iAAVE","iDPI","iAUD","iCRV","iJPY","iKRW","iCVX","iSUSD","iCHF","iUNI","iWSTETH"]
name2ct={ "EURS":"0xa8caea564811af0e92b1e044f3edd18fa9a73e4f" }
# map from om keys: om has key 'MYST1' possibly; handle
key_for={ }
rows=[]
for sym in order:
    entry=None
    for k,v in om.items():
        if k==sym or v.get('usym','').lower()==sym[1:].lower():
            entry=v; break
    if sym=="EURS":
        for k,v in om.items():
            if v['ct'].lower()=="0xa8caea564811af0e92b1e044f3edd18fa9a73e4f": entry=v;break
    if not entry: 
        # find by ct in solvency prior
        continue
    ct=entry['ct']; und=entry['und']; udec=entry['udec'] or 18
    ts=w1(ct,"totalSupply()"); tb=w1(ct,"totalBorrows()"); tr=w1(ct,"totalReserves()")
    ic=w1(ct,"internalCash()"); er=w1(ct,"exchangeRateStored()")
    onchain=w1arg(und,"balanceOf(address)",ct)
    rows.append(dict(sym=sym,ct=ct,und=und,udec=udec,ts=ts,tb=tb,tr=tr,ic=ic,er=er,onchain=onchain,price=entry.get('price')))
json.dump(rows,open("data/solvency2.json","w"),indent=1)
print(f"{'sym':8}{'totBorrow(u)':>16}{'reserves(u)':>14}{'intCash(u)':>14}{'onChain(u)':>14}{'exRate':>10}{'util%':>7}  reconcile(onchain-intCash)")
for r in rows:
    d=10**r['udec']
    def f(x): return '?' if x is None else f"{x/d:,.2f}"
    util = (r['tb']/(r['tb']+r['ic'])*100) if (r['tb'] and r['ic'] is not None and (r['tb']+r['ic'])>0) else (100.0 if r['tb'] else 0)
    rec = (r['onchain']-r['ic']) if (r['onchain'] is not None and r['ic'] is not None) else None
    print(f"{r['sym']:8}{f(r['tb']):>16}{f(r['tr']):>14}{f(r['ic']):>14}{f(r['onchain']):>14}{(r['er']/1e18 if r['er'] else 0):>10.4f}{util:>7.1f}  {('' if rec is None else f'{rec/d:,.4f}')}")
