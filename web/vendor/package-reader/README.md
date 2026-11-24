# Browser package photo reader dependencies

The application loads the following static files after the visitor submits a local photo. It passes the photograph to two local browser workers. The worker requests fetch engine files, language models and the three-entry registry from this site's origin. Pixels, names and recognized text stay in memory for the current read. Refreshing or choosing another file clears the results.

| Component | Pinned version | Distributed files | Source and terms |
| --- | --- | --- | --- |
| Tesseract.js browser worker | 6.0.1 | ocr-worker.js | [Source](https://github.com/naptha/tesseract.js/tree/v6.0.1), [Apache 2.0](licenses/tesseract-js.txt), [bundled notices](licenses/ocr-worker-notices.txt) |
| Tesseract.js Core | 6.0.0 | tesseract-core-lstm.wasm.js, including embedded scalar WASM | [Source](https://github.com/naptha/tesseract.js-core/tree/v6.0.0), [Apache 2.0](licenses/tesseract-core.txt), image codec and math library notices under licenses/ |
| Korean and English Tesseract language data | @tesseract.js-data/kor and /eng 1.0.0, 4.0.0_best_int | kor.traineddata.gz and eng.traineddata.gz | [Tesseract.js language data](https://github.com/naptha/tessdata), [model license](licenses/language-models.txt). The npm packaging declares MIT. Only model binaries are distributed here. |
| zxing-wasm reader | 2.2.1 | zxing/reader/index.js, zxing/share.js, zxing_reader.wasm | [Source](https://github.com/Sec-ant/zxing-wasm/tree/v2.2.1), [wrapper MIT](licenses/zxing-wasm.txt), [C++ bridge Apache 2.0](licenses/zxing-bridge.txt), [ZXing-C++ Apache 2.0](licenses/zxing-cpp.txt), [image reader notices](licenses/stb.txt) |

The bundled ZXing-C++ revision is c0a7c6cd2165457c721c58045edd22ffee9624e9. Its reader WASM SHA-256 is 1c961d9d9a1f0001f5d00486bcf8e1b1a91fcf9fe17ebcbd6e2b6efe21e23038. No writer binary is used.

Run `python scripts/vendor_package_reader.py` in the repository to verify the checked-in assets offline. Pass `--rebuild` to download the exact npm archives, verify fixed SHA-512 archive digests and pinned notice hashes, and regenerate these files. The registry is derived from REGISTERED_GTINS in src/pickloop/pack_barcode.py. Raw OCR and its numeric characters never participate in this registry lookup.

Run `node --test tests/package-reader.mjs` to check image headers, pixel limits, the registry, checksum normalization, ambiguity, and cancellation. `node tests/package-reader-offline.mjs /path/to/photo.png` runs the bundled engines on an existing PNG using Node's worker API. For a browser-sized input, apply EXIF orientation, composite transparency over white, and fit the long edge to 2560 pixels before encoding to PNG. The browser page performs these steps on a local canvas.
