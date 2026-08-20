# Iron Bank (ex‑CREAM) — Security Audit

**Target:** Iron Bank lending protocol (Compound‑v2 fork), Ethereum mainnet
**Entry point handed to me:** Comptroller / Unitroller `0xAB1c342C7bf5Ec5F02ADEA1c2270670bCa144CbB`
**Scope of work:** find ways an attacker can take value or seize control they weren't entitled to; resolve, read and recover the full trust graph.
**State snapshot:** chain block timestamp `1787265599` = **2026‑08‑20 22:39 UTC**.
**Verification sources:** Etherscan V2 verified source (Solidity v0.5.17), on‑chain `eth_call` against live state (incl. `from`‑spoofed simulation), `getLogs` for mapping reconstruction, canonical Chainlink FeedRegistry.
**Findings 1–3 were validated by live‑state simulation — see §11 for the PoC results, exposure sizing, and gating proofs. The headline numbers: ~$30.3M collateral single‑sourced by the oracle; ~$2.3M uncollateralized credit‑line debt outstanding; Finding 2's revert‑DoS is proven live (real accounts' `getAccountLiquidity` reverts) but its *current* non‑credit exposure is dust (~$22) — its weight is structural.**

---

## 0. Verdict (read the shelf‑life clause)

I did **not** find an unprivileged, atomic "drain the protocol today" bug. The core is a mature Compound‑v2 fork; its standard money‑market math is unchanged, and the three Iron‑Bank‑specific modifications I audited in depth — **collateral‑cap dual accounting**, **ERC‑3156 flash loans**, and the **per‑market P2P credit line** — each preserve the invariants they touch (traced in §5–§7).

The material risk is concentrated in **one dependency the whole system leans on: the price oracle** (`PriceOracleProxyIB`, flagged in discovery as "the mover"). It is a **single‑source valuation with no staleness, liveness or deviation validation**. This is not hypothetical: **two listed markets (iMIM, iDPI) are already un‑priceable right now** because Chainlink removed their feeds, and `getUnderlyingPrice` reverts. That revert **bricks the account‑liquidity computation** for any account touching those markets, which disables their liquidation — a standing bad‑debt enabler (Finding 1 + its composition in Finding 2).

**This verdict has an expiry date and depends on mutable/external state:**
- It assumes the live Chainlink feeds keep updating. The moment **any single feed freezes or is removed** (the FX feeds carrying the large Fixed‑Forex credit lines are the prime candidates, and MIM/DPI prove Chainlink does exactly this to these assets), the oracle either serves a **stale price → protocol‑wide over‑borrow / bad debt**, or **reverts → market bricked / positions unliquidatable**. There is no code guard against either.
- It assumes the current pause configuration (iMIM/iDPI mint‑paused) holds. Pauses are **admin/guardian storage**, not structure.
- Funds are **not** independently assessed for the three external Fixed‑Forex protocol contracts that hold large uncollateralized credit‑line debt, nor for the `v1PriceOracle`; these are named external trust boundaries (§9).

Severity headline: **1 High** (oracle design; Critical *impact* if a major‑collateral feed degrades, but the trigger is external, not attacker‑controlled, and not live today), **1 Medium** (oracle‑revert → unliquidatable‑position DoS / bad‑debt, live precondition), plus **centralization / divergence** items (unbounded credit‑line power; a multisig‑gated unlimited‑borrow backdoor on the two largest markets) and **1 Low** accounting/solvency note (phantom sUSD cash in a dead market).

---

## 1. Premise check (what the target actually is)

The discovery note was accurate on the headline facts and I confirmed them from chain state, with three refinements worth stating up front because they change where the risk sits:

1. **The oracle address is current.** `Comptroller.oracle()` → `0xbd6f5add9b7a6eb151933cb4efd50be4eca71451` (matches the brief). Its `reg()` is the **canonical** Chainlink FeedRegistry `0x47Fb2585D2C56Fe188D0E6ec628a38b74fCeeeDf`.
2. **There are two implementations, not one.** 22 markets delegate to `0x7e8844ea…2b05`; **iWETH and iWSTETH delegate to `0x2ac63723…1702`**, which has the *same contract name* but **different bytecode** — it carries a hardcoded recovery backdoor (Finding 4). "Weakest deployment governs," and these are the two largest ETH‑denominated markets.
3. **"Single‑source valuation (the mover)" is the whole ballgame, and it is already partially broken.** iMIM and iDPI revert on pricing *now*.

Everything below is anchored to code I fetched or state I queried; where I infer, I say so.

---

## 2. Resolved system (trust graph)

### 2.1 Downstream (what the target leans on)

| Role | Address | Type / notes | Read as |
|---|---|---|---|
| Unitroller (proxy) | `0xAB1c342C…4CbB` | storage/proxy → Comptroller | source (verified) |
| Comptroller (impl) | `0xcb9ab119…d59f` | brains, v0.5.17 | source (verified), `Comptroller.sol` 1380 loc |
| Price oracle | `0xbd6f5add…1451` | `PriceOracleProxyIB` | source (verified), 349 loc — **the mover** |
| → Chainlink FeedRegistry `reg` | `0x47Fb2585…eeDf` | canonical Chainlink | external; behavior probed live |
| → Band `ref` | `0xda7a001b…74c3` | `StdReference` | external; **currently unused by any listed market** (all use Chainlink or wstETH/V1 path) |
| → V1 oracle `v1PriceOracle` | `0x3abce8f1…5cf7` | IB manual oracle | **not decompiled** — only prices deprecated iSUSD whose underlying is defunct (§9) |
| CToken delegate (22 mkts) | `0x7e8844ea…2b05` | `CCollateralCapErc20Delegate` | source (verified) |
| CToken delegate (iWETH,iWSTETH) | `0x2ac63723…1702` | `CCollateralCapErc20Delegate` (**divergent bytecode**) | source (verified); diffed vs the other |
| 24 markets | via `getAllMarkets()` | all `isListed=1`, `version=COLLATERALCAP(1)` | enumerated live |

Per‑market interest‑rate models were not individually decompiled; I bounded them behaviorally (live `borrowRatePerBlock` is ~6.9% of `borrowRateMaxMantissa` on the maxed markets, so no accrual brick — §8 rebuttal).

### 2.2 Upstream (what holds power over the target)

| Power | Holder | Type | What it can do |
|---|---|---|---|
| `admin` | `0x5b12f04e…ac17` | contract | set oracle, list/delist markets, set collateral factors, unpause anything, set credit limits, upgrade implementations |
| `guardian` | `0x9d960dae…30aa` | contract | **pause** mint/borrow/flashloan/transfer/seize (cannot unpause — `_setMintPaused` requires `admin` for `state==false`), disable oracle feeds |
| `creditLimitManager` | `0x8f3ae32d…77d9` | contract (same code as admin) | **grant arbitrary uncollateralized credit** in any market (Finding 3) |
| Oracle `admin`/`guardian` | same as above | contract | set/disable Chainlink aggregators & Band references, mark markets deprecated |
| `IB_MULTISIG` (hardcoded) | `0xA5fC0BbfcD…84Eb` | Gnosis Safe proxy (172 b) | `borrowOnEvilSpellBehalf` on iWETH/iWSTETH — **unlimited uncollateralized borrow** (Finding 4) |

Credit‑account holders (external protocols trusted to borrow without collateral) are enumerated in §4.3.

Map + recovered artifacts live under `audit/src/` (source), `audit/data/` (live state JSON), `audit/keccak.py` (selector/topic derivation).

---

## 3. What the system must keep true (invariants)

Written before hunting, to have something to test against:

- **I1 (backing):** every unit of internal accounting (`accountTokens`, `accountBorrows`) is backed by real underlying held or owed. Cash is tracked as `internalCash`, not `balanceOf` — donations cannot inflate the exchange rate.
- **I2 (collateralization):** for any non‑credit account, `Σ collateralValue·CF ≥ Σ borrowValue`; borrows exceeding this are impossible except through the sanctioned credit‑line path.
- **I3 (collateral‑cap consistency):** for every account, `accountTokens ≥ accountCollateralTokens`, and `Σ accountCollateralTokens = totalCollateralTokens ≤ collateralCap` (when cap ≠ 0). Liquidity counts *collateral* tokens; redemption operates on *total* tokens; the buffer is freely movable.
- **I4 (pricing correctness):** `getUnderlyingPrice` returns a fresh, correct USD‑mantissa price for every listed market, or the dependent operation fails safe.
- **I5 (credit line):** an account may borrow uncollateralized **only** up to `_creditLimits[account][market]`, set **only** by admin/creditLimitManager.
- **I6 (liquidation liveness):** an undercollateralized non‑credit borrower is always liquidatable.

The oracle findings are a direct break of **I4**, and (by composition) of **I6**.

---

## 4. Live state that the code can't show

### 4.1 Global config
`closeFactor=0.5`, `liquidationIncentive=1.08`, `collateralFactorMax=0.9`, `flashFeeBips=3` (0.03%), `liquidityMining=0x0` (LM inactive), `transfer/seize` not paused, `borrowCapGuardian=0`, `supplyCapGuardian=0`.

### 4.2 Per‑market pricing source & collateral role (audit/data/oracle_map.json)

| Market | Underlying | Oracle source | CF | Priceable now? |
|---|---|---|---|---|
| iWETH,iWSTETH | WETH, wstETH | CL ETH/USD; **wstETH = stETH/USD × stEthPerToken** | .85/.70 | yes |
| iDAI,iUSDC,iUSDT | DAI/USDC/USDT | CL x/USD | .90 | yes |
| iWBTC | WBTC | CL WBTC/BTC × BTC/USD | .80 | yes |
| iLINK,iYFI,iSNX,iAAVE,iCRV,iCVX,iUNI,iSUSHI | majors | CL x/USD (SUSHI via /ETH) | .5–.7 | yes |
| **iMIM** | MIM | CL MIM/USD | .90 | **NO — reverts "Feed not found"** |
| **iDPI** | DPI | CL DPI/USD | .55 | **NO — reverts "Feed not found"** |
| iGBP,iEUR,iAUD,iJPY,iKRW,iCHF | ib* synths | CL FX/USD (ISO‑code base) | **0** (borrow‑only) | yes (feeds fresh) |
| EURS | STASIS EUR | **CL EUR/USD** (no EURS feed) | .60 | yes |
| iSUSD | sUSD | **V1/deprecated** oracle | .50 | yes (but underlying defunct) |

Feed staleness at snapshot: all live feeds < 26 h old (audit/data/feed_staleness.json). **iMIM and iDPI Chainlink feeds are removed** (registry reverts).

### 4.3 Credit accounts (reconstructed from 191 `CreditLimitChanged` events — audit/data/credit_limits.json)

Current nonzero `_creditLimits[protocol][market]`:
- **Large lines, FX synthetic markets only** (by design — these mint the ib* Fixed‑Forex synths): `0x6b419752…c576`, `0x0a0b0632…fd90`, `0x8338aa89…bbef` across iKRW/iJPY/iEUR/iGBP/iAUD/iCHF (e.g. iKRW limit ≈ 6.55e29, iJPY ≈ 2e26).
- `0xba5ebaf3…e54b` (recovery/backstop): tiny real limits on iYFI/iSUSD + `limit=1` markers on the majors.
- Numerous `limit=1` "marker" accounts (make an address a credit account — blocking mint/redeem/liquidate — without meaningful borrow capacity).
- **No large credit line exists on any major market** (iWETH/iDAI/iUSDC/iUSDT/iWBTC): only `limit=1` markers. This bounds the credit‑line drain surface to the FX synthetics + the trust in the three Fixed‑Forex contracts.

### 4.4 Solvency reconciliation (audit/data/solvency2.json)
`internalCash == underlying.balanceOf(cToken)` for **every** market **except iSUSD** (Finding 5). Most majors sit at **~100% utilization** (`internalCash ≈ 0`): iWETH, iDAI, iUSDC, iUSDT, iYFI, iSNX, iWBTC, iSUSHI, iEUR, iAAVE, iCRV, iCVX, iUNI, iWSTETH. **Consequence:** suppliers in those markets currently cannot withdraw (no free cash) — a liquidity/market‑state fact, not itself a code bug, but it is the "semi‑abandoned" backdrop and it means most nominal TVL is *already drawn*, not sitting exposed to a fresh exploit.

---

## 5. Findings

### Finding 1 — Oracle performs single‑source valuation with no staleness/liveness/deviation validation (HIGH; Critical‑impact if a major‑collateral feed degrades)

**Code:** `audit/src/oracle_PriceOracleProxyIB/contracts__PriceOracle__PriceOracleProxyIB.sol`

```solidity
function getPriceFromChainlink(address base, address quote) internal view returns (uint256) {
    (, int256 price, , , ) = reg.latestRoundData(base, quote);
    require(price > 0, "invalid price");                       // <-- ONLY check
    return mul_(uint256(price), 10**(18 - uint256(reg.decimals(base, quote))));
}
function getPriceFromBAND(string memory symbol) internal view returns (uint256) {
    StdReferenceInterface.ReferenceData memory data = ref.getReferenceData(symbol, QUOTE_SYMBOL);
    require(data.rate > 0, "invalid price");                   // <-- ONLY check
    return data.rate;
}
```

`latestRoundData` returns `(roundId, answer, startedAt, updatedAt, answeredInRound)`. The code consumes `answer` and **discards `updatedAt` and `answeredInRound`**; Band's `lastUpdatedBase/Quote` are likewise discarded. There is **one source per asset** — no median, no second feed, no sanity band. `getUnderlyingPrice` (same file) selects exactly one branch (Chainlink → Band → V1) and returns it directly into the comptroller's collateralization math (`getHypotheticalAccountLiquidityInternal`, `liquidateCalculateSeizeTokens`).

**Invariant broken:** I4 (pricing correctness/freshness).

**Two failure modes, both un‑guarded:**

- **1a — silent staleness → over‑borrow / bad debt.** If a feed's aggregator freezes (stops updating but is not removed), `latestRoundData` keeps returning the last value with `price>0`. The protocol keeps valuing that asset at the stale price. If it is **collateral that has really fallen**, borrowers stay "healthy" against phantom value and can borrow up to the stale valuation → the debt becomes unbacked. **Value at risk = all debt collateralized by that asset** (for majors like WETH/WBTC that is the bulk of the book → Critical impact). If it is a **borrowable asset that has really risen**, its stale‑low valuation undercounts new debt → over‑borrow. No line bounds staleness, so tolerance is effectively infinite.

- **1b — feed removal → revert → market bricked (LIVE).** When Chainlink *deprecates* a feed it is removed from the registry and `latestRoundData` **reverts "Feed not found."** This is the case **right now for MIM/USD and DPI/USD**, so `getUnderlyingPrice(iMIM)` and `(iDPI)` revert (reproduced live). A reverting price does not fail safe — it propagates (see Finding 2).

**Reproduction (live):** `reg.latestRoundData(0x99d8…MIM, 0x…0348 USD)` → revert `Feed not found`; `oracle.getUnderlyingPrice(iMIM)` → revert. Same for DPI. All other configured feeds return fresh values (< 26 h).

**Why existing protections don't stop it:** none exist. `require(price>0)` catches a zeroed answer, not a stale or removed one. The `guardian` can *disable* an aggregator, but that is a manual, reactive control and switches the asset to "no price" (revert) — it does not add freshness validation.

**Attacker / cost:** the *trigger* (a Chainlink feed freezing or being removed) is **not attacker‑controlled** — this is why I rate it High rather than Critical and separate severity from exploitability. But it is a *when‑not‑if* event for these asset classes (MIM and DPI already happened; Chainlink has an established pattern of sunsetting FX and small‑cap feeds), and the code offers zero defense. Once triggered, realizing the loss is an ordinary borrow/withdraw — in scope (a code flaw cashed out through a normal action).

**Severity/confidence:** Severity **High** (impact up to Critical — protocol‑wide bad debt if a major collateral feed goes stale‑high). Confidence that the flaw is real: **certain** (plain code reading + live reverts). Confidence it is exploitable *at will today*: **low** (feeds currently fresh).

**Minimal fix:** in `getPriceFromChainlink`, read the full tuple and enforce `require(updatedAt != 0 && block.timestamp - updatedAt <= heartbeat[base][quote], "stale")` and `require(answeredInRound >= roundId)`; add a per‑feed max‑deviation / second‑source sanity check; and make a removed feed (revert) degrade to a safe, liquidation‑preserving fallback rather than bricking (see Finding 2 fix). For Band, enforce `data.lastUpdatedBase/Quote` freshness.

**Falsified if:** you can show a freshness/second‑source check somewhere on the consuming path in the comptroller (there is none — `getHypotheticalAccountLiquidityInternal` only does `require(oraclePriceMantissa > 0)` after the call).

---

### Finding 2 — A reverting oracle for one listed market bricks the whole‑account liquidity computation → borrowers holding it become unliquidatable (MEDIUM structural; **proven live but current realized exposure ≈ $22** — see §11)

> **Validation correction (§11):** the mechanism is confirmed on‑chain — three real accounts' `getAccountLiquidity` reverts "Feed not found" today, un‑gated. **But the only *non‑credit* accounts poisoned right now are two dust iMIM borrowers (~$8 and ~$14 collateral).** The one large poisoned account, `0xba5ebaf…` ($792k debt), is a **credit account** (`limit=1` markers on every major it borrows) and is therefore **already unliquidatable as a credit account regardless of iDPI** — its exposure belongs to Finding 3, not here. So Finding 2's live value‑at‑risk is ~$22; its severity is **structural** (it recurs at full size the moment any *un‑paused* market's feed is removed).

**Code:** `audit/src/comptroller_impl_Comptroller/contracts__Comptroller.sol`, `getHypotheticalAccountLiquidityInternal`:

```solidity
CToken[] memory assets = accountAssets[account];
for (uint256 i = 0; i < assets.length; i++) {
    CToken asset = assets[i];
    if (!isMarketListedOrSoftDelisted(address(asset))) continue;
    (oErr, vars.cTokenBalance, vars.borrowBalance, vars.exchangeRateMantissa) = asset.getAccountSnapshot(account);
    if (vars.cTokenBalance == 0 && vars.borrowBalance == 0 && asset != cTokenModify) continue;  // only skip if zero balance
    ...
    vars.oraclePriceMantissa = oracle.getUnderlyingPrice(asset);   // <-- REVERTS for iMIM/iDPI; whole call reverts
    require(vars.oraclePriceMantissa > 0, "price error");
    ...
}
```

The loop calls `oracle.getUnderlyingPrice(asset)` **unconditionally** for every entered asset with a nonzero balance. If **one** such asset reverts (Finding 1b), the entire function reverts. This function backs `getAccountLiquidity`, `redeemAllowedInternal`, `borrowAllowed`, and — critically — `liquidateBorrowAllowed`:

```solidity
function liquidateBorrowAllowed(...) external returns (uint256) {
    ...
    (Error err, , uint256 shortfall) = getAccountLiquidityInternal(borrower);  // reverts if borrower holds iMIM/iDPI
    require(err == Error.NO_ERROR, "failed to get account liquidity");
    ...
}
```

**Invariant broken:** I6 (liquidation liveness).

**Impact / exploit shape:** any account that has **entered** iMIM or iDPI (or any future feed‑dead market) and holds a nonzero balance there becomes **impossible to liquidate in every market**, because every liquidation path first computes its whole‑account liquidity, which reverts. The account can ride an underwater position on *other* collateral to default; the loss lands on suppliers as bad debt. Framed as an attack:

1. Attacker supplies real collateral (e.g. WETH) in a healthy market and borrows near the limit.
2. Attacker enters the poison market and holds a nonzero balance there.
3. Attacker's collateral later falls below the debt. Liquidators call `liquidateBorrow` → `liquidateBorrowAllowed` → `getAccountLiquidityInternal` → **revert**. The attacker keeps the borrowed funds; suppliers eat the shortfall.

This is value transfer from suppliers to the defaulting borrower (in scope — a code flaw, cashed out by an ordinary default), disproportionate to and independent of the attacker's stake.

**Why it is Medium, not High, *today* (and the shelf‑life):**
- The two live poison markets (iMIM, iDPI) have **mint paused** (`mintGuardianPaused=1`), so an attacker **cannot freshly mint** to self‑poison. They would have to source existing iMIM/iDPI cTokens (supply ≈ 616 MIM / a few $k DPI) from a current holder via transfer (transfers are not paused) — non‑trivial and small.
- **But this is exactly the "a current configuration value is not a guard" trap.** The mint‑pause is **admin‑mutable** (`_setMintPaused(...,false)` requires `admin`). And the precondition regenerates for free the instant **any un‑paused market's feed dies** — the FX markets (iEUR/iGBP/iJPY/iKRW/iAUD/iCHF), which are **not** mint‑paused and carry the **large Fixed‑Forex credit lines**, are the most likely next casualties (single FX feeds are what Chainlink sunsets). If, say, iEUR's feed is removed, every account holding iEUR is instantly unliquidatable, with no attacker action required to create the condition.
- Accounts **already** holding iMIM/iDPI are unliquidatable now; live exposure is bounded by those markets' small size.

**Minimal fix:** in the liquidity loop, treat a reverting/zero price defensively — e.g. `try`/staleness‑aware fetch that, on failure, **excludes the asset from collateral but still counts its borrows** (fail‑safe toward liquidation), or hard‑delist a feed‑dead market so `isMarketListedOrSoftDelisted` returns false and the loop `continue`s past it. (Note a hard‑delist today would un‑brick iMIM/iDPI holders — a concrete operational mitigation.)

**Falsified if:** a cited guard makes the poison market skippable (it is not — `isMarketListedOrSoftDelisted(iMIM)=true` since `isListed=1`, so the `continue` is not taken, and the balance is nonzero for a holder).

---

### Finding 3 — P2P credit line: unbounded uncollateralized borrow power (CENTRALIZATION / design; code is sound; composes with Finding 1)

**Code:** `Comptroller.sol` `borrowAllowed` (credit branch) + `_setCreditLimit`:

```solidity
uint256 creditLimit = _creditLimits[borrower][cToken];
if (creditLimit > 0) {
    (uint256 oErr, , uint256 borrowBalance, ) = CToken(cToken).getAccountSnapshot(borrower);
    require(creditLimit >= add_(borrowBalance, borrowAmount), "insufficient credit limit");  // NO collateral check
} else { /* normal liquidity check */ }
```
```solidity
function _setCreditLimit(address protocol, address market, uint256 creditLimit) external {
    require(msg.sender == admin || msg.sender == creditLimitManager, "admin or credit limit manager only");
    _setCreditLimitInternal(protocol, market, creditLimit);
}
```

**Assessment:** the divergence itself is **implemented correctly** and self‑consistent — I traced that credit accounts cannot mint/redeem/be‑transferred‑to/be‑liquidated/be‑seized‑from (`mintAllowed`, `redeemAllowedInternal`, `transferAllowed`, `liquidateBorrowAllowed`, `seizeAllowed` all gate on `isCreditAccount`), that a credit account's uncollateralized debt is still fully counted against it in any *other* market's liquidity check, and that no unprivileged actor can self‑grant a limit (I5 holds). So there is **no code bug** here for an outside attacker.

**Why it is still reportable (per the "bound every privileged input" rule):** `creditLimitManager` (`0x8f3ae32d…`, same code as `admin`) can set **any** limit on **any** market with **no cap, rate limit, or collateral** — i.e. it can authorize an **unbounded uncollateralized withdrawal** of any market's cash. Today the large lines are confined to FX synthetics held by the three Fixed‑Forex contracts (`0x6b41…`, `0x0a0b…`, `0x8338…`), and **the majors carry only `limit=1` markers** — so the standing drain surface is bounded to those synthetics + trust in Fixed‑Forex. That is a snapshot, not a structural guarantee: one `_setCreditLimit(evil, iUSDC, huge)` call reopens it. The three Fixed‑Forex contracts' own solvency (which backs the FX credit debt) is **not assessed here** (§9).

**Composition with Finding 1:** the credit lines live in exactly the FX markets whose single Chainlink FX feeds are the likeliest to be sunset. A dead FX feed both bricks that market (Finding 2) *and* strands a large uncollateralized position — the two shapes reinforce.

**Fix (defense‑in‑depth):** add a global/ per‑market cap and timelock on credit‑limit increases; monitor Fixed‑Forex solvency off‑chain.

---

### Finding 4 — iWETH/iWSTETH implementation carries a hardcoded, multisig‑gated unlimited‑borrow backdoor (CENTRALIZATION / divergence; not unprivileged; weakest‑deployment)

**Code:** `audit/src/impl2_wrappednative_CCollateralCapErc20Delegate/contracts__CCollateralCapErc20.sol` (delegate `0x2ac63723…1702`, used **only** by iWETH and iWSTETH):

```solidity
function borrowOnEvilSpellBehalf(uint256 borrowAmount, bool isNative) external nonReentrant returns (uint256) {
    address EVIL_SPELL  = 0x560A8E3B79d23b0A525E15C6F3486c6A293DDAd2;
    address IB_MULTISIG = 0xA5fC0BbfcD05827ed582869b7254b6f141BA84Eb;
    require(msg.sender == IB_MULTISIG, "!admin");
    accrueInterest();
    return borrowFreshUnchecked(msg.sender, address(uint160(EVIL_SPELL)), borrowAmount, isNative);
}
```
`borrowFreshUnchecked` (CToken.sol) **skips `comptroller.borrowAllowed`** — no collateral, credit, cap, or price check — assigns the debt to `EVIL_SPELL` and sends the underlying to the caller (`IB_MULTISIG`). This is a **post‑incident recovery lever** (the "Cream lineage incident history" — the Alpha Homora / Spell episode; `EVIL_SPELL` is a 40 KB contract, `IB_MULTISIG` a Safe proxy).

**Assessment:** I verified the **only** unchecked entry is this function and it is gated to the hardcoded multisig — the normal `borrowFresh` still enforces `borrowAllowed` (so ordinary borrows on iWETH/iWSTETH are safe), and no unprivileged path reaches `borrowFreshUnchecked`. So this is **not an unprivileged attack**. It is, however, a **standing, unbounded power** for `IB_MULTISIG` to borrow **all available cash** out of the two largest markets without collateral, invisible to anyone who reads only the other 22 markets' bytecode. Reported per the "name what can drain the target, and bound privileged inputs" obligations. The rest of impl2's divergence (a `getCollateralTokens` refactor, seize/redeem restructuring) I diffed line‑by‑line and confirmed **behavior‑preserving**.

**Fix:** if recovery is complete, upgrade iWETH/iWSTETH back to the standard delegate to remove the lever; otherwise document it and confirm the multisig's signer policy.

---

### Finding 5 — iSUSD reports phantom cash against a defunct underlying (LOW / accounting; not extractable)

`iSUSD.internalCash()` = 4,048.35 sUSD, but `sUSD.balanceOf(iSUSD)` = **0** and `sUSD.totalSupply()` = **0** — the sUSD token at `0x57ab1ec2…5f51` is fully migrated/defunct. The market's accounting claims cash that isn't there. **Not exploitable for gain** (a redeem of the "cash" portion calls `doTransferOut` of sUSD, which reverts on a zero balance), but it means iSUSD cToken holders hold overvalued, unredeemable claims. It is a deprecated, V1‑priced, wind‑down market. **Fix:** hard‑delist iSUSD and socialize/write off the residue.

---

## 6. Entry‑point ledger (every externally reachable path, and why it's safe or not)

**Comptroller (Unitroller):**
- `enterMarkets/exitMarket` — register/unregister collateral + membership; exit blocked if it would create shortfall (`redeemAllowedInternal`). Safe (but shares the Finding‑2 revert on a poison asset).
- `mintAllowed/redeemAllowed/borrowAllowed/repayBorrowAllowed/liquidateBorrowAllowed/seizeAllowed/transferAllowed/flashloanAllowed` — hooks; caller‑gated where needed (`borrowAllowed` self‑enroll requires `msg.sender==cToken`). `borrowAllowed`/`redeemAllowed`/`liquidateBorrowAllowed` inherit Finding 2.
- admin/guardian/creditLimitManager setters — access‑controlled (§2.2); `_setCreditLimit` is Finding 3.
- views (`getAccountLiquidity`, `creditLimits`, `getAllMarkets`, …) — read‑only; liquidity views inherit Finding 2 revert.

**CToken (both delegates):**
- `mint/redeem/redeemUnderlying/borrow/repayBorrow/repayBorrowBehalf/liquidateBorrow` — `nonReentrant` + `accrueInterest` + comptroller hook. Standard.
- `transfer/transferFrom/approve/seize` — `seize` restricted to a cToken `msg.sender` via `seizeInternal`; collateral‑cap accounting preserves I3.
- `flashLoan` — `nonReentrant`; requires exact `cashOnChainAfter == cashOnChainBefore + fee`; **preserves exchange rate during the callback** (it debits `internalCash` and credits `totalBorrows` by the same `amount`, so `cash+borrows` is invariant) → no read‑only‑reentrancy on `exchangeRateStored`. Safe.
- `gulp` — `nonReentrant`; moves `balanceOf − internalCash` **to reserves** (protocol), not to suppliers → neutralizes donation/first‑depositor inflation. Safe.
- `registerCollateral/unregisterCollateral` — `msg.sender == comptroller` only.
- `_becomeImplementation/_resignImplementation/_set*` admin — gated.
- `borrowOnEvilSpellBehalf` (impl2 only) — `IB_MULTISIG` only (Finding 4).

**Oracle:** `getUnderlyingPrice` (view; Findings 1–2); `_set*/_disable*/_enable*/_updateDeprecatedMarkets` — admin/guardian only.

No unprivileged fund‑moving path with a missing or defeatable guard was found beyond the oracle‑driven ones.

---

## 7. Dependency / composition map (what reads state another actor writes)

- **exchangeRate** reads `internalCash`, `totalBorrows`, `totalReserves`. Writers: mint/redeem/borrow/repay/accrueInterest/flashLoan/gulp. Checked: donation via direct transfer → absorbed by `gulp` to reserves (no supplier gain); flashLoan preserves `cash+borrows` (no mid‑callback manipulation). **No exploit.**
- **liquidity** reads `oracle.getUnderlyingPrice`, `collateralFactor`, `accountCollateralTokens`, `accountBorrows`. Writer of price = external feed. → **Findings 1–2**.
- **collateral accounting** (`accountTokens` vs `accountCollateralTokens` vs `totalCollateralTokens`): traced through mint/redeem/seize/transfer/register/unregister; `accountTokens ≥ accountCollateralTokens` and the `totalCollateralTokens ≤ collateralCap` bound hold on every path (I3). `balanceOf`/`getAccountSnapshot` deliberately return the *collateral* balance (used for seize limits & liquidity), while redemption uses *total* tokens — internally consistent, not a bug.
- **credit path** vs normal liquidity: a credit account's uncollateralized debt is counted against it everywhere except its own credit market; cannot be laundered into free collateral. **No exploit** (I5).
- **splitting / rounding:** money‑market math is standard Compound `Exponential` truncation; no split‑to‑profit path (mint/redeem/borrow/repay are linear in amount; liquidation seize uses a single `div_`; flash fee is `amount·3/10000` floored — sub‑3334 wei loans pay zero fee but that is a loss to the *lender protocol* bounded to dust, not a drain of principal).
- **degenerate states:** no market at `totalSupply==0` (inflation attack N/A); `internalCash≈0` (100% util) already noted (§4.4).

---

## 8. Rebuttal register (candidates killed, with the citation)

- **First‑depositor / donation exchange‑rate inflation** — killed: cash is `internalCash` (tracked), not `balanceOf`; donations routed to reserves by `gulp` (`CCollateralCapErc20.sol` `gulp`, `getCashPrior`). No live `totalSupply==0` market.
- **Flash‑loan read‑only reentrancy on exchange rate** — killed: `flashLoan` debits `internalCash` and credits `totalBorrows` by the same `amount` before the callback, leaving `cash+borrows−reserves` invariant; `nonReentrant` on all same‑contract paths.
- **Fee‑on‑transfer / non‑standard underlying breaking flashLoan accounting** — killed: exact‑repayment `require(cashOnChainAfter == cashOnChainBefore + totalFee)` reverts rather than mis‑accounts.
- **Interest‑accrual brick at 100% utilization** — killed: live `borrowRatePerBlock` ≈ 6.9% of `borrowRateMaxMantissa` on the maxed markets; margin is large.
- **Credit account self‑grant / liquidity laundering** — killed: `_setCreditLimit` is admin/creditLimitManager‑gated; credit debt is counted in cross‑market liquidity (`getHypotheticalAccountLiquidityInternal`).
- **impl2 seize/redeem refactor introducing an accounting error on iWETH/iWSTETH** — killed: line‑by‑line diff shows `getCollateralTokens` extraction is behavior‑preserving; the removed `if(seizeTokens==0) return` only drops a no‑op short‑circuit.
- **`borrowOnEvilSpellBehalf` reachable by non‑multisig** — killed: `require(msg.sender == IB_MULTISIG)`; normal `borrowFresh` retains `borrowAllowed`.
- **balanceOf returning collateral (not total) tokens enabling under/over‑seize** — killed: liquidation seizes ≤ `balanceOf`(=collateral) and `seizeInternal` decrements `accountTokens` by `seizeTokens` while decrementing collateral only by the collateral portion, preserving I3.

**Cross‑product check (rejected × rejected):** the only pairing that composes into something larger is **Finding 1 (feed death) × Finding 3 (large FX credit line)** on the FX markets — reported as the composition inside Findings 2 and 3 rather than as separate mediums.

---

## 9. What I could not read / assumed (and how it cuts)

- **`v1PriceOracle` `0x3abce8f1…5cf7` — not decompiled.** It is a manually‑maintained IB oracle in the value path only for deprecated markets; the sole listed consumer is iSUSD, whose underlying `sUSD.totalSupply()==0` (defunct). Impact of it being wrong: bounded to the dead iSUSD market. Low.
- **Band `ref` `0xda7a…74c3`** — present as a fallback but **no listed market currently routes to it** (all use Chainlink / wstETH / V1). If a future `_setReferences` points a market at Band, the same missing‑staleness flaw (Finding 1) applies to `data.lastUpdatedBase/Quote`.
- **Three Fixed‑Forex protocol contracts (`0x6b41…`, `0x0a0b…`, `0x8338…`)** hold the large uncollateralized FX credit debt. Their **own** solvency/logic is an **external trust boundary I did not audit** — if one is insolvent or exploitable, the FX‑market suppliers bear it. Named, not assessed.
- **Per‑market interest‑rate models** — bounded behaviorally (no brick), not individually decompiled.
- **Off‑chain / operational trust:** the `admin`/`guardian`/`creditLimitManager` and `IB_MULTISIG` multisigs decide oracle wiring, listings, pauses, credit grants, and the iWETH/iWSTETH recovery lever. A clean on‑chain result **does not** imply the system is safe against these role‑holders; their key management is out of chain view. What each controls and the blast radius is in §2.2 and Findings 3–4.

**If my assumption that the live Chainlink feeds keep updating is wrong, Findings 1–2 move from latent to active**, and the verdict's severity rises accordingly.

---

## 10. Reproduction pointers

- Resolved source: `audit/src/*` (comptroller, oracle, both delegates, unitroller).
- Live state: `audit/data/oracle_map.json` (source per asset), `audit/data/feed_staleness.json` (updatedAt/age), `audit/data/credit_limits.json` (191 events reconstructed), `audit/data/solvency2.json` (internalCash vs on‑chain), `audit/data/SUMMARY.md`.
- Selector/topic derivation: `audit/keccak.py` (validated against known vectors).
- Key live reverts: `oracle.getUnderlyingPrice(iMIM)` / `(iDPI)` → `execution reverted: Feed not found`; `reg.latestRoundData(MIM,USD)` → same.

---

## 11. Validation / PoC (live‑state simulation, un‑exaggerated sizing)

I validated Findings 1–3 against **live mainnet state** via `eth_call` (including `from`‑spoofed calls, which the Etherscan V2 proxy honours) at the snapshot block. No local fork was needed — real accounts and real balances are stronger evidence than a synthetic fork. Raw results: `audit/data/VALIDATION.md`, `audit/data/credit_debt_usd.json`, `audit/data/poison_accounts.json`.

### 11.1 Finding 2 — proven live, un‑gated; but current exposure is dust
`comptroller.getAccountLiquidity(account)` on **real** accounts entered into the dead‑feed markets:

| account | market | result |
|---|---|---|
| `0x6e868846…58e4` | iMIM borrower | **REVERT `execution reverted: Feed not found`** |
| `0xdeb9553e…1574` | iMIM borrower | **REVERT `Feed not found`** |
| `0xba5ebaf3…e54b` | iDPI borrower | **REVERT `Feed not found`** |
| `0x6b41…c576` (control, not in dead mkts) | — | `err=0, shortfall=224,520` (succeeds) |
| random EOA (control) | — | `err=0, 0, 0` (succeeds) |

So the revert is real and nothing catches it — liquidation of these accounts is impossible (`liquidateBorrowAllowed → getAccountLiquidityInternal → revert`). **Sizing the honest way** (reconstructing each poisoned account across all 24 markets, since the protocol's own liquidity call can't): the two iMIM borrowers hold **$8 and $14** of collateral (dust). The third, `0xba5ebaf…`, carries **$792k** of debt with **$0** collateral — but it is a **credit account** on every major it borrows, so it is *already* exempt from liquidation (`liquidateBorrowAllowed` requires `!isCreditAccount`) independent of the iDPI poison; that debt is Finding‑3 credit exposure. **Finding 2's live value‑at‑risk ≈ $22.** Its severity is structural, not current: iMIM/iDPI are mint‑paused and tiny, but the identical condition regenerates at full scale the instant Chainlink removes any *un‑paused* market's feed (the FX markets are the likely next, and they hold the credit lines).

### 11.2 Finding 3 — sized, and gating confirmed by simulation
Total **uncollateralized credit‑line debt outstanding ≈ $2.30M** (from real `getAccountSnapshot` borrow balances × oracle price):

| borrower | markets | debt |
|---|---|---|
| Fixed‑Forex `0x8338…`, `0x0a0b…`, `0x6b41…` | iEUR/iCHF/iKRW/iAUD/iGBP/iJPY (synths) | ≈ **$1.51M** (iEUR $745k, iCHF $276k, iKRW $221k, iAUD $208k, iGBP $34k, iJPY $26k) |
| backstop `0xba5ebaf…` | WETH/USDC/DAI/USDT/WBTC | ≈ **$792k**, $0 collateral |

Gating simulated live (from‑spoofed):
- `borrowAllowed(iEUR, FixedForex, 1000e18)` → **returns 0 (ALLOWED)** although the borrower has **$0 collateral** → the credit branch skips the liquidity check exactly as read. **Confirmed.**
- `_setCreditLimit(attacker, iUSDC, 1e30)` **from `creditLimitManager`** → **succeeds** (unbounded grant); **from a random address** → **REVERT `admin or credit limit manager only`**. → The power is real and unbounded, but **role‑gated** (not an unprivileged bug), matching the report.
- Additional live bound: `borrowAllowed` enforces `borrowCap` *before* the credit branch (a 1e30 borrow reverts `market borrow cap reached`), so per‑market credit borrows are also capped by the (admin/guardian‑mutable) `borrowCaps`.

### 11.3 Finding 1 — sized, with an honest throttle on *extraction*
Total collateral valued by the single‑source oracle (from `totalCollateralTokens × exchangeRate × price`): **≈ $30.3M** (borrowing power ≈ $27.3M), dominated by **USDT/USD $20.4M** ($18.3M power), **DAI/USD $9.0M** ($8.1M), **USDC/USD $0.82M** — each priced by exactly one Chainlink feed with **no `updatedAt`/`answeredInRound`/deviation check** on any consuming path. That is the notional exposed to a single feed going stale or wrong.

**Un‑exaggeration caveat on the *extraction* direction:** the large‑collateral stablecoin markets (iUSDT/iUSDC/iDAI) sit at **~100% utilization (`internalCash ≈ 0`)**, so an attacker who *over‑values* collateral via a stale feed still **cannot withdraw cash that isn't there**. Borrowable liquidity today is concentrated in the FX synth markets (~$3.5M equiv, themselves oracle‑exposed) and ~$59k of iLINK. So Finding 1's over‑borrow/bad‑debt path is **latent** — it needs *both* a feed to degrade *and* borrowable liquidity — whereas the **DoS/brick direction (Finding 2) needs no liquidity and is already live**. This is why I rate Finding 1 High on *structure/notional* while stating plainly that at‑will extraction today is throttled by the drained markets (itself a mutable condition — suppliers can re‑add liquidity at any time).

### 11.4 Net effect of validation on the verdict
Nothing was found to *gate* the mechanisms (no try/catch on the oracle revert; the credit path genuinely skips collateral; the manager grant is unbounded). The corrections are to **sizing/immediacy**, and they cut toward *less* immediate impact than a naive reading of the findings would suggest: Finding 2's live exposure is ~$22 (structural risk remains), and Finding 1's extraction is throttled by empty markets (structural/notional exposure of ~$30M remains). Finding 3's ~$2.3M is real, deliberate, and role‑gated. The verdict in §0 stands, now quantified.
