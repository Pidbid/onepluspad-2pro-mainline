# 重新下载仓库锁定的原厂 OTA

[English](OTA-DOWNLOAD.md) · [项目首页](../README.zh-CN.md)

`packaging/boot-reference/` 下的构建输入与固件闭包都来自同一个完整 OTA
（`OPD2413_11.C.34_1340_202607031844`）。`packaging/boot-reference/source.json`
中记录的 URL 是一个早已过期的签名 CDN 链接，无法原样重新拉取。本文记录如何再次取得
完整包，以及如何确认它与项目锁定的版本一致。

## 下载闸门

BBK 通过一个闸门分发安装包：

```
https://component-ota-cn.allawntech.com/downloadCheck?c=…&p=…&d=…&g=…&id=…&…&s=…
```

不带原厂升级程序的身份请求头时，闸门返回

```json
{"body":null,"errMsg":"2306","responseCode":2306}
```

且永不跳转。闸门接受

```
userId: oplus-ota|<versionCode>
```

只有 `oplus-ota|` 前缀会被校验，竖线后的值无关紧要，因此写常量即可。`2306` 表示
"缺少升级程序身份"，而不是"链接失效"；不加该前缀的其他请求会返回 `2309`。

带上该请求头后，闸门返回 `302` 跳转到签名后的 CDN 对象：

```
https://gauss-compota-c-cn.allawnfs.com/remove-<token>/g-<id>/component-ota/<y>/<m>/<d>/<obj>.zip
  ?sign=…&t=…&AWSAccessKeyId=…&Expires=…&Signature=…
```

签名链接的有效期只有几分钟。客户端应当保留**闸门** URL 并按请求重新解析，这也正是
`scripts/fetch-oplus-ota.py` 的做法。

## 找到闸门 URL

有镜像站收录了已发布版本的闸门：

```sh
curl -s 'https://roms.danielspringer.at/api/ota.php?model=OPD2413' -o opd2413.json
jq -r '.releases[] | "\(.version) \(.ota_version)\n  \(.source_url)"' opd2413.json
```

发布同一条"官方链接"的机型页面同样可用；其 JavaScript 只是加了一个复制按钮，不会修改
URL。

## 下载

```sh
python3 scripts/fetch-oplus-ota.py \
  --gate "$(jq -r '.releases[] | select(.ota_version|test("C.34")) | .source_url' opd2413.json)" \
  --output OPD2413_C34_full.zip --jobs 16 --md5 c7d36364f94daa509c19f71b1e100982
```

该工具先用 `Range: bytes=0-0` 探测大小，再分块下载；每当分块被拒就重新解析闸门，
因此签名过期不会浪费已下载的数据；最后校验 MD5。

锁定版本实测：

| | |
|---|---|
| 版本 | `OPD2413_16.0.9.400(CN01)` |
| 字节数 | 8,113,415,565 |
| MD5 | `c7d36364f94daa509c19f71b1e100982` |
| SHA-256 | `71bd5d0cf23b2a46e7b134a3a362c3703322aaaaf3a9951938c827d8b3a67bde` |

该 SHA-256 与 `packaging/boot-reference/source.json` 中记录的
`origin.archive_sha256` 一致，这也是确认所下载的就是项目锁定的同一个未修改安装包的
方式。

## 解出分区

```sh
unzip -o OPD2413_C34_full.zip payload.bin
payload-dumper-go -l payload.bin
payload-dumper-go -c 8 -o extracted -p vendor,odm,product,system,system_ext,vendor_dlkm payload.bin
fsck.erofs --extract=tree/vendor extracted/vendor.img
```

## 备注

* 某些网络需要对这些域名绕过本机 HTTP 代理，否则 TLS 会以
  `UNEXPECTED_EOF_WHILE_READING` 失败：

  ```sh
  env -u HTTPS_PROXY -u https_proxy curl -s 'https://roms.danielspringer.at/api/ota.php?model=OPD2413'
  ```

* 设备已是最新版本时，两个升级端点都会回答"无事可做"：`otag.h2os.com/post/Query_Update`
  返回 `204`，`component-otapc-cn.allawntech.com/update/v3` 返回
  `responseCode 2004, artifactV1Result is empty`。两者都不是下载失败。
* 安装包内 `vendor/etc/sensors/config` 与 `packaging/sensors/rom/` 下保存的副本字节一致。
