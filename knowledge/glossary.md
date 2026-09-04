# Glossary

Plain-English definitions of terms used in plan reports and conversations. No balances
here (those live in snapshots/). Agents: keep entries short; add terms when a report
uses something not listed.

## Reading the results tables

- **Success %** — Of the simulated market histories (2,000 in Monte Carlo), the share
  where the plan never runs out of money before the horizon ends. "Failure" means the
  portfolio hits zero — Social Security keeps paying and the house is still there, so
  it's a forced lifestyle drop, not destitution.
- **Median terminal (real)** — The estate left at the end of the horizon in the
  middle-of-the-road outcome, in today's purchasing power. Half of outcomes end richer,
  half poorer. It's buffer + legacy, not spending.
- **p10 terminal (real)** — The 10th-percentile ending estate: a genuinely unlucky
  market draw. The "floor under bad luck." Watch this alongside success %.
- **Median lifetime tax** — Total tax paid across the whole simulation in the median
  path. Levers like Roth ladders move this number more than they move success %.
- **Median first failure year** — Among only the failing paths, the median year the
  money runs out. Tells you *when* trouble bites, not how often.
- **Real vs nominal dollars** — Real = today's purchasing power (inflation stripped
  out); nominal = the sticker price in that future year. All results are reported real.
  Spending inputs are real (they auto-grow with inflation); a fixed mortgage payment is
  nominal (inflation shrinks it in real terms).

## Simulation modes

- **Deterministic (det)** — One path with fixed average returns. Good for reading the
  year-by-year ledger; useless for risk.
- **Monte Carlo (mc)** — 2,000 randomized market histories with volatile, correlated
  returns and inflation. Source of the success % numbers. Deliberately stingier than
  history (5% real stocks vs ~6.5% historical).
- **Historical (hist)** — Replays every actual rolling window since 1871 (Depression,
  stagflation included). Reality check on the Monte Carlo.
- **Sequence risk** — Bad returns early in retirement hurt far more than the same
  returns later, because withdrawals lock in the losses. The main reason retire-early
  scenarios fail; the main thing guardrails defend against.

## Plan machinery

- **Base plan / overlay** — `scenarios/base.yaml` is the plan of record; overlays are
  small "what-if" files stacked on top (retire at 55, house move, etc.). Nothing is
  adopted until it's merged into base and logged in decisions.md.
- **Snapshot** — Dated file of actual account balances (`snapshots/`). The plan always
  runs from the newest one.
- **Horizon / plan-to age** — The age the money must last to. Default is 95 (longevity
  insurance); planning to a shorter horizon frees up spending but accepts the risk of
  living past it.
- **Spending taper ("retirement smile")** — Flexible spending stepping down with age
  (full to 75, reduced 75–84, minimal 85+) instead of flat-forever. Matches observed
  retiree behavior; placeholder amounts pending calibration.
- **Guardrail** — Pre-agreed rule: after a negative market year in retirement, cut
  discretionary spending 50% for that year. Turns panic into policy; worth real
  success-% points.
- **Discretionary** — Expense streams flagged as cuttable (restaurants, travel, vehicle
  fund). Guardrails only cut these.
- **Withdrawal order** — Which pot pays for retirement first: cash → taxable →
  traditional → Roth → HSA. Roth and HSA go last because tax-free compounding is most
  valuable given the longest runway.

## Income & business

- **K-1 / pass-through income** — An S-corp owner is taxed on their share of company
  *profit* (K-1 box 1), not on the cash actually received.
- **Phantom income** — The taxed-but-not-received slice of K-1 profit (profit share
  minus cash distributions). Costs tax today; builds S-corp basis.
- **S-corp basis** — Cumulative invested-plus-retained value in the company; reduces
  capital-gain tax if the stake is ever sold.
- **QBI (§199A)** — Deduction of up to 20% of pass-through business income, subject to
  wage/income caps. Currently expires after 2025 tax year rules unless extended;
  modeled per the parameter files.
- **PIA / FRA** — Social Security's Primary Insurance Amount: the monthly benefit at
  Full Retirement Age (67). Claiming early cuts it; each year of delay past FRA adds 8%
  (to 70). SSA estimates assume earnings continue until claiming — retiring
  early shaves the real figure.

## Tax strategies

- **Roth conversion ladder** — In low-income years (retired, pre-RMD), deliberately
  move money from traditional IRA/401k to Roth, paying tax now at low brackets to avoid
  higher brackets later. Moves lifetime tax, not success %.
- **RMD** — Required Minimum Distribution: forced, taxable withdrawals from traditional
  accounts starting at 73 or 75 depending on birth year. What conversion ladders defuse.
- **Backdoor Roth** — Non-deductible IRA contribution immediately converted to Roth;
  legal workaround to income limits.
- **Pro-rata rule** — The IRS taxes IRA conversions in proportion to ALL pre-tax IRA
  money. Large traditional IRA balances make backdoor Roths mostly taxable — a
  standard CPA question before starting one.
- **MAGI (ACA)** — the income measure ACA subsidies key off: AGI + tax-exempt muni
  interest + the untaxed part of Social Security. Conversions AND realized gains from
  taxable withdrawals raise it dollar-for-dollar; that's the ladder/subsidy conflict.
  The engine reports it per year as the `aca_magi` ledger column.
- **ACA premium tax credit (subsidy)** — a refundable federal credit that covers the
  gap between the benchmark plan's premium and your "expected contribution"
  (2.1%–9.96% of MAGI, rising with income). Computed in-engine since 2026-09-04.
- **FPL / 400% cliff** — the Federal Poverty Level ($21,150 for a household of 2 in
  the 2026 coverage year) scales the subsidy bands. One dollar of MAGI above 400% of
  FPL forfeits the ENTIRE credit — potentially five figures of tax swing on one dollar
  of income.
- **Benchmark (SLCSP) premium** — the second-lowest-cost Silver plan on the exchange;
  the credit formula prices against it. Until a real quote is available, the configured
  premium stream doubles as the proxy.
- **Expected contribution / applicable percentage** — the share of MAGI you're deemed
  able to pay for the benchmark plan (Rev. Proc. table, interpolated within bands);
  credit = benchmark − contribution, floored at zero.
- **Pre-Medicare bridge** — The years between early retirement and Medicare at 65 when
  health insurance must be bought privately. The expense stream charges full price;
  any earned credit shows up as reduced (possibly negative) federal tax.
- **Asset location** — Which account *type* holds which asset: bonds belong in
  traditional accounts (worst-taxed income sheltered), stocks in taxable (favorable
  LTCG rates), highest-growth assets in Roth.
- **Tax character of yield** — Interest, qualified dividends, muni interest, and
  US-government interest are all taxed differently (federally and by Michigan — MI
  exempts Treasury/SGOV interest, taxes out-of-state muni interest). Why the same yield
  isn't the same after-tax.
