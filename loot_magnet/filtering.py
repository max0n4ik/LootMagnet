"""Pure loot classification; colors come from database_tables/rarity.json."""
import math
import struct

RARITIES = ("common", "uncommon", "rare", "epic", "legendary", "pearlescent")
COLORS = {
    "ammo": (0.435, 0.435, 0.435, 1.0),
    "eridium": (0.5, 0.0, 1.0, 1.0),
    "health": (1.0, 0.0, 0.0, 1.0),
    "mission": (0.0, 1.0, 1.0, 1.0),
    "money": (1.0, 1.0, 0.0, 1.0),
    "common": (0.287441, 0.278894, 0.391573, 1.0),
    "uncommon": (0.010330, 0.250158, 0.025187, 1.0),
    "rare": (0.016807, 0.119538, 0.434154, 1.0),
    "epic": (0.254152, 0.010330, 0.450786, 1.0),
    "legendary": (1.0, 0.229151, 0.0, 1.0),
}
CONSUMABLES = ("ammo", "eridium", "health", "money")
# Live User.Color matches displaycolor.source in the same game table, not
# attracteffectparameters.Color. Accept both explicit palettes, never nearest color.
DISPLAY_COLORS = {
    "common": (0.514918, 0.491021, 0.623961, 1.0),
    "uncommon": (0.095307, 0.558341, 0.111932, 1.0),
    "rare": (0.018500, 0.337164, 0.590619, 1.0),
    "epic": (0.479320, 0.056128, 0.658375, 1.0),
    # User-identified pearlescent ORD sniper, repeated in two live reports.
    "pearlescent": (0.309469, 1.0, 0.644480, 1.0),
}


def classify_beam(data, offsets):
    """Only recognize a complete, known User.Color; unknowns never match."""
    for name, offset in offsets:
        if name != "User.Color":
            continue
        if not isinstance(offset, int) or offset < 0 or offset + 16 > len(data):
            return "unknown"
        color = struct.unpack_from("<4f", data, offset)
        if not all(math.isfinite(v) for v in color):
            return "unknown"
        for rarity, expected in [*COLORS.items(), *DISPLAY_COLORS.items()]:
            if all(abs(a - b) <= 0.00002 for a, b in zip(color, expected)):
                return rarity
    return "unknown"


def accepts(kind, allowed_rarities, consumables):
    if kind == "gear_unknown":
        # All rarities selected: allow moving actual gear, without guessing its rarity.
        return set(allowed_rarities) == set(RARITIES)
    return kind in allowed_rarities if kind in RARITIES else (
        consumables and kind in CONSUMABLES
    )


def in_radius(origin, location, radius):
    values = (*origin, *location, radius)
    return all(math.isfinite(v) for v in values) and radius > 0 and sum(
        (a - b) ** 2 for a, b in zip(origin, location)
    ) <= radius * radius


def ring_position(origin, index):
    angle = index * (2 * math.pi / 12)
    radius = 150.0 + 60.0 * (index // 12)
    return (origin[0] + radius * math.cos(angle),
            origin[1] + radius * math.sin(angle), origin[2])
