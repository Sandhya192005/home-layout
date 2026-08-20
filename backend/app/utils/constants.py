"""Static design data used by the floor-plan generation engine.

All dimensions are in feet, all areas in square feet, unless noted otherwise.
"""

# Compass zone layout of the 3x3 Vastu grid.
# Row 0 = North row, Row 1 = Middle row, Row 2 = South row
# Col 0 = West col,  Col 1 = Middle col, Col 2 = East col
ZONE_GRID = [
    ["NW", "N", "NE"],
    ["W", "C", "E"],
    ["SW", "S", "SE"],
]

# Which grid (row, col) each compass zone corresponds to.
ZONE_CELL = {
    "NW": (0, 0), "N": (0, 1), "NE": (0, 2),
    "W": (1, 0), "C": (1, 1), "E": (1, 2),
    "SW": (2, 0), "S": (2, 1), "SE": (2, 2),
}

# room_type -> design metadata
# weight: relative floor-area share used when partitioning the buildable rectangle
# priority: higher = placed/assigned first (important rooms get their preferred zone)
# zones: ordered list of preferred Vastu compass zones (best first)
# habitable: whether the room needs a window for light/ventilation
# min_w / min_l: minimum sensible width/length in feet
ROOM_LIBRARY = {
    "living_room": {
        "label": "Living Room", "weight": 1.6, "priority": 8, "min_w": 10, "min_l": 12,
        "zones": ["N", "NE", "E", "C"], "habitable": True,
        "furniture": [
            {"type": "sofa_set", "w": 6, "l": 3},
            {"type": "center_table", "w": 3, "l": 1.5},
            {"type": "tv_unit", "w": 5, "l": 1},
        ],
    },
    "master_bedroom": {
        "label": "Master Bedroom", "weight": 1.45, "priority": 9, "min_w": 11, "min_l": 13,
        "zones": ["SW", "S", "W"], "habitable": True,
        "furniture": [
            {"type": "bed_king", "w": 6.5, "l": 6.5},
            {"type": "wardrobe", "w": 6, "l": 2},
            {"type": "dresser", "w": 3, "l": 1.5},
        ],
    },
    "bedroom": {
        "label": "Bedroom", "weight": 1.0, "priority": 6, "min_w": 10, "min_l": 11,
        "zones": ["NW", "N", "W", "S"], "habitable": True,
        "furniture": [
            {"type": "bed_queen", "w": 5, "l": 6.5},
            {"type": "wardrobe", "w": 4, "l": 2},
        ],
    },
    "kitchen": {
        "label": "Kitchen", "weight": 0.95, "priority": 8, "min_w": 8, "min_l": 10,
        "zones": ["SE", "NW", "E"], "habitable": True,
        "furniture": [
            {"type": "l_shape_counter", "w": 8, "l": 2},
            {"type": "sink", "w": 2, "l": 2},
            {"type": "stove", "w": 2.5, "l": 2},
            {"type": "refrigerator", "w": 2.5, "l": 2.5},
        ],
    },
    "dining_room": {
        "label": "Dining Room", "weight": 0.8, "priority": 5, "min_w": 9, "min_l": 10,
        "zones": ["W", "C", "NW", "N"], "habitable": True,
        "furniture": [{"type": "dining_table_6", "w": 6, "l": 3.5}],
    },
    "pooja_room": {
        "label": "Pooja Room", "weight": 0.22, "priority": 7, "min_w": 4, "min_l": 5,
        "zones": ["NE", "N", "E"], "habitable": False,
        "furniture": [{"type": "mandir_unit", "w": 3, "l": 1.5}],
    },
    "study_room": {
        "label": "Study Room", "weight": 0.6, "priority": 4, "min_w": 8, "min_l": 9,
        "zones": ["N", "E", "NE"], "habitable": True,
        "furniture": [
            {"type": "study_table", "w": 4, "l": 2},
            {"type": "bookshelf", "w": 3, "l": 1},
        ],
    },
    "bathroom": {
        "label": "Bathroom", "weight": 0.32, "priority": 6, "min_w": 5, "min_l": 7,
        "zones": ["NW", "W", "S", "N"], "habitable": False,
        "furniture": [
            {"type": "wc", "w": 1.5, "l": 2},
            {"type": "wash_basin", "w": 2, "l": 1.5},
            {"type": "shower", "w": 3, "l": 3},
        ],
    },
    "accessible_bathroom": {
        # sized for a ~5ft wheelchair turning circle, unlike the standard bathroom
        "label": "Accessible Bathroom", "weight": 0.42, "priority": 6, "min_w": 6, "min_l": 9,
        "zones": ["NW", "W", "S", "N"], "habitable": False,
        "furniture": [
            {"type": "wc", "w": 1.5, "l": 2},
            {"type": "wash_basin", "w": 2, "l": 1.5},
            {"type": "shower", "w": 3.5, "l": 3.5},
            {"type": "grab_bar", "w": 2, "l": 0.5},
        ],
    },
    "utility": {
        "label": "Utility Room", "weight": 0.3, "priority": 3, "min_w": 5, "min_l": 7,
        "zones": ["NW", "S", "W"], "habitable": False,
        "furniture": [{"type": "washing_machine", "w": 2.5, "l": 2.5}, {"type": "wash_sink", "w": 2, "l": 1.5}],
    },
    "balcony": {
        "label": "Balcony", "weight": 0.35, "priority": 2, "min_w": 4, "min_l": 7,
        "zones": ["N", "E", "S"], "habitable": False,
        "furniture": [{"type": "planters", "w": 2, "l": 1}],
    },
    "home_office": {
        "label": "Home Office", "weight": 0.55, "priority": 4, "min_w": 8, "min_l": 9,
        "zones": ["N", "E", "NE"], "habitable": True,
        "furniture": [{"type": "desk", "w": 4, "l": 2}, {"type": "chair", "w": 2, "l": 2}],
    },
    "servant_room": {
        "label": "Servant Room", "weight": 0.5, "priority": 2, "min_w": 7, "min_l": 8,
        "zones": ["S", "SW", "NW"], "habitable": True,
        "furniture": [{"type": "bed_single", "w": 3, "l": 6}],
    },
    "store_room": {
        "label": "Store Room", "weight": 0.3, "priority": 2, "min_w": 5, "min_l": 6,
        "zones": ["NW", "S", "SW"], "habitable": False,
        "furniture": [{"type": "shelving", "w": 4, "l": 1.5}],
    },
    "guest_room": {
        "label": "Guest Room", "weight": 0.95, "priority": 5, "min_w": 10, "min_l": 11,
        "zones": ["NW", "N", "W"], "habitable": True,
        "furniture": [{"type": "bed_queen", "w": 5, "l": 6.5}, {"type": "wardrobe", "w": 4, "l": 2}],
    },
    "gym": {
        "label": "Gym", "weight": 0.6, "priority": 2, "min_w": 8, "min_l": 9,
        "zones": ["W", "S", "SW"], "habitable": True,
        "furniture": [{"type": "equipment_rack", "w": 4, "l": 2}],
    },
    "library": {
        "label": "Library", "weight": 0.5, "priority": 2, "min_w": 8, "min_l": 8,
        "zones": ["N", "E", "W"], "habitable": True,
        "furniture": [{"type": "bookshelf", "w": 5, "l": 1}],
    },
    "staircase": {
        "label": "Staircase", "weight": 0.0, "priority": 10, "min_w": 4, "min_l": 10,
        "zones": ["S", "SW", "W"], "habitable": False, "furniture": [],
    },
    "veranda": {
        # a covered semi-open entrance porch -- always pinned to whichever
        # zone actually faces the street (see FRONT_ZONES_BY_FACING)
        "label": "Veranda", "weight": 0.32, "priority": 7, "min_w": 6, "min_l": 5,
        "zones": ["N", "NE", "E", "W"], "habitable": False,
        "furniture": [{"type": "chair", "w": 2, "l": 2}, {"type": "planters", "w": 2, "l": 1}],
    },
    "foyer": {
        # an enclosed entrance hall, alternative to veranda -- same front-zone pinning
        "label": "Foyer", "weight": 0.25, "priority": 7, "min_w": 5, "min_l": 5,
        "zones": ["N", "NE", "E", "W"], "habitable": False, "furniture": [],
    },
}

# Approximate open-parking footprint per vehicle (feet)
CAR_PARKING_SIZE = {"w": 9.0, "l": 17.0}
TWO_WHEELER_PARKING_SIZE = {"w": 3.5, "l": 7.0}

# Wheelchair ramp footprint at the main entrance (feet)
RAMP_WIDTH = 4.0
RAMP_LENGTH = 8.0

# Driveway gate opening at the plot boundary (feet)
MAIN_GATE_WIDTH = 10.0

WALL_THICKNESS_EXTERIOR = 0.75  # 9 inch
WALL_THICKNESS_INTERIOR = 0.42  # 5 inch
DOOR_WIDTH_MAIN = 3.5
DOOR_WIDTH_INTERNAL = 3.0
WINDOW_WIDTH_DEFAULT = 4.0

# Setback rules (simplified local-body norms) as a fraction of the relevant plot dimension,
# with sensible minimums/maximums in feet.
SETBACK_RULES = {
    "front": {"fraction": 0.12, "min": 5.0, "max": 15.0},
    "rear": {"fraction": 0.08, "min": 3.0, "max": 10.0},
    "side": {"fraction": 0.06, "min": 3.0, "max": 8.0},
}

MAX_GROUND_COVERAGE = 0.70  # max fraction of plot area the ground floor footprint may occupy

# Construction cost per sqft by quality tier (illustrative, INR)
COST_TIERS = {
    "economy": 1500,
    "standard": 1900,
    "premium": 2500,
    "luxury": 3500,
}
