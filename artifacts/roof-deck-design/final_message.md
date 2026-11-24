I have completed the roof deck design and delivered the archive at:

- **`/filesystem/final_batch4__structural_task7_roof_deck_design__blind/output/submission.zip`**

At its root, `submission.zip` contains the four required deliverables:
1. **`deck_design.xlsx`** — Complete multi-sheet design workbook (`Zones`, `DesignBasis`, `Drifts`, `CalcSummary`, `Diaphragm`, `BOM`).
2. **`roof_deck_plan.dxf`** — Roof deck framing and zoning plan in project grid coordinates (feet), with closed `LWPOLYLINE` zone rectangles on layer `S-DECK-ZONE`, `TEXT` zone labels inside each zone on layer `S-DECK-TEXT`, roof framing on layer `S-FRAMING`, and framed openings (`RO-1`, `RO-2`, `RO-3`) on layer `S-OPENING`.
3. **`constraint_register.xlsx`** — Governing project and code constraint register (`Register` sheet with columns `document`, `clause`, `value`, `applies_to`).
4. **`design_basis.md`** — Engineering narrative documenting governing document precedence and conflict resolution, gravity/snow/drift calculations, wind uplift and seismic diaphragm basis, finite-element semi-rigid diaphragm analysis, and cost-optimized zoning decisions.

---

### Key Engineering Results

#### 1. Governing Documents & Design Basis (`DesignBasis`)
- **Precedence**: Per Transmittal `T-118` (`2026-08-01`) and Owner's Basis of Design `OBD-DC2-A Rev A` (`Section 9`), `EOR-DC-RD-01 Rev 2` (`2026-07-31`), the 3D structural coordination model (`DC2-A-STR Rev C`), `A-201 Rev C`, `M-401 Rev C`, `S-101 Rev 3`, `S-501 Rev 2`, `LAT-2026-003 Rev 1`, `SNOW-2026-014 Rev 0`, and the 2026 ASCE 7-22 Risk Category III Site Class D USGS seismic data govern over superseded Rev 1 criteria, Rev B drawings, single-station Canyon Ferry records, and 2019 preliminary/archival files.
- **Snow & Gravity Basis**:
  - `PG_PSF = 63` psf, `CE = 0.90`, `CT = 1.00`, `IS = 1.10`, `PF_PSF = 43.66` psf, `GAMMA_PCF = 22.19` pcf (`hb = 1.968` ft).
  - `LR_PSF = 20` psf (unreduced per `UFC 3-301-01 Table E-1 Item 51` and `EOR-DC-RD-01 Rev 2 Clause 4.2` for deck panel tributary area `18 sf <= 200 sf`).
- **Wind & Seismic Basis**:
  - `QH_PSF = 29.93` psf (`V = 115` mph, Exposure C, `h = 32` ft), `A_ZONE_FT = 12.8` ft (`2a = 25.6` ft), C&C net uplift pressures `-32.3` psf (Zone 1'), `-47.3` psf (Zone 1), `-74.2` psf (Zone 2), `-101.2` psf (Zone 3).
  - `SDS = 0.44`, `IE = 1.25`, `R = 3.25`, `W_SEISMIC_PSF = 26.73` psf (`18.0 psf` dead load `+ 0.20 * 43.66 psf` snow load since `pf > 30 psf`), `FPX_KIP = 195.43` kip (`Cs = 0.1692`, `W = 1,154.82` kip).
  - `WIND_X_KIP = 118.0` kip, `WIND_Y_KIP = 152.0` kip, `DIAPHRAGM_CLASS = semi-rigid`.

#### 2. Governing Snow Drift Surcharges (`Drifts`)
| Location | Face | Peak Surcharge (`psf`) | `band_from_ft` | `band_to_ft` | Governing Drift Condition |
|---|---|---:|---:|---:|---|
| `MEP-PH-1` | `W` | `104.28` | `60.0` | `41.20` | Leeward drift (`lu = 120.0` ft E-W enclosure length, `hd = 4.70` ft) |
| `SCR-N` | `S` | `89.48` | `164.0` | `147.85` | Windward drift (`lu = 164.0` ft south fetch, `0.75 hd = 4.035 ft > hc = 4.032` ft, truncated) |
| `PARAPET` | `N` | `34.01` | `180.0` | `167.74` | Windward drift (`lu = 180.0` ft south fetch, `h = 3.5` ft, truncated at `hc = 1.532` ft, `w = 8 hc = 12.26` ft) |
| `RTU-1` | `E` | `98.17` | `36.0` | `53.70` | Windward drift (`lu = 204.0` ft east fetch from `x = 240` to `36` ft, `0.75 hd = 4.42` ft) |

#### 3. Roof Deck Zoning (`Zones` & `CalcSummary`) & Bill of Materials (`BOM`)
- The `40 × 30` grid (`1,200` cells of `6 ft × 6 ft`, minus `28` cells removed by framed openings `RO-1`, `RO-2`, `RO-3` = `1,172` deck cells = `42,192 sf`) is partitioned into **5 zones (`Z1`–`Z5`)** across **14 non-overlapping rectangles** using **2 stock deck gages (`18` and `22` gage)** and **3 attachment patterns**:
  - **`Z1`** (`18 ga`, `36/9`, `3` sidelap screws/span; `2` rectangles: `[0, 18] × [0, 180]` and `[210, 240] × [0, 180]`, `8,640 sf`): Covers all four Wind Zone 3 corners (`101.2 psf` uplift) and the high-shear East collector bay adjacent to `BF-Y3`/`BF-Y4` and `RO-3` (`governing_scenario = S08`).
  - **`Z2`** (`18 ga`, `36/7`, `3` sidelap screws/span; `7` rectangles, `16,560 sf`): Covers the high snow-drift bands around `MEP-PH-1`, `SCR-N`, `SCR-E`, and the RTUs, as well as the perimeters of framed openings `RO-1`, `RO-2`, and `RO-3` (`governing_scenario = S02`).
  - **`Z3`** (`18 ga`, `36/4`, `2` sidelap screws/span; `1` rectangle: `[42, 66] × [48, 132]`, `2,016 sf`): Interior west drift band of `MEP-PH-1` outside all perimeter and opening boundary zones (`governing_scenario = S02`).
  - **`Z4`** (`22 ga`, `36/9`, `3` sidelap screws/span; `2` rectangles: `[18, 210] × [0, 24]` and `[18, 210] × [168, 180]`, `6,912 sf`): North and South Wind Zone 2 perimeter bands outside the corners (`governing_scenario = S04`).
  - **`Z5`** (`22 ga`, `36/7`, `3` sidelap screws/span; `2` rectangles: `[18, 42] × [48, 132]` and `[66, 180] × [60, 120]`, `8,856 sf`): Low-drift interior roof areas (`governing_scenario = S08`).
- **BOM Quantities**:
  - `deck area 18 gage`: **`26,424 sf`**
  - `deck area 22 gage`: **`15,768 sf`**
  - `support fasteners`: **`17,800 ea`**
  - `sidelap connectors`: **`6,920 ea`**