### Delivered Package

The final submittal package has been written to:
- `/filesystem/final_batch4__electrical_task8_electrical_specs__blind/output/submission.zip`

It contains:
1. **`specs/`** — Six tailored Division 26 Unified Facilities Guide Specifications (`.docx`) edited from the furnished `.SEC` masters in `20_guide_specifications/UFGS_Division_26_SpecsIntact/` per Task Order 0004 (`SOW_TaskOrder_Division26_Specs.docx`, Table 1):
   - `specs/26 05 73.docx` — *POWER SYSTEM STUDIES*
   - `specs/26 20 00.docx` — *INTERIOR DISTRIBUTION SYSTEM*
   - `specs/26 24 13.docx` — *SWITCHBOARDS*
   - `specs/26 32 15.docx` — *ENGINE-GENERATOR SET STATIONARY 15-2500 KW, WITH AUXILIARIES*
   - `specs/26 36 23.docx` — *AUTOMATIC TRANSFER SWITCHES*
   - `specs/26 51 00.docx` — *INTERIOR LIGHTING*
2. **`design_basis.xlsx`** — The electrical design basis workbook containing the seven required sheets (`Sections`, `Feeders`, `ShortCircuit`, `Photometric`, `StepLoad`, `Register`, and `Findings`).

---

### Key Engineering Results & Design Basis Summary

1. **Feeders (`Feeders` sheet — 17 service and feeder runs, copper only at 75°C, $\text{PF}=0.85$, $\text{VD}\le 2.0\%$ [$\le 3.0\%$ on motor feeder `HM1` and generator optional standby feeder `GEN-ATSE`], conduit fill $\le 40\%$ including copper EGC)**:
   - `MSB`: `251.5 ft`, `5` sets of `250` kcmil Cu in `4 in` PVC, `vd_pct = 1.58%`, `fill_pct = 12.44%`
   - `HM1`: `195.0 ft`, `2` sets of `2/0` AWG Cu in `3 in` RMC, `vd_pct = 2.66%`, `fill_pct = 14.60%`
   - `H1A`: `12.0 ft`, `1` set of `2/0` AWG Cu in `2.5 in` EMT, `vd_pct = 0.17%`, `fill_pct = 18.69%`
   - `H2A`: `91.0 ft`, `1` set of `1/0` AWG Cu in `2.5 in` EMT, `vd_pct = 1.42%`, `fill_pct = 15.58%`
   - `ATS-E`: `20.5 ft`, `1` set of `4/0` AWG Cu in `2.5 in` EMT, `vd_pct = 0.24%`, `fill_pct = 27.29%`
   - `HE1`: `16.5 ft`, `1` set of `3/0` AWG Cu in `2.5 in` EMT, `vd_pct = 0.20%`, `fill_pct = 22.55%`
   - `ATS-L`: `26.5 ft`, `1` set of `6` AWG Cu in `1.5 in` EMT, `vd_pct = 0.27%`, `fill_pct = 14.49%`
   - `T-1A`: `23.5 ft`, `1` set of `1/0` AWG Cu in `3 in` EMT, `vd_pct = 0.33%`, `fill_pct = 8.25%`
   - `LP1A`: `12.0 ft`, `2` sets of `2/0` AWG Cu in `3 in` EMT, `vd_pct = 0.31%`, `fill_pct = 12.38%`
   - `T-2A`: `19.5 ft`, `1` set of `3` AWG Cu in `2.5 in` EMT, `vd_pct = 0.32%`, `fill_pct = 6.57%`
   - `LP2A`: `12.0 ft`, `1` set of `4/0` AWG Cu in `2.5 in` EMT, `vd_pct = 0.28%`, `fill_pct = 27.29%`
   - `T-C1`: `55.5 ft`, `1` set of `6` AWG Cu in `2 in` EMT, `vd_pct = 0.51%`, `fill_pct = 7.03%`
   - `LC1`: `12.0 ft`, `1` set of `1` AWG Cu in `2 in` EMT, `vd_pct = 0.40%`, `fill_pct = 22.85%`
   - `T-E1`: `21.0 ft`, `1` set of `6` AWG Cu in `1.25 in` EMT, `vd_pct = 0.19%`, `fill_pct = 15.78%`
   - `LE1`: `10.0 ft`, `1` set of `1` AWG Cu in `1.5 in` EMT (upsized from `1.25 in` EMT where $5\times\text{\#1 AWG}=51.27\%>40\%$), `vd_pct = 0.33%`, `fill_pct = 37.67%`
   - `GEN-ATSL`: `219.0 ft`, `1` set of `4` AWG Cu in `1.25 in` PVC, `vd_pct = 1.44%`, `fill_pct = 28.01%`
   - `GEN-ATSE`: `225.0 ft`, `1` set of `4/0` AWG Cu in `2.5 in` PVC, `vd_pct = 2.63%`, `fill_pct = 34.05%`

2. **Short-Circuit Analysis (`ShortCircuit` sheet — 1,000 kVA service transformer, $Z=5.75\%$, $X/R=6.5$, 250 MVA at 12.47 kV utility primary, plus 113 kVA connected motor contribution at $X_d''=0.20\text{ pu}$)**:
   - `MSB` (480 V): `17.18 kA` available fault $\rightarrow$ `18 kA` minimum specified rating (22 kA standard switchboard rating)
   - `HM1` (480 V): `11.29 kA` available fault $\rightarrow$ `14 kA` minimum specified rating
   - `H1A` (480 V): `15.18 kA` available fault $\rightarrow$ `18 kA` minimum specified rating
   - `H2A` (480 V): `10.38 kA` available fault $\rightarrow$ `14 kA` minimum specified rating
   - `ATS-E` (480 V): `15.27 kA` available fault $\rightarrow$ `18 kA` minimum specified rating
   - `HE1` (480 V): `14.34 kA` available fault $\rightarrow$ `18 kA` minimum specified rating
   - `ATS-L` (480 V): `10.88 kA` available fault $\rightarrow$ `14 kA` minimum specified rating
   - `LP1A` (208 V): `5.84 kA` available fault $\rightarrow$ `10 kA` minimum specified rating
   - `LP2A` (208 V): `4.05 kA` available fault $\rightarrow$ `10 kA` minimum specified rating
   - `LC1` (208 V): `2.79 kA` available fault $\rightarrow$ `10 kA` minimum specified rating
   - `LE1` (208 V): `2.86 kA` available fault $\rightarrow$ `10 kA` minimum specified rating

3. **Photometric & Whole-Building LPD (`Photometric` sheet — 36 spaces, $35,342\text{ ft}^2$, $\text{LLF}=0.90$)**:
   - Corrected the 5 non-compliant BIM Rev C spaces (`102`: $18\rightarrow 24\times\text{L1}$, $35.7\text{ fc}$; `116`: $4\rightarrow 6\times\text{L5}$, $178.9\text{ fc}$, $U=2.80\le 3.0$; `140`: $30\rightarrow 16\times\text{L1}$, $34.6\text{ fc}$; `198`: $16\rightarrow 6\times\text{L5}$, $31.6\text{ fc}$; `280`: $16\rightarrow 6\times\text{L5}$, $31.6\text{ fc}$), reducing whole-building connected lighting power from $10,388\text{ W}$ ($\text{LPD}=0.2940\text{ W/ft}^2 > 0.285\text{ W/ft}^2$) to $9,508\text{ W}$ ($\text{LPD}=0.2690\text{ W/ft}^2 \le 0.285\text{ W/ft}^2$).

4. **Generator Step-Load Sequencing (`StepLoad` sheet — 150 kW / 187.5 kVA standby diesel generator `GEN-1`, $X_d''=0.12\text{ pu}$)**:
   - **Step 1** (`EGRESS-LTG, FIRE-ALARM, COMM-MNS, ELEV-CTRL` via `ATS-L` within $\le 10\text{ s}$): `40.0 kVA` starting load, `2.50%` voltage dip ($\le 20\%$ limit), `0.80 s` recovery ($\le 3.0\text{ s}$ limit).
   - **Step 2** (`RECEPT-HE1, AHU-1, CHWP-1` via `ATS-E` at $t=15\text{ s}$): `159.8 kVA` starting load, `9.07%` voltage dip ($\le 15\%$ limit), `1.33 s` recovery ($\le 5.0\text{ s}$ limit).
   - **Step 3** (`AHU-2, CHWP-2, EF-1-4` sequenced at $t=25\text{ s}$): `167.0 kVA` starting load, `9.14%` voltage dip ($\le 15\%$ limit), `1.33 s` recovery ($\le 5.0\text{ s}$ limit), final cumulative running load $101.3\text{ kW}$ ($67.5\%$) / $118.1\text{ kVA}$ ($63.0\%$).

Delivered files:
/filesystem/final_batch4__electrical_task8_electrical_specs__blind/build_specs.py (100657 bytes)