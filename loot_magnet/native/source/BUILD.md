# Native pickup helper source

`bridge.cpp` is the complete source for `loot_native_bridge.dll`. It uses upstream SDK headers and dynamically resolves exports from the already loaded SDK. It does not link or rebuild the SDK implementation.

## Build requirements

- Windows x64, MSVC with C++20 support and a Windows SDK.
- An x64 Native Tools developer shell, with `cl.exe` on PATH.
- [unrealsdk source](https://github.com/bl-sdk/unrealsdk/tree/b1852aa440277afcce8a13566b5487aeae5a7ae9) at commit `b1852aa440277afcce8a13566b5487aeae5a7ae9`, including its submodules.
- The generated SDK configure include directory containing `unrealsdk/version.inl` and `unrealsdk/git.inl`, produced by configuring that SDK checkout for OAK2 using its upstream CMake instructions. No SDK DLL needs to be built or installed.

From an x64 developer PowerShell, set `$sdk` to that source checkout and `$configured` to its generated configure include directory, then run from this directory:

```powershell
cl.exe /nologo /std:c++20 /EHsc /MD /O2 /W4 /WX /utf-8 /LD /DUNREALSDK_FLAVOUR=UNREALSDK_FLAVOUR_OAK2 /DUNREALSDK_SHARED "/I$sdk/src" "/I$sdk/libs/minhook/include" "/I$sdk/libs/tomlplusplus/include" "/I$configured" bridge.cpp /link /OUT:loot_native_bridge.dll
```

Copy the resulting helper into `loot_magnet/native/` and update `dll_sha256` and `bytes` in `build-manifest.json` to match your binary (PowerShell `Get-FileHash -Algorithm SHA256` gives the hash). The Python adapter refuses a binary that does not match its manifest. This standalone developer-shell recipe has not been rerun independently; the distributed binary was built with these compiler settings using the author's portable MSVC environment.

Only system/runtime libraries are linked. Never replace `unrealsdk.dll` or `pyunrealsdk.dll` with this helper. SDK licensing and source links are in `../../licenses/THIRD-PARTY.md`.
