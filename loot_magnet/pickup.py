"""Project-owned, version-pinned pickup bridge; no SDK patches or Python argument copies."""
import ctypes
import hashlib
import json
from pathlib import Path

import unrealsdk
from mods_base import get_pc
from unrealsdk.unreal import WrappedStruct

ROOT = Path(__file__).resolve().parent
FUNCTION = '/Script/OakGame.OakPlayerController:ServerUseJunkObject'
PICKUP_CLASS = '/Script/GbxGame.InventoryPickup'
PICKUP_SIZE = 2496
# shortcut: actor field offset is still game-build-specific; replace after a validated API is found.
JUNK_OFFSET = 1944
_library = None


def library():
    global _library
    if _library is None:
        dll = ROOT / 'native/loot_native_bridge.dll'
        manifest = json.loads(dll.with_name('build-manifest.json').read_text(encoding='utf-8'))
        if hashlib.sha256(dll.read_bytes()).hexdigest() != manifest['dll_sha256']:
            raise RuntimeError('Bridge DLL does not match its build manifest')
        module = ctypes.CDLL(str(dll))
        module.lm_prepare.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        module.lm_prepare.restype = ctypes.c_int
        module.lm_pickup.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        module.lm_pickup.restype = ctypes.c_int
        _library = module
    return _library


def prepare(pc):
    if pc is None or pc != get_pc() or not pc.Pawn:
        raise RuntimeError('Load a character first')
    function = pc.ServerUseJunkObject.func
    props = list(function._properties())
    expected = [('JunkId', 'StructProperty', 0, 4), ('bWasHeld', 'BoolProperty', 4, 1),
                ('bAutoTrash', 'BoolProperty', 5, 1)]
    actual = [(str(p.Name), str(p.Class.Name), int(p.Offset_Internal), int(p.ElementSize)) for p in props]
    if (function._path_name() != FUNCTION or function._get_struct_size() != 8
            or actual != expected or any(int(p.ArrayDim) != 1 for p in props)):
        raise RuntimeError('Unsupported reflected pickup parameter layout')
    kind = props[0].Struct
    if kind._path_name() != '/Script/GbxGame.JunkId' or kind._get_struct_size() != 4:
        raise RuntimeError('Unsupported JunkId type')
    error = ctypes.create_string_buffer(1024)
    code = library().lm_prepare(error, len(error))
    if code:
        raise RuntimeError(error.value.decode('utf-8', errors='replace'))
    return function


def read_junk_id(actor):
    if (not actor or actor.Class._path_name() != PICKUP_CLASS
            or actor.Class._get_struct_size() != PICKUP_SIZE
            or actor.IsActorBeingDestroyed() or actor.bHidden):
        raise RuntimeError('Unsupported or inactive pickup actor')
    raw = bytes(ctypes.memoryview_at(actor._get_address() + JUNK_OFFSET, 4, readonly=True))
    if raw == b'\xff' * 4:
        raise RuntimeError('Inactive JunkId')
    return raw


def request_pickup(pc, actor):
    function = prepare(pc)
    raw = read_junk_id(actor)
    # Allocate SDK-owned storage and keep this Python owner alive until native dispatch returns.
    arguments = WrappedStruct(function)
    view = ctypes.memoryview_at(arguments._get_address(), 8)
    view[:] = raw + bytes(4)
    error = ctypes.create_string_buffer(1024)
    original_flags = function.FunctionFlags
    try:
        code = library().lm_pickup(function._get_address(), pc._get_address(),
                                    arguments._get_address(), 8, error, len(error))
    finally:
        # Upstream restores flags on normal returns; cover a caught C++ exception too.
        if function.FunctionFlags != original_flags:
            function.FunctionFlags = original_flags
    if code:
        raise RuntimeError(error.value.decode('utf-8', errors='replace'))
    return {'junk_hex': raw.hex(), 'native_dispatch_returned': True}
