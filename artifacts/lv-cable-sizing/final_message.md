OPTIMIZATION_CONVERGED

The low-voltage wire schedule and supporting engineering package for **Building 4210, Consolidated Support Facility (Project P-4210)** have been globally optimized via exhaustive catalog search and verified against all 35 constraint families (including self-checked nominal pass and violated-constraint failure assertions). The certified optimal package is stored in `/filesystem/electrical__lv_cable_sizing__blind/output/submission.zip`.

### Delivered Files (in `/filesystem/electrical__lv_cable_sizing__blind/output/submission.zip`)
1. **`wire_schedule.csv`** — 32-circuit wire schedule carrying the exact 27 required columns (`circuit` through `drop_v`).
2. **`E-621_wire_schedule.dxf`** — Contract drawing sheet `E-621` (`Project P-4210`) carrying the title block, abbreviation legend, and TEXT entities for all 32 circuits in the exact column order of `wire_schedule.csv`.
3. **`calc_book.xlsx`** — Stored-value calculation workbook with sheets `front_sheet`, `duct_assignment`, and `cost_ledger`.
4. **`design_basis.md`** — Basis of Design opening with the required structured `json` block followed by complete engineering prose.
5. **`constraint_register.xlsx`** — Code-compliance matrix containing 69 atomic single-requirement, single-document, single-clause rows (`req_id, document, clause, requirement, value, unit, kind, applies_to, resolution`).

### Certified Optimal Results Summary
- **Codes of Record**: **NFPA 70 (2023)** and **IBC (2024)**, adopted by **UFC 1-200-01** (Change 4, 17 Dec 2024) and **UFC 3-501-01** (Change 4, 27 Nov 2024); precedence rule: **most restrictive limit governs** (**EDS-26 Rev 4** §1.2; **UFC 3-501-01** ¶1-3; Drawing **G-001** General Note 2).
- **Environmental & Thermal Parameters**:
  - Outdoor design dry-bulb: `42 °C` (**EDS-26 Rev 4** §5.4, NOAA `USW00003145`).
  - Roof cable tray `CT-R1`: `46 °C` ambient, `1,030 W/m²` solar irradiance (`α = 0.6`, `h = 14.0 W/(m²·K)`), `N = 18` CCCs, single-layer `∑OD = 11.560 in. ≤ 16.20 in.`.
  - Underground duct banks `DB-1` and `DB-2`: undisturbed earth ambient `27.45 °C`, engineered full-trench thermal backfill `0.60 K·m/W` (native soil `0.95 K·m/W` rejected), concrete encasement `0.55 K·m/W`, load factor `1.0`.
  - Interior spaces: `45 °C` in Mechanical Room 121 and Fire Pump Room 105; `40 °C` in all other interior rooms (**M-501-C** Table 1).
- **Duct-Bank Assignment & Mutual Heating**:
  - `SE-1` (`6 × 500 kcmil CU`, EGC `4/0 CU` in `DB-1`): `D1, D2, D5, D6, D9, D10` (`348.12 A/set`, `2,088.72 A ≥ 2,000 A`, `ΔT_m = 31.09 K`).
  - `F-10` (`2 × 500 kcmil AL`, EGC `#1 CU` in `DB-1`): `D4, D8` (`302.23 A/set`, `604.46 A ≥ 600 A`, `ΔT_m = 23.53 K`; `D3, D7` unoccupied thermal buffer; `D11, D12` reserved for communications).
  - `F-05` (`3 × 600 kcmil AL`, EGC `250 kcmil CU` in `DB-2`): `D1, D2, D3` (`336.00 A/set`, `ΔT_m = 1.54 K`).
- **Voltage-Drop Budget (`≤ 3.0%` feeder chain, `≤ 3.0%` branch, `≤ 5.0%` cumulative from `T-1 secondary lugs`, `transformer_reset = false` at `K-13`)**:
  - `SE-1` (`MSB-1`): `1.0434%`
  - `SE-1 + F-01` (`MCC-1`): `2.5752%`
  - `SE-1 + F-02` (`DP-2`): `1.4066%`
  - `SE-1 + F-02 + F-06 + F-07` (`LP-1`): `2.7703%`
  - `SE-1 + F-05` (`DP-3`): `2.5811%` (holding `B-17` at `CMP-1` with `#6 AWG` max terminal limit to `4.9280% ≤ 5.0%`)
  - `SE-1 + F-10` (`ATS-1`): `2.7774%`
- **Large-Conductor Standardization (`≤ 5` distinct sizes `≥ 1/0 AWG`)**:
  - `4/0`, `300 kcmil`, `400 kcmil`, `500 kcmil`, `600 kcmil` (5 distinct sizes).
- **Certified Minimum Installed Cost (`40,254 ft ≥ 38,000 ft` -> `-6%` campus quantity break)**:
  - **Gross Conductor**: Material `$74,525.10` + Labour `$24,251.55` = `$98,776.65`
  - **6% Campus Quantity Break**: Material `-$4,471.51` + Labour `-$1,455.09` = `-$5,926.60`
  - **Net Conductor**: Material `$70,053.59` + Labour `$22,796.46` = `$92,850.05`
  - **Terminations**: Material `$5,100.92` + Labour `$4,500.78` = `$9,601.70`
  - **Interior Raceway (RGS)**: Material `$21,406.08` + Labour `$26,183.52` = `$47,589.60`
  - **Total Installed Cost**: Material **`$96,560.59`** + Labour **`$53,480.76`** = **`$150,041.35`**