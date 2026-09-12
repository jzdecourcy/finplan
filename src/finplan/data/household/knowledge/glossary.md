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
- **Success threshold** — The success % a household treats as "green light." 100% is
  not the standard: industry practice reads ~85%+ as comfortable, 70–85% as workable
  with monitoring, below 70% as rework. The metric measures the odds a ROBOTIC
  spender runs short, not ruin — real households adjust yearly, failures arrive
  late with Social Security still underneath, and the model excludes home equity
  and any private-business stake valued at $0. Chasing the last few points costs
  years of work.

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
- **Overlay naming** — File stems are `<family>_<value>` in snake_case (`retire_57`,
  `roth_ladder_22`, `move_2030_mortgage`, `ss_70`); the family is the lever being
  pulled. `meta.name` always equals the stem and `meta.description` is the one-line
  plain-English summary reports and tools show.

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
- **Buy-sell agreement** — The contract between co-owners of a private company that
  says who must buy a departing owner's shares, at what price, and how it's paid, on
  death, disability, divorce, or bankruptcy. Often funded by life insurance on each
  owner. Read it for what it does NOT cover — many are silent on voluntary retirement.
- **Stated value vs appraised value** — Buy-sell price can be a number the owners
  re-sign each year (stated value) or, if that lapses, a formal appraisal of fair
  market value. Whether the annual re-signing happened decides which one applies.
- **Passive K-1 tail** — Keeping S-corp shares after you stop working there, so the
  pro-rata K-1 income and distributions continue. Model it as a `scorp_tail` overlay
  family (a stress condition, not a lever — the other owners control distributions).

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
- **Capital-gain distribution** — An actively managed fund/CEF sells winners inside the
  fund and passes the realized gains to you every December (1099-DIV box 2a); you pay
  LTCG tax on them even though you sold nothing and the cash was reinvested. The tax
  drag of active funds vs index ETFs — modeled as the `ltcg_distributions` yield on a
  taxable account. The reinvested amount raises cost basis, so lifetime gain is
  unchanged; you just pay the tax decades earlier.
- **Roth catch-up rule (SECURE 2.0 §603)** — From 2026, the extra 401k "catch-up"
  contribution allowed at 50+ must go in as Roth (after-tax) — but only for people
  whose prior-year W-2 wages from the employer sponsoring the plan topped $145k
  (indexed upward each year). Under the threshold, catch-ups can stay pre-tax.
  Only the catch-up slice is ever affected; the regular deferral limit can always
  be pre-tax. K-1 pass-through income and a spouse's wages don't count toward the
  wage test.
- **Mega backdoor Roth** — A 401k feature, not a law: the plan lets you add *after-tax*
  (non-Roth) contributions above the normal deferral limit, up to the overall annual-
  additions cap, and then convert them to Roth inside the plan or roll them to a Roth
  IRA. Needs the plan document to allow both steps. Unlike the IRA backdoor it does not
  trip the pro-rata rule. Model it as a `contrib_*` overlay.
- **Annual additions limit (§415(c))** — The cap on everything going into one person's
  401k in a year: your deferrals, employer match, and after-tax contributions combined
  ($72,000 for 2026). Age-50 catch-up sits on top of it.
- **ACP test** — Nondiscrimination test comparing highly compensated employees' match
  and after-tax contribution rates with everyone else's. Safe-harbor plans skip it for
  deferrals and match, but NOT for after-tax contributions — the usual reason a mega
  backdoor fails at a small company.

## Sweeps (`plan sweep`)

- **Lever vs. stress** — A *lever* is something the household chooses (retire age,
  Roth ladder, guardrail, SS claim age, house move). A *stress condition* is something
  it doesn't (how long we live, whether spending drifts up, what a volatile income
  actually pays). A sweep crosses only the levers and re-runs every combination under
  every stress condition. Optimising over a stress condition would be optimising the
  weather.
- **Cell** — One combination of lever choices, e.g. `r57+nolad+gr50+ss67+stay`. The
  grid is every cell × every stress condition.
- **Reference condition** — The first stress entry (normally plain base). Estate and
  tax columns in the summary are read from it.
- **Worst-case success** — The lowest success % a cell scores across all the stress
  conditions. Cells are ranked on this, not on base success, so a choice that is
  second-best everywhere beats one that is best in one world and fragile in the rest.
- **Frontier (Pareto)** — The cells that no other cell beats on *both* worst-case success
  and median estate at once. Every cell on it is a legitimate choice; moving along it
  is buying estate with points, or points with estate. Cells off it are dominated.
- **Main effect** — For one lever, the average outcome of each option with every other
  lever averaged out. Reads as "what does picking this option cost or buy, on average."
  Interactions (one lever mattering more given another) are what the full grid adds.
- **MC noise band** — The same cell re-run with a few different random seeds. Any
  difference between two cells smaller than this band is seed luck, not signal.

## Portfolio and cash

- **Asset classes (stocks / bonds / cash)** — The only three things the engine models.
  Every account is a mix of them (e.g. 80/20), each with its own expected real return,
  volatility, and correlation from base.yaml's market block. No funds, durations, or
  yield curves exist inside the model: a Treasury fund is labeled "bonds" (intermediate
  behavior) or "cash" (T-bill behavior), and a short-term fund has to be one or the
  other. Fine over decades; would need a fourth class if duration ever drove a decision.
- **Emergency fund / operating buffer** — Cash kept out of the market to cover spending
  and lumpy bills (quarterly estimated taxes) without selling anything. Typically 6-12
  months of spending; sweeping the `cash_*` overlay family prices how much more than
  that is worth holding (usually nothing in points, and it costs estate).
- **Lump sum vs dollar-cost averaging** — Investing all at once vs in tranches over
  months. Lump sum wins on average (money is in the market longer); tranches are a
  regret hedge, cheap if spread over a few months, costly if over years.
- **I-bond fixed rate** — The permanent above-inflation part of a Series I bond's yield,
  set at issue. A 0% fixed rate means the bond earns exactly inflation — the engine's
  0% real cash return — tax-deferred and state-exempt.
- **Rule of 55** — Leave your employer in or after the calendar year you turn 55 and
  that employer's 401(k) can be tapped without the 10% early-withdrawal penalty
  (normal income tax still applies). Only that plan — never IRAs, and rolling the
  money to an IRA forfeits it. Modeled via `rule_of_55: true` on the current employer's 401(k)s;
  only usable in practice if the plan allows partial withdrawals (open question).
- **72(t) / SEPP** — "Substantially Equal Periodic Payments": commit to fixed annual
  withdrawals from a traditional IRA and the 10% penalty is waived at ANY age — but
  the payments must run untouched for at least 5 years or until 59½, whichever is
  later, or all the waived penalties come back with interest. The escape hatch for
  retiring before 55; rigid, so a CPA computes the number. Modeled via `policies.sepp`.
- **MESP netting rule (Michigan 529 deduction)** — Michigan lets you deduct 529
  contributions (Schedule 1 line 17, $10k/yr on a joint return, worth 4.25% = $425)
  but only the amount contributed *minus* qualified withdrawals and rollovers from the
  *same account* in the *same tax year*. Contributing to a plan you are drawing for
  tuition that year earns nothing; the engine applies this netting.
- **529 non-qualified withdrawal** — Taking 529 money for anything other than qualified
  education: the earnings portion is ordinary income plus a 10% federal penalty, and
  Michigan adds back any amount you previously deducted (Schedule 1 line 8). The
  engine never does this on its own; a 529 is only drawn for education-tagged expenses.
- **529-to-Roth rollover** — Since 2024, leftover 529 money can move to the
  beneficiary's Roth IRA: $35k lifetime per beneficiary, the account must be 15+ years
  old, paced at the annual IRA limit, and the kid needs earned income. Not modeled.
- **Cash deployment tiers (hold / reserve / deploy / lean)** — The `cash_*` overlay
  family: how much of today's cash stays cash. *reserve* also parks money for a known
  near-term outlay (a house gap); *lean* keeps only ~3 months. Sweep it rather than
  guess; the usual verdict is deploy, and lean adds nothing.

## Estate and gifting

- **Step-up in basis** — When someone dies, the cost basis of assets they held in
  taxable accounts (brokerage shares, the house) resets to the value on the date of
  death, so all the gain built up during their life is never taxed. Does not apply to
  IRAs, 401ks, or Roths. The reason appreciated stock is better bequeathed than gifted
  or sold late in life.
- **10-year rule** — Since the SECURE Act (2020), a child who inherits an IRA or 401k
  must empty it within 10 years of the owner's death (with annual minimums if the owner
  had reached RMD age). Pre-tax money comes out as ordinary income on the child's
  return; inherited Roth money comes out tax-free. Spouses are exempt. The estate-side
  case for shifting pre-tax money to Roth and taxable.
- **Annual gift exclusion** — The amount one person can give another each year with no
  gift-tax filing ($19,000 in 2026; a couple can give $38,000 to each child). Funding
  a kid's Roth IRA contribution is a gift of that size, well under the exclusion.
- **Lifetime gift/estate exemption** — The total a person can give away above the
  annual exclusions, during life plus at death, before any gift or estate tax is owed
  ($15M per person from 2026, indexed; unused amount is portable to the surviving
  spouse). Gifts above the annual exclusion are reported on Form 709 and reduce it;
  no tax is paid until it is used up.
- **Gift splitting** — A married couple treating one spouse's gift as half from each,
  doubling the annual exclusion. Automatic for gifts from a joint account; from a
  separately titled account it needs a Form 709 election.
- **Direct-payment exclusion** — Tuition paid straight to a school, or medical bills
  paid straight to the provider, for anyone, are not gifts at all and are unlimited.
  Paying the kid and letting them pay the school IS a gift.
- **Kiddie tax** — Investment income of a child under 19 (or under 24 if a full-time
  student) above a small threshold is taxed at the parents' rate. Defeats gifting
  appreciated stock to a college kid to sell at their 0% capital-gains rate.
- **Lady Bird deed** — An enhanced life-estate deed (Michigan, Florida, Texas and a few
  other states): the owner keeps full control of the house (can sell, mortgage, change
  their mind) and it passes to the named person at death without probate, still
  getting the step-up. Cheaper than a trust for a single asset.
- **Uncapping (Michigan)** — Michigan resets a property's taxable value to 50% of
  market value when ownership transfers, ending the inflation cap accumulated since
  purchase. Transfers of residential property to close relatives are exempt if the use
  stays residential.
- **Initial withdrawal rate** — first-year retirement spending plus taxes, minus
  Social Security and other income, divided by the portfolio at retirement. The
  classic sanity check: the "4% rule" (Bengen 1994, Trinity study 1998) found ~4%
  survived ~95% of 30-year historical periods, and ~3.5% survived nearly all periods
  of 40+ years. A Monte Carlo that assumes lower-than-historical returns will read a
  few points below those figures on purpose.
- **Tax reconciliation** — feeding a filed return's income lines into `plan tax-year`
  for that year and comparing the engine's AGI, taxable income, tax, and state tax
  against the return line by line. Validates the tax code in the engine against
  reality; every difference must have a named cause. Needs a parameter file for that
  tax year (`src/finplan/data/tax/us_federal_<year>.yaml`).
- **Flow-through entity (FTE) tax** — some states (e.g. Michigan) let an S-corp or
  partnership elect to pay state income tax at the entity level, deductible federally,
  which lowers the K-1. The state then adds the owner's share back on the state return
  and usually gives a matching credit. The engine models the addback via an income
  stream's `state_tax_addback` fraction; the credit is not modeled.
- **Capital loss carryforward** — when realized capital losses exceed gains in a year,
  only $3,000 of the excess reduces ordinary income; the rest carries to later years
  and nets against future gains first. The engine tracks it per simulated path (ledger
  column `capital_loss_carryforward`).
- **IRMAA (income-related monthly adjustment amount)** — the Medicare surcharge higher-
  income people pay on top of the standard Part B and Part D premiums. Social Security
  sets it from the tax return filed two years earlier (MAGI = AGI plus tax-exempt
  interest), in five tiers; for a couple the first tier starts above $218,000 (2026).
  It is a cliff, not a slope: one dollar over a threshold costs the whole tier for the
  year. The engine prices it per person 65+ (ledger columns `tax_irmaa`, `irmaa_tier`).
  Large Roth conversions or RMDs in one year raise IRMAA two years later, which is why
  conversions are cheapest before age 63.
