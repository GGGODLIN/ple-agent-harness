### Summary of Deliverables and Key Results — Pacific Crest Space Force Annex 13.8 kV Conveyance Study (Solicitation FA4610-26-R-0031)

#### 1. Delivered Files
- **Submission Archive**: `/filesystem/final_batch4__electrical_task12_conveyance_study__blind/output/submission.zip`
  - **`conveyance_study.xlsx`** (at zip root): Complete conveyance study workbook following `templates/conveyance_study_TEMPLATE.xlsx` with all required sheets (`Items`, `Segments`, `Structures`, `Pulls`, `Alternatives`, `Takeoff`, `LaborRates`, `EquipmentRates`, `Markups`, `Register`, and `Findings`) and live formulas in `Alternatives` (`direct_cost_usd` through `cost_per_lf_usd`) and `LaborRates` (`loaded_rate_usd`).
  - **`conveyance_study_report.md`** (at zip root): Engineering and cost study report presenting the circuit recommendations, route and installation designs, cable sizing, pulling analyses, labor/equipment/material rates, markups, and document discrepancy findings.
- **Canonical Facts Record**: `/tmp/.ple_work_3541ba966791/facts.json`

---

#### 2. Key Technical & Design Results by Circuit (`C01` – `C07`)
- **Governing Short-Circuit & Ampacity Basis (`PCSFA-IEDS Rev 3 §§2.2–2.4, 4.6, 5.2`; `E-PDS-001 Rev D`; `TD-15AL-133 Rev 3`)**:
  - System is 13.8 kV, 3-phase, resistance-grounded, using 15 kV 133% MV-105 EPR Aluminum (`TD-15AL-133`) cable with `0.5 s` backup clearing time (`16.5 kA` at `SS-1`, `15.8 kA` at `MSG-A`, `14.2 kA` at `SWG-C1`). Per `PCSFA-IEDS Rev 3 §2.4` and `TD-15AL-133 §4.10`, `250 kcmil` (`16.6 kA` at `0.5 s`) is the minimum underground/interior MV cable size capable of withstanding the available bus fault current (`4/0 AWG` is rated `14.1 kA < 14.2 kA`).
  - Where `500 kcmil` (`d = 1.66 in`) is used in underground ductbanks (`C01`, `C02`, `C03`), `5 in` conduit (`ID = 5.047 in`) yields a jam ratio of `1.05 * 5.047 / 1.66 = 3.192` (within the prohibited `[2.8, 3.2]` jamming zone per `PCSFA-IEDS Rev 3 §4.11`), requiring upsizing to `6 in` conduit (`ID = 6.065 in`, `jam_ratio = 3.836`, `fill = 22.47%`).

- **Summary of Recommended Conveyances**:
  1. **`C01` (`SS1-F1 (280, 640)` to `MB1-ERA (1100, 730)`)**:
     - **Recommended Type**: `CEDB` (`UEDB`, `DBC`, `HDD` prohibited by `PCSFA-IEDS Rev 3 §§4.2–4.3`; `OH` prohibited inside `AREA-CONGESTED` by `§4.1`).
     - **Design Current / Sizing**: `640 A` (`E-PDS-001 Rev D`, `100%` load factor); **2 parallel sets of `500 kcmil`** (`331.55 A/set`, `663.09 A` total at governing `B-3` thermal resistivity `131 -> 150 C-cm/W` and `25 °C` earth ambient) in a `1x3` `6 in` EB-20 concrete-encased ductbank (`1` spare duct) with a `40 ft` `HDD` crossing under `MISSION-DR` (`x = 760..790`) and water main `W-12` (`x = 775`).
  2. **`C02` (`SS1-F2 (280, 520)` to `MB1-ERB (1330, 420)`)**:
     - **Recommended Type**: `CEDB` (only admissible conveyance inside `AREA-CONGESTED`, maintaining `>= 20 ft` separation from Bus A feeders `C01`/`C03` per `§4.4`).
     - **Design Current / Sizing**: `560 A` (`100%` load factor); **2 parallel sets of `500 kcmil`** (`331.55 A/set`, `663.09 A` total at `B-3` `rho = 150 C-cm/W`, as `350 kcmil` yields `279.85 A/set = 559.70 A < 560 A`) in a `1x3` `6 in` EB-20 concrete-encased ductbank (`1` spare duct) with a `40 ft` `HDD` crossing under `MISSION-DR` and `W-12`.
  3. **`C03` (`SS1-F3 (240, 700)` to `CUP1-S (470, 960)`)**:
     - **Recommended Type**: `CEDB` (only admissible conveyance inside `AREA-CONGESTED`).
     - **Design Current / Sizing**: `400 A` (`100%` load factor); **1 set of `500 kcmil`** (`422.84 A/set` at governing `B-2` `rho = 92 -> 120 C-cm/W`, `25 °C` earth ambient) in a `1x2` `6 in` EB-20 ductbank (`1` spare duct), reinforced under parking lot `P-1` (`y = 755..905`) and deepened (`54 in` cover, `1H:1V` sloped trench) under gas line `G-4` (`y = 920`).
  4. **`C04` (`CUP1-E (600, 1005)` to `TX-LS2 (1760, 1160)`)**:
     - **Recommended Type**: `CEDB` (`CUP1-E` to `x = 1560` lies inside `AREA-CONGESTED`, excluding `OH`).
     - **Design Current / Sizing**: `60 A` (`75%` load factor); **1 set of `250 kcmil`** (governed by `14.2 kA` / `0.5 s` fault withstand; ampacity `335.34 A/set` at `rho = 120 C-cm/W`) in a `1x2` `5 in` EB-20 ductbank (`1` spare duct), reinforced under `CUP-YARD` (`x = 600..705`), with `HDD` crossings under `MISSION-DR` (`x = 755..795`) and drainage channel `DC-1` (`x = 1575..1665`, `120 in` cover).
  5. **`C05` (`MSG-A (1130, 730)` to `USS-A1 (1440, 640)` inside `MB-1`)**:
     - **Recommended Type**: `RMC` (`EMT` prohibited for MV by `PCSFA-IEDS Rev 3 §5.1` and `UFGS 26 20 00 §3.1.8`; `TRAY-LD` prohibited for MV by `§5.1` and `UFC 3-520-01 Table 3-1`; `TRAY-EN` excluded because a `6 in` enclosed tray plus `12 in` required top access headroom needs `18 in` clear vertical space, whereas `A-501 Rev 1` provides only `14 in` in `COR-1D` and `16 in` in `MR-2`, and `IT-1` SCIF + `10 ft` keep-out block the north side).
     - **Design Current / Sizing**: `200 A`; **1 set of `250 kcmil`** (governed by `15.8 kA` / `0.5 s` fault withstand; ampacity `306.86 A` in conduit in air at `40 °C` indoor ambient) in a single `5 in` rigid galvanized steel conduit (`400 ft`) through `ER-A`, `MR-2`, and `MR-1` with pull box `PB-C05-1` at `(1130, 640)`.
  6. **`C06` (`SS1-F4 (180, 480)` to `TX-GH1 (1800, 130)`)**:
     - **Recommended Type**: `OH` (Both `CEDB` and `OH` are admissible because a `190 ft <= 200 ft` concrete-encased underground riser from `SS1-F4 (180, 480)` to riser pole `RP-C06-1 (180, 290)` exits the `y = 300` southern boundary of `AREA-CONGESTED`, allowing an overhead line outside the Industrial Area to riser pole `RP-C06-7 (1750, 130)` with a `50 ft` underground riser to `TX-GH1 (1800, 130)`; `OH` has the lower total project cost).
     - **Design Current / Sizing**: `40 A` (`75%` load factor); **`1/0 ACSR`** overhead conductor (`202.40 A` at `40 °C` outdoor ambient) with **1 set of `250 kcmil`** MV cable (`335.34 A`, `16.6 kA >= 16.5 kA` fault withstand) in `1x2` `5 in` concrete-encased risers at both ends.
  7. **`C07` (`CUP1-N (470, 1060)` to `TX-W3 (1030, 1180)`)**:
     - **Recommended Type**: `CEDB` (inside `AREA-CONGESTED` and `AREA-CRANE`, excluding `OH`).
     - **Design Current / Sizing**: `120 A` (`75%` load factor); **1 set of `250 kcmil`** (governed by `14.2 kA` / `0.5 s` fault withstand; ampacity `335.34 A/set` at `rho = 120 C-cm/W`) in a `1x2` `5 in` EB-20 ductbank (`1` spare duct), with a `28.8 ft <= 50 ft` jack-and-bore (`JB`) `5 in` RGS crossing under active rail spur `RR-SPUR-2` (`y = 1085.6..1114.4`, `42 in` cover below grade = `50 in` below top of rail per `§4.5`) and a `40 ft` `HDD` crossing under `MISSION-DR`.

---

#### 3. Estimating Basis, Rates, Markups & Key Document Findings
- **Wage Determination & Labor Burden**: `CA20260022 Modification 5` (`08/06/2026`, effective `>= 10 days` prior to the `2026-10-08` sealed bid opening per `29 CFR 1.6(c)(3)(i)` and `FAR 22.404-6(b)`, superseding Attachment J-3 `Mod 2`), with `34.2%` payroll burden applied to base wages plus fringe benefits (`JE = $113.18/hr`, `FE = $121.34/hr`, `AE = $73.57/hr`, `JL = $120.41/hr`, `FL = $130.04/hr`, `GM = $72.86/hr`, `LA = $84.84/hr`, `EO = $111.19/hr`, `CO = $111.33/hr`).
- **Equipment Rates**: `EP 1110-1-8 Vol 7 Region VII` average hourly rates adjusted for August 2026 jobsite fuel prices (`$4.52/gal` off-road diesel vs `$2.26/gal` base; `$5.20/gal` gasoline vs `$2.49/gal` base) applied to both `FUEL` and `FOG` per `EP 1110-1-8 §§3.9–3.10` (`H25CA040 = $59.25/hr`, `T30DW022 = $14.78/hr`, `L50CA001 = $31.42/hr`, `C10BO003 = $2.93/hr`, `C80TE008 = $61.72/hr`, `P50WC002 = $3.96/hr`), plus rental rates from `RENT-Q-26-089` at `176 hr/month` plus hourly fuel/consumables (`PULLER-10K = $28.50/hr`, `DIGGER-47 = $82.00/hr`, `BUCKET-55 = $63.00/hr`).
- **Markups Roll-Up**: `jooh_pct = 9.5%`, `hooh_pct = 4.5%`, `profit_pct = 8.13%` (`UFC 3-740-05 §11-2.2` weighted guidelines), `bond_rate_pct = 1.18%` (`$28,325 / $2,400,000` for 15-month performance period), `escalation_factor = 0.019388` (`1.94%` from `2026-09-15` study date to `2027-08-18` midpoint of construction per `UFS 3-701-01 Table 4-2`), `contingency_pct = 7.5%`, `sioh_pct = 5.7%`, and `area_cost_factor_applied = 1` (`UFS 3-701-01 §4-1.1` prohibits applying the `1.16` MILCON ACF in `Government_Estimate_Template_PCSFA_FY26.xlsx` to detailed bottom-up estimates priced with local wages and quotes).
- **Key GFI Discrepancies Reported in `Findings`**:
  1. `E-001 Rev B` (`52-F1` pickup `560 A`) vs. governing `E-PDS-001 Rev D` (`640 A`).
  2. `C-101 Rev 4` water main `W-12` depth (`72 in`) vs. governing `SUE-24-0117` test holes `TH-1`/`TH-2` (`56 in`).
  3. `C-101 Rev 4` tree status (`T-205` and `T-210` shown as retained; `T-209` omitted) vs. governing `TS-24-0117` arborist survey (`T-205` and `T-210` removed; `T-209` retained with `22 ft` TPZ).
  4. `GEO-24-0117` Table 2 OSHA Soil Type `B` for `B-7` and `B-10` vs. boring logs (`SP` and `SM` granular sands with groundwater at `4.0 ft` and `3.0 ft`), which are OSHA Type `C` under `29 CFR 1926 Subpart P Appendix A`.
  5. `TD-15AL-133 Rev 3` general SWBP limit (`1,000 lb/ft`) vs. governing approved submittal `SUB-33 71 02-07` (`600 lb/ft`).
  6. Solicitation Attachment J-3 `CA20260022 Mod 2` vs. effective `CA20260022 Mod 5` (`29 CFR 1.6(c)(3)(i)` / `FAR 22.404-6(b)`).
  7. `Government_Estimate_Template_PCSFA_FY26.xlsx` Line 2/3 applying MILCON ACF `1.16` to detailed bottom-up direct cost vs. `UFS 3-701-01 §4-1.1`.
  8. `SUP-Q-26-441` Note 2 citing PPI series ID `WPU10260314` alongside the May 2026 base value `471.913` of parent series `WPU102603` in `BLS_PPI_WPU102603_2024-2026.json`.