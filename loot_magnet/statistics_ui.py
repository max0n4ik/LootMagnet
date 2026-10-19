"""Statistics presentation; uses the ImGui API bundled with BLImGui."""
from contextlib import contextmanager

from .statistics import GEAR_LABELS, RARITY_LABELS

GOLD = (0.94, 0.75, 0.39, 1.0)
TEAL = (0.36, 0.85, 0.73, 1.0)
MUTED = (0.56, 0.61, 0.69, 1.0)
RARITY_COLORS = {
    "common": (0.75, 0.77, 0.82, 1.0), "uncommon": (0.40, 0.86, 0.45, 1.0),
    "rare": (0.34, 0.64, 1.0, 1.0), "epic": (0.76, 0.47, 0.98, 1.0),
    "legendary": (1.0, 0.65, 0.24, 1.0), "pearlescent": (0.48, 1.0, 0.78, 1.0),
    "unknown": MUTED,
}


@contextmanager
def report_style():
    from blimgui import imgui
    variables = [(imgui.StyleVar_.window_padding, (22, 18)),
                 (imgui.StyleVar_.item_spacing, (10, 9)),
                 (imgui.StyleVar_.cell_padding, (12, 7)),
                 (imgui.StyleVar_.child_rounding, 9.0),
                 (imgui.StyleVar_.frame_rounding, 5.0)]
    colors = [(imgui.Col_.window_bg, (0.055, 0.067, 0.086, 1.0)),
              (imgui.Col_.child_bg, (0.085, 0.103, 0.13, 1.0)),
              (imgui.Col_.border, (0.16, 0.19, 0.24, 1.0)),
              (imgui.Col_.table_header_bg, (0.12, 0.15, 0.19, 1.0)),
              (imgui.Col_.table_row_bg_alt, (0.11, 0.13, 0.16, 0.65)),
              (imgui.Col_.button, (0.17, 0.21, 0.26, 1.0)),
              (imgui.Col_.button_hovered, (0.25, 0.30, 0.36, 1.0)),
              (imgui.Col_.button_active, (0.31, 0.36, 0.42, 1.0))]
    for key, value in variables:
        imgui.push_style_var(key, value)
    for key, value in colors:
        imgui.push_style_color(key, value)
    try:
        yield
    finally:
        imgui.pop_style_color(len(colors))
        imgui.pop_style_var(len(variables))


def breakdown_rows(stats):
    return [(GEAR_LABELS[kind], rarity, stats.last_breakdown.get(kind, {}).get(rarity, 0),
             stats.breakdown.get(kind, {}).get(rarity, 0))
            for kind in GEAR_LABELS for rarity in RARITY_LABELS
            if stats.breakdown.get(kind, {}).get(rarity, 0)
            or stats.last_breakdown.get(kind, {}).get(rarity, 0)]


def draw_report(stats):
    from blimgui import imgui
    last, total = stats.last, stats.total
    imgui.text_colored(GOLD, "LOOT MAGNET  /  COLLECTION REPORT")
    imgui.text_disabled("Confirmed backpack pickups, grouped by equipment type and rarity.")
    imgui.spacing()
    if imgui.begin_table("summary_cards", 3, imgui.TableFlags_.sizing_stretch_same):
        try:
            for title, value, subtitle, color in (
                ("LAST RUN", last["confirmed_gear"], f"{last['matched']:,} matched / {last['found']:,} nearby", TEAL),
                ("ALL TIME", total["confirmed_gear"], "equipment pickups confirmed", GOLD),
                ("ACTIVATIONS", total["uses"], "successful loot scans", (0.69, 0.77, 0.93, 1.0)),
            ):
                imgui.table_next_column()
                imgui.begin_child(title, (0, 112), imgui.ChildFlags_.borders)
                try:
                    imgui.text_disabled(title)
                    imgui.set_window_font_scale(1.65)
                    imgui.text_colored(color, f"{value:,}")
                    imgui.set_window_font_scale(1.0)
                    imgui.text_disabled(subtitle)
                finally:
                    imgui.end_child()
        finally:
            imgui.end_table()
    imgui.spacing()
    flags = imgui.TableFlags_.row_bg | imgui.TableFlags_.borders_inner_h | imgui.TableFlags_.sizing_stretch_prop
    imgui.text_colored(GOLD, "RARITIES")
    if imgui.begin_table("rarity_totals", 3, flags):
        try:
            for label in ("Rarity", "Last run", "All time"):
                imgui.table_setup_column(label)
            imgui.table_headers_row()
            for rarity, label in RARITY_LABELS.items():
                recent = sum(row.get(rarity, 0) for row in stats.last_breakdown.values())
                lifetime = sum(row.get(rarity, 0) for row in stats.breakdown.values())
                if rarity == "unknown" and not recent and not lifetime:
                    continue
                imgui.table_next_row()
                imgui.table_next_column()
                imgui.text_colored(RARITY_COLORS[rarity], label)
                for value in (recent, lifetime):
                    imgui.table_next_column()
                    imgui.text_colored(TEAL if value else MUTED, f"{value:,}")
        finally:
            imgui.end_table()
    imgui.spacing()
    imgui.text_colored(GOLD, "EQUIPMENT  /  TYPE + RARITY")
    rows = breakdown_rows(stats)
    table_height = min(260, 40 + 31 * len(rows), max(100, imgui.get_content_region_avail().y - 164))
    if not rows:
        imgui.text_disabled("No detailed pickups yet. Collect equipment to fill this report.")
    elif imgui.begin_table("equipment_breakdown", 4, flags | imgui.TableFlags_.scroll_y,
                           (0, table_height)):
        try:
            for label in ("Equipment type", "Rarity", "Last run", "All time"):
                imgui.table_setup_column(label)
            imgui.table_setup_scroll_freeze(0, 1)
            imgui.table_headers_row()
            for label, rarity, recent, lifetime in rows:
                imgui.table_next_row()
                imgui.table_next_column()
                imgui.text_unformatted(label)
                imgui.table_next_column()
                imgui.text_colored(RARITY_COLORS[rarity], RARITY_LABELS[rarity])
                for value in (recent, lifetime):
                    imgui.table_next_column()
                    imgui.text_colored(TEAL if value else MUTED, f"{value:,}")
        finally:
            imgui.end_table()
    tracked = sum(sum(row.values()) for row in stats.breakdown.values())
    historical = max(0, total["confirmed_gear"] - tracked)
    if historical:
        imgui.text_disabled(f"Previous versions: {historical:,} pickups without type / rarity details.")
    imgui.spacing()
    imgui.separator()
    imgui.text_wrapped(f"Consumable packs moved: {last['moved_consumables']:,} last run / "
                      f"{total['moved_consumables']:,} all time. Pickup quantities are not tracked.")
    imgui.text_wrapped(f"Gear moved: {last['moved_gear']:,} / {total['moved_gear']:,}    "
                      f"Pickup requests: {last['requests']:,} / {total['requests']:,}  (last / all)")
