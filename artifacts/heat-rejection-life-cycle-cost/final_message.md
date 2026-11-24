OPTIMIZATION_CONVERGED

The condenser water heat rejection replacement package for Papago Federal Center, Phoenix, Arizona (95% Construction Documents) has been verified by a self-checked Python optimization and constraint-verification suite (confirming both nominal feasibility across all 28 constraint families and constraint-violation rejection) and delivered at `/filesystem/final_batch4__mechanical_task3_ct_heat_lcc__blind/output/submission.zip`.

### Delivered Archive Contents (`/filesystem/final_batch4__mechanical_task3_ct_heat_lcc__blind/output/submission.zip`)
1. `CT_SCHEDULE_CUP.dxf`, `CT_SCHEDULE_ANNEX.dxf`, `CT_SCHEDULE_LAB.dxf` — Cooling tower schedules (`M-CTWR-SCHD`), closed rectangular cell support frame plan outlines (`M-CTWR-PLAN`) in the plan coordinates of `M-401 Rev C`, and revisioned title blocks (`G-TBLK`).
2. `CT_CALC_CUP.xlsx`, `CT_CALC_ANNEX.xlsx`, `CT_CALC_LAB.xlsx` — Five-sheet calculation workbooks (`DesignPoint`, `OffDesign` with 180 joint-frequency scenario bins summing to 8,760.0 hours, `WaterBalance`, `Energy`, and `LifeCycleCost`).
3. `constraint_register.csv` — Complete register of 156 applied requirements mapped to their governing project documents, clauses, values, and bound items, with all superseded, cancelled, and reference-only documents excluded from authority.
4. `design_basis.md` — Engineering design basis recording the governing documents, resolution of the three library conflicts, calculation methodology, and the governing constraint and relative margin for each plant.

---

### Summary of Key Results

| Parameter | `CUP` | `ANNEX` | `LAB` |
|---|---|---|---|
| **Cell Model & Count (`MODEL` × `CELLS`)** | `CTX-0600-S` × `4` | `CTX-0600-S` × `4` | `CTX-0900-H` × `3` |
| **Total / Per-Cell Design Flow (`GPMTOTAL` / `GPM`)** | `1,800 gpm` / `450 gpm` | `1,800 gpm` / `450 gpm` | `2,025 gpm` / `675 gpm` |
| **Design Wet-Bulb (`WBDESIGN` / `DesignWetBulb_F`)** | `80.0 °F` | `80.0 °F` | `80.0 °F` |
| **Scheduled / Achieved `CWS_F`** | `85.37 °F` / `85.36 °F` | `85.70 °F` / `85.69 °F` | `86.00 °F` / `85.99 °F` |
| **Scheduled / Achieved `Range_F`** | `12.66 °F` / `12.66 °F` | `13.69 °F` / `13.69 °F` | `14.59 °F` / `14.59 °F` |
| **Scheduled / Achieved `Approach_F`** | `5.37 °F` / `5.36 °F` | `5.70 °F` / `5.69 °F` | `6.00 °F` / `5.99 °F` |
| **Achieved Design `CWR_F` & `WaterFlowRatio`** | `98.02 °F` / `0.7500` | `99.38 °F` / `0.7500` | `100.58 °F` / `0.7500` |
| **Reset Schedule (`CWSMIN` / `CWSOFFSET`)** | `65.0 °F` / `11.5 °F` | `79.5 °F` / `11.5 °F` | `57.5 °F` / `8.5 °F` |
| **Redundancy Wet-Bulb & Capacity (`N-1` cells)** | `81.0 °F` / `909.65 tons` (`≥ 820`) | `81.0 °F` / `940.42 tons` (`≥ 880`) | `81.0 °F` / `1,205.22 tons` (`≥ 1,070`) |
| **99.6% Dry-Bulb & Freeze Protection (`BASINHEATER`)** | `38.0 °F` / `NO` | `38.0 °F` / `NO` | `38.0 °F` / `NO` |
| **Casing Material / Eliminator (`DRIFT`) / Motor** | `SS-304` / `DE-2` (`0.002%`) / `20 hp` (`91.7%`) | `SS-304` / `DE-2` (`0.002%`) / `20 hp` (`91.7%`) | `SS-304` / `DE-2` (`0.002%`) / `20 hp` (`91.7%`) |
| **Cycles of Concentration (`COC` / `MaxAllowableCOC`)** | `4.14` / `4.142` (`PSI = 5.601`) | `4.00` / `4.001` (`PSI = 5.600`) | `3.87` / `3.879` (`PSI = 5.601`) |
| **Evaporation Method (`EVAPMETHOD`)** | `SATURATED-EXIT` | `SATURATED-EXIT` | `SATURATED-EXIT` |
| **Annual Makeup / Allocation Limit (`kgal/yr`)** | `9,581.6` / `10,300.0` | `12,575.9` / `12,600.0` | `16,980.0` / `17,400.0` |
| **Annual Plant Energy (`AnnualPlantEnergy_kWh`)** | `2,126,665.5 kWh` | `3,893,886.3 kWh` | `3,551,637.5 kWh` |
| **Peak Coincident Demand / MCC Spare Capacity (`kW`)** | `515.03` / `528.00` | `570.69` / `590.00` | `633.01` / `641.14` |
| **Initial Investment (`Investment_USD`)** | `$782,208.00` | `$782,208.00` | `$778,848.00` |
| **Proposed Design `LCC_USD` (`26 yr` study, `d = 3.0%`)** | `$5,645,200.16` | `$7,847,771.93` | `$8,532,284.42` |
| **Basic Design `BasicDesignLCC_USD`** | `$5,890,940.15` | `$8,108,828.23` | `$8,820,663.84` |
| **Life-Cycle Net Savings (`NetSavings_USD`)** | **`$245,739.99`** | **`$261,056.30`** | **`$288,379.42`** |
| **Governing Constraint & Relative Margin** | `electrical capacity` (`0.0246`) | `water allocation` (`0.0019`) | `electrical capacity` (`0.0127`) |