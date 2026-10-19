# SDK notices

This experimental mod uses the unrealsdk API and the BoundFunction declaration from bl-sdk/unrealsdk, commit b1852aa440277afcce8a13566b5487aeae5a7ae9. Upstream SDK authors retain copyright to their code. The SDK is licensed under GNU LGPL version 3; the LGPL and incorporated GPL texts accompany this package.

Upstream source, license and headers:

- https://github.com/bl-sdk/unrealsdk/tree/b1852aa440277afcce8a13566b5487aeae5a7ae9
- https://github.com/bl-sdk/unrealsdk/blob/b1852aa440277afcce8a13566b5487aeae5a7ae9/LICENSE
- https://github.com/bl-sdk/unrealsdk/blob/b1852aa440277afcce8a13566b5487aeae5a7ae9/src/unrealsdk/unreal/wrappers/bound_function.h

No unrealsdk or pyunrealsdk DLL, game binary, or modified SDK implementation is distributed in this package. Install the upstream SDK separately. The project-owned bridge dynamically resolves the SDK dispatch used by BoundFunction::call_with_params; its source is included under native/source. It does not compile the SDK copy_struct implementation. Native ABI guards intentionally restrict this prototype to the inspected SDK revision.

The bridge source and build recipe are supplied for review. This notice does not relicense upstream material. The included LGPL/GPL texts cover the upstream SDK material; no separate license grant for project-owned code is asserted here.
