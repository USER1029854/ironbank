FORK PoC (ganache mainnet fork @ block 25799697, driven from an unprivileged test EOA
0xf39f…2266; upstream Tenderly archive via local rate-limited forwarder). Script: audit/poc.py

--- FINDING 3 (P2P credit line) — UNPRIVILEGED REACH ---
A1  attacker._setCreditLimit(attacker, iUSDC, 1e30)      -> REVERT "admin or credit limit manager only"
A2  attacker.iLINK.borrow(1 LINK) with $0 collateral      -> REVERT "market borrow cap reached"
    => cannot self-grant credit; cannot borrow uncollateralized.  UNPRIVILEGED AT RISK = $0

--- FINDING 1 (single-source oracle) — UNPRIVILEGED PRICE MOVE / OVER-BORROW ---
C1  attacker.oracle._setAggregators([],[],[])             -> REVERT "only the admin may set the aggregators"
    attacker supplies 100 WETH, enters market             -> borrowing power computed = $198,214 (100*ETH*0.85)
C3  attacker.iLINK.borrow(100000 LINK) >> collateral      -> REVERT "market borrow cap reached"
    (note: iLINK is AT its borrow cap now, so even its ~5.6k LINK cash is not borrowable by anyone)
    => no unprivileged primitive moves any price; borrow bounded by collateral*CF and by borrowCaps.
       UNPRIVILEGED AT RISK TODAY = $0. ($30.3M single-sourced collateral is exposed only to an
       EXTERNAL Chainlink feed degrading — not attacker-triggerable.)

--- FINDING 2 (oracle revert bricks liquidity) — UNPRIVILEGED SELF-POISON ---
    attacker supplies 100 WETH (liq $198,214), BEFORE poison getAccountLiquidity -> OK
    acquires iMIM cTokens via OTC (modeled: impersonated holder 0x197939c1… transfers 4724 cMIM)
    attacker.enterMarkets([iMIM])                          -> SUCCESS
    AFTER poison: getAccountLiquidity(attacker)            -> REVERT "Feed not found"
    third-party liquidator.liquidateBorrow(attacker,…)     -> REVERT "Feed not found"   (LIQUIDATION BRICKED)
    => unprivileged attacker CAN make itself unliquidatable. BUT immediate extractable profit = $0:
       needs collateral to later fall below debt (EXTERNAL price move); and in current state the
       attacker cannot even build leveraged debt (borrow caps binding). STRUCTURAL risk only.

BOTTOM LINE (unprivileged, no gate/no admin, at-will, TODAY):
  Finding 1: $0   Finding 2: $0   Finding 3: $0   Finding 4: $0
  Every finding is either externally-triggered (feed degradation) or role-gated. Lower urgency
  for immediate theft; the fixes remain worthwhile for resilience/centralization.
