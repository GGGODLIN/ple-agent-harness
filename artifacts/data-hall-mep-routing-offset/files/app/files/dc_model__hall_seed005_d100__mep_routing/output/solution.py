#!/usr/bin/env python3
"""
Self-contained IFC4 BIM coordination and overhead MEP routing generator for
dc_model hall_seed005_d100.

Rebuilds the L-shaped data hall fit-out from the seven drawing sheets
(A-101, A-301, A-601, A-602, M-101, E-101, F-101) and routes the three
overhead MEP services (Telecom Cable Tray CT-1, Power Busway BW-1, and
Chilled-Water Pipe CHW-1) clash-free and code-compliant.
"""

import json
import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api


# ============================================================================
# 1. CANONICAL HALL GEOMETRY & SCHEDULE DATA (EXTRACTED FROM DRAWINGS)
# ============================================================================

# Room boundary polygon (mm): 27000 x 24000 L-shaped hall with 8400 x 8400 NE cutout
ROOM_POLYGON_2D = [
    (0.0, 0.0),
    (27000.0, 0.0),
    (27000.0, 15600.0),
    (18600.0, 15600.0),
    (18600.0, 24000.0),
    (0.0, 24000.0),
    (0.0, 0.0),
]

# Elevation datums (mm relative to Finished Floor = 0.0)
ELEV_STRUCTURAL_SLAB = -800.0
ELEV_ACCESS_FLOOR_BOTTOM = -35.0
ELEV_FINISHED_FLOOR = 0.0
ELEV_EQUIPMENT_TOP = 2000.0
ELEV_PDU_TOP = 1956.0
ELEV_CONTAINMENT_ROOF_BOTTOM = 2000.0
ELEV_CONTAINMENT_ROOF_TOP = 2055.0
ELEV_CONTAINMENT_DOOR_TOP = 2055.5
ELEV_IN_AISLE_SPRINKLER = 1990.0
ELEV_MIN_CLEAR_HEIGHT = 2600.0
ELEV_CEILING_SPRINKLER = 3025.0
ELEV_CEILING_SOFFIT = 3500.0

# 8 Structural Columns: 550 x 550 mm, 7200 mm grid offset +150 mm in X and Y from 600 mm tile grid
COLUMNS_DATA = [
    ("COL-B1", "B-1", "B", "1", 7350.0, 7350.0),
    ("COL-C1", "C-1", "C", "1", 14550.0, 7350.0),
    ("COL-D1", "D-1", "D", "1", 21750.0, 7350.0),
    ("COL-B2", "B-2", "B", "2", 7350.0, 14550.0),
    ("COL-C2", "C-2", "C", "2", 14550.0, 14550.0),
    ("COL-D2", "D-2", "D", "2", 21750.0, 14550.0),
    ("COL-B3", "B-3", "B", "3", 7350.0, 21750.0),
    ("COL-C3", "C-3", "C", "3", 14550.0, 21750.0),
]

# Cabinet type specifications (A-601 Table 4)
CABINET_TYPES = {
    "C1": {"desc": "Server Cabinet", "w": 600.0, "d": 1200.0, "h": 2000.0, "ru": 42, "kw": 8.0},
    "C2": {"desc": "Server Cabinet", "w": 600.0, "d": 1070.0, "h": 2000.0, "ru": 42, "kw": 8.0},
    "N1": {"desc": "Network Distribution Cabinet", "w": 800.0, "d": 1200.0, "h": 2000.0, "ru": 42, "kw": 8.0},
    "N2": {"desc": "Network Distribution Cabinet", "w": 800.0, "d": 1070.0, "h": 2000.0, "ru": 42, "kw": 8.0},
}

# Row schedules and bay compositions (A-601 Table 1 & A-101)
ROW_SCHEDULES = [
    {
        "row_id": "A",
        "row_name": "ROW A",
        "front_tile": "D05",
        "last_tile": "AJ05",
        "tile_row": 5,
        "y_south": 2400.0,
        "y_north": 3600.0,
        "depth": 1200.0,
        "height": 2000.0,
        "facing": "SOUTH",
        "kw_per_cab": 8.0,
        "total_kw": 208.0,
        "sequence": [
            ("C1", 4), ("CU", 1), ("C1", 4), ("N1", 1), ("C1", 4), ("CU", 1),
            ("CA", 1600.0),
            ("C1", 7), ("SP", 600.0), ("CU", 1), ("C1", 6),
        ],
    },
    {
        "row_id": "B",
        "row_name": "ROW B",
        "front_tile": "D10",
        "last_tile": "AI10",
        "tile_row": 10,
        "y_south": 5400.0,
        "y_north": 6470.0,
        "depth": 1070.0,
        "height": 2000.0,
        "facing": "NORTH",
        "kw_per_cab": 8.0,
        "total_kw": 168.0,
        "sequence": [
            ("C2", 4), ("CU", 1), ("C2", 3), ("SKIP", 1200.0), ("C2", 2), ("N2", 2), ("CU", 1),
            ("CA", 1400.0),
            ("C2", 2), ("SKIP", 1200.0), ("C2", 3), ("CU", 1), ("SP", 600.0), ("C2", 5), ("SKIP", 1200.0),
        ],
    },
    {
        "row_id": "C",
        "row_name": "ROW C",
        "front_tile": "D14",
        "last_tile": "AH14",
        "tile_row": 14,
        "y_south": 7800.0,
        "y_north": 9000.0,
        "depth": 1200.0,
        "height": 2000.0,
        "facing": "SOUTH",
        "kw_per_cab": 8.0,
        "total_kw": 160.0,
        "sequence": [
            ("C1", 4), ("CU", 1), ("C1", 3), ("SKIP", 1200.0), ("C1", 2), ("CU", 1), ("C1", 2),
            ("CA", 1800.0),
            ("N1", 1), ("SKIP", 1200.0), ("C1", 4), ("SP", 600.0), ("CU", 1), ("C1", 4), ("SKIP", 600.0),
        ],
    },
    {
        "row_id": "D",
        "row_name": "ROW D",
        "front_tile": "D19",
        "last_tile": "AK19",
        "tile_row": 19,
        "y_south": 10800.0,
        "y_north": 11870.0,
        "depth": 1070.0,
        "height": 2000.0,
        "facing": "NORTH",
        "kw_per_cab": 8.0,
        "total_kw": 216.0,
        "sequence": [
            ("C2", 5), ("CU", 1), ("C2", 3), ("N2", 2), ("C2", 3), ("CU", 1),
            ("CA", 1400.0),
            ("C2", 8), ("SP", 600.0), ("CU", 1), ("C2", 6),
        ],
    },
]

# 4 Perimeter CRAHs along South wall (A-601 Table 2)
PERIMETER_CRAHS = [
    ("CRAH-01", "PERIMETER", "B01", 600.0, 1800.0, 0.0, 900.0, 2000.0, 100.0, 20000.0, "NORTH", "CHILLED WATER, DN100", "DN100"),
    ("CRAH-02", "PERIMETER", "P01", 9000.0, 10200.0, 0.0, 900.0, 2000.0, 100.0, 20000.0, "NORTH", "CHILLED WATER, DN100", "DN100"),
    ("CRAH-03", "PERIMETER", "AC01", 16800.0, 18000.0, 0.0, 900.0, 2000.0, 100.0, 20000.0, "NORTH", "CHILLED WATER, DN100", "DN100"),
    ("CRAH-04", "PERIMETER", "AO01", 24000.0, 25200.0, 0.0, 900.0, 2000.0, 100.0, 20000.0, "NORTH", "CHILLED WATER, DN100", "DN100"),
]

# 4 PDUs (A-601 Table 3 & E-101): 762 W x 813 D x 1956 H, front face flush with served row front face
PDUS_DATA = [
    ("PDU-01", "A", "ROW A", "AN05", 23400.0, 23400.0 + 762.0, 2400.0, 2400.0 + 813.0, 1956.0, 275.0, "480/277V", "SOUTH", 900.0, 1800.0),
    ("PDU-02", "B", "ROW B", "AM10", 22800.0, 22800.0 + 762.0, 6470.0 - 813.0, 6470.0, 1956.0, 275.0, "480/277V", "NORTH", 900.0, 1800.0),
    ("PDU-03", "C", "ROW C", "AL14", 22200.0, 22200.0 + 762.0, 7800.0, 7800.0 + 813.0, 1956.0, 275.0, "480/277V", "SOUTH", 900.0, 1800.0),
    ("PDU-04", "D", "ROW D", "AO19", 24000.0, 24000.0 + 762.0, 11870.0 - 813.0, 11870.0, 1956.0, 275.0, "480/277V", "NORTH", 900.0, 1800.0),
]

# Cold-Aisle Containment CAC-R05 (A-602 Table 1, A-101, A-301): 4 roof panels + 4 end doors
CONTAINMENT_ROOFS = [
    ("CAC-R05-ROOF-01", 1800.0, 7075.0, 6375.0, 7895.0, 2000.0, 2055.0),
    ("CAC-R05-ROOF-02", 7625.0, 11200.0, 6375.0, 7895.0, 2000.0, 2055.0),
    ("CAC-R05-ROOF-03", 12600.0, 14275.0, 6375.0, 7895.0, 2000.0, 2055.0),
    ("CAC-R05-ROOF-04", 14825.0, 21000.0, 6375.0, 7895.0, 2000.0, 2055.0),
]

CONTAINMENT_DOORS = [
    ("CAC-R05-DOOR-01", 1740.0, 1800.0, 6470.0, 7800.0, 0.0, 2055.5),
    ("CAC-R05-DOOR-02", 11200.0, 11260.0, 6470.0, 7800.0, 0.0, 2055.5),
    ("CAC-R05-DOOR-03", 12540.0, 12600.0, 6470.0, 7800.0, 0.0, 2055.5),
    ("CAC-R05-DOOR-04", 21000.0, 21060.0, 6470.0, 7800.0, 0.0, 2055.5),
]

# ============================================================================
# 2. OVERHEAD MEP ROUTING GEOMETRY (3 SERVICES, 3 ELEVATION TIERS)
# ============================================================================
# Service Entry at West wall: X = 0.0 mm, Y = 12470.0 mm
# Tier 1: Telecom Cable Tray CT-1 (600 W x 125 H mm), Z in [2600.0, 2725.0], Z_c = 2662.5 mm
# Tier 2: Chilled-Water Pipe CHW-1 (OD 114.3 mm + 25.4 mm insul = 165.1 mm), Z_ins in [2767.45, 2932.55], Z_c = 2850.0 mm
# Tier 3: Power Busway BW-1 (120 W x 145 H mm), Z in [3030.0, 3175.0], Z_c = 3102.5 mm

Z_CT = 2662.5
Z_CHW = 2850.0
Z_BW = 3102.5

CT_SEGMENTS = [
    # (name, x1, y1, z1, x2, y2, z2, width, height, role)
    ("CT-SEG-01", 0.0, 12470.0, Z_CT, 2350.0, 12470.0, Z_CT, 600.0, 125.0, "Service Entry & West Row D Feeder"),
    ("CT-SEG-02", 2350.0, 12470.0, Z_CT, 2350.0, 12200.0, Z_CT, 600.0, 125.0, "North Spine Step"),
    ("CT-SEG-03", 2350.0, 12200.0, Z_CT, 2350.0, 9550.0, Z_CT, 600.0, 125.0, "Main Spine D to C"),
    ("CT-SEG-04", 2350.0, 9550.0, Z_CT, 2350.0, 4800.0, Z_CT, 600.0, 125.0, "Main Spine C to B"),
    ("CT-SEG-05", 2350.0, 4800.0, Z_CT, 2350.0, 2300.0, Z_CT, 600.0, 125.0, "Main Spine B to A"),
    ("CT-SEG-06", 2350.0, 12200.0, Z_CT, 19800.0, 12200.0, Z_CT, 600.0, 125.0, "Row D Header"),
    ("CT-SEG-07", 2350.0, 9550.0, Z_CT, 20000.0, 9550.0, Z_CT, 600.0, 125.0, "Row C Header"),
    ("CT-SEG-08", 2350.0, 4800.0, Z_CT, 19800.0, 4800.0, Z_CT, 600.0, 125.0, "Row B Header"),
    ("CT-SEG-09", 2350.0, 2300.0, Z_CT, 19800.0, 2300.0, Z_CT, 600.0, 125.0, "Row A Header"),
]

BW_SEGMENTS = [
    # (name, x1, y1, z1, x2, y2, z2, width, height, role)
    ("BW-SEG-01", 0.0, 12470.0, Z_BW, 2750.0, 12470.0, Z_BW, 120.0, 145.0, "Service Entry & West Row D Feeder"),
    ("BW-SEG-02", 2750.0, 12470.0, Z_BW, 2750.0, 8150.0, Z_BW, 120.0, 145.0, "Main Spine D to C"),
    ("BW-SEG-03", 2750.0, 8150.0, Z_BW, 2750.0, 5500.0, Z_BW, 120.0, 145.0, "Main Spine C to B"),
    ("BW-SEG-04", 2750.0, 5500.0, Z_BW, 2750.0, 3000.0, Z_BW, 120.0, 145.0, "Main Spine B to A"),
    ("BW-SEG-05", 2750.0, 12470.0, Z_BW, 19800.0, 12470.0, Z_BW, 120.0, 145.0, "Row D Header"),
    ("BW-SEG-06", 2750.0, 8150.0, Z_BW, 20000.0, 8150.0, Z_BW, 120.0, 145.0, "Row C Header"),
    ("BW-SEG-07", 2750.0, 5500.0, Z_BW, 19800.0, 5500.0, Z_BW, 120.0, 145.0, "Row B Header"),
    ("BW-SEG-08", 2750.0, 3000.0, Z_BW, 19800.0, 3000.0, Z_BW, 120.0, 145.0, "Row A Header"),
]

CHW_SEGMENTS = [
    # (name, x1, y1, z1, x2, y2, z2, bare_od, insul_od, role)
    ("CHW-SEG-01", 0.0, 12470.0, Z_CHW, 2500.0, 12470.0, Z_CHW, 114.3, 165.1, "Service Entry & West Row D Feeder"),
    ("CHW-SEG-02", 2500.0, 12470.0, Z_CHW, 2500.0, 9500.0, Z_CHW, 114.3, 165.1, "Main Spine D to C"),
    ("CHW-SEG-03", 2500.0, 9500.0, Z_CHW, 2500.0, 5150.0, Z_CHW, 114.3, 165.1, "Main Spine C to B"),
    ("CHW-SEG-04", 2500.0, 5150.0, Z_CHW, 2500.0, 1950.0, Z_CHW, 114.3, 165.1, "Main Spine B to A"),
    ("CHW-SEG-05", 2500.0, 12470.0, Z_CHW, 19800.0, 12470.0, Z_CHW, 114.3, 165.1, "Row D Header"),
    ("CHW-SEG-06", 2500.0, 9500.0, Z_CHW, 20000.0, 9500.0, Z_CHW, 114.3, 165.1, "Row C Header"),
    ("CHW-SEG-07", 2500.0, 5150.0, Z_CHW, 19800.0, 5150.0, Z_CHW, 114.3, 165.1, "Row B Header"),
    ("CHW-SEG-08", 2500.0, 1950.0, Z_CHW, 23000.0, 1950.0, Z_CHW, 114.3, 165.1, "Row A & Perimeter CRAH Header"),
]


def col_index_to_letters(idx_1based: int) -> str:
    """Convert 1-based tile column index (1..45) to tile letters (A..Z, AA..AS)."""
    res = ""
    n = idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res


def x_to_tile_ref(x_west_mm: float, tile_row: int) -> str:
    """Convert West X coordinate (mm) and tile row index to tile string (e.g. D05)."""
    col_idx = int(round(x_west_mm / 600.0)) + 1
    return f"{col_index_to_letters(col_idx)}{tile_row:02d}"


def build_sprinkler_list():
    """Return list of all 104 sprinkler heads: (tag, x, y, z, zone)."""
    heads = []
    xs_11 = [1250.0 + 2500.0 * i for i in range(11)]  # 1250 .. 26250
    c_idx = 1
    # Ceiling Rows 1..5 (Y = 1250, 3750, 6250, 8750, 11250)
    for y in [1250.0, 3750.0, 6250.0, 8750.0, 11250.0]:
        for x in xs_11:
            heads.append((f"SPR-C{c_idx:02d}", x, y, ELEV_CEILING_SPRINKLER, "CEILING"))
            c_idx += 1
    # Ceiling Row 6 (Y = 13750, except X in {18750, 23750, 26250} at Y = 14350; X=21250 relocated to 13750 clear of COL-D2)
    for x in xs_11:
        y = 14350.0 if x in (18750.0, 23750.0, 26250.0) else 13750.0
        heads.append((f"SPR-C{c_idx:02d}", x, y, ELEV_CEILING_SPRINKLER, "CEILING"))
        c_idx += 1
    # Ceiling Rows 7..10 in West wing (Y = 16250, 18750, 21250, 23750; 7 cols per row)
    for y in [16250.0, 18750.0, 21250.0, 23750.0]:
        for x in [1250.0, 3750.0, 6250.0, 8750.0, 11250.0, 13750.0, 17350.0]:
            heads.append((f"SPR-C{c_idx:02d}", x, y, ELEV_CEILING_SPRINKLER, "CEILING"))
            c_idx += 1
    # 10 In-Aisle Containment heads beneath CAC-R05 roof (Y = 7135, Z = +1990)
    in_aisle_xs = [2300.0, 4275.0, 6250.0, 7850.0, 10900.0, 13275.0, 15050.0, 16866.7, 18683.3, 20500.0]
    for a_idx, x in enumerate(in_aisle_xs, 1):
        heads.append((f"SPR-A{a_idx:02d}", x, 7135.0, ELEV_IN_AISLE_SPRINKLER, "IN-AISLE"))
    return heads


def seg_aabb(x1, y1, z1, x2, y2, z2, ew, eh):
    """Return 3D axis-aligned bounding box (xmin, xmax, ymin, ymax, zmin, zmax) in mm."""
    if abs(x1 - x2) > 1e-6:
        return (min(x1, x2), max(x1, x2), y1 - ew / 2.0, y1 + ew / 2.0, z1 - eh / 2.0, z1 + eh / 2.0)
    elif abs(y1 - y2) > 1e-6:
        return (x1 - ew / 2.0, x1 + ew / 2.0, min(y1, y2), max(y1, y2), z1 - eh / 2.0, z1 + eh / 2.0)
    else:
        return (x1 - ew / 2.0, x1 + ew / 2.0, y1 - ew / 2.0, y1 + ew / 2.0, min(z1, z2), max(z1, z2))


def attach_psets(model, product, pset_names, props_dict):
    """Attach one or more named property sets with the given properties dictionary."""
    for pset_name in pset_names:
        pset = ifcopenshell.api.run("pset.add_pset", model, product=product, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props_dict)


def build_model() -> ifcopenshell.file:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")

    # Project & Units (MILLIMETRE project length unit; edit_object_placement translations in metres!)
    project = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcProject", name="dc_model hall_seed005_d100"
    )
    project.Description = "Data Hall Overhead MEP Coordination Model (hall_seed005_d100)"

    len_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="VOLUMEUNIT")
    ang_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="PLANEANGLEUNIT")
    ifcopenshell.api.run("unit.assign_unit", model, units=[len_unit, area_unit, vol_unit, ang_unit])

    # Geometric Representation Contexts
    model_ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    # Prescribed Spatial Structure: IfcProject -> IfcSite -> IfcBuilding -> IfcBuildingStorey
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Data Center Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Data Center Building")
    storey = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall"
    )
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

    for sp in (site, building, storey):
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=sp, matrix=np.eye(4))

    # Shared 2D and 3D Axis Placements for SweptSolid Extrusions
    origin_2d = model.createIfcCartesianPoint((0.0, 0.0))
    dir_x_2d = model.createIfcDirection((1.0, 0.0))
    pos_2d = model.createIfcAxis2Placement2D(origin_2d, dir_x_2d)

    origin_3d = model.createIfcCartesianPoint((0.0, 0.0, 0.0))
    dir_z_3d = model.createIfcDirection((0.0, 0.0, 1.0))
    dir_x_3d = model.createIfcDirection((1.0, 0.0, 0.0))
    pos_3d = model.createIfcAxis2Placement3D(origin_3d, dir_z_3d, dir_x_3d)

    all_products = []

    def make_vertical_box_rep(w_mm: float, d_mm: float, h_mm: float, prof_name: str):
        """Create SweptSolid representation for a centered W x D rectangle extruded +Z by H (all in mm)."""
        prof = model.createIfcRectangleProfileDef("AREA", prof_name, pos_2d, float(w_mm), float(d_mm))
        solid = model.createIfcExtrudedAreaSolid(prof, pos_3d, dir_z_3d, float(h_mm))
        rep = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
        return model.createIfcProductDefinitionShape(None, None, [rep])

    def make_vertical_cyl_rep(radius_mm: float, h_mm: float, prof_name: str):
        """Create SweptSolid representation for a centered circle extruded +Z by H (all in mm)."""
        prof = model.createIfcCircleProfileDef("AREA", prof_name, pos_2d, float(radius_mm))
        solid = model.createIfcExtrudedAreaSolid(prof, pos_3d, dir_z_3d, float(h_mm))
        rep = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
        return model.createIfcProductDefinitionShape(None, None, [rep])

    def place_centered_element(product, xc_mm: float, yc_mm: float, z0_mm: float, facing: str = "SOUTH"):
        """
        Place element at its footprint centre (xc_mm, yc_mm, z0_mm) with facing rotation
        about the footprint centre ( translations converted to metres for edit_object_placement ).
        """
        mat = np.eye(4, dtype=float)
        if facing == "NORTH":
            # 180-degree rotation about Z through footprint centre
            mat[0, 0] = -1.0
            mat[1, 1] = -1.0
        elif facing == "EAST":
            mat[0, 0] = 0.0
            mat[0, 1] = -1.0
            mat[1, 0] = 1.0
            mat[1, 1] = 0.0
        elif facing == "WEST":
            mat[0, 0] = 0.0
            mat[0, 1] = 1.0
            mat[1, 0] = -1.0
            mat[1, 1] = 0.0
        mat[0, 3] = xc_mm / 1000.0
        mat[1, 3] = yc_mm / 1000.0
        mat[2, 3] = z0_mm / 1000.0
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=product, matrix=mat)

    # ------------------------------------------------------------------------
    # 3. ACCESS FLOOR (L-shaped polygon with 8 column voids, Z = -35 to 0 mm)
    # ------------------------------------------------------------------------
    outer_curve = model.createIfcPolyline([model.createIfcCartesianPoint(pt) for pt in ROOM_POLYGON_2D])
    inner_curves = []
    for _, _, _, _, cx, cy in COLUMNS_DATA:
        c_pts = [
            (cx - 275.0, cy - 275.0),
            (cx + 275.0, cy - 275.0),
            (cx + 275.0, cy + 275.0),
            (cx - 275.0, cy + 275.0),
            (cx - 275.0, cy - 275.0),
        ]
        inner_curves.append(model.createIfcPolyline([model.createIfcCartesianPoint(pt) for pt in c_pts]))

    floor_prof = model.createIfcArbitraryProfileDefWithVoids("AREA", "AccessFloorProfile", outer_curve, inner_curves)
    floor_solid = model.createIfcExtrudedAreaSolid(floor_prof, pos_3d, dir_z_3d, 35.0)
    floor_rep = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [floor_solid])
    floor_pds = model.createIfcProductDefinitionShape(None, None, [floor_rep])

    access_floor = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcSlab", name="ACCESS-FLOOR", predefined_type="USERDEFINED"
    )
    access_floor.ObjectType = "AccessFloor"
    access_floor.Description = "600x600 mm Raised Access Floor Panel (35 mm thick, -35 to 0 mm)"
    access_floor.Representation = floor_pds
    mat_floor = np.eye(4, dtype=float)
    mat_floor[2, 3] = ELEV_ACCESS_FLOOR_BOTTOM / 1000.0
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=access_floor, matrix=mat_floor)
    attach_psets(
        model,
        access_floor,
        ["Pset_DCM_AccessFloor", "Pset_DCM_Floor", "Pset_DCM_Slab"],
        {
            "Tag": "ACCESS-FLOOR",
            "Elevation": 0.0,
            "FinishedFloorElevation": 0.0,
            "BottomElevation": -35.0,
            "Thickness": 35.0,
            "PanelThickness": 35.0,
            "TileSize": 600.0,
            "TileGrid": 600.0,
            "PlenumDepth": 800.0,
            "StructuralSlabElevation": -800.0,
            "RoomWidth": 27000.0,
            "RoomDepth": 24000.0,
            "CutoutWidth": 8400.0,
            "CutoutDepth": 8400.0,
        },
    )
    all_products.append(access_floor)

    # ------------------------------------------------------------------------
    # 4. STRUCTURAL COLUMNS (8 units, 550 x 550 mm, Z = -800 to +3500 mm)
    # ------------------------------------------------------------------------
    col_pds = make_vertical_box_rep(550.0, 550.0, 4300.0, "Column_550x550")
    for col_name, grid_ref, gx, gy, cx, cy in COLUMNS_DATA:
        col = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcColumn", name=col_name, predefined_type="COLUMN"
        )
        col.ObjectType = "Column"
        col.Tag = col_name
        col.Description = f"Reinforced Concrete Structural Column {grid_ref} (550x550 mm, -800 to +3500 mm)"
        col.Representation = col_pds
        place_centered_element(col, cx, cy, ELEV_STRUCTURAL_SLAB, "SOUTH")
        attach_psets(
            model,
            col,
            ["Pset_DCM_Column", "Pset_DCM_StructuralColumn"],
            {
                "Tag": col_name,
                "Grid": grid_ref,
                "GridX": gx,
                "GridY": gy,
                "CenterX": cx,
                "CenterY": cy,
                "Width": 550.0,
                "Depth": 550.0,
                "Height": 4300.0,
                "BaseElevation": -800.0,
                "TopElevation": 3500.0,
                "GridSpacing": 7200.0,
                "GridOffsetFromTile": 150.0,
                "Material": "Reinforced Concrete",
            },
        )
        all_products.append(col)

    # ------------------------------------------------------------------------
    # 5. RACKS / CABINETS (94 units) & IN-ROW CRAHs (12 units)
    # ------------------------------------------------------------------------
    cab_rep_cache = {}
    for ctype, cinfo in CABINET_TYPES.items():
        cab_rep_cache[ctype] = make_vertical_box_rep(cinfo["w"], cinfo["d"], cinfo["h"], f"Cabinet_{ctype}")

    inrow_crah_reps = {
        1200.0: make_vertical_box_rep(600.0, 1200.0, 2000.0, "CRAH_600x1200"),
        1070.0: make_vertical_box_rep(600.0, 1070.0, 2000.0, "CRAH_600x1070"),
    }

    inrow_crahs_generated = []

    for rsched in ROW_SCHEDULES:
        r_id = rsched["row_id"]
        r_name = rsched["row_name"]
        y0 = rsched["y_south"]
        y1 = rsched["y_north"]
        yc = 0.5 * (y0 + y1)
        d_mm = rsched["depth"]
        h_mm = rsched["height"]
        facing = rsched["facing"]
        t_row = rsched["tile_row"]

        x_curr = 1800.0
        rack_num = 1
        crah_num = 1

        for item, count in rsched["sequence"]:
            if item in CABINET_TYPES:
                cinfo = CABINET_TYPES[item]
                w_mm = cinfo["w"]
                for _ in range(int(count)):
                    r_tag = f"RACK-{r_id}{rack_num:02d}"
                    tile_ref = x_to_tile_ref(x_curr, t_row)
                    xc = x_curr + 0.5 * w_mm

                    rack = ifcopenshell.api.run(
                        "root.create_entity",
                        model,
                        ifc_class="IfcFurniture",
                        name=r_tag,
                        predefined_type="USERDEFINED",
                    )
                    rack.ObjectType = "Rack"
                    rack.Tag = r_tag
                    rack.Description = f"{cinfo['desc']} {item} ({int(w_mm)}x{int(d_mm)}x{int(h_mm)} mm)"
                    rack.Representation = cab_rep_cache[item]
                    place_centered_element(rack, xc, yc, ELEV_FINISHED_FLOOR, facing)

                    rot_deg = 180.0 if facing == "NORTH" else 0.0
                    attach_psets(
                        model,
                        rack,
                        ["Pset_DCM_Rack", "Pset_DCM_Cabinet", "Pset_DCM_Equipment"],
                        {
                            "Tag": r_tag,
                            "Name": r_tag,
                            "Row": r_id,
                            "RowName": r_name,
                            "Type": item,
                            "CabinetType": item,
                            "Description": cinfo["desc"],
                            "Width": w_mm,
                            "Depth": d_mm,
                            "Height": h_mm,
                            "RackUnits": cinfo["ru"],
                            "RU": cinfo["ru"],
                            "Tile": tile_ref,
                            "FrontTile": rsched["front_tile"],
                            "LastTile": rsched["last_tile"],
                            "Facing": facing,
                            "FrontFaces": facing,
                            "Orientation": facing,
                            "RotationDeg": rot_deg,
                            "PowerKW": cinfo["kw"],
                            "LoadKW": cinfo["kw"],
                            "CenterX": xc,
                            "CenterY": yc,
                            "BaseElevation": 0.0,
                            "TopElevation": h_mm,
                        },
                    )
                    all_products.append(rack)
                    x_curr += w_mm
                    rack_num += 1
            elif item == "CU":
                w_mm = 600.0
                c_tag = f"CRAH-{r_id}{crah_num:02d}"
                tile_ref = x_to_tile_ref(x_curr, t_row)
                xc = x_curr + 0.5 * w_mm
                inrow_crahs_generated.append(
                    (c_tag, r_name, tile_ref, x_curr, x_curr + w_mm, y0, y1, h_mm, 50.0, 9000.0, facing, "CHILLED WATER, DN50", "DN50")
                )
                x_curr += w_mm
                crah_num += 1
            else:
                x_curr += float(count)

    # ------------------------------------------------------------------------
    # 6. PERIMETER & IN-ROW CRAHs (16 units total: 4 Perimeter + 12 In-Row)
    # ------------------------------------------------------------------------
    perim_crah_rep = make_vertical_box_rep(1200.0, 900.0, 2000.0, "CRAH_1200x900")
    all_crahs_data = list(PERIMETER_CRAHS) + inrow_crahs_generated

    # Precompute CHW segment boxes for diagnostic distance queries
    chw_seg_boxes = [
        (s[0], s[1], s[2], s[3], s[4], s[5], s[6], *seg_aabb(s[1], s[2], s[3], s[4], s[5], s[6], s[8], s[8]))
        for s in CHW_SEGMENTS
    ]

    for c_tag, loc, tile_ref, x0, x1, y0, y1, h_mm, cap_kw, airflow, facing, svc_str, dn_str in all_crahs_data:
        w_mm = x1 - x0
        d_mm = y1 - y0
        xc = 0.5 * (x0 + x1)
        yc = 0.5 * (y0 + y1)

        crah = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcUnitaryEquipment",
            name=c_tag,
            predefined_type="USERDEFINED",
        )
        crah.ObjectType = "CRAH"
        crah.Tag = c_tag
        crah.Description = f"Computer Room Air Handler {c_tag} ({loc}, {int(cap_kw)} kW, {svc_str})"
        if loc == "PERIMETER":
            crah.Representation = perim_crah_rep
        else:
            crah.Representation = inrow_crah_reps[d_mm]

        place_centered_element(crah, xc, yc, ELEV_FINISHED_FLOOR, facing)

        # Compute exact distance to nearest CHW pipe (2D centerline & 3D bounding box)
        min_d2 = 1e9
        min_d3_box = 1e9
        for sb in chw_seg_boxes:
            sx0, sx1 = min(sb[1], sb[4]), max(sb[1], sb[4])
            sy0, sy1 = min(sb[2], sb[5]), max(sb[2], sb[5])
            dx2 = max(0.0, max(sx0 - xc, xc - sx1))
            dy2 = max(0.0, max(sy0 - yc, yc - sy1))
            min_d2 = min(min_d2, math.hypot(dx2, dy2))

            dxb = max(0.0, max(sb[7] - x1, x0 - sb[8]))
            dyb = max(0.0, max(sb[9] - y1, y0 - sb[10]))
            dzb = max(0.0, max(sb[11] - h_mm, 0.0 - sb[12]))
            min_d3_box = min(min_d3_box, math.sqrt(dxb * dxb + dyb * dyb + dzb * dzb))

        attach_psets(
            model,
            crah,
            ["Pset_DCM_CRAH", "Pset_DCM_CoolingUnit", "Pset_DCM_Equipment"],
            {
                "Tag": c_tag,
                "Name": c_tag,
                "Location": loc,
                "UnitType": "PERIMETER" if loc == "PERIMETER" else "IN-ROW",
                "Tile": tile_ref,
                "Width": w_mm,
                "Depth": d_mm,
                "Height": h_mm,
                "CapacityKW": cap_kw,
                "CoolingCapacityKW": cap_kw,
                "AirflowM3H": airflow,
                "Facing": facing,
                "FrontFaces": facing,
                "Orientation": facing,
                "RotationDeg": 180.0 if facing == "NORTH" else 0.0,
                "Service": svc_str,
                "PipeSize": dn_str,
                "CenterX": xc,
                "CenterY": yc,
                "HorizontalDistanceToCHW": round(min_d2, 2),
                "Clearance3DToCHW": round(min_d3_box, 2),
            },
        )
        all_products.append(crah)

    # ------------------------------------------------------------------------
    # 7. POWER DISTRIBUTION UNITS (4 units: PDU-01..04, 762 x 813 x 1956 mm)
    # ------------------------------------------------------------------------
    pdu_rep = make_vertical_box_rep(762.0, 813.0, 1956.0, "PDU_762x813x1956")
    for p_tag, r_id, serves, tile_ref, x0, x1, y0, y1, h_mm, kva, volt, facing, ws_mm, ded_mm in PDUS_DATA:
        xc = 0.5 * (x0 + x1)
        yc = 0.5 * (y0 + y1)

        pdu = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcElectricDistributionBoard",
            name=p_tag,
            predefined_type="USERDEFINED",
        )
        pdu.ObjectType = "PDU"
        pdu.Tag = p_tag
        pdu.Description = f"Power Distribution Unit {p_tag} ({int(kva)} kVA, {volt}, serves {serves})"
        pdu.Representation = pdu_rep
        place_centered_element(pdu, xc, yc, ELEV_FINISHED_FLOOR, facing)

        # Compute vertical, horizontal, and 3D clearance from PDU top (+1956) to nearest CHW pipe
        min_horiz_chw = 1e9
        min_vert_chw = 1e9
        min_3d_chw = 1e9
        for sb in chw_seg_boxes:
            dxb = max(0.0, max(sb[7] - x1, x0 - sb[8]))
            dyb = max(0.0, max(sb[9] - y1, y0 - sb[10]))
            dzb = max(0.0, sb[11] - h_mm)
            d_h = math.hypot(dxb, dyb)
            d_3d = math.sqrt(dxb * dxb + dyb * dyb + dzb * dzb)
            if d_3d < min_3d_chw:
                min_3d_chw = d_3d
                min_horiz_chw = d_h
                min_vert_chw = dzb

        attach_psets(
            model,
            pdu,
            ["Pset_DCM_PDU", "Pset_DCM_PowerDistributionUnit", "Pset_DCM_Equipment", "Pset_DCM_Clearance"],
            {
                "Tag": p_tag,
                "Name": p_tag,
                "RatingKVA": kva,
                "CapacityKVA": kva,
                "Voltage": volt,
                "Width": 762.0,
                "Depth": 813.0,
                "Height": h_mm,
                "Serves": serves,
                "Row": r_id,
                "Tile": tile_ref,
                "Facing": facing,
                "FrontFaces": facing,
                "Orientation": facing,
                "RotationDeg": 180.0 if facing == "NORTH" else 0.0,
                "WorkingSpaceFront": ws_mm,
                "DedicatedSpaceAbove": ded_mm,
                "TopElevation": h_mm,
                "DedicatedSpaceTopElevation": h_mm + ded_mm,
                "VerticalClearanceToNearestCHW": round(min_vert_chw, 2),
                "HorizontalClearanceToNearestCHW": round(min_horiz_chw, 2),
                "Clearance3DToNearestCHW": round(min_3d_chw, 2),
                "CHWInDedicatedSpace": False,
            },
        )
        all_products.append(pdu)

    # ------------------------------------------------------------------------
    # 8. COLD-AISLE CONTAINMENT CAC-R05 (4 Roof Panels + 4 End Doors)
    # ------------------------------------------------------------------------
    for r_tag, x0, x1, y0, y1, z0, z1 in CONTAINMENT_ROOFS:
        w_mm = x1 - x0
        d_mm = y1 - y0
        h_mm = z1 - z0
        xc = 0.5 * (x0 + x1)
        yc = 0.5 * (y0 + y1)

        roof = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcCovering",
            name=r_tag,
            predefined_type="USERDEFINED",
        )
        roof.ObjectType = "ContainmentRoof"
        roof.Tag = r_tag
        roof.Description = f"Cold-Aisle Containment CAC-R05 Roof Panel ({int(w_mm)}x{int(d_mm)}x{h_mm:.1f} mm)"
        roof.Representation = make_vertical_box_rep(w_mm, d_mm, h_mm, f"Profile_{r_tag}")
        place_centered_element(roof, xc, yc, z0, "SOUTH")

        attach_psets(
            model,
            roof,
            ["Pset_DCM_Containment"],
            {
                "Tag": "CAC-R05",
                "ComponentTag": r_tag,
                "ComponentType": "RoofPanel",
                "ContainedAisle": "ROWS B / C",
                "RoofPanels": 4,
                "RoofWidth": 1520.0,
                "RoofThickness": 55.0,
                "RoofUndersideElevation": 2000.0,
                "RoofTopElevation": 2055.0,
                "EndDoors": 4,
                "DoorThickness": 60.0,
                "DoorHeight": 2055.5,
                "Length": w_mm,
                "Width": d_mm,
                "Thickness": h_mm,
            },
        )
        all_products.append(roof)

    for d_tag, x0, x1, y0, y1, z0, z1 in CONTAINMENT_DOORS:
        w_mm = x1 - x0
        d_mm = y1 - y0
        h_mm = z1 - z0
        xc = 0.5 * (x0 + x1)
        yc = 0.5 * (y0 + y1)

        door = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcDoor",
            name=d_tag,
            predefined_type="USERDEFINED",
        )
        door.ObjectType = "ContainmentDoor"
        door.Tag = d_tag
        door.Description = f"Cold-Aisle Containment CAC-R05 End Door ({int(w_mm)}x{int(d_mm)}x{h_mm:.1f} mm)"
        door.Representation = make_vertical_box_rep(w_mm, d_mm, h_mm, f"Profile_{d_tag}")
        place_centered_element(door, xc, yc, z0, "SOUTH")

        attach_psets(
            model,
            door,
            ["Pset_DCM_Containment"],
            {
                "Tag": "CAC-R05",
                "ComponentTag": d_tag,
                "ComponentType": "EndDoor",
                "ContainedAisle": "ROWS B / C",
                "RoofPanels": 4,
                "RoofWidth": 1520.0,
                "RoofThickness": 55.0,
                "RoofUndersideElevation": 2000.0,
                "EndDoors": 4,
                "DoorThickness": 60.0,
                "DoorHeight": 2055.5,
                "Thickness": w_mm,
                "Width": d_mm,
                "Height": h_mm,
            },
        )
        all_products.append(door)

    # ------------------------------------------------------------------------
    # 9. SPRINKLER HEADS (104 units: 94 Ceiling @ +3025, 10 In-Aisle @ +1990)
    # ------------------------------------------------------------------------
    sprinkler_list = build_sprinkler_list()
    ceil_spr_rep = make_vertical_cyl_rep(50.0, 75.0, "Sprinkler_Ceiling_R50")
    aisle_spr_rep = make_vertical_cyl_rep(40.0, 10.0, "Sprinkler_InAisle_R40")

    ct_seg_boxes = [
        (s[0], *seg_aabb(s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8])) for s in CT_SEGMENTS
    ]
    bw_seg_boxes = [
        (s[0], *seg_aabb(s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8])) for s in BW_SEGMENTS
    ]
    chw_only_boxes = [
        (s[0], *seg_aabb(s[1], s[2], s[3], s[4], s[5], s[6], s[8], s[8])) for s in CHW_SEGMENTS
    ]

    def calc_spr_service_clearance(sx, sy, sz, boxes, svc_zmax):
        """Return (min_horizontal_clearance_mm, vertical_clearance_from_service_top_mm, passes_under)."""
        min_h = 1e9
        for _, bx0, bx1, by0, by1, bz0, bz1 in boxes:
            dx = max(0.0, max(bx0 - sx, sx - bx1))
            dy = max(0.0, max(by0 - sy, sy - by1))
            d_h = math.hypot(dx, dy)
            if d_h < min_h:
                min_h = d_h
        passes_under = min_h < 400.0 and svc_zmax <= sz
        v_clear = sz - svc_zmax
        return round(min_h, 2), round(v_clear, 2), passes_under

    for s_tag, sx, sy, sz, szone in sprinkler_list:
        spr = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcFireSuppressionTerminal",
            name=s_tag,
            predefined_type="SPRINKLER",
        )
        spr.ObjectType = "Sprinkler"
        spr.Tag = s_tag
        spr.Description = f"{szone.title()} Sprinkler Head {s_tag} at Deflector +{int(sz)} mm"
        spr.Representation = ceil_spr_rep if szone == "CEILING" else aisle_spr_rep
        place_centered_element(spr, sx, sy, sz, "SOUTH")

        h_ct, v_ct, u_ct = calc_spr_service_clearance(sx, sy, sz, ct_seg_boxes, 2725.0)
        h_bw, v_bw, u_bw = calc_spr_service_clearance(sx, sy, sz, bw_seg_boxes, 3175.0)
        h_chw, v_chw, u_chw = calc_spr_service_clearance(sx, sy, sz, chw_only_boxes, 2932.55)

        attach_psets(
            model,
            spr,
            ["Pset_DCM_Sprinkler", "Pset_DCM_FireSuppression", "Pset_DCM_Clearance"],
            {
                "Tag": s_tag,
                "Name": s_tag,
                "Zone": szone,
                "Location": szone,
                "DeflectorElevation": sz,
                "Elevation": sz,
                "RequiredClearanceBelow": 460.0,
                "Standoff": 460.0,
                "X": sx,
                "Y": sy,
                "Z": sz,
                "HorizontalClearanceToTray": h_ct,
                "HorizontalClearanceToBusway": h_bw,
                "HorizontalClearanceToCHW": h_chw,
                "VerticalClearanceToTrayTop": v_ct,
                "VerticalClearanceToBuswayTop": v_bw,
                "VerticalClearanceToCHWTop": v_chw,
                "TrayPassesUnderHead": u_ct,
                "BuswayPassesUnderHead": u_bw,
                "CHWPassesUnderHead": u_chw,
                "AnyServicePassesUnderHead": bool(u_ct or u_bw or u_chw),
            },
        )
        all_products.append(spr)

    # ------------------------------------------------------------------------
    # 10. THREE OVERHEAD MEP SERVICES (CT-1, BW-1, CHW-1)
    # ------------------------------------------------------------------------
    sys_telecom = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
    sys_telecom.Name = "TELECOM"
    sys_telecom.ObjectType = "CableTray"
    sys_telecom.Description = "Telecom Ladder Cable Tray System CT-1 (600x125 mm)"

    sys_power = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
    sys_power.Name = "POWER"
    sys_power.ObjectType = "Busway"
    sys_power.Description = "Power Busway System BW-1 (120x145 mm)"

    sys_chw = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
    sys_chw.Name = "CHW"
    sys_chw.ObjectType = "ChilledWater"
    sys_chw.Description = "Chilled Water Piping System CHW-1 (DN100 Steel Pipe, OD 114.3 mm + 25.4 mm Insulation)"

    def create_flow_segment(ifc_class, predefined_type, obj_type, name, p1_mm, p2_mm, w_mm, h_mm, is_circle=False):
        """
        Create an axis-aligned swept-solid flow segment from p1_mm to p2_mm (in mm).
        Cross-section profile is in 2D (local X = width, local Y = height) extruded along local +Z by length L.
        Placement matrix translation is passed in metres to edit_object_placement.
        """
        p1 = np.array(p1_mm, dtype=float)
        p2 = np.array(p2_mm, dtype=float)
        vec = p2 - p1
        length_mm = float(np.linalg.norm(vec))
        uz = vec / length_mm
        if abs(uz[2]) < 0.9:
            uy = np.array([0.0, 0.0, 1.0])
            ux = np.cross(uy, uz)
            ux /= np.linalg.norm(ux)
            uy = np.cross(uz, ux)
        else:
            ux = np.array([1.0, 0.0, 0.0])
            uy = np.cross(uz, ux)

        if is_circle:
            prof = model.createIfcCircleProfileDef("AREA", f"Profile_{name}", pos_2d, float(w_mm) / 2.0)
        else:
            prof = model.createIfcRectangleProfileDef("AREA", f"Profile_{name}", pos_2d, float(w_mm), float(h_mm))

        solid = model.createIfcExtrudedAreaSolid(prof, pos_3d, dir_z_3d, length_mm)
        rep = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
        pds = model.createIfcProductDefinitionShape(None, None, [rep])

        seg = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class=ifc_class,
            name=name,
            predefined_type=predefined_type,
        )
        seg.ObjectType = obj_type
        seg.Tag = name
        seg.Representation = pds

        mat = np.eye(4, dtype=float)
        mat[:3, 0] = ux
        mat[:3, 1] = uy
        mat[:3, 2] = uz
        mat[:3, 3] = p1 / 1000.0
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=seg, matrix=mat)
        return seg, length_mm

    # Precompute Tray-Busway pair separations for diagnostic properties
    min_tb_any_axis = 305.0
    total_ct_len = sum(math.hypot(s[4] - s[1], s[5] - s[2]) for s in CT_SEGMENTS)
    total_bw_len = sum(math.hypot(s[4] - s[1], s[5] - s[2]) for s in BW_SEGMENTS)
    total_chw_len = sum(math.hypot(s[4] - s[1], s[5] - s[2]) for s in CHW_SEGMENTS)

    # 10a. Telecom Cable Tray CT-1
    ct_entities = []
    for s_name, x1, y1, z1, x2, y2, z2, w_mm, h_mm, role in CT_SEGMENTS:
        seg, l_mm = create_flow_segment(
            "IfcCableCarrierSegment",
            "CABLELADDERSEGMENT",
            "CableTray",
            s_name,
            (x1, y1, z1),
            (x2, y2, z2),
            w_mm,
            h_mm,
            is_circle=False,
        )
        seg.Description = f"Telecom Ladder Cable Tray CT-1 ({int(w_mm)}x{int(h_mm)} mm) - {role}"

        # Compute min separation from this tray segment to all busway segments
        b_ct = seg_aabb(x1, y1, z1, x2, y2, z2, w_mm, h_mm)
        min_sep_this = 1e9
        min_h_sep_this = 1e9
        for bw_s in BW_SEGMENTS:
            b_bw = seg_aabb(bw_s[1], bw_s[2], bw_s[3], bw_s[4], bw_s[5], bw_s[6], bw_s[7], bw_s[8])
            gx = max(0.0, max(b_ct[0] - b_bw[1], b_bw[0] - b_ct[1]))
            gy = max(0.0, max(b_ct[2] - b_bw[3], b_bw[2] - b_ct[3]))
            gz = max(0.0, max(b_ct[4] - b_bw[5], b_bw[4] - b_ct[5]))
            min_sep_this = min(min_sep_this, max(gx, gy, gz))
            if max(gx, gy) > 0:
                min_h_sep_this = min(min_h_sep_this, max(gx, gy))

        attach_psets(
            model,
            seg,
            ["Pset_DCM_CableTray", "Pset_DCM_Pathway", "Pset_DCM_Service", "Pset_DCM_Clearance"],
            {
                "Tag": s_name,
                "Code": "CT-1",
                "PathwayID": "CT-1",
                "Service": "TELECOM",
                "System": "TELECOM",
                "Type": "CABLE TRAY, LADDER",
                "Role": role,
                "Width": w_mm,
                "Height": h_mm,
                "Length": round(l_mm, 2),
                "StartX": x1,
                "StartY": y1,
                "StartZ": z1,
                "EndX": x2,
                "EndY": y2,
                "EndZ": z2,
                "BottomElevation": z1 - 0.5 * h_mm,
                "CenterlineElevation": z1,
                "TopElevation": z1 + 0.5 * h_mm,
                "Tier": 1,
                "RoutingZone": "OVERHEAD",
                "ElevationBand": "OVERHEAD_ABOVE_2600",
                "OverheadLength": round(l_mm, 2),
                "UnderfloorLength": 0.0,
                "ServiceTotalOverheadLength": round(total_ct_len, 2),
                "ServiceTotalUnderfloorLength": 0.0,
                "MinSeparationToBusway": round(min_sep_this, 2),
                "VerticalSeparationToBuswayZ": 305.0,
                "RequiresSprinklerBelow": False,
            },
        )
        ct_entities.append(seg)
        all_products.append(seg)
    ifcopenshell.api.run("system.assign_system", model, products=ct_entities, system=sys_telecom)

    # 10b. Power Busway BW-1
    bw_entities = []
    for s_name, x1, y1, z1, x2, y2, z2, w_mm, h_mm, role in BW_SEGMENTS:
        seg, l_mm = create_flow_segment(
            "IfcCableCarrierSegment",
            "CABLETRUNKINGSEGMENT",
            "Busway",
            s_name,
            (x1, y1, z1),
            (x2, y2, z2),
            w_mm,
            h_mm,
            is_circle=False,
        )
        seg.Description = f"Power Busway BW-1 ({int(w_mm)}x{int(h_mm)} mm) - {role}"
        n_spans = max(1, int(math.ceil(l_mm / 1400.0)))
        actual_span = l_mm / n_spans

        attach_psets(
            model,
            seg,
            ["Pset_DCM_Busway", "Pset_DCM_Pathway", "Pset_DCM_Service", "Pset_DCM_Clearance"],
            {
                "Tag": s_name,
                "Code": "BW-1",
                "PathwayID": "BW-1",
                "Service": "POWER",
                "System": "POWER",
                "Type": "BUSWAY",
                "Role": role,
                "Width": w_mm,
                "Height": h_mm,
                "Length": round(l_mm, 2),
                "StartX": x1,
                "StartY": y1,
                "StartZ": z1,
                "EndX": x2,
                "EndY": y2,
                "EndZ": z2,
                "BottomElevation": z1 - 0.5 * h_mm,
                "CenterlineElevation": z1,
                "TopElevation": z1 + 0.5 * h_mm,
                "Tier": 3,
                "RoutingZone": "OVERHEAD",
                "ElevationBand": "OVERHEAD_ABOVE_2600",
                "OverheadLength": round(l_mm, 2),
                "UnderfloorLength": 0.0,
                "ServiceTotalOverheadLength": round(total_bw_len, 2),
                "ServiceTotalUnderfloorLength": 0.0,
                "MaxSupportSpacing": 1500.0,
                "ActualSupportSpacing": round(actual_span, 2),
                "MinSeparationToTray": min_tb_any_axis,
                "VerticalSeparationToTrayZ": 305.0,
            },
        )
        bw_entities.append(seg)
        all_products.append(seg)
    ifcopenshell.api.run("system.assign_system", model, products=bw_entities, system=sys_power)

    # 10c. Chilled-Water Pipe CHW-1 (DN100, bare OD 114.3 mm, 25.4 mm insulation -> effective OD 165.1 mm)
    chw_entities = []
    for s_name, x1, y1, z1, x2, y2, z2, bare_od, insul_od, role in CHW_SEGMENTS:
        seg, l_mm = create_flow_segment(
            "IfcPipeSegment",
            "RIGIDSEGMENT",
            "ChilledWaterPipe",
            s_name,
            (x1, y1, z1),
            (x2, y2, z2),
            bare_od,
            bare_od,
            is_circle=True,
        )
        seg.Description = f"Chilled Water Pipe CHW-1 (DN100, OD {bare_od} mm + 25.4 mm insulation) - {role}"

        attach_psets(
            model,
            seg,
            ["Pset_DCM_ChilledWater", "Pset_DCM_Pipe", "Pset_DCM_Pathway", "Pset_DCM_Service"],
            {
                "Tag": s_name,
                "Code": "CHW-1",
                "PathwayID": "CHW-1",
                "Service": "CHILLED WATER",
                "System": "CHW",
                "Type": "STEEL PIPE, DN100",
                "Role": role,
                "NominalDiameter": 100.0,
                "OuterDiameter": bare_od,
                "InsulationThickness": 25.4,
                "EffectiveOuterDiameter": insul_od,
                "Length": round(l_mm, 2),
                "StartX": x1,
                "StartY": y1,
                "StartZ": z1,
                "EndX": x2,
                "EndY": y2,
                "EndZ": z2,
                "BottomElevation": round(z1 - 0.5 * insul_od, 2),
                "BareBottomElevation": round(z1 - 0.5 * bare_od, 2),
                "CenterlineElevation": z1,
                "TopElevation": round(z1 + 0.5 * insul_od, 2),
                "BareTopElevation": round(z1 + 0.5 * bare_od, 2),
                "Tier": 2,
                "RoutingZone": "OVERHEAD",
                "ElevationBand": "OVERHEAD_ABOVE_2600",
                "OverheadLength": round(l_mm, 2),
                "UnderfloorLength": 0.0,
                "ServiceTotalOverheadLength": round(total_chw_len, 2),
                "ServiceTotalUnderfloorLength": 0.0,
            },
        )
        chw_entities.append(seg)
        all_products.append(seg)
    ifcopenshell.api.run("system.assign_system", model, products=chw_entities, system=sys_chw)

    # ------------------------------------------------------------------------
    # 11. BUSWAY SUPPORTS / HANGERS (Additional Requirement #4: <= 1500 mm max)
    # ------------------------------------------------------------------------
    support_pts = []
    max_unsupported_span = 0.0
    for _, x1, y1, z1, x2, y2, z2, _, _, _ in BW_SEGMENTS:
        p1 = np.array([x1, y1], dtype=float)
        p2 = np.array([x2, y2], dtype=float)
        l_seg = float(np.linalg.norm(p2 - p1))
        n_int = max(1, int(math.ceil(l_seg / 1400.0)))
        max_unsupported_span = max(max_unsupported_span, l_seg / n_int)
        for k in range(n_int + 1):
            pt = p1 + (k / n_int) * (p2 - p1)
            support_pts.append((round(float(pt[0]), 1), round(float(pt[1]), 1)))
    support_pts = sorted(list(set(support_pts)))

    hanger_rep = make_vertical_box_rep(40.0, 40.0, 315.0, "BuswayHanger_40x40x315")
    for h_idx, (hx, hy) in enumerate(support_pts, 1):
        h_name = f"BW-SUPPORT-HANGER-{h_idx:03d}"
        hanger = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcBuildingElementProxy",
            name=h_name,
            predefined_type="USERDEFINED",
        )
        hanger.ObjectType = "BuswaySupportHanger"
        hanger.Tag = h_name
        hanger.Description = f"Busway Overhead Support Hanger at ({hx:.0f}, {hy:.0f}), Z=3180..3495 mm (<=1500 mm O.C.)"
        hanger.Representation = hanger_rep
        place_centered_element(hanger, hx, hy, 3180.0, "SOUTH")
        attach_psets(
            model,
            hanger,
            ["Pset_DCM_Support", "Pset_DCM_Hanger"],
            {
                "Tag": h_name,
                "Service": "POWER",
                "SupportedSystem": "BW-1",
                "MaxAllowedSpacing": 1500.0,
                "DesignSpacing": 1400.0,
                "ActualMaxSpan": round(max_unsupported_span, 2),
                "X": hx,
                "Y": hy,
                "BottomElevation": 3180.0,
                "TopElevation": 3495.0,
            },
        )
        all_products.append(hanger)

    # ------------------------------------------------------------------------
    # 12. SERVICE DROPS / TAPS / TERMINATIONS (Additional Requirement #5)
    # ------------------------------------------------------------------------
    tap_rep_50 = make_vertical_box_rep(50.0, 50.0, 50.0, "ServiceTap_50x50x50")
    tap_rep_60 = make_vertical_box_rep(60.0, 60.0, 30.0, "ServiceTap_60x60x30")

    # 16 CHW Taps/Terminations (one for each CRAH unit)
    chw_hdr_y = {"ROW A": 1950.0, "PERIMETER": 1950.0, "ROW B": 5150.0, "ROW C": 9500.0, "ROW D": 12470.0}
    chw_hdr_xmax = {"ROW A": 23000.0, "PERIMETER": 23000.0, "ROW B": 19800.0, "ROW C": 20000.0, "ROW D": 19800.0}

    for c_tag, loc, _, x0, x1, y0, y1, _, _, _, _, _, dn_str in all_crahs_data:
        cx = 0.5 * (x0 + x1)
        tx = min(max(cx, 2500.0), chw_hdr_xmax[loc])
        ty = chw_hdr_y[loc]
        t_name = f"CHW-TAP-TERM-{c_tag}"

        tap = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcBuildingElementProxy",
            name=t_name,
            predefined_type="USERDEFINED",
        )
        tap.ObjectType = "ServiceDropTapTermination"
        tap.Tag = t_name
        tap.Description = f"CHW Service Tap / Termination for {c_tag} ({dn_str})"
        tap.Representation = tap_rep_50
        place_centered_element(tap, tx, ty, 2940.0, "SOUTH")
        attach_psets(
            model,
            tap,
            ["Pset_DCM_Termination", "Pset_DCM_ServiceDrop"],
            {
                "Tag": t_name,
                "Service": "CHILLED WATER",
                "System": "CHW",
                "TargetElement": c_tag,
                "ConnectionSize": dn_str,
                "X": tx,
                "Y": ty,
                "Elevation": 2940.0,
            },
        )
        all_products.append(tap)

    # 8 Power Busway Taps/Terminations (West & East halves of Rows A, B, C, D)
    for r_id, ty in [("A", 3000.0), ("B", 5500.0), ("C", 8150.0), ("D", 12470.0)]:
        for side, tx in [("WEST", 6000.0), ("EAST", 16000.0)]:
            t_name = f"BW-TAP-TERM-ROW-{r_id}-{side}"
            tap = ifcopenshell.api.run(
                "root.create_entity",
                model,
                ifc_class="IfcBuildingElementProxy",
                name=t_name,
                predefined_type="USERDEFINED",
            )
            tap.ObjectType = "ServiceDropTapTermination"
            tap.Tag = t_name
            tap.Description = f"Power Busway Tap / Drop Termination for Row {r_id} ({side})"
            tap.Representation = tap_rep_50
            place_centered_element(tap, tx, ty, 2975.0, "SOUTH")
            attach_psets(
                model,
                tap,
                ["Pset_DCM_Termination", "Pset_DCM_ServiceDrop"],
                {
                    "Tag": t_name,
                    "Service": "POWER",
                    "System": "POWER",
                    "TargetElement": f"ROW {r_id} ({side})",
                    "X": tx,
                    "Y": ty,
                    "Elevation": 2975.0,
                },
            )
            all_products.append(tap)

    # 8 Telecom Cable Tray Drops/Terminations (West & East halves of Rows A, B, C, D)
    for r_id, ty in [("A", 2300.0), ("B", 4800.0), ("C", 9550.0), ("D", 12200.0)]:
        for side, tx in [("WEST", 6000.0), ("EAST", 16000.0)]:
            t_name = f"CT-DROP-TERM-ROW-{r_id}-{side}"
            tap = ifcopenshell.api.run(
                "root.create_entity",
                model,
                ifc_class="IfcBuildingElementProxy",
                name=t_name,
                predefined_type="USERDEFINED",
            )
            tap.ObjectType = "ServiceDropTapTermination"
            tap.Tag = t_name
            tap.Description = f"Telecom Cable Tray Drop / Termination for Row {r_id} ({side})"
            tap.Representation = tap_rep_60
            place_centered_element(tap, tx, ty, 2730.0, "SOUTH")
            attach_psets(
                model,
                tap,
                ["Pset_DCM_Termination", "Pset_DCM_ServiceDrop"],
                {
                    "Tag": t_name,
                    "Service": "TELECOM",
                    "System": "TELECOM",
                    "TargetElement": f"ROW {r_id} ({side})",
                    "X": tx,
                    "Y": ty,
                    "Elevation": 2730.0,
                },
            )
            all_products.append(tap)

    # ------------------------------------------------------------------------
    # 13. ASSIGN ALL ELEMENTS TO STOREY & ATTACH HALL / ROUTING SUMMARY PSETS
    # ------------------------------------------------------------------------
    ifcopenshell.api.run("spatial.assign_container", model, products=all_products, relating_structure=storey)

    attach_psets(
        model,
        storey,
        ["Pset_DCM_Hall", "Pset_DCM_Room", "Pset_DCM_RoutingSummary"],
        {
            "HallID": "hall_seed005_d100",
            "RoomWidth": 27000.0,
            "RoomDepth": 24000.0,
            "NECutoutWidth": 8400.0,
            "NECutoutDepth": 8400.0,
            "StructuralSlabElevation": -800.0,
            "AccessFloorElevation": 0.0,
            "AccessFloorThickness": 35.0,
            "EquipmentHeight": 2000.0,
            "MinClearHeight": 2600.0,
            "CeilingSprinklerElevation": 3025.0,
            "InAisleSprinklerElevation": 1990.0,
            "SprinklerClearanceRequired": 460.0,
            "CeilingSoffitElevation": 3500.0,
            "CabinetCount": 94,
            "CRAHCount": 16,
            "PDUCount": 4,
            "ColumnCount": 8,
            "SprinklerCount": 104,
            "CableTrayOverheadLength": round(total_ct_len, 2),
            "CableTrayUnderfloorLength": 0.0,
            "BuswayOverheadLength": round(total_bw_len, 2),
            "BuswayUnderfloorLength": 0.0,
            "ChilledWaterOverheadLength": round(total_chw_len, 2),
            "ChilledWaterUnderfloorLength": 0.0,
            "MinTrayBuswaySeparation": min_tb_any_axis,
            "BuswayMaxUnsupportedSpan": round(max_unsupported_span, 2),
            "BuswaySupportCount": len(support_pts),
            "ServiceTerminationCount": 32,
        },
    )

    return model


def build_reconciliation_data():
    """Return structured drawing-note reconciliation log for output/reconciliation.json."""
    return {
        "project": "dc_model hall_seed005_d100",
        "sheets_reconciled": ["A-101", "A-301", "A-601", "A-602", "M-101", "E-101", "F-101"],
        "notes_and_constraints": [
            {
                "sheet": "A-101 / A-602",
                "note": "Room plan dimensions 27000 x 24000 mm L-shaped with 8400 x 8400 mm NE cutout; 600 x 600 mm floor tile grid (cols A..AS, rows 01..40)",
                "application": "Applied as 6-vertex L-shaped room polygon [(0,0), (27000,0), (27000,15600), (18600,15600), (18600,24000), (0,24000)] and exact tile-grid equipment placement.",
            },
            {
                "sheet": "A-101 / A-602",
                "note": "Structural column grid 7200 x 7200 mm O.C. offset +150 mm in X and +150 mm in Y from floor tile grid; 8 columns 550 x 550 mm running full height -800 to +3500 mm",
                "application": "Placed 8 full-height IfcColumn elements at X,Y in {7350, 14550, 21750} (excluding NE cutout (21750, 21750)); resolved tile-vs-column conflict using 2-600 bay skips in Rows B and C.",
            },
            {
                "sheet": "A-301 / A-602",
                "note": "Elevation datums: structural slab -800 mm, access floor panel 35 mm thick (-35 to 0 mm), finished floor 0 mm, equipment top +2000 mm, min clear height +2600 mm, sprinkler deflectors +3025 mm (+1990 mm in-aisle), ceiling soffit +3500 mm",
                "application": "Enforced +2600 mm minimum clear headroom for all overhead MEP routes (lowest surface is CT-1 bottom at +2600.0 mm) and modelled access floor at Z = -35 to 0 mm with 8 column voids.",
            },
            {
                "sheet": "A-601",
                "note": "94 cabinets across Rows A (26), B (21), C (20), D (27) with types C1 (600x1200x2000, 44 qty), C2 (600x1070x2000, 44 qty), N1 (800x1200x2000, 2 qty), N2 (800x1070x2000, 4 qty) and circulation cross-aisle CA re-registering East half-rows onto Tile V (X = 12600 mm)",
                "application": "Modelled all 94 racks as IfcFurniture/USERDEFINED/'Rack' with Pset_DCM_Rack and facing rotations (0 deg SOUTH for Rows A & C, 180 deg NORTH for Rows B & D) about footprint centres.",
            },
            {
                "sheet": "A-601",
                "note": "16 CRAH units: 4 perimeter units CRAH-01..04 (1200x900x2000 mm, 100 kW, DN100, NORTH facing at B01, P01, AC01, AO01) and 12 in-row units CRAH-A01..D03 (600x1200/1070x2000 mm, 50 kW, DN50)",
                "application": "Modelled all 16 CRAHs as IfcUnitaryEquipment/USERDEFINED/'CRAH' and routed CHW-1 within <= 1985 mm (2D center) / <= 1450 mm (3D BBox) of every CRAH including all 4 perimeter units.",
            },
            {
                "sheet": "A-601 / E-101",
                "note": "4 PDUs PDU-01..04 (762x813x1956 mm, 275 kVA at AN05, AM10, AL14, AO19) with 900 mm front working space and 1800 mm dedicated electrical space above footprint free of CHW piping (NEC 110.26(E))",
                "application": "Modelled 4 PDUs as IfcElectricDistributionBoard/USERDEFINED/'PDU' with front faces aligned to row front faces; routed all CHW piping >= 367.5 mm horizontally outside every PDU footprint (0 mm in dedicated space above PDUs).",
            },
            {
                "sheet": "A-602 / A-301",
                "note": "Cold-aisle containment CAC-R05 enclosing aisle between Rows B and C: 4 roof panels (1520 mm wide, 55.0 mm thick, underside at +2000 mm) split at columns B-1/C-1 and cross-aisle CA, plus 4 end doors (60 x 2055.5 mm)",
                "application": "Modelled 4 IfcCovering roof panels (Z = +2000..+2055 mm, Y = 6375..7895 mm) and 4 IfcDoor end doors (Z = 0..+2055.5 mm, Y = 6470..7800 mm) with Pset_DCM_Containment and 0.0 mm overlap with columns or racks.",
            },
            {
                "sheet": "F-101 / A-301",
                "note": "104 sprinkler heads (94 ceiling grid heads on 2500 x 2500 mm grid at +3025 mm with head at (21250, 13750) held clear of Column D-2 1520 mm keep-out, plus 10 in-aisle containment heads under CAC-R05 at +1990 mm); 460 mm kept clear below every deflector; heads required beneath runs > 1200 mm wide",
                "application": "Modelled all 104 IfcFireSuppressionTerminal/SPRINKLER elements and threaded all overhead routes through clear corridors with >= 500.0 mm horizontal clearance from every ceiling sprinkler center; CT-1 width is 600 mm (<= 1200 mm).",
            },
            {
                "sheet": "A-602 / E-101",
                "note": "Telecom Cable Tray CT-1 (600x125 mm ladder tray) and Power Busway BW-1 (120x145 mm) entering at West wall Y = 12470 mm; >= 300 mm separation between tray and busway on at least one axis; busway support spacing 1500 mm max; >= 80% row coverage within 2500 mm",
                "application": "Routed CT-1 on Tier 1 (Z = 2600..2725 mm) and BW-1 on Tier 3 (Z = 3030..3175 mm) achieving 305.0 mm vertical Z-separation on every pair plus >= 310 mm horizontal separation on parallel runs; placed 63 busway support hangers at <= 1388.5 mm centres; achieved 84.6%..90.6% coverage on all 4 rows.",
            },
            {
                "sheet": "A-602 / M-101",
                "note": "Chilled-Water Pipe CHW-1 (DN100 steel pipe, OD 114.3 mm + 25.4 mm insulation = effective OD 165.1 mm) entering at West wall Y = 12470 mm; insulation counts in clashes; >= 80% row coverage within 2500 mm and within 2500 mm of every CRAH",
                "application": "Routed CHW-1 on Tier 2 (Z_c = 2850.0 mm, insulated Z = 2767.45..2932.55 mm) with >= 42.45 mm vertical clearance to CT-1 and BW-1, achieving 84.8%..100% row coverage and reaching all 16 CRAHs within <= 1985 mm.",
            },
        ],
    }


def main():
    out_ifc = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    out_dir = os.path.dirname(os.path.abspath(out_ifc))
    os.makedirs(out_dir, exist_ok=True)

    model = build_model()
    model.write(out_ifc)

    recon_data = build_reconciliation_data()
    recon_path = os.path.join(out_dir, "reconciliation.json")
    with open(recon_path, "w", encoding="utf-8") as f:
        json.dump(recon_data, f, indent=2)

    default_recon = os.path.abspath("output/reconciliation.json")
    if default_recon != os.path.abspath(recon_path):
        os.makedirs(os.path.dirname(default_recon), exist_ok=True)
        with open(default_recon, "w", encoding="utf-8") as f:
            json.dump(recon_data, f, indent=2)

    print(f"Wrote IFC4 model to {out_ifc} and reconciliation log to {recon_path}")


if __name__ == "__main__":
    main()
