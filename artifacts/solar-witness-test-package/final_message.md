The canonical facts registry (`/tmp/.ple_work_e8bb012aebfb/facts.json`) and the deliverable (`Municipal_Witness_Test_Package.docx`) have been reconciled and verified with zero mismatches across all fields.

---

### 1. Deliverable Filed

- **Word Document:** `Municipal_Witness_Test_Package.docx`
  - **Nextcloud Document Store Path:** `/DER_Program/Commissioning/Municipal/Municipal_Witness_Test_Package.docx`
  - **Local Container Filesystem Path:** `/filesystem/Commissioning/Municipal/Municipal_Witness_Test_Package.docx`
- **Case Tracking (OpenProject — Project `DER Program Backlog Review`, Project ID `3`):**
  - **Batch Case Closed:** **Work Package `#45`** (*Process the municipal witness-test waiver batch*) — Updated with the full batch determination (in both the case description and activity log comment), linked to the three standing witness-test scheduling items, and closed (`Status: Closed`, `100%` complete).
  - **Standing Witness-Test Scheduling Items Logged (Linked to Case `#45`):**
    - **Work Package `#47`** (*Schedule on-site witness test — Darnwick Elementary School Array (640 kW, Arvexa PV-750)*, Relation `#8`)
    - **Work Package `#48`** (*Schedule on-site witness test — Holcott Public Library Array (510 kW, Selvix SV-720)*, Relation `#9`)
    - **Work Package `#49`** (*Schedule on-site witness test — Lockmere Middle School Array (720 kW, Selvix SV-720)*, Relation `#10`)

---

### 2. Batch Scope Determination as of `07/14/2025`

Of the six municipal arrays covered by `Checklist_Cravenwood_High.pdf` through `Checklist_Tresbay_Community_Center.pdf` (all pre-marked as waiver-eligible at submission):

- **Out of Scope (1 Array):**
  - **Tresbay Community Center Array** (`560 kW` AC, Town of Tresbay, `PXA-2025-0061`, `Checklist_Tresbay_Community_Center.pdf` / `COMM-2025-TRB-01`): **Withdrew its request on `07/09/2025`** per DER Program Office case tracking (Case `#45`) and is out of scope for the batch on `07/14/2025`. *(For historical file completeness only: its cover-sheet inverter `Vexlar Energy VX-140C`, 4 × 140 kW, appears on `CEL-2025-Q2` Inverters tab Row 18, and its utility-owned RTU telemetry test to SOC under `TCS-02 §5` was `Pending` at the time of withdrawal.)*
- **In Scope (5 Arrays — all Commercial Small-Scale DER, `500 kW – 1 MW`, Category 2):**
  1. **Cravenwood High School Array** (`860 kW` AC, Cravenwood Community School District, `PXA-2024-0779`, Feeder `ALN-137`, `COMM-CK-CRV-HS-01`)
  2. **Darnwick Elementary School Array** (`640 kW` AC, Darnwick Community School District, `COMM-CHK-DARN-ELEM`)
  3. **Holcott Public Library Array** (`510 kW` AC, Town of Holcott, `CX-HOL-LIB-01`)
  4. **Lockmere Middle School Array** (`720 kW` AC, Lockmere Community School District, `PXA-2024-0793`, Feeder `ALN-152`, `COMM-LKM-MS-2025-06`)
  5. **Marden Falls Water Reclamation Facility Array** (`980 kW` AC, City of Marden Falls, `DER-CX-2025-0624-MFWRF`)

---

### 3. Call on `CEL-2025-Q2` Carriage & Witness-Test / Waiver Eligibility (`ENG-PRC-014 Rev 3 §3 & §4.1`)

Under `ENG-PRC-014 Rev 3` (*DER Witness Test & Waiver Procedure*, effective `04/30/2025`) §3 (and Corollaries 1–5) and §4.1, witness-test waiver eligibility is governed exclusively by whether the inverter or power conversion equipment **actually installed at the facility** appears in the body of the **current** Certified Equipment List (`CEL-2025-Q2`, published `04/30/2025`, superseding `CEL-2024-Q4` of `10/31/2024`). Per `ENG-PRC-014 Rev 3 §4.1 & §4.3`, the written waiver disposition itself stays with Standards Engineering (`Evan Solberg`).

| Array (In Scope on 07/14/2025) | Checklist Model vs. Equipment Actually Installed | Call on Carriage (`CEL-2025-Q2`) & Basis | Witness-Test / Waiver Call (`ENG-PRC-014 Rev 3`) | Case Tracking Scheduling Item |
|---|---|---|---|---|
| **Cravenwood High School Array** (`860 kW`, `PXA-2024-0779`, `COMM-CK-CRV-HS-01`) | Checklist & Installed: `Solmery Power SM-215K-3P` (`4 × 215 kW`, verified on site `06/17/2025`) | **CARRIED** — Listed in `CEL-2025-Q2`, `Inverters` tab, **Row 6** (215 kW, UL 1741-SB, effective `11/18/2024`) | **Waiver Eligible** (`§3, §4.1`); no on-site witness test required. Forwarded to Standards Engineering (`Evan Solberg`) for written waiver disposition (`§4.1, §4.3`). | None required (Recorded on Case `#45`) |
| **Marden Falls Water Reclamation Facility Array** (`980 kW`, `DER-CX-2025-0624-MFWRF`) | Checklist & Installed: `Solmery Power SM-245K-3P` (`4 × 245 kW`, verified on site `06/24/2025`) | **CARRIED** — Listed in `CEL-2025-Q2`, `Inverters` tab, **Row 7** (245 kW, UL 1741-SB, effective `01/27/2025`) | **Waiver Eligible** (`§3, §4.1`); no on-site witness test required. Forwarded to Standards Engineering (`Evan Solberg`) for written waiver disposition (`§4.1, §4.3`). | None required (Recorded on Case `#45`) |
| **Darnwick Elementary School Array** (`640 kW`, `COMM-CHK-DARN-ELEM`) | Checklist & Installed: `Arvexa PV-750` (walkdown `06/15/2025` by `M. Halbrook, P.E.`) | **NOT CARRIED** — `Arvexa PV-750` is absent from `CEL-2025-Q2` (and was never listed on `CEL-2024-Q4`). Pre-marked Section 6 waiver box was an unverified batch copy-forward (flagged on commissioning wiki Comment `#13` by `Evan Solberg`). | **Ineligible for Waiver — On-Site Witness Test Required** prior to PTO (`§3 Corollary 2, §4.1, §4.2`). | **Work Package `#47`** (Linked to Case `#45`) |
| **Holcott Public Library Array** (`510 kW`, `CX-HOL-LIB-01`) | Checklist & Installed: `Selvix SV-720` (Footnote 1 cited superseded `CEL-2024-Q4`) | **NOT CARRIED** — Appeared only on superseded `CEL-2024-Q4` (`Inverters` Row 29, `10/31/2024`) and was delisted/removed from `CEL-2025-Q2` (`04/30/2025`; Front Matter Row 22, Notes Rows 6–8; flagged on commissioning wiki Comment `#12` by `Evan Solberg`). | **Ineligible for Waiver — On-Site Witness Test Required** prior to PTO (`§3 Corollaries 1, 3, 4, 5 & §4.1, §4.2`). | **Work Package `#48`** (Linked to Case `#45`) |
| **Lockmere Middle School Array** (`720 kW`, `PXA-2024-0793`, `COMM-LKM-MS-2025-06`) | Checklist (`06/18/2025`): `4 × Torvane Electric TE-180K` (`CEL-2025-Q2` Row 14)<br>**Actually Installed:** **`Selvix SV-720`** (substituted on site after checklist submission per commissioning wiki Comment `#15` by `Evan Solberg`) | **NOT CARRIED** — Under `ENG-PRC-014 §2, §3 Corollary 2, & §4.1`, eligibility depends on the inverter actually installed on site (`Selvix SV-720`), which was delisted/removed from `CEL-2025-Q2` after superseded `CEL-2024-Q4` (Row 29). | **Ineligible for Waiver — On-Site Witness Test Required** prior to PTO (`§2, §3 Corollaries 1, 2, 3, 5 & §4.1, §4.2`). | **Work Package `#49`** (Linked to Case `#45`) |

---

### 4. Witness-Test Scope & Scheduling Package Summary (Non-Carried Arrays: Darnwick Elementary `#47`, Holcott Public Library `#48`, Lockmere Middle `#49`)

- **Tests to Be Performed & Basis (`ENG-PRC-014 Rev 3 §4.2`, `IEEE 1547.1`, `IEEE 1547-2018 Clause 4`, `DIS-01 Rev 4 §5 Table 5-1 Category 2 & §6`, `DPS-07 Rev 2`):**
  1. **Protective-Function Trip & Reconnect Timing Tests:** On-site verification of under-/over-voltage (`ANSI 27/59`) and under-/over-frequency (`ANSI 81U/81O`) trip pickup magnitudes and clearing times, post-disturbance reconnect window and reconnect delay timer, and feeder/service protection coordination against the approved site settings sheet and coordination study (including at Lockmere Middle: verification of `27/59`, `81U/81O`, `25`, `32` elements, DER breaker local/remote trip from the substituted `Selvix SV-720` auxiliary relay, and POI recloser reclose-block interlock on Feeder `ALN-152`, since Sections 2 and 3 of `COMM-LKM-MS-2025-06` were recorded against the replaced `Torvane TE-180K` units).
  2. **Anti-Islanding Function Test:** Live open-utility / loss-of-grid unintentional islanding test per `IEEE 1547.1` confirming the installed inverter (`Arvexa PV-750` at Darnwick Elementary; `Selvix SV-720` at Holcott Public Library and Lockmere Middle) detects islanding and ceases to energize within `≤ 2.0 seconds` (`DIS-01 Rev 4 §5 Table 5-1 Category 2 & §6`).
  3. **Voltage and Frequency Ride-Through (VRT / FRT) & Voltage-Support Verifications:** Verification of programmed Category II voltage and frequency ride-through profiles and active/reactive power control settings against the approved settings sheet (`DIS-01 Rev 4 §6`), plus verification at Lockmere Middle that utility RTU `RTU-LKM-171-04` polls and reports valid live points from the substituted `Selvix SV-720` gateway (`TCS-02 §3.3(a), §3.6, §5`).
- **Who Schedules, Performs, and Witnesses (`ENG-PRC-014 Rev 3 §4.2, §4.3`):**
  - **Scheduled / Coordinated By:** Alleniom Utilities DER Program Commissioning Coordinator.
  - **Performed / Operated By:** The Customer (**Darnwick Community School District**, **Town of Holcott**, and **Lockmere Community School District** — `P. Ashworth`, Facilities Director) and each customer's qualified **Commissioning Agent / contractor of record** (coordinated with Alleniom Field Engineers `M. Halbrook, P.E.` [`AFE-1042`] and `K. Ondras` [`AFE-2231`]), who supply the written test plan, calibrated test instrumentation, and qualified personnel to operate the equipment.
  - **Witnessed, Recorded & Dispositioned By:** **Alleniom Utilities Witness Engineer** from **Standards Engineering** (`Evan Solberg`, Standards Engineer, or designated Alleniom witness engineer), who observes on site, records calibrated instrument identifiers and measured values, assigns pass/fail dispositions per test point, and signs and dates the formal witness test record (`ENG-PRC-014 §4.3`).
- **What Has to Be on File First (`ENG-PRC-014 Rev 3 §4.1–§4.3`, `DIS-01 Rev 4 §7`, `TCS-02 §3.6, §5`):**
  - **Prior to Conducting the On-Site Witness Test:**
    1. Updated commissioning checklists (`COMM-CHK-DARN-ELEM`, `CX-HOL-LIB-01`, `COMM-LKM-MS-2025-06`) recording `CEL-2025-Q2` as consulted, documenting that the installed inverter is not carried, and re-marking each checklist from `"waiver eligible"` to `"witness test required"` (`ENG-PRC-014 §4.1, §4.3`), plus the pending Field Services Supervisor sign-off on `CX-HOL-LIB-01`.
    2. **Specific to Lockmere Middle (`COMM-LKM-MS-2025-06`, `PXA-2024-0793`):** Written ISA change-order documentation under `DIS-01 Rev 4 §7` (*Other post-execution changes* — equipment model substitution within the same `720 kW` nameplate rating and same POI on Feeder `ALN-152`), revised as-built single-line diagram and equipment schedule, and revised Checklist Sections 2 and 3 replacing the removed `4 × Torvane Electric TE-180K` serial numbers (`TE180K-24-11482 / -11487 / -11491 / -11502`) and firmware (`Torvane FW 4.11.02`) with the installed `Selvix SV-720` serial number(s), firmware, and approved settings sheet.
    3. Verified construction-complete walkdown record, approved single-line diagram, approved protection settings sheet / coordination study, customer/commissioning agent written `IEEE 1547.1` witness test plan, current test-instrument calibration certificates/identifiers, operator qualifications, scheduling correspondence (`ENG-PRC-014 §4.2, §4.3`), and manufacturer certificates of conformance / factory test reports (`ENG-PRC-014 §4.3`).
  - **Prior to SOC Release / PTO Issuance:**
    1. Signed Alleniom witness engineer test record with passing dispositions across all test points (`ENG-PRC-014 §4.2, §4.3` — no post-PTO deferral or conditional PTO permitted).
    2. Live utility-owned RTU and SCADA telemetry confirmed at the SOC operator display by SOC Shift Supervisor `Lena Kovalchuk` per `TCS-02 §3.6, §5` (requiring RTU allocation, installation, backhaul provisioning, and end-to-end point verification at Darnwick Elementary [Section 5 `Pending`] and Holcott Public Library [Section E-1, E-2, E-4 `Pending`], and re-confirmation of active `RTU-LKM-171-04` polling with the substituted `Selvix SV-720` gateway at Lockmere Middle).

---

### 5. List of Arrays the System Operations Center (SOC) Can Be Asked to Release as of `07/14/2025`

- **Eligible for SOC Release for Permission to Operate (PTO) on the `07/14/2025` Record (1 Array):**
  - **Marden Falls Water Reclamation Facility Array (`980 kW` AC, City of Marden Falls, `Checklist_Marden_Falls_WRF.pdf` / `DER-CX-2025-0624-MFWRF`):** The **only** array in the batch that satisfies both `CEL-2025-Q2` carriage (`Solmery Power SM-245K-3P`, `Inverters` Row 7 — waiver-eligible under `ENG-PRC-014 §3, §4.1`) **and** `TCS-02 §5` live telemetry (`Pass` on `06/24/2025`: utility-owned RTU installed and provisioned; SCADA points verified end-to-end with SOC). SOC can be asked to release Marden Falls WRF for PTO immediately upon Standards Engineering (`Evan Solberg`) signing the pending waiver disposition block on `DER-CX-2025-0624-MFWRF` (`ENG-PRC-014 §4.1, §4.3`).
- **Arrays That Cannot Be Released by SOC for PTO on `07/14/2025` (4 In-Scope Arrays + 1 Withdrawn Array):**
  - **Cravenwood High School Array (`860 kW` AC, `PXA-2024-0779`, `COMM-CK-CRV-HS-01`):** Carried on `CEL-2025-Q2` (`Inverters` Row 6) and waiver-eligible as to the witness test, **but blocked from SOC PTO release by `TCS-02 §5`** because Checklist Section 5 (items 5.1–5.4: utility-owned RTU installation, SCADA point map load, end-to-end point check with SOC, and comm path test) remains **`Pending`**.
  - **Lockmere Middle School Array (`720 kW` AC, `PXA-2024-0793`, `COMM-LKM-MS-2025-06`):** Has utility RTU `RTU-LKM-171-04` installed (`06/12/2025`) and SCADA verified (`06/17/2025`, `TKT-25-04188`), **but blocked from SOC PTO release by `ENG-PRC-014 §3, §4.2, §4.3`** because the post-checklist substituted `Selvix SV-720` is not carried on `CEL-2025-Q2` and requires an on-site witness test prior to PTO (Work Package `#49`).
  - **Darnwick Elementary School Array (`640 kW` AC, `COMM-CHK-DARN-ELEM`):** Blocked by **both** `ENG-PRC-014 §4.2, §4.3` (on-site witness test required — Work Package `#47`) **and** `TCS-02 §5` (Section 5 items 5.1–5.4 `Pending`; RTU allocation not yet scheduled).
  - **Holcott Public Library Array (`510 kW` AC, `CX-HOL-LIB-01`):** Blocked by **both** `ENG-PRC-014 §4.2, §4.3` (on-site witness test required — Work Package `#48`) **and** `TCS-02 §5` (Section E items E-1, E-2, E-4 `Pending`; utility RTU not yet allocated or installed).
  - **Tresbay Community Center Array (`560 kW` AC, `PXA-2025-0061`, `COMM-2025-TRB-01`):** **Out of Scope** — withdrew request on `07/09/2025`.