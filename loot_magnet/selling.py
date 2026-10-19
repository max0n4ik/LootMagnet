"""Single-item sales, only for an immediate, unambiguous hotkey pickup."""
import unrealsdk


def sale_context(pc):
    origin = pc.Pawn.K2_GetActorLocation()
    machines = [m for m in unrealsdk.find_all("OakVendingMachine", exact=False)
                if m and m != m.Class.ClassDefaultObject and not m.IsActorBeingDestroyed()]
    if not machines:
        raise RuntimeError("Trash Magnet: no loaded vending machine; nothing collected")
    machine = min(machines, key=lambda m: sum(
        (getattr(m.K2_GetActorLocation(), k) - getattr(origin, k)) ** 2 for k in ("X", "Y", "Z")))
    cash = next(c for c in pc.CurrencyManager.currencies if str(c.type.Name) == "Cash")
    token = unrealsdk.make_struct("SToken", Name="Cash", Hash=cash.type.Hash)
    return machine, token


def sell_new_pickup(pc, before, after, original, context):
    if before is None or after is None or original is None:
        return False
    added = set(after) - set(before)
    if len(added) != 1:
        return False
    target = next(iter(added))
    if target in original:
        return False
    entries = [e for e in pc.PlayerState.BackpackItems.items
               if int(e.InventoryItem.Item.data.InstanceId) == target]
    if len(entries) != 1:
        return False
    entry = entries[0]
    item = entry.InventoryItem
    # State zero was verified on the successfully sold test weapon. Unknown states stay.
    if (entry.IsLocked or int(item.Flags) != 0 or int(item.EquipSlot) != -1
            or int(item.Item.State.Flags) != 0 or int(item.Handle.Handle) < 0):
        return False
    machine, token = context
    if machine.IsActorBeingDestroyed():
        return False
    handle = unrealsdk.make_struct("InventoryItemHandle", Handle=item.Handle.Handle)
    cash_before = next(int(c.Amount) for c in pc.CurrencyManager.currencies if str(c.type.Name) == "Cash")
    pc.ServerSellItem(machine, handle, "backpack", token)
    # A request alone is not a sale confirmation; never retry automatically.
    absent = not any(int(e.InventoryItem.Item.data.InstanceId) == target
                     for e in pc.PlayerState.BackpackItems.items)
    cash_after = next(int(c.Amount) for c in pc.CurrencyManager.currencies if str(c.type.Name) == "Cash")
    return absent and cash_after > cash_before
