"""Persistent counters; only matching new backpack instance IDs confirm gear pickup."""

COUNTERS = ("uses", "moved_gear", "moved_consumables", "requests", "confirmed_gear")
LAST_COUNTERS = ("found", "matched", *COUNTERS[1:])
RARITY_LABELS = {"common": "Common", "uncommon": "Uncommon", "rare": "Rare", "epic": "Epic",
                 "legendary": "Legendary", "pearlescent": "Pearlescent", "unknown": "Unknown"}
GEAR_LABELS = {"pistol": "Pistols", "smg": "SMGs", "assault_rifle": "Assault rifles",
               "shotgun": "Shotguns", "sniper": "Sniper rifles", "heavy_weapon": "Heavy weapons",
               "shield": "Shields", "grenade": "Grenades", "class_mod": "Class mods",
               "enhancement": "Enhancements", "repair_kit": "Repair kits", "other_gear": "Other gear"}
BODY_TYPES = (("Weapons/Pistols/", "pistol"), ("Weapons/SMG/", "smg"),
              ("Weapons/AssaultRifles/", "assault_rifle"), ("Weapons/Shotguns/", "shotgun"),
              ("Weapons/Sniper/", "sniper"), ("Gadgets/HeavyWeapons/", "heavy_weapon"),
              ("Shields/", "shield"), ("GrenadeGadgets/", "grenade"),
              ("ClassMods/", "class_mod"), ("Enhancements/", "enhancement"),
              ("RepairKits/", "repair_kit"))


def gear_type(body):
    path = str(body)
    return next((kind for prefix, kind in BODY_TYPES if "/Game/Gear/" + prefix in path), "other_gear")


def load_breakdown(saved):
    if not isinstance(saved, dict):
        return {}
    result = {}
    for kind in GEAR_LABELS:
        row = saved.get(kind, {})
        if isinstance(row, dict):
            clean = {rarity: counter(row.get(rarity)) for rarity in RARITY_LABELS
                     if counter(row.get(rarity))}
            if clean:
                result[kind] = clean
    return result


def counter(value):
    return value if type(value) is int and value >= 0 else 0


class Statistics:
    def __init__(self, saved=None):
        saved = saved if isinstance(saved, dict) else {}
        self.total = {key: counter(saved.get(key)) for key in COUNTERS}
        last = saved.get("last", {})
        last = last if isinstance(last, dict) else {}
        self.last = {key: counter(last.get(key)) for key in LAST_COUNTERS}
        self.baseline = None
        self.pending = {}
        self.breakdown = load_breakdown(saved.get("breakdown"))
        self.last_breakdown = load_breakdown(last.get("breakdown"))

    def snapshot(self):
        return {**self.total, "breakdown": load_breakdown(self.breakdown),
                "last": {**self.last, "breakdown": load_breakdown(self.last_breakdown)}}

    def start(self, found, matched, backpack_ids):
        self.total["uses"] += 1
        self.last = dict.fromkeys(LAST_COUNTERS, 0)
        self.last.update(found=found, matched=matched)
        self.baseline = set(backpack_ids) if backpack_ids is not None else None
        self.pending.clear()
        self.last_breakdown = {}

    def moved(self, gear):
        key = "moved_gear" if gear else "moved_consumables"
        self.last[key] += 1
        self.total[key] += 1

    def requested(self, instance_id, kind="other_gear", rarity="unknown"):
        self.last["requests"] += 1
        self.total["requests"] += 1
        if (type(instance_id) is int and instance_id > 0 and self.baseline is not None
                and instance_id not in self.baseline):
            self.pending[instance_id] = (kind if kind in GEAR_LABELS else "other_gear",
                                         rarity if rarity in RARITY_LABELS else "unknown")

    def observe(self, backpack_ids):
        if backpack_ids is None or self.baseline is None:
            return 0
        confirmed = set(self.pending) & (set(backpack_ids) - self.baseline)
        for instance_id in confirmed:
            kind, rarity = self.pending.pop(instance_id)
            for breakdown in (self.breakdown, self.last_breakdown):
                row = breakdown.setdefault(kind, {})
                row[rarity] = row.get(rarity, 0) + 1
        self.last["confirmed_gear"] += len(confirmed)
        self.total["confirmed_gear"] += len(confirmed)
        return len(confirmed)
