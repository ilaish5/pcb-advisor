# Vendored libraries

Everything the Library 3D quick preview needs is committed here, so the app never fetches code from the internet.
Loaded on demand by `ui/js/views/model3d.js` (the importmap in `ui/index.html` points `three` at the copy below).

| Library | Version | Files | Licence | Source |
|---|---|---|---|---|
| three.js | 0.170.0 (`REVISION = '170'`) | `three/build/three.module.js`, `three/examples/jsm/controls/OrbitControls.js`, `three/examples/jsm/loaders/VRMLLoader.js` | MIT (`three/LICENSE`) | https://registry.npmjs.org/three/-/three-0.170.0.tgz |
| chevrotain | 9.0.1 | `three/examples/jsm/libs/chevrotain.module.min.js` (the parser VRMLLoader imports; ships inside three's examples) | Apache-2.0 | same three-0.170.0 package |
| occt-import-js | 0.0.23 | `occt/occt-import-js.js`, `occt/occt-import-js.wasm` (7.6 MB, OpenCascade compiled to WebAssembly: reads STEP) | LGPL-2.1 (`occt/license.occt-import-js.txt`); the OpenCascade part is LGPL-2.1 with its exception (`occt/license.occt.txt`) | https://registry.npmjs.org/occt-import-js/-/occt-import-js-0.0.23.tgz |
| Atkinson Hyperlegible Next and Mono | @fontsource 5.3.0 (both) | `fonts/*.woff2` (latin and latin-ext subsets; Next 400/500/600/700, Mono 400/500/600), `fonts/fonts.css` (the `@font-face` rules, written for this repo) | SIL OFL 1.1 (`fonts/LICENSE.*.txt`) | https://registry.npmjs.org/@fontsource/atkinson-hyperlegible-next/-/atkinson-hyperlegible-next-5.3.0.tgz and https://registry.npmjs.org/@fontsource/atkinson-hyperlegible-mono/-/atkinson-hyperlegible-mono-5.3.0.tgz |

The font files are unmodified copies of the npm package's own files. The occt-import-js files are unmodified and loaded as a separate script and `.wasm` file, so a user can replace them.

## SHA-256

```
ce1fa418de16a19495a9f72495580e3015d7745c296d3ce0485897f902ddedfb  three/build/three.module.js
80efaadea4f8a636a65fb0bd08bfef62f3d93a0bb94e2e7500f23176c5c07f4e  three/examples/jsm/controls/OrbitControls.js
0e8827f3d2e9644bde7bf202c17c7ed2773f4bbf59774ec9f026fba86bf760e3  three/examples/jsm/loaders/VRMLLoader.js
026047366a9bdd0961eb79857fd5d84db204589942193012aabe7e3bee381045  three/examples/jsm/libs/chevrotain.module.min.js
3fb44ce11d00611f9b3f3c5775d520ebab48930c1f08279b7b1316f05f0d3379  occt/occt-import-js.js
33391fc9d94ea5c869a6718488bf0a9a464222bac9bdc764dfe1690cef281952  occt/occt-import-js.wasm
7ffe1954587c77dfba1cf8eb9b2ea743671fa6e63f9e7a2f258119d42e14eefe  occt/license.occt-import-js.txt
090f8eb6ba63e72887c1f89b009fb1656cfda02d83b6e9805b20468520a5d77f  occt/license.occt.txt
```

`.gitattributes` marks `ui/vendor/**` as `-text`, so git keeps these bytes exactly (no line-ending conversion).

The page also keeps every icon inline (`KIT_ICONS` in `ui/js/kit.js`) and loads nothing from the network; `tests/test_ui_model_icons.py` fails if that changes.

SHA-256 of the font files: `sha256sum ui/vendor/fonts/*` against the same npm tarballs.

To update: replace the files from the new npm tarball, update the importmap only if the path changes, bump this table.
