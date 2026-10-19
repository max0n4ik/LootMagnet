"""Oak2 loot magnet. All Unreal calls run in SDK keybind/command callbacks."""
from argparse import Namespace
from collections import Counter
import math
import time
import webbrowser

import unrealsdk
from mods_base import (BoolOption, EInputEvent, HiddenOption, SliderOption, build_mod,
                       command, get_pc, hook, keybind)
from unrealsdk.hooks import Type
from unrealsdk.unreal import IGNORE_STRUCT, WeakPointer

from .filtering import RARITIES, accepts, classify_beam, in_radius, ring_position
from .pickup import request_pickup, prepare as prepare_pickup
from .statistics import Statistics, gear_type, GEAR_LABELS
from .selling import sale_context, sell_new_pickup
from .statistics_ui import draw_report, report_style

radius = SliderOption("radius", 3000, 500, 10000, 250,
                      display_name="Radius (100 units ~= 1 metre)")
pickup_gear = BoolOption("pickup_gear", True, display_name="Pick up matching gear")
consumables = BoolOption("consumables", True, display_name="Collect consumables")
rarity_options = {name: BoolOption(name, True, display_name=name.title())
                  for name in RARITIES}
saved_statistics = HiddenOption("statistics", {})
type_options = {name: BoolOption("loot_type_" + name, True, display_name=label)
                for name, label in GEAR_LABELS.items()}
trash_radius = SliderOption("trash_radius", 3000, 500, 10000, 250,
                            display_name="Trash Magnet radius")
trash_rarity_options = {name: BoolOption("trash_" + name, name in ("common", "uncommon"),
                                        display_name=name.title()) for name in RARITIES}
trash_type_options = {name: BoolOption("trash_type_" + name, True, display_name=label)
                      for name, label in GEAR_LABELS.items()}
OPTIONS = [radius, pickup_gear, consumables, *rarity_options.values(), *type_options.values(),
           trash_radius, *trash_rarity_options.values(), *trash_type_options.values(), saved_statistics]
stats = Statistics()
tracking_pc = None
tracking_pawn = None
tracking_deadline = 0.0
next_tracking_poll = 0.0
GITHUB_URL = "https://github.com/max0n4ik"
last_status = "Ready. F6: Loot Magnet; F8: Trash Magnet; Ctrl+F6 or F7: settings."
window_owned = False
pending_window = None
reset_confirmation = False
busy = False
pending_action = None
MAX_BATCH = 100


def notify(message):
    global last_status
    last_status = message
    print(f"[Loot Magnet] {message}")


def backpack_ids(pc):
    try:
        return {entry.InventoryItem.Item.data.InstanceId
                for entry in pc.PlayerState.BackpackItems.items
                if entry.InventoryItem.Item.data.InstanceId > 0}
    except Exception:
        # An unreadable backpack is not an empty backpack.
        return None


def save_statistics():
    saved_statistics.value = stats.snapshot()
    try:
        saved_statistics.save()
    except Exception as exc:
        print(f"[Loot Magnet] Could not save statistics: {exc}")


def poll_tracking(force=False):
    global tracking_pc, tracking_pawn, next_tracking_poll
    if busy or not stats.pending or tracking_pc is None:
        return
    now = time.monotonic()
    if not force and now < next_tracking_poll:
        return
    next_tracking_poll = now + 0.2
    pc = tracking_pc()
    if not pc or pc != get_pc() or (tracking_pawn is not None and tracking_pawn() != pc.Pawn):
        stats.pending.clear()
        tracking_pc = None
        tracking_pawn = None
        return
    if stats.observe(backpack_ids(pc)):
        save_statistics()
    if not stats.pending or now >= tracking_deadline:
        stats.pending.clear()
        tracking_pc = None
        tracking_pawn = None


@hook("/Script/Engine.CameraModifier:BlueprintModifyCamera", Type.POST_UNCONDITIONAL)
def track_pickups(obj, args, ret, func):
    # Same Oak2 game-thread callback used by BLImGui; no window is required.
    process_pending_window()
    process_pending_action()
    poll_tracking()


def queue_run(preview=False, pickup_all=False, trash=False, from_bind=False):
    global pending_action
    if not mod.is_enabled:
        return
    if trash and not preview and not from_bind:
        notify("Trash Magnet can only run from its dedicated keybind.")
        return
    if pending_action is not None or busy:
        notify("A magnet action is already queued or running.")
        return
    pc = get_pc()
    if not pc or not pc.Pawn:
        notify("Load a character first.")
        return
    pending_action = (time.monotonic(), WeakPointer(pc), WeakPointer(pc.Pawn),
                      dict(preview=preview, pickup_all=pickup_all, trash=trash, from_bind=from_bind))
    notify("Queued for the next game camera tick.")


def process_pending_action():
    global pending_action
    if pending_action is None or busy:
        return
    created, player, pawn, options = pending_action
    pending_action = None
    pc = player()
    if (not mod.is_enabled or time.monotonic() - created > 2.0
            or not pc or pc != get_pc() or not pawn() or pawn() != pc.Pawn):
        notify("Queued action cancelled: character changed or action expired.")
        return
    # Keybinds, console commands and native-window buttons all dispatch here.
    # Never bind or invoke the native bridge from the external ImGui thread.
    run(**options)


def reset_statistics():
    global stats, tracking_pc, tracking_pawn, reset_confirmation
    reset_confirmation = False
    stats = Statistics()
    tracking_pc = None
    tracking_pawn = None
    save_statistics()
    notify("Statistics reset.")


def valid(actor):
    return bool(actor and actor != actor.Class.ClassDefaultObject
                and not actor.IsActorBeingDestroyed() and not actor.bHidden
                and actor.RootPrimitiveComponent)


def location(actor):
    point = actor.K2_GetActorLocation()
    return point.X, point.Y, point.Z


def beam(actor):
    component = actor.AttractEffectComponent
    if not component:
        return "unknown"
    params = component.OverrideParameters
    return classify_beam(bytes(params.ParameterData),
                         [(str(v.Name), v.Offset) for v in params.SortedParameterOffsets])


def item_kind(actor):
    kind = beam(actor)
    if kind == "unknown" and "/Game/Gear/" in str(getattr(actor, "BodyData", None)):
        return "gear_unknown"
    return kind


def vendor_items(pc):
    # Vending-machine displays are InventoryPickup actors too.
    displays = []
    for machine in unrealsdk.find_all("OakVendingMachine", exact=False):
        if not machine or machine == machine.Class.ClassDefaultObject:
            continue
        if machine.IsActorBeingDestroyed():
            continue
        item = machine.GetIOTDForPlayer(pc)
        if item:
            displays.append(item)
    return displays


def candidates(pc, origin, search_radius):
    displays = vendor_items(pc)
    found = []
    errors = 0
    for actor in unrealsdk.find_all("InventoryPickup", exact=False):
        try:
            if not valid(actor) or actor in displays:
                continue
            pos = location(actor)
            if not in_radius(origin, pos, search_radius):
                continue
            kind = item_kind(actor)
            distance = sum((a - b) ** 2 for a, b in zip(origin, pos))
            found.append((distance, actor, kind))
        except Exception:
            # An actor may disappear while scanning a shared world.
            errors += 1
    found.sort(key=lambda entry: entry[0])
    return found, errors


def run(preview=False, pickup_all=False, trash=False, from_bind=False):
    global busy, tracking_pc, tracking_pawn, tracking_deadline, next_tracking_poll
    if trash and not preview and not from_bind:
        notify("Trash Magnet can only run from its dedicated keybind.")
        return
    if not preview:
        poll_tracking(force=True)
        if stats.pending:
            notify("Waiting for pickup confirmation (up to 3 seconds).")
            return
    if busy:
        notify("A batch is already running.")
        return
    busy = True
    stats_started = False
    try:
        pc = get_pc()
        if not pc or not pc.Pawn:
            notify("Load a character first.")
            return
        search_radius = float((trash_radius if trash else radius).value)
        if not math.isfinite(search_radius) or not 500 <= search_radius <= 10000:
            notify("Invalid radius; choose 500..10000.")
            return
        selected_rarities = trash_rarity_options if trash else rarity_options
        selected_types = trash_type_options if trash else type_options
        allowed = {name for name, opt in selected_rarities.items() if opt.value is True}
        origin = location(pc.Pawn)
        found, errors = candidates(pc, origin, search_radius)
        matched = [row for row in found if (
            row[2] in (*RARITIES, "gear_unknown") if pickup_all
            else ((row[2] in allowed) if trash else accepts(row[2], allowed, consumables.value is True)))
            and (not trash or "/Game/Gear/" in str(getattr(row[1], "BodyData", None)))
            and (pickup_all or row[2] not in (*RARITIES, "gear_unknown")
                 or selected_types[gear_type(getattr(row[1], "BodyData", None))].value is True)]
        if preview:
            notify(f"Nearby: {dict(Counter(row[2] for row in found))}; "
                   f"match={len(matched)}, scan_errors={errors}. Nothing moved.")
            for _, actor, kind in found[:20]:
                print(f"[Loot Magnet] {kind}: {actor._path_name()} | BodyData={actor.BodyData}")
                if kind in ("unknown", "gear_unknown") and actor.AttractEffectComponent:
                    params = actor.AttractEffectComponent.OverrideParameters
                    data = bytes(params.ParameterData)
                    for var in params.SortedParameterOffsets:
                        if str(var.Name) == "User.Color" and var.Offset >= 0:
                            print(f"[Loot Magnet] Unknown User.Color={data[var.Offset:var.Offset + 16].hex()}")
            return
        original_ids = backpack_ids(pc)
        if trash and original_ids is None:
            raise RuntimeError("Cannot read backpack; Trash Magnet stopped")
        context = sale_context(pc) if trash and matched else None
        if any(kind in RARITIES or (pickup_all and kind == "gear_unknown")
               for _, _, kind in matched) and (trash or pickup_all or pickup_gear.value):
            prepare_pickup(pc)
        stats.start(len(found), len(matched), original_ids)
        stats_started = True
        moved = requests = gear_index = sold = kept = 0
        for _, actor, kind in matched[:MAX_BATCH]:
            try:
                if not valid(actor):
                    continue
                # Re-read before moving; never process an actor that changed classification.
                if item_kind(actor) != kind:
                    continue
                should_pickup = (kind in RARITIES or (pickup_all and kind == "gear_unknown")) and (
                    trash or pickup_all or pickup_gear.value)
                if kind in (*RARITIES, "gear_unknown"):
                    if should_pickup:
                        forward = pc.Pawn.GetActorForwardVector()
                        target = (origin[0] + forward.X * 120, origin[1] + forward.Y * 120,
                                  origin[2] - 40)
                    else:
                        target = ring_position(origin, gear_index)
                        gear_index += 1
                else:
                    target = (origin[0], origin[1], origin[2] - 40)
                vector = unrealsdk.make_struct("Vector", X=target[0], Y=target[1], Z=target[2])
                actor.RootPrimitiveComponent.SetSimulatePhysics(True)
                if not actor.K2_TeleportTo(vector, IGNORE_STRUCT):
                    errors += 1
                    continue
                moved += 1
                stats.moved(gear=kind in (*RARITIES, "gear_unknown"))
                if should_pickup and valid(actor):
                    collected_type = gear_type(getattr(actor, "BodyData", None))
                    before_pickup = backpack_ids(pc)
                    native_result = request_pickup(pc, actor)
                    requests += 1
                    after_pickup = backpack_ids(pc)
                    added = (after_pickup - before_pickup
                             if before_pickup is not None and after_pickup is not None else set())
                    # BL4 assigns a new InstanceId when moving gear into the backpack.
                    stats.requested(next(iter(added)) if len(added) == 1 else None, collected_type, kind)
                    stats.observe(after_pickup)
                    print(f"[Loot Magnet] Native pickup: added={sorted(added)}; result={native_result}")
                    if trash:
                        if sell_new_pickup(pc, before_pickup, after_pickup, original_ids, context):
                            sold += 1
                        else:
                            kept += 1
            except Exception as exc:
                errors += 1
                print(f"[Loot Magnet] Skipped item: {exc}")
        sale_status = f"Trash Magnet: sold={sold}; unconfirmed/kept={kept}. " if trash else "Loot Magnet: "
        notify(sale_status + f"Teleported={moved}; pickup requests={requests}; "
               f"confirmed gear={stats.last['confirmed_gear']}; errors={errors}; "
               f"left for next press={max(0, len(matched) - MAX_BATCH)}. "
               "Requests do not confirm pickup; a full backpack may refuse them.")
    except Exception as exc:
        notify(f"Stopped: {exc}")
    finally:
        busy = False
        if stats_started:
            if stats.pending:
                tracking_pc = WeakPointer(pc)
                tracking_pawn = WeakPointer(pc.Pawn)
                tracking_deadline = time.monotonic() + 3.0
                next_tracking_poll = 0.0
            save_statistics()
            poll_tracking(force=True)


@keybind("Loot Magnet - collect", "F6", event_filter=EInputEvent.IE_Pressed)
def collect():
    # Oak2 matches a single FKey name, not strings such as 'Ctrl+F6'.
    pc = get_pc()
    if pc and any(pc.IsInputKeyDown(unrealsdk.make_struct("Key", KeyName=name))
                  for name in ("LeftControl", "RightControl")):
        show_settings()
        return
    queue_run()


@keybind("Trash Magnet - collect and sell", "F8", event_filter=EInputEvent.IE_Pressed)
def collect_trash():
    queue_run(trash=True, from_bind=True)


@command(description="Teleport and request pickup for matching loot in radius.")
def lootmagnet_run(args: Namespace):
    queue_run()


@command(description="Request pickup of all gear in radius, ignoring rarity and pickup toggles.")
def lootmagnet_pickup_all(args: Namespace):
    queue_run(pickup_all=True)


@command(description="Read nearby loot classifications without moving or collecting anything.")
def lootmagnet_preview(args: Namespace):
    queue_run(preview=True)


def draw_window():
    global reset_confirmation
    import blimgui
    from blimgui import imgui
    visible, opened = imgui.begin("Loot Magnet settings", True)
    try:
        if not opened:
            reset_confirmation = False
            blimgui.close_window()
            return
        if visible:
            draw_contents()
    finally:
        imgui.end()


def draw_contents():
    global reset_confirmation
    import blimgui
    from blimgui import imgui
    if not mod.is_enabled:
        imgui.text_wrapped("Loot Magnet is disabled. Close this window and enable the mod.")
        return
    imgui.text_wrapped("Loot Magnet: F6. Trash Magnet: F8. Rebind both in the SDK mod menu.")
    imgui.text_wrapped("Native pickup on the standard SDK. Actions run on the next game tick.")
    imgui.separator()
    imgui.text("Loot Magnet - collect and keep")
    changed, value = imgui.slider_int("Radius", int(radius.value), 500, 10000)
    if changed:
        radius.value = value
    for opt in [pickup_gear, consumables, *rarity_options.values()]:
        changed, value = imgui.checkbox(opt.display_name, bool(opt.value))
        if changed:
            opt.value = value
    if imgui.collapsing_header("Equipment types##loot"):
        for name, opt in type_options.items():
            changed, value = imgui.checkbox(opt.display_name + "##loot_" + name, bool(opt.value))
            if changed:
                opt.value = value
    imgui.text_wrapped("Unclassified gear is TELEPORTED ONLY when all rarities are enabled. "
                       "Mission beams are skipped. Loot Magnet never sells. "
                       "Settings are saved to sdk_mods/settings/loot_magnet.json.")
    imgui.separator()
    imgui.text("Trash Magnet - collect and sell (F8)")
    changed, value = imgui.slider_int("Radius##trash", int(trash_radius.value), 500, 10000)
    if changed:
        trash_radius.value = value
    for name, opt in trash_rarity_options.items():
        changed, value = imgui.checkbox(opt.display_name + "##trash_" + name, bool(opt.value))
        if changed:
            opt.value = value
    if imgui.collapsing_header("Equipment types##trash"):
        for name, opt in trash_type_options.items():
            changed, value = imgui.checkbox(opt.display_name + "##trash_type_" + name, bool(opt.value))
            if changed:
                opt.value = value
    imgui.text_wrapped("Dedicated keybind only. Sells only its own confirmed new pickups. "
                       "Manual pickups and existing backpack items are excluded. "
                       "Unknown rarity and consumables are skipped. A loaded vending machine is required.")
    if imgui.button("Preview trash filter"):
        queue_run(preview=True, trash=True)
    imgui.separator()
    if imgui.button("Statistics"):
        show_statistics()
    imgui.same_line()
    if imgui.button("Preview"):
        queue_run(preview=True)
    imgui.same_line()
    if imgui.button("Collect now"):
        queue_run()
    if imgui.button("Pick up all gear"):
        queue_run(pickup_all=True)
    imgui.same_line()
    if imgui.button("Close"):
        reset_confirmation = False
        blimgui.close_window()
    if imgui.button("GitHub: max0n4ik"):
        open_profile()
    imgui.text_wrapped(last_status)


def draw_statistics():
    global reset_confirmation
    from blimgui import imgui
    draw_report(stats)
    if reset_confirmation:
        imgui.text_wrapped("Reset all statistics? This cannot be undone.")
        if imgui.button("Reset##confirm_statistics"):
            reset_statistics()
        imgui.same_line()
        if imgui.button("Cancel##cancel_statistics"):
            reset_confirmation = False
    elif imgui.button("Reset statistics"):
        reset_confirmation = True
    imgui.separator()


def draw_statistics_window():
    global reset_confirmation
    import blimgui
    from blimgui import imgui
    with report_style():
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.work_pos, imgui.Cond_.always)
        imgui.set_next_window_size(viewport.work_size, imgui.Cond_.always)
        visible, opened = imgui.begin("Loot Magnet statistics", True,
                                      imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_resize
                                      | imgui.WindowFlags_.no_collapse)
        try:
            if not opened:
                reset_confirmation = False
                blimgui.close_window()
                return
            if visible:
                draw_statistics()
                if imgui.button("Settings"):
                    show_settings()
                imgui.same_line()
                if imgui.button("GitHub: max0n4ik"):
                    open_profile()
                imgui.same_line()
                if imgui.button("Close"):
                    reset_confirmation = False
                    blimgui.close_window()
        finally:
            imgui.end()


def open_profile():
    try:
        if not webbrowser.open(GITHUB_URL):
            notify(f"Open in your browser: {GITHUB_URL}")
    except Exception as exc:
        notify(f"Cannot open browser: {exc}. {GITHUB_URL}")


@keybind("Loot Magnet settings (F7)", "F7")
def open_settings():
    show_settings()


def show_settings():
    request_window("settings")


def show_statistics():
    request_window("statistics")


def create_owned_window(page):
    global window_owned
    import blimgui
    if page == "statistics":
        blimgui.create_window("Loot Magnet statistics", width=820, height=840, callback=draw_statistics_window)
    else:
        blimgui.create_window("Loot Magnet", width=620, height=720, callback=draw_window)
    window_owned = True


def request_window(page):
    global pending_window, reset_confirmation
    reset_confirmation = False
    try:
        import blimgui
        if blimgui.is_window_open():
            current = getattr(getattr(blimgui, "IMPL", None), "_draw_callback", None)
            wanted = draw_statistics_window if page == "statistics" else draw_window
            if current in (draw_window, draw_statistics_window):
                pending_window = page if current is not wanted else None
                blimgui.close_window()
            else:
                notify("Close the other mod's BLImGui window first.")
            return
        if blimgui.hello_imgui.is_using_hello_imgui():
            pending_window = page
            return
        create_owned_window(page)
    except ImportError:
        notify("Install and enable BLImGui for the settings window. JSON settings still work.")
    except Exception as exc:
        notify(f"Cannot open settings: {exc}")


def process_pending_window():
    global pending_window
    if pending_window is None:
        return
    try:
        import blimgui
        # close_window only sets a flag: wait until the backend has destroyed its old context.
        if blimgui.hello_imgui.is_using_hello_imgui():
            if getattr(getattr(blimgui, "IMPL", None), "_draw_callback", None) not in (
                    draw_window, draw_statistics_window):
                pending_window = None
                notify("Close the other mod's BLImGui window first.")
            return
        page, pending_window = pending_window, None
        create_owned_window(page)
    except Exception as exc:
        pending_window = None
        notify(f"Cannot open window: {exc}")


@command(description="Open the optional BLImGui Loot Magnet settings window.")
def lootmagnet_gui(args: Namespace):
    show_settings()


@command(description="Open the separate loot statistics window.")
def lootmagnet_stats(args: Namespace):
    show_statistics()


def on_disable():
    global window_owned, tracking_pc, tracking_pawn, reset_confirmation, pending_window, pending_action
    pending_action = None
    pending_window = None
    reset_confirmation = False
    poll_tracking(force=True)
    stats.pending.clear()
    tracking_pc = None
    tracking_pawn = None
    if window_owned:
        try:
            import blimgui
            # Do not close a window owned by another mod after our window was closed.
            if getattr(getattr(blimgui, "IMPL", None), "_draw_callback", None) in (draw_window, draw_statistics_window):
                blimgui.close_window()
        except ImportError:
            pass
        window_owned = False


mod = build_mod(options=OPTIONS,
                keybinds=[collect, collect_trash, open_settings],
                hooks=[track_pickups],
                commands=[lootmagnet_run, lootmagnet_pickup_all, lootmagnet_preview, lootmagnet_gui, lootmagnet_stats],
                on_disable=on_disable)
stats = Statistics(saved_statistics.value)
