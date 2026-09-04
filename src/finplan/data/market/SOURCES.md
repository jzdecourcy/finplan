# Market Data Sources

## `historical_annual.csv`

Long-run annual nominal returns for US stocks, bonds and cash, plus US CPI inflation.

| Field | Meaning |
|---|---|
| `year` | Calendar year |
| `stocks` | S&P 500 total return (price + dividends), nominal, decimal |
| `bonds` | US 10-year Treasury total return (coupon + price change), nominal, decimal |
| `cash` | 3-month US Treasury bill return, nominal, decimal |
| `inflation` | US CPI year-over-year change, decimal |

**Coverage:** 1928 through 2025 inclusive — 98 rows, one per calendar year, ascending.
Values are plain decimals rounded to 6 places (e.g. `0.438112` = +43.8112%).

### Source

- **Name:** Aswath Damodaran (NYU Stern), *Historical Returns on Stocks, Bonds and Bills: 1928–Current*
- **File:** <https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls>
- **HTML version:** <https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html>
- **Landing page:** <https://pages.stern.nyu.edu/~adamodar/>
- **Retrieved:** 2026-09-03
- **Source last updated:** 2026-01-05 (per the HTML page; the workbook's own "Date updated" cell is stale but the data runs through 2025)

`stocks`, `bonds` and `cash` come from the workbook's **"Returns by year"** sheet, columns
*S&P 500 (includes dividends)*, *US T. Bond (10-year)* and *3-month T.Bill* respectively.

### Inflation series

`inflation` comes from the same workbook's **"Inflation Rate"** sheet, which Damodaran
sources from FRED series **CPIAUCNS** (Consumer Price Index for All Urban Consumers, All
Items, US City Average, *not* seasonally adjusted).

The series is **December-over-December**, not annual-average. Confirmed against known
values: 1979 = 13.29%, 1980 = 12.52%, 2022 = 6.45% — these match Dec/Dec CPI prints, not
the annual-average figures (11.3%, 13.5%, 8.0%).

**Consequence to be aware of:** Dec/Dec is more volatile than annual-average and can
diverge sharply in years when prices turned mid-year. 2008 is the clearest case — Dec/Dec
inflation was **+0.09%** (the oil-price collapse in H2 wiped out the H1 spike) while the
annual average was +3.8%. Backtests that deflate nominal returns year-by-year will see
2008 as a near-zero-inflation year.

### Sanity checks performed at retrieval

| Year | Series | Expected | Value in CSV |
|---|---|---|---|
| 1931 | stocks | ≈ -43.8% | -0.438375 |
| 1954 | stocks | ≈ +52.6% | 0.525633 |
| 2008 | stocks | ≈ -36.5% | -0.365523 |
| 2022 | bonds | ≈ -17.8% | -0.178282 |
| 1980 | cash | ≈ +11% | 0.113919 |
| 1979 | inflation | 11–13% | 0.132939 |
| 1980 | inflation | 11–13% | 0.125163 |

All within tolerance of the published landmarks.

### Notes and caveats

- **Gold is not included.** The workbook also carries US small cap, Baa corporate bonds,
  real estate and gold; only the four series above were extracted. Re-parse the same
  sheet if additional asset classes are needed later.
- **Bond returns are total returns on a constant-maturity 10-year Treasury**, computed by
  Damodaran from yields rather than taken from an index. They will not match a specific
  tradeable fund exactly.
- **T-bill returns are the annual bill rate**, so `cash` is effectively the realised
  one-year return from rolling 3-month bills.
- **2025 is included** and reflects a full calendar year, but it is the most recently
  added row upstream and therefore the most likely to be revised.
- Returns are **nominal**. Real returns must be derived by deflating with `inflation`;
  the CSV deliberately stores no pre-computed real series.

### Reproducing the parse

```python
import csv, xlrd  # pip install xlrd  (needed for legacy .xls)

wb = xlrd.open_workbook("histretSP.xls")

sheet = wb.sheet_by_name("Returns by year")   # header on row 19, data from row 20
returns = {}
for r in range(20, sheet.nrows):
    v = sheet.row_values(r)
    if isinstance(v[0], float) and 1900 < v[0] < 2100:
        returns[int(v[0])] = (v[1], v[4], v[3])  # stocks, bonds, cash

sheet = wb.sheet_by_name("Inflation Rate")    # data from row 11; col 2 is the decimal
inflation = {
    int(v[0]): v[2]
    for v in (sheet.row_values(r) for r in range(11, sheet.nrows))
    if isinstance(v[0], float) and 1900 < v[0] < 2100 and isinstance(v[2], float)
}

with open("historical_annual.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["year", "stocks", "bonds", "cash", "inflation"])
    for y in sorted(returns):
        s, b, c = returns[y]
        w.writerow([y, round(s, 6), round(b, 6), round(c, 6), round(inflation[y], 6)])
```
