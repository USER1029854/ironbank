# Minimal pure-python keccak-256 (Ethereum). Validated against known vectors.
def keccak256(data: bytes) -> bytes:
    RC=[0x0000000000000001,0x0000000000008082,0x800000000000808A,0x8000000080008000,
        0x000000000000808B,0x0000000080000001,0x8000000080008081,0x8000000000008009,
        0x000000000000008A,0x0000000000000088,0x0000000080008009,0x000000008000000A,
        0x000000008000808B,0x800000000000008B,0x8000000000008089,0x8000000000008003,
        0x8000000000008002,0x8000000000000080,0x000000000000800A,0x800000008000000A,
        0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008]
    ROT=[[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]]
    MASK=(1<<64)-1
    def rol(x,n): n%=64; return ((x<<n)|(x>>(64-n)))&MASK
    rate=136 # 1088 bits for keccak-256
    # padding (keccak pad10*1 with 0x01 domain)
    m=bytearray(data)
    m.append(0x01)
    while len(m)%rate!=(rate-1): m.append(0x00)
    m.append(0x80)
    # state as 5x5 lanes
    S=[[0]*5 for _ in range(5)]
    for off in range(0,len(m),rate):
        block=m[off:off+rate]
        for i in range(rate//8):
            lane=int.from_bytes(block[i*8:i*8+8],'little')
            S[i%5][i//5]^=lane
        # 24 rounds
        for rnd in range(24):
            C=[S[x][0]^S[x][1]^S[x][2]^S[x][3]^S[x][4] for x in range(5)]
            D=[C[(x-1)%5]^rol(C[(x+1)%5],1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    S[x][y]^=D[x]
            B=[[0]*5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    B[y][(2*x+3*y)%5]=rol(S[x][y],ROT[x][y])
            for x in range(5):
                for y in range(5):
                    S[x][y]=B[x][y]^((~B[(x+1)%5][y])&B[(x+2)%5][y])
            S[0][0]^=RC[rnd]
    out=bytearray()
    for i in range(4): # 32 bytes = 4 lanes
        out+= (S[i%5][i//5]).to_bytes(8,'little')
    return bytes(out)
def sel(sig): return keccak256(sig.encode()).hex()[:8]
def topic(sig): return '0x'+keccak256(sig.encode()).hex()
if __name__=="__main__":
    assert keccak256(b'').hex()=="c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470", keccak256(b'').hex()
    assert sel("transfer(address,uint256)")=="a9059cbb", sel("transfer(address,uint256)")
    assert sel("getAllMarkets()")=="b0772d0b"
    print("keccak OK")
    for s in ["getUnderlyingPrice(address)","markets(address)","decimals()","collateralCap()","totalSupply()",
              "totalBorrows()","totalReserves()","getCash()","exchangeRateStored()","reserveFactorMantissa()",
              "borrowCaps(address)","supplyCaps(address)","balanceOf(address)","implementation()","admin()",
              "creditLimits(address,address)","isMarketSoftDelisted(address)","borrowIndex()","accrualBlockNumber()",
              "internalCash()","totalCollateralTokens()","interestRateModel()","comptroller()","underlying()"]:
        print(sel(s), s)
    print("EVENT CreditLimitChanged:", topic("CreditLimitChanged(address,address,uint256)"))
    print("EVENT NewImplementation:", topic("NewImplementation(address,address)"))
