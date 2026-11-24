### Deliverable

* **Materials Acceptance Record**: `/filesystem/Thelbridge_Materials_Acceptance_Fill_Compaction_2026-0708.docx` (prepared using `/filesystem/Thelbridge_Materials_Acceptance_Record_TEMPLATE.docx` for Verification Register **Item 054**, Birchwood Village Expansion Program — Package A, and verified against canonical values in `/tmp/.ple_work_722d1f6c093c/facts.json`).

---

### 1. Acceptance Determination

* **Determination**: **`REJECTED`** (Verification Register **Item 054** remains **OPEN** and cannot be closed as accepted until corrective rework, passing full-depth retesting, reissued reporting, and missing verification records are in hand).
* **Summary**: In **Field Density Test Report `SF-26-0708`** (tested `07/08/2026`, issued `07/09/2026`), Vantree Materials Testing, LLC evaluated the four Lift 6 nuclear-gauge tests (`FD-14` through `FD-17`, El. `748.6 ft`) against an inapplicable Phase 1 **ASTM D698 Method A (Standard Proctor)** curve (`VMT-2024-0403-P1B`, $\gamma_{d,\max} = 118.6\text{ pcf}$, $w_{\text{opt}} = 12.1\%$) and omitted moisture compliance evaluation entirely. When re-evaluated against the governing **ASTM D1557-12(2021) Method C (Modified Proctor)** basis (`VMT-25-0918-P04`, $\gamma_{d,\max} = 128.4\text{ pcf}$, $w_{\text{opt}} = 9.2\%$) under **Specification Section 31 20 00, Earth Moving (Rev.3, 03/06/2026), Article 3.4.B**, all four test locations satisfy the $\ge 95.0\%$ dry density requirement ($95.7\%$ to $98.2\%$), and locations **`FD-15` (Block A, Grid D-5)** and **`FD-16` (Block A, Grid F-4)** satisfy both density and moisture criteria, but locations **`FD-14` (Block A, Grid B-3, $w = 6.1\%$, −3.1% from $w_{\text{opt}}$)** and **`FD-17` (Block A, Grid G-2, $w = 5.8\%$, −3.4% from $w_{\text{opt}}$)** **FAIL** the mandatory moisture content window of **$8.2\%$ to $11.2\%$** (−1.0% to +2.0% of $w_{\text{opt}} = 9.2\%$). Under **Articles 3.4.B, 3.4.C, 3.4.D, and 3.7.C**, no test location may be accepted on density alone and failing tests may not be averaged with passing tests.

---

### 2. Acceptance Basis, Resulting Numerical Limits, and Record Evidence

1. **Acceptance Basis Applied**:
   * **Governing Standard & Laboratory Report**: **ASTM D1557-12(2021) Method C (Modified Proctor, $56,000\text{ ft-lbf/ft}^3$)**, established by **Vantree Materials Testing Report No. `VMT-25-0918-P04`** (dated `09/18/2025`, Sample ID `LWP-PA-SF-2025-01`, Larchwood Pit — Package A structural fill, USCS classification **SM / SW-SM**, $9.4\%$ passing No. 200 sieve, Non-Plastic (NP), $G_s = 2.68$):
     * **Maximum Dry Density ($\gamma_{d,\max}$)**: **$128.4\text{ pcf}$**
     * **Optimum Moisture Content ($w_{\text{opt}}$)**: **$9.2\%$**
2. **Numerical Limits Produced by Specification Section 31 20 00, Article 3.4.B**:
   * **Minimum In-Place Dry Density ($\ge 95.0\%$ of $\gamma_{d,\max}$)**:
     $$0.95 \times 128.4\text{ pcf} = \mathbf{121.98\text{ pcf}} \quad (\text{reported as } \mathbf{122.0\text{ pcf}} \text{ in Report VMT-25-0918-P04, Section 7, p. 3})$$
   * **Allowable In-Place Moisture Content Range (−1.0% to +2.0% of $w_{\text{opt}} = 9.2\%$)**:
     $$9.2\% - 1.0\% = \mathbf{8.2\%} \quad \text{to} \quad 9.2\% + 2.0\% = \mathbf{11.2\%}$$
   * **Per-Location Dual-Criterion Rule (Articles 3.4.B, 3.4.C.3, 3.4.D)**: Both $\gamma_{d,\text{field}} \ge 121.98\text{ pcf}$ ($122.0\text{ pcf}$; $\ge 95.0\%$) **and** $8.2\% \le w_{\text{field}} \le 11.2\%$ must be independently satisfied at each test location.
3. **What in the Record Establishes This Basis (and Excludes `VMT-2024-0403-P1B`)**:
   * **Specification Section 31 20 00, Earth Moving (Rev.3, 03/06/2026) (`Spec_312000_Earth_Moving_Rev3.pdf`)**:
     * **Article 1.2.A.1 (p. 1)** explicitly bars ASTM D698: *"Cited for historical borrow characterization only; not the acceptance basis for Package A structural fill."*
     * **Articles 1.2.A.2, 1.3.E, 1.4.C, 2.1.A–D, 3.4.B, 3.4.D, and 3.7.B (pp. 1–5)** establish ASTM D1557 Method C on the placed granular structural fill (SM or SW-SM, $\le 12\%$ passing No. 200, $\text{PI} \le 6$) as the mandatory acceptance denominator.
   * **Vantree Modified Proctor Report `VMT-25-0918-P04` (`Proctor_D1557_PackageA_Structural_Fill.pdf`, 09/18/2025, Section 1, p. 1 & Section 7, p. 3)**: Expressly states that its purpose is to establish the acceptance basis for Package A structural fill under Spec 31 20 00 Article 3.4.B and that *"This result supersedes any earlier Proctor result for structural fill on Package A."*
   * **Contractor's Block A Placement Log (`Fill_Placement_Records_BlockA_SlabOnGrade.xlsx`, Record No. `RB-FPR-BA-2026`, signed 07/09/2026)**: `Cover` tab Rows 24–25 and `Notes` tab Note 5 explicitly carry `Vantree Materials Testing Report VMT-25-0918-P04, ASTM D1557 Method C, γd,max = 128.4 pcf, wopt = 9.2%` as the governing Proctor reference for the Block A slab-on-grade fill (matching the Block B mass fill record `RB-FPR-BB-2025`, `Cover` Row 24 and `Notes` Note 3).
   * **Submittal Register, Verification Register, RFI Log, and Geotechnical Report**:
     * **Submittal `31-BR-A`** (Rev.1 reviewed `07/17/2025`, NM) and **Submittal `31-PR-A`** (*Modified Proctor Test Report — Package A Borrow*, reviewed `09/22/2025`, NET, `Submittal_Register_PackageA.xlsx` Rows 9–10, 33);
     * **Verification Register Item 012** (closed `09/22/2025`, `Thelbridge_Verification_Register_PkgA.xlsx` Row 14, confirming `Proctor D1557 — Package A Structural Fill` on file);
     * **RFI 014** (closed `06/23/2025`, `RFI_Log_PackageA.xlsx` Row 18: *"Confirm D1557 Method C per Spec 31 20 00 Article 3.4.B; laboratory Proctor result on file"*); and
     * **Geotechnical Investigation Report `KGI-2024-0417` Rev.2** (`02/14/2025`, Section 9.5, p. 19 [PDF p. 20]), specifying $95\%$ of ASTM D1557 maximum dry density and $-1\%$ to $+2\%$ of modified Proctor optimum moisture.
   * **Why `VMT-2024-0403-P1B` Used in `SF-26-0708` Is Invalid**: `Proctor_D698_Phase1_Borrow.pdf` (`04/03/2024`) was an **ASTM D698 Method A (Standard Proctor)** test on Phase 1 off-site **Wexford Ridge Borrow — Phase 1 source** (Sample `VMT-24-0325-138`), a reddish-brown silty clay classified **CL-ML** with **$68.0\%$ passing the No. 200 sieve** and **$\text{PI} = 11$** ($\text{LL} = 32, \text{PL} = 21$)—a cohesive material that fails Spec 31 20 00 Articles 2.1.A–B and was not placed at Block A.

---

### 3. Re-Evaluation of Lift 6 Test Results (`FD-14` Through `FD-17`, Report `SF-26-0708`)

| Test ID | Location (Lift 6, El. 748.6 ft) | Measured Dry Density $\gamma_d$ (pcf) | Reported % Compaction (vs. D698: 118.6 pcf) | Actual % Compaction (vs. D1557: 128.4 pcf) | Density Status ($\ge 95.0\%$ / $\ge 122.0\text{ pcf}$) | Measured Moisture $w$ (%) | Moisture Dev. from $w_{\text{opt}}$ ($9.2\%$ D1557) | Moisture Status ($8.2\%$ to $11.2\%$) | Spec 31 20 00 Art. 3.4.B Disposition |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`FD-14`** | Block A, Grid B-3 | $124.8$ | $105.2\%$ | **$97.2\%$** ($97.20\%$) | **PASS** | $6.1\%$ | **−3.1%** | **FAIL** | **FAIL / REJECTED** |
| **`FD-15`** | Block A, Grid D-5 | $123.5$ | $104.1\%$ | **$96.2\%$** ($96.18\%$) | **PASS** | $9.8\%$ | **+0.6%** | **PASS** | **PASS** |
| **`FD-16`** | Block A, Grid F-4 | $122.9$ | $103.6\%$ | **$95.7\%$** ($95.72\%$) | **PASS** | $10.4\%$ | **+1.2%** | **PASS** | **PASS** |
| **`FD-17`** | Block A, Grid G-2 | $126.1$ | $106.3\%$ | **$98.2\%$** ($98.21\%$) | **PASS** | $5.8\%$ | **−3.4%** | **FAIL** | **FAIL / REJECTED** |

---

### 4. Evaluation of Testing Execution and Record Completeness Under Section 31 20 00

What was done and recorded to date is **not sufficient** to support acceptance of the Block A slab-on-grade fill under Specification Section 31 20 00 for the following reasons:

1. **Direct-Transmission Probe Depth vs. Compacted Lift Thickness (Article 3.3.C vs. `SF-26-0708` Section 2)**:
   * While Vantree used the required **ASTM D6938 (nuclear gauge, direct-transmission mode)** method with a calibrated **Troxler Model 3440 Surface Moisture-Density Gauge** (Serial No. `34-047162`, calibrated `02/06/2026`, daily standardization counts `2,478` density / `738` moisture verified `07/08/2026`, `60`-s count time) and issued the report within 24 hours (`07/09/2026`), the probe depth was set to **$6.0\text{ in}$** (`6-in`, `SF-26-0708`, Section 2, p. 1; Notes to tabulation, p. 2), whereas the Contractor's placement log (`RB-FPR-BA-2026`, `Cover` Row 21; `Daily Placement Log` Rows 19–24) records an **$8.0\text{-in}$ loose / $7.2\text{-in}$ compacted lift thickness**. A $6.0\text{-in}$ probe depth leaves the bottom $1.2\text{ in}$ of the $7.2\text{-in}$ lift untested, failing to verify compliance *"throughout the full thickness of the lift"* as required by **Article 3.3.C**.
2. **Testing Frequency on Lift 6 vs. Lifts 1–5 and Test Numbering Discrepancy (Articles 3.4.B and 3.7.A.1)**:
   * Under **Articles 3.4.B and 3.7.A.1**, the required frequency is **1 test per $5,000\text{ sf}$ per lift and not fewer than 3 tests per lift regardless of lift area**. Across the **$11,400\text{ sf}$** Block A pad (grids `B–G / 1–5`, $11,400 \div 5,000 = 2.28 \rightarrow 3\text{ tests minimum per lift}$), the **4 tests** on Lift 6 (`FD-14` through `FD-17`, or $1\text{ test per } 2,850\text{ sf}$) satisfy the Rev.3 specification frequency.
   * However, in `RB-FPR-BA-2026` (`Cover` Row 31; `Daily Placement Log` Rows 19–23 and Row 31), the Contractor claims **3 tests per lift across Lifts 1–5 (15 tests total)** under reports **`FDR-BA-01 through FDR-BA-05`**, yet Lift 6 in `SF-26-0708` begins at **`FD-14`** (`FD-14` through `FD-17`), implying only **13 prior tests (`FD-01` through `FD-13`)** across Lifts 1–5 (which would leave at least one or two underlying lifts below the mandatory 3-test minimum of Article 3.7.A.1 unless test IDs overlapped).
3. **Missing Preceding Lift Reports `FDR-BA-01` Through `FDR-BA-05` (Articles 1.5.B.1, 1.6.B, 3.4.A, 3.7.B, 3.7.C)**:
   * Reports **`FDR-BA-01 through FDR-BA-05`** for Lifts 1–5 (`06/22/2026 – 07/08/2026` placement period, El. `745.0` to `748.0 ft`, `3.6 ft` total pad thickness across `6` lifts to El. `748.6 ft`) are absent from the project verification file. Because Vantree applied the wrong Proctor (`VMT-2024-0403-P1B`) and omitted moisture evaluation on Lift 6, `FDR-BA-01 through FDR-BA-05` must be inspected to verify that Lifts 1–5 were evaluated against (and met) ASTM D1557 Method C (`VMT-25-0918-P04`) for both density ($\ge 122.0\text{ pcf}$) and moisture ($8.2\%$ to $11.2\%$)—especially given recorded 90–93 °F temperatures, surface drying on `06/26` (Lift 4) and `06/30` (Lift 5), and dry-side rework near Grid E-4 on Lift 5 (`RB-FPR-BA-2026`, `Daily Placement Log` Rows 22–23; `Notes` Notes 7–8).
4. **Borrow Source Traceability and Placed-Material Correspondence Gap (Articles 1.3.E, 1.4.C, 1.5.A.1–2, 2.1.A–D, 3.7.A.2, 3.7.C, and RFI 079)**:
   * `RB-FPR-BA-2026` (`Cover` Row 23; `Notes` Note 4) records that the Block A fill (`136` loads, ~1,904 CY loose) was drawn from **`Stockpile north of Block C - approved for reuse per RFI 079`** (`10/10/2025`). However, **RFI 079** (`RFI_Log_PackageA.xlsx` Row 23) expressly conditioned approval on a gradation retest: *"Approved subject to gradation retest; see letter TPM-25-079."* Neither the gradation/Atterberg/USCS retest confirming that the north-of-Block-C stockpile matches Larchwood Pit sample `LWP-PA-SF-2025-01` (`VMT-25-0918-P04`) nor a stockpile-specific ASTM D1557 Method C test is on file in `Submittal_Register_PackageA.xlsx`.
5. **Report Content Non-Conformance in `SF-26-0708` (Articles 1.5.B.1, 3.7.B, 3.7.C)**:
   * `SF-26-0708` fails to state the ASTM D1557 Method C denominators, percent compaction relative to $128.4\text{ pcf}$, moisture deviation from $w_{\text{opt}} = 9.2\%$, and a dual-criterion disposition under Article 3.4.B/D.

---

### 5. What Must Be in Hand Before Anything Is Built on This Fill

Before any capillary break course (Article 2.3), vapor retarder, reinforcement, or slab-on-grade concrete is placed on the Block A fill pad (El. `748.6 ft`), the following seven items must be completed and in hand:

1. **Physical Rework of Failing Lift 6 Zones (Articles 3.3.B–C, 3.4.C.1, 3.7.C, 3.8.A)**: Rowan Bay Constructors must scarify full lift thickness, moisture-condition into the **$8.2\%$ to $11.2\%$** window, and recompact (minimum 6 passes CS56B vibratory smooth-drum + 4 passes PS-150C pneumatic roller) the failing Lift 6 zones around **`FD-14` (Block A, Grid B-3)** and **`FD-17` (Block A, Grid G-2)** and any other desiccated/disturbed surface areas across the $11,400\text{ sf}$ pad.
2. **Full-Depth Nuclear-Gauge Retesting of Reworked Lift 6 (Articles 3.3.C, 3.4.B, 3.4.C.2)**: Vantree must retest all reworked Lift 6 areas per ASTM D6938 direct-transmission mode using a probe depth penetrating the full $7.2\text{-in}$ compacted lift thickness, demonstrating simultaneous compliance with **$\gamma_d \ge 121.98\text{ pcf}$ ($122.0\text{ pcf}$; $\ge 95.0\%$ of $128.4\text{ pcf}$)** and **$8.2\% \le w \le 11.2\%$** at every location.
3. **Reissued Lift 6 Field Density Report (Articles 1.4.B, 1.5.B.1, 3.7.B, 3.7.C)**: Vantree must supersede Report `SF-26-0708` with a PE-sealed report carrying the governing ASTM D1557 Method C denominators from `VMT-25-0918-P04` ($\gamma_{d,\max} = 128.4\text{ pcf}$, $w_{\text{opt}} = 9.2\%$), recalculated percent compaction, moisture deviation from optimum, dual-criterion pass/fail dispositions for all original and retest points, and confirmation of technician J. Rennick's radiation safety/ASTM D6938 qualification records.
4. **Preceding Lift Reports `FDR-BA-01` Through `FDR-BA-05` and Test ID Reconciliation (Articles 1.5.B.1, 1.6.B, 3.7.A.1, 3.7.B, 3.7.C)**: Complete copies of `FDR-BA-01 through FDR-BA-05` for Lifts 1–5 must be submitted and audited to confirm at least 3 passing tests per lift (reconciling the 15-test log count vs. Lift 6 starting at `FD-14`) and compliance with both $\ge 122.0\text{ pcf}$ dry density and $8.2\%\text{ to }11.2\%$ moisture against `VMT-25-0918-P04`.
5. **RFI 079 Stockpile Gradation Retest & Placed-Material Correspondence Documentation (Articles 1.3.E, 1.4.C, 1.5.A.1–2, 2.1.A–D, 3.7.A.2, 3.7.C)**: Submission of the sieve gradation, Atterberg limits, and USCS classification test report required by **RFI 079 (`TPM-25-079`)** for the stockpile north of Block C confirming compliance with Article 2.1.A–B (SM / SW-SM, $\le 12\%$ passing No. 200, $\text{PI} \le 6$) and material correspondence with `VMT-25-0918-P04` (or a stockpile-specific ASTM D1557 Method C Proctor if different).
6. **Subgrade Acceptance Memo (`TPM-26-063`, `06/18/2026`), Test-Strip Report (`06/19/2026`), Updated Placement Log (`RB-FPR-BA-2026` Rev.1), and Closure of RFI 125 (Articles 1.6.A, 3.2.B, 3.4.A, 3.8.A)**: Filing of memo `TPM-26-063` and the `06/19/2026` test-strip verification report, an updated Contractor placement log recording the Lift 6 rework/retests and surface protection, and formal closure of **RFI 125** confirming that Article 3.4.B/D requires both density and moisture compliance at every test location.
7. **Written Thelbridge Materials Acceptance Record (`ACCEPTED`) Closing Item 054**: Issuance of a superseding signed Thelbridge Materials Acceptance Record releasing the hold point per the Owner's `07/06/2026` Verification Directive before the `07/20/2026` closure deadline and the `07/22/2026` hold point.