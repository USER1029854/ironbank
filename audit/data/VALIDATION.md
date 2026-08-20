VALIDATION (live-state eth_call simulation against mainnet, block ts 2026-08-20 22:39 UTC)

FINDING 2 (oracle-revert bricks liquidity -> unliquidatable) — PROVEN LIVE, UN-GATED:
  getAccountLiquidity() REVERTS "Feed not found" for real accounts entered in iMIM/iDPI:
    0x6e868846...58e4 (iMIM borrower)  -> REVERT
    0xdeb9553e...1574 (iMIM borrower)  -> REVERT
    0xba5ebaf3...e54b (iDPI borrower)  -> REVERT
  Control (not in dead markets) succeed: FixedForex 0x6b41 -> err=0; random -> 0/0/0.
  => No try/catch, no gate. Liquidation of these accounts is impossible.
  CURRENT REALIZED EXPOSURE = DUST: the only NON-credit poisoned accounts are the two
  iMIM dust borrowers (collateral $8 and $14; ~5 MIM debt total). 0xba5ebaf is a CREDIT
  account (limit=1 markers on every major it borrows) => already unliquidatable as a
  credit account regardless of iDPI; its $792k is credit/backstop debt (Finding 3), not
  poison-enabled bad debt. So Finding 2's LIVE value-at-risk today ≈ $22.
  SEVERITY IS STRUCTURAL: recurs at full size if any UN-paused market's feed is removed
  (the FX markets carrying the credit lines are the prime candidates).

FINDING 3 (P2P credit line) — SIZED + GATING CONFIRMED:
  Uncollateralized credit-line debt outstanding ≈ $2.30M:
    FixedForex FX synth debt ≈ $1.51M (iEUR $745k, iCHF $276k, iKRW $221k, iAUD $208k, iGBP $34k, iJPY $26k)
    backstop 0xba5ebaf major-market debt ≈ $792k (WETH/USDC/DAI/USDT/WBTC), $0 collateral
  Gating (simulated live):
    borrowAllowed(iEUR, FixedForex, 1000e18) -> ALLOWED(0) with $0 collateral (credit path skips liquidity) — CONFIRMED
    _setCreditLimit(attacker,iUSDC,1e30) FROM creditLimitManager -> SUCCESS (arbitrary grant) — unbounded power
    _setCreditLimit(...) FROM random -> REVERT "admin or credit limit manager only" — NOT unprivileged
    Additional bound: borrowAllowed enforces borrowCap BEFORE the credit branch (huge amt -> "market borrow cap reached"),
      so per-market credit borrow is bounded by borrowCaps (mutable by admin/guardian).

FINDING 1 (single-source oracle, no staleness) — SIZED:
  Total collateral valued by the single-source oracle ≈ $30.3M (borrowing power ≈ $27.3M).
  Largest single-feed exposures: USDT/USD $20.4M coll ($18.3M power), DAI/USD $9.0M ($8.1M), USDC/USD $0.82M.
  iMIM/iDPI collateral is registered (tct>0) but UNPRICEABLE now (feeds dead).
  IMPORTANT THROTTLE on value-EXTRACTION today: the large-collateral stablecoin markets (iUSDT/iUSDC/iDAI)
  sit at ~100% utilization (internalCash ≈ 0), so an attacker over-valuing collateral cannot withdraw
  non-existent cash. Borrowable liquidity is concentrated in the FX synth markets (own oracle risk) + small iLINK.
  So Finding 1's over-borrow/extraction is latent (needs a feed to degrade AND borrowable cash); the DoS/brick
  direction (Finding 2) needs no liquidity and is proven live.
  No staleness/deviation guard exists on any consuming path (getPriceFromChainlink ignores updatedAt/answeredInRound).
