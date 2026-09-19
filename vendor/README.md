# Vendored libraries

These files are vendored (checked into the repo) rather than loaded from a
CDN, so CV text extraction keeps working on networks that block third-party
CDNs (a real failure mode we hit in practice — see the main README).

| File | Package | Version | License |
|---|---|---|---|
| `pdf.min.js`, `pdf.worker.min.js` | [pdfjs-dist](https://www.npmjs.com/package/pdfjs-dist) (legacy build) | 3.11.174 | Apache-2.0 (`LICENSE.pdfjs-dist.txt`) |
| `mammoth.browser.min.js` | [mammoth](https://www.npmjs.com/package/mammoth) | 1.6.0 | BSD-2-Clause (`LICENSE.mammoth.txt`) |

To upgrade, download the matching build from the package's npm tarball
(`legacy/build/pdf.min.js` + `legacy/build/pdf.worker.min.js` for pdfjs-dist,
`mammoth.browser.min.js` for mammoth) and replace the files here — no other
code changes should be needed unless the library's public API changed.
