### Summary of Work and Results

#### 1. Target Deliverable Path and Structure
- Target archive path: `/filesystem/final_batch4__electrical_task17_ec_0205_d100__blind/output/submission.zip` (note: time expired during the final coordinate reconciliation step before the zip archive was written to disk; all underlying data, symbol detections, coordinate transformations, and calculations are recorded in `/tmp/.ple_work_ea0198f990cc/`).
- Required archive contents: `takeoff.csv`, `locations.csv`, `bom.csv`, `register.csv`, and `basis.md`.

---

#### 2. Key Results — Device Takeoff (`takeoff.csv`)

From `E-001` (Symbol Legend), `E-002` (Device and Mounting Schedule), the device plans (`E-201`..`E-204`, `E-211`), the enlarged plans (`E-231`..`E-233`), `A-101`, `A-102`, `A-601`, `M-101` (Revision 2, dated `2026-08-03`), and `ADD-02` (dated `2026-08-07`, governing over Revision 2 of `E-201` dated `2026-07-27`):

| `type_mark` | `description` | `quantity` | Basis Summary |
|---|---|---:|---|
| `R1` | `RECEPTACLE, DUPLEX, 20 A, 125 V, WALL-MOUNTED` | **47** | Drawn across `E-201`..`E-204` and `E-231`..`E-233`, minus the duplex receptacles deleted in the Revision 2 cloud in Grid Bay `A1` on `E-201` per `ADD-02 Item 02-1` |
| `R2` | `RECEPTACLE, QUADRAPLEX, 20 A, 125 V, WALL-MOUNTED` | **10** | `2` drawn on `E-202`, `3` on `E-232`, `3` on `E-233`, plus `2` added in Grid Bay `A1` on `E-201` at the first and second deleted `R1` positions measured from the south per `ADD-02 Item 02-1` |
| `R3` | `RECEPTACLE, DUPLEX, GFCI, 20 A, 125 V, WALL-MOUNTED` | **7** | `2` drawn on `E-231`, `3` on `E-232`, `2` on `E-233` |
| `R4` | `RECEPTACLE, DUPLEX, ISOLATED GROUND, 20 A, 125 V, ORANGE` | **6** | `4` drawn on `E-202`, `2` on `E-233` |
| `R5` | `RECEPTACLE, DUPLEX, WEATHER-RESISTANT, WITH EXTRA-DUTY WHILE-IN-USE COVER` | **20** | `4` drawn in the Entry Vestibule on `E-201` (`DAMP`) + `16` required by Keynote `<2>` on `E-201` (`4` perimeter CRAH + `12` in-row CRAH on `A-601` Rev 2, carried under `DRY-STUD`) |
| `R6` | `RECEPTACLE, DUPLEX, 20 A, 125 V, EMERGENCY BRANCH, RED` | **4** | `1` drawn on `E-201`, `1` on `E-203`, `1` on `E-231`, `1` on `E-233` |
| `R7` | `BOX, OUTLET, FLOOR, TWO-GANG, IN ACCESS FLOOR` | **8** | `1` drawn on `E-232`, `1` on `E-233` + `6` required by Keynote `<3>` on `E-201` (`1` at each of the `6` PDUs on `A-601`) |
| `R8` | `RECEPTACLE, LOCKING, NEMA L6-30R, 30 A, 250 V, WALL-MOUNTED` | **0** | Scheduled on `E-001`/`E-002`; zero instances on any plan (`E-05`) |
| `J1` | `BOX, JUNCTION, 100 X 100 X 38 MM, ABOVE CEILING, WITH BLANK COVER` | **38** | `11` on `E-201`, `7` on `E-202`, `7` on `E-203`, `8` on `E-204`, `4` on `E-231`, `1` on `E-232` |
| `P1` | `BOX, PULL, 300 X 300 X 150 MM, SURFACE` | **6** | `1` on `E-201`, `1` on `E-202`, `1` on `E-203`, `1` on `E-231`, `1` on `E-232`, `1` on `E-233` |
| `F1` | `APPLIANCE, NOTIFICATION, VISIBLE, WALL-MOUNTED` | **12** | `8` required by Keynote `<1>` on `E-201` (`4` North + `4` South structural column bays, `DRY-MASONRY`) + `4` required by Keynote `<4>` on `E-211` (`4` exit doors with `EGRESS = YES` on `A-102`: `D-01` & `D-02` in `P-R1` -> `RATED-2HR`; `D-04` in `W-W` & `D-05` in `W-E` -> `DRY-STUD`; `D-03` has `EGRESS = NO`) |
| `F2` | `APPLIANCE, NOTIFICATION, AUDIBLE/VISIBLE, WALL-MOUNTED` | **4** | `1` drawn on `E-211`, `2` on `E-231`, `1` on `E-233` |
| `F3` | `STATION, MANUAL PULL, ADDRESSABLE, WALL-MOUNTED` | **3** | `2` drawn on `E-211`, `1` on `E-233` |
| `F4` | `DETECTOR, SMOKE, PHOTOELECTRIC, ADDRESSABLE, CEILING-MOUNTED` | **6** | `6` drawn on `E-211` |
| `F5` | `DETECTOR, SMOKE, PHOTOELECTRIC, ADDRESSABLE, UNDER ACCESS FLOOR` | **18** | `15` drawn on `E-211`, `2` on `E-232`, `1` on `E-233` |
| `F6` | `DETECTOR, SMOKE, PROJECTED BEAM, PAIR (TRANSMITTER AND RECEIVER)` | **0** | Scheduled on `E-001`/`E-002`; zero instances on any plan (`E-05`) |
| `D1` | `DETECTOR, SMOKE, DUCT, FURNISHED BY DIV 23, WIRED UNDER DIV 28` | **27** | `25` drawn on `E-211`, `1` on `E-231`, `1` on `E-232` |

---

#### 3. Unresolved Symbols (`E-06`)
- **`E-211` (Fire Alarm Device Plan)**: **9** unscheduled circle-with-cross (`⊕`) symbols inside the Data Hall at `(y, x)` = `(1062, 606)` in `C1`, `(1062, 1078)` in `C1`, `(1062, 2496)` in `C3`, `(1565, 1077)` in `B1`, `(1565, 2021)` in `B3`, `(2479, 606)` in `A1`, `(2573, 1077)` in `A1`, `(2573, 2021)` in `A3`, and `(2573, 2495)` in `A3`, plus **1** unscheduled square-with-diagonal-cross (`☒`) symbol at `(1564, 2495)` in `B3`.
- **`E-231` (Enlarged Electrical Plan `ELEC 2/7`)**: **1** unscheduled large square-with-cross (`54x55 px`) symbol at `(1369, 1920)` (`A102 = (2447, 456)`, Grid Bay `A1`).
- **`E-233` (Enlarged Electrical Plan `PDU 4/7`)**: **1** unscheduled circle-with-tick symbol at `(951, 1112)` (`A102 = (1592, 2977)`, Grid Bay `B4`).
- Per convention `C6` and clause `E-06`, zero quantity is carried for these symbols in `takeoff.csv` and `bom.csv`.

---

#### 4. Condition Precedence, Assemblies, and Pricing Method (`bom.csv`)
- **Precedence**:
  1. Schedule `E-002` branch/mounting conditions take precedence: `R6` -> `EMERGENCY`; `R4` -> `IG`; `J1`, `F4`, and `D1` -> `CEILING`; `R7` and `F5` -> `ACCESS-FLOOR`.
  2. Drawn devices inside areas hatched `DAMP` on `A-102` take `DAMP` (`4` drawn `R5` receptacles in the Entry Vestibule on `E-201`).
  3. All other drawn wall-conditioned devices take the construction of the nearest wall centreline on `A-102` (`P1` -> `DRY-STUD`, `P2` -> `DRY-MASONRY`, `P3` -> `RATED-2HR`).
  4. Unshown keyed-note devices take the construction of the wall named by the note (`Keynote <1>` -> `DRY-MASONRY`; `Keynote <4>` -> `2 RATED-2HR` + `2 DRY-STUD` per `A-102` Door Schedule) or `DRY-STUD` where no wall is named (`Keynote <2>` -> `16 R5` in `DRY-STUD`).
- **While-in-Use Weatherproof Hood**: Required by `spec/26_20_00 §2.2` and `spec/26_05_33 §2.5` for `R5` / `DAMP`, but absent from `product_data/device_catalogue_2026.md`; noted as a catalogue omission with no line item carried in `bom.csv`.
- **Pricing, Spare Stock, and Carton Rounding**:
  - Attribution rows (`for_type_mark` = device type mark) carry `Q_req(item, m, c)` priced at the tier band earned by the item's total work quantity `Q_req(item)` across the project (`E-16`).
  - Purchase rows (`for_type_mark = (PURCHASE)`, `condition = (STOCK)`) carry `Q_buy(item) = ceil(1.05 * Q_req(item) / carton_qty) * carton_qty` (5% owner spare stock per `OPR §4` / `E-18`, rounded up to full cartons per `E-17`).