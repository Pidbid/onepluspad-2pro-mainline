# Re-downloading the pinned stock OTA

[中文](OTA-DOWNLOAD.zh-CN.md) · [Project overview](../README.md)

The build inputs under `packaging/boot-reference/` and the firmware closure come
from one full OTA (`OPD2413_11.C.34_1340_202607031844`). The URL recorded in
`packaging/boot-reference/source.json` is a signed CDN link that has long
expired, so it cannot be re-fetched as-is. This note records how a full package
can be obtained again, and how the result is verified against the release the
project was built from.

## The download gate

BBK serves packages through a gate:

```
https://component-ota-cn.allawntech.com/downloadCheck?c=…&p=…&d=…&g=…&id=…&…&s=…
```

Without the stock updater's identity header the gate answers

```json
{"body":null,"errMsg":"2306","responseCode":2306}
```

and never redirects. The gate accepts

```
userId: oplus-ota|<versionCode>
```

Only the `oplus-ota|` prefix is validated; the value after the pipe is ignored,
so a constant works. `2306` therefore means "missing updater identity", not
"expired link". Anything else without the prefix returns `2309`.

With the header the gate answers `302` to a signed CDN object:

```
https://gauss-compota-c-cn.allawnfs.com/remove-<token>/g-<id>/component-ota/<y>/<m>/<d>/<obj>.zip
  ?sign=…&t=…&AWSAccessKeyId=…&Expires=…&Signature=…
```

Signed links live for minutes. Clients should keep the *gate* URL and re-resolve
it per request, which is what `scripts/fetch-oplus-ota.py` does.

## Finding a gate URL

A catalog mirrors the gates for released builds:

```sh
curl -s 'https://roms.danielspringer.at/api/ota.php?model=OPD2413' -o opd2413.json
jq -r '.releases[] | "\(.version) \(.ota_version)\n  \(.source_url)"' opd2413.json
```

The device model page that publishes the same "official link" also works; its
JavaScript only adds a copy button and does not modify the URL.

## Downloading

```sh
python3 scripts/fetch-oplus-ota.py \
  --gate "$(jq -r '.releases[] | select(.ota_version|test("C.34")) | .source_url' opd2413.json)" \
  --output OPD2413_C34_full.zip --jobs 16 --md5 c7d36364f94daa509c19f71b1e100982
```

The tool probes the size with `Range: bytes=0-0`, downloads in chunks, re-resolves
the gate whenever a chunk is rejected so a signature expiry never wastes bytes,
and verifies MD5 at the end.

Measured for the pinned release:

| | |
|---|---|
| version | `OPD2413_16.0.9.400(CN01)` |
| bytes | 8,113,415,565 |
| MD5 | `c7d36364f94daa509c19f71b1e100982` |
| SHA-256 | `71bd5d0cf23b2a46e7b134a3a362c3703322aaaaf3a9951938c827d8b3a67bde` |

The SHA-256 matches the `origin.archive_sha256` recorded in
`packaging/boot-reference/source.json`, which is how the download is confirmed to
be the same unmodified package the project pins.

## Extracting partitions

```sh
unzip -o OPD2413_C34_full.zip payload.bin
payload-dumper-go -l payload.bin
payload-dumper-go -c 8 -o extracted -p vendor,odm,product,system,system_ext,vendor_dlkm payload.bin
fsck.erofs --extract=tree/vendor extracted/vendor.img
```

## Notes

* Some networks need the local HTTP proxy bypassed for these hosts, otherwise TLS
  fails with `UNEXPECTED_EOF_WHILE_READING`:

  ```sh
  env -u HTTPS_PROXY -u https_proxy curl -s 'https://roms.danielspringer.at/api/ota.php?model=OPD2413'
  ```

* The two update endpoints answer "nothing to do" when the device is already on
  the newest build: `otag.h2os.com/post/Query_Update` returns `204`, and
  `component-otapc-cn.allawntech.com/update/v3` returns
  `responseCode 2004, artifactV1Result is empty`. Neither is a download failure.
* `vendor/etc/sensors/config` inside the package is byte-identical to the copies
  stored in `packaging/sensors/rom/`.
