import urllib.request, json, time, sys
EK="YOUR_ETHERSCAN_V2_KEY"
V2="https://api.etherscan.io/v2/api"
markets=["0x41c84c0e2ee0b740cf0d31f63f3b6f627dc6b393","0x8e595470ed749b85c6f7669de83eae304c2ec68f","0x9e8e207083ffd5bdc3d99a1f32d1e6250869c1a9","0xe7bff2da8a2f619c2586fb83938fa56ce803aa16","0xfa3472f7319477c9bfecdd66e4b948569e7621b9","0x12a9cc33a980daa74e00cc2d1a0e74c57a93d12c","0x8fc8bfd80d6a9f17fb98a373023d72531792b431","0x48759f220ed983db51fa7a8c0d2aab8f3ce4166a","0x76eb2fe28b36b3ee97f3adae0c69606eedb2a37c","0x226f3738238932ba0db2319a8117d9555446102f","0xecab2c76f1a8359a06fab5fa0ceea51280a97ecf","0x00e5c0774a5f065c285068170b20393925c84bf3","0xa8caea564811af0e92b1e044f3edd18fa9a73e4f","0x30190a3b52b5ab1daf70d46d72536f5171f22340","0x7736ffb07104c0c400bb0cc9a7c228452a732992","0x86bbd9ac8b9b44c95ffc6baae58e25033b7548aa","0xb8c5af54bbdcc61453144cf472a9276ae36109f9","0x215f34af6557a6598dbda9aa11cc556f5ae264b1","0x3c9f5385c288ce438ed55620938a4b967c080101","0xe0b57feed45e7d908f2d0dacd26f113cf26715bf","0xa7c4054afd3dbbbf5bfe80f41862b89ea05c9806","0x1b3e95e8ecf7a7cab6c4de1b344f94865abd12d5","0xfeeb92386a055e2ef7c2b598c872a4047a7db59f","0xbc6b6c837560d1fe317ebb54e105c89f303d5afd"]
def call(to,data):
    u=f"{V2}?chainid=1&module=proxy&action=eth_call&to={to}&data={data}&tag=latest&apikey={EK}"
    for _ in range(3):
        try:
            r=json.load(urllib.request.urlopen(u,timeout=30)).get('result','')
            return r
        except Exception as e:
            time.sleep(1)
    return None
def dec_str(hexret):
    if not hexret or not hexret.startswith('0x') or len(hexret)<130: return '?'
    h=hexret[2:]
    try:
        ln=int(h[64:128],16); raw=bytes.fromhex(h[128:128+ln*2]); return raw.decode('utf8','replace')
    except: return '?'
def dec_addr(h):
    if not h or len(h)<66: return '?'
    return '0x'+h[-40:]
def dec_uint(h):
    if not h or not h.startswith('0x'): return None
    try: return int(h,16)
    except: return None
# selectors
SYM="0x95d89b41"; UND="0x6f307dc3"; IMPL="0x5c60da1b"; DEC="0x313ce567"; RF="0x173b9904"; ADMIN="0xf851a440"
for m in markets:
    sym=dec_str(call(m,SYM))
    und=dec_addr(call(m,UND))
    impl=dec_addr(call(m,IMPL))
    print(f"{m}\t{sym}\tunderlying={und}\timpl={impl}")
