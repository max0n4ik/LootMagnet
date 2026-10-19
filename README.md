# Loot Magnet for Borderlands 4

[Русский README](README.ru.md)

Loot Magnet brings nearby drops to your character and can collect equipment into your backpack. It has two independently configured actions: **Loot Magnet** keeps items, while **Trash Magnet** collects and sells matching items when you press its key.

**Version 0.2.0 is an experimental Windows x64 build.** It uses the standard SDK plus a small native helper included with the mod; replacing the SDK DLLs is not required.

## Features

- Separate pickup radius, equipment types and rarity filters for each magnet.
- Loot Magnet collects matching equipment and brings ammo, money, health and eridium into contact-pickup range.
- Pick up all gear collects equipment regardless of the type and rarity checkboxes and never sells it.
- Trash Magnet sells only items immediately identified as newly collected by its own key-triggered action. Normal manual pickups do not trigger sales.
- A settings window and a separate statistics window: last action, totals, uses, and confirmed equipment pickups by type and rarity. Reset requires confirmation.
- Settings and statistics persist between sessions.

## Requirements

- Borderlands 4 on Windows x64.
- The BL4 Python SDK, including `mods_base`. This build targets Python 3.14 and unrealsdk 3.2.0, commit `b1852aa4`. Other SDK revisions are not supported by the native helper.
- [BLImGui](https://github.com/juso40/blimgui) for the settings and statistics windows.

SDK projects: [unrealsdk](https://github.com/bl-sdk/unrealsdk), [pyunrealsdk](https://github.com/bl-sdk/pyunrealsdk). Install the SDK and BLImGui using their upstream instructions first.

## Installation

1. Close the game completely.
2. Download [loot_magnet-0.2.0-native.zip](dist/loot_magnet-0.2.0-native.zip) using GitHub's **Download raw file** button.
3. Remove any older Loot Magnet installation from `sdk_mods` (move it outside that directory). Keep `sdk_mods/settings/loot_magnet.json` to preserve settings and statistics.
4. Extract the **entire `loot_magnet` folder** from the archive into `<Borderlands 4>/sdk_mods/`.
5. Start the game and enable Loot Magnet and BLImGui in the SDK mod menu.

The resulting layout must include:

```text
Borderlands 4/
  sdk_mods/
    loot_magnet/
      __init__.py
      native/
        loot_native_bridge.dll
        build-manifest.json
```

Do not rename the ZIP to `.sdkmod`: the native DLL must be extracted onto disk. Install only one copy of the mod. Disable other loot magnets and auto-selling mods while testing.

## Controls

| Default key | Action |
| --- | --- |
| F6 | Loot Magnet: collect and keep matching loot |
| F8 | Trash Magnet: collect and sell matching equipment |
| F7 or Ctrl+F6 | Open settings |

The main actions can be rebound in the SDK keybind menu. If a shortcut does not open settings, use `lootmagnet_gui` in the SDK console. Open statistics from settings or with `lootmagnet_stats`.

Other console commands: `lootmagnet_preview`, `lootmagnet_run`, `lootmagnet_pickup_all`. Console commands and window buttons never authorize selling.

## Trash Magnet behavior

The default trash filter accepts Common and Uncommon equipment. Review its filters before pressing F8. A loaded vending-machine context is required; without it the action stops before pickup. Selling away from a machine has not been verified.

Only one immediately appearing backpack ID per pickup request qualifies for sale. Existing backpack items, equipped items, locked items and items with nonzero state flags are excluded. Ambiguous or delayed pickups remain in the backpack; there is no background sale retry. Consumables and unknown-rarity items are excluded from Trash Magnet.

## Current limits and validation

- Single-item native pickup was confirmed in game on the original SDK DLL pair. The complete F6/F8 batch workflow on that SDK still needs in-game validation; local mock and ABI tests do not emulate the engine.
- Pickup reads a game-build-specific field offset. A game update can break compatibility even when the class size is unchanged. The helper rejects known SDK/parameter-layout mismatches.
- At most 100 nearby matching objects are processed per action. Leave room in your backpack; free equipped-weapon slots are not required for backpack pickup.
- Excess ammo is not deleted. Consumables are moved for the game's contact pickup rather than directly inserted into inventory.
- Unknown-rarity gear is only moved when all rarities are enabled; Pick up all gear can attempt to collect it without selling.
- Co-op behavior is unverified. Statistics are shared by both magnets; this is not a per-item journal.
- Full item serial extraction and filters based on individual item parts are still research work and are not included.

## Source and native helper

Python source is in `loot_magnet/`. The complete helper source and build notes are in [`loot_magnet/native/source/`](loot_magnet/native/source/BUILD.md). The archive includes the compiled helper and its SHA-256 manifest. Game binaries, SDK DLLs, save files and research dumps are not distributed here.

See [third-party notices](loot_magnet/licenses/THIRD-PARTY.md) for SDK licensing. Development used OpenAI Codex. This is a community mod by [max0n4ik](https://github.com/max0n4ik), not an official SDK or game release.
