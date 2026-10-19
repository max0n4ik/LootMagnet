// Project-owned caller for the verified unrealsdk 3.2.0 OAK2 ABI.
#include "unrealsdk/unreal/wrappers/bound_function.h"
#include <cstddef>
#include <type_traits>

using unrealsdk::unreal::BoundFunction;
static_assert(std::is_standard_layout_v<BoundFunction>);
static_assert(sizeof(void*) == 8 && sizeof(BoundFunction) == 16);
static_assert(offsetof(BoundFunction, func) == 0 && offsetof(BoundFunction, object) == 8);

namespace {
using Invoke = void (*)(const BoundFunction*, void*);
using Version = uint32_t (*)();
using VersionString = const char* (*)();
std::atomic<DWORD> callback_thread{0};

int fail(int code, const char* message, char* error, size_t capacity) noexcept {
    if (error != nullptr && capacity != 0) {
        strncpy_s(error, capacity, message, _TRUNCATE);
    }
    return code;
}

Invoke resolve() {
    // Never LoadLibrary a second SDK or initialize a game DLL in another process.
    const auto module = GetModuleHandleW(L"unrealsdk.dll");
    if (module == nullptr) {
        throw std::runtime_error("unrealsdk.dll is not already loaded");
    }
    const auto version = reinterpret_cast<Version>(GetProcAddress(module, "_unrealsdk_export__get_version"));
    const auto version_string = reinterpret_cast<VersionString>(GetProcAddress(module, "_unrealsdk_export__get_version_str"));
    const auto invoke = reinterpret_cast<Invoke>(GetProcAddress(module, "_unrealsdk_export__bound_function_call_with_params"));
    if (version == nullptr || version_string == nullptr || invoke == nullptr) {
        throw std::runtime_error("Required SDK ABI exports are missing");
    }
    // shortcut: this bridge is pinned to the locally inspected SDK commit; review ABI before upgrades.
    const auto text = version_string();
    if (version() != 0x030200 || text == nullptr
        || std::string_view(text).find("b1852aa4") == std::string_view::npos) {
        throw std::runtime_error("Unsupported SDK build; expected 3.2.0 at b1852aa4");
    }
    return invoke;
}
}

extern "C" __declspec(dllexport) int lm_prepare(char* error, size_t capacity) noexcept {
    try {
        resolve();
        DWORD expected = 0;
        const auto current = GetCurrentThreadId();
        if (!callback_thread.compare_exchange_strong(expected, current) && expected != current) {
            return fail(2, "Bridge is bound to a different callback thread", error, capacity);
        }
        return 0;
    } catch (const std::exception& ex) {
        return fail(1, ex.what(), error, capacity);
    } catch (...) {
        return fail(1, "Unknown native exception while preparing bridge", error, capacity);
    }
}

extern "C" __declspec(dllexport) int lm_pickup(
    void* function, void* object, void* params, size_t size, char* error, size_t capacity) noexcept {
    try {
        if (callback_thread.load() == 0 || callback_thread.load() != GetCurrentThreadId()) {
            return fail(2, "Prepare and invoke from the same SDK callback thread", error, capacity);
        }
        if (function == nullptr || object == nullptr || params == nullptr || size != 8
            || reinterpret_cast<uintptr_t>(params) % 4 != 0) {
            return fail(3, "Invalid pointers, size or alignment", error, capacity);
        }
        const auto bytes = static_cast<const unsigned char*>(params);
        if (bytes[4] != 0 || bytes[5] != 0 || bytes[6] != 0 || bytes[7] != 0) {
            return fail(3, "Only ordinary pickup is allowed: held/trash/padding must be zero", error, capacity);
        }
        uint32_t identity{};
        std::memcpy(&identity, params, sizeof(identity));
        if (identity == 0xFFFFFFFF) {
            return fail(3, "Inactive JunkId", error, capacity);
        }
        const BoundFunction bound{
            static_cast<unrealsdk::unreal::UFunction*>(function),
            static_cast<unrealsdk::unreal::UObject*>(object)};
        // This is the same SDK dispatch used by BoundFunction::call_with_params.
        // Keep its locking/ProcessEvent behavior while avoiding Python's by-value argument copy.
        resolve()(&bound, params);
        return 0;
    } catch (const std::exception& ex) {
        return fail(4, ex.what(), error, capacity);
    } catch (...) {
        return fail(4, "Unknown C++ exception during SDK dispatch", error, capacity);
    }
}
