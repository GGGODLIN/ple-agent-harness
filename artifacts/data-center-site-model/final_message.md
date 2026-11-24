OPTIMIZATION_CONVERGED

### Final Summary (`submission/model.ifc`)

I ran a self-checked Python catalog optimization script (`/tmp/optimize_campus.py`, including `assert` checks verifying both a nominal feasible design pass and a violated-constraint failure) and updated **`submission/model.ifc`** via same-directory `submission/._ple_stage_model.ifc` + `os.replace`, followed by a full round-trip IFC4 STEP parse and 17-requirement verification (`/tmp/roundtrip_validate_ifc.py`).

#### 1. Deliverable Path
- **`submission/model.ifc`**: Valid IFC4 STEP Physical File (`148` entities) containing `IfcProject`, `IfcSite`, 7 `IfcBuilding` entities with extruded 3D solids (`IfcExtrudedAreaSolid`), aggregated `IfcBuildingStorey` entities, `DCD_Layout` property sets, and the `DCD_Networks` JSON payload on `IfcSite`.

#### 2. Optimized Building Placements & Massing
- **`DH_P1`** (`data_hall`, Phase 1): Rectangle `[83.5, 31.5]` to `[174.0, 81.5]` (`90.5 × 50.0 m = 4,525.0 m²`, aspect ratio `1.81 ≤ 2.5`), 2 storeys (`0.0 m`, `4.5 m`), `HeightM = 9.0 m`, `GrossFloorAreaM2 = 9,050.0 m² ≥ 7,200 m²`.
- **`DH_P2`** (`data_hall`, Phase 2): Rectangle `[81.5, 188.0]` to `[172.0, 238.0]` (`90.5 × 50.0 m = 4,525.0 m²`, aspect ratio `1.81 ≤ 2.5`), 2 storeys (`0.0 m`, `4.5 m`), `HeightM = 9.0 m`, `GrossFloorAreaM2 = 9,050.0 m² ≥ 7,200 m²`.
- **`SUB`** (`substation`, Phase 1): 4-vertex convex parallelogram `[(186.0, 210.0), (210.0, 170.0), (236.0, 170.0), (212.0, 210.0)]` (`1,040.0 m² ≥ 1,000 m²`), 1 storey (`0.0 m`), `HeightM = 5.0 m`, `GrossFloorAreaM2 = 1,040.0 m²`.
- **`CTP`** (`cooling_plant`, Phase 1): Rectangle `[231.5, 182.0]` to `[259.5, 211.0]` (`28.0 × 29.0 m = 812.0 m² ≥ 800 m²`), 1 storey (`0.0 m`), `HeightM = 3.5 m`, `GrossFloorAreaM2 = 812.0 m²`.
- **`BRM`** (`berm`, Phase 1): 4-vertex convex trapezoid `[(243.0, 259.0), (298.0, 204.0), (298.0, 210.0), (249.0, 259.0)]` (`312.0 m² ≥ 300 m²`), 1 storey (`0.0 m`), `HeightM = 5.4 m`, `GrossFloorAreaM2 = 312.0 m²`.
- **`GEN`** (`generator_yard`, Phase 1): Rectangle `[276.0, 236.0]` to `[299.0, 258.0]` (`23.0 × 22.0 m = 506.0 m² ≥ 500 m²`), 1 storey (`0.0 m`), `HeightM = 3.3 m`, `GrossFloorAreaM2 = 506.0 m²`.
- **`RET`** (`stormwater_retention`, Phase 1): Rectangle `[20.0, 31.0]` to `[74.0, 63.0]` (`54.0 × 32.0 m = 1,728.0 m² ≥ 100 m²`), extruded `0.3 m` from `z = -0.3 m` to `z = 0.0 m`, 1 storey (`0.0 m`), `HeightM = 0.0 m`, `GrossFloorAreaM2 = 1,728.0 m²`.

#### 3. Optimized Networks & Objective Values
- **`road_p1`** (`road`, `width_m: 6.0`, `phase: 1`): `[[180.0, 0.0], [180.0, 215.0], [264.0, 224.0]]` (`299.48 m`).
- **`road_p2`** (`road`, `width_m: 6.0`, `phase: 2`): `[[180.0, 215.0], [178.0, 215.0]]` (`2.00 m`).
- **`mv_util`** (`mv_power`, `width_m: 0.0`, `phase: 1`): `[[320.0, 195.0], [236.5, 169.5], [210.0, 169.5]]` (`113.81 m`).
- **`mv_dh1`** (`mv_power`, `width_m: 0.0`, `phase: 1`): `[[210.0, 169.5], [195.0, 166.0], [174.5, 81.0]]` (`102.84 m`).
- **`mv_dh2`** (`mv_power`, `width_m: 0.0`, `phase: 2`): `[[210.0, 169.5], [172.5, 188.5]]` (`42.04 m`).
- **Phase 1 Weighted Cost (`1.0 × MV + 0.3 × Road`)**: `216.65 + 0.3 × 299.48 =` **`306.49 ≤ 314.0`** (`7.51` margin below cap).
- **Total Weighted Cost (`1.0 × MV + 0.3 × Road`)**: `258.69 + 0.3 × 301.48 =` **`349.13 ≤ 473.0`** (`123.87` below cap and `105.57` below `reference_cost = 454.7`).
- **Acoustic Performance**: Cumulative receptor sound levels are **`36.55 dB(A)`** (`R1`, Phase 1), **`38.35 dB(A)`** (`R2`, Phase 1), **`37.11 dB(A)`** (`R1`, Phase 1+2), and **`38.37 dB(A)`** (`R2`, Phase 1+2), all well below the **`42.35 dB(A)`** limit.