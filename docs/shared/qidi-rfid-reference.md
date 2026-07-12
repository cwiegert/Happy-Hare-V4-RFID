# QIDI Box RFID Reference

Source: <https://wiki.qidi3d.com/en/QIDIBOX/RFID>

This note captures the QIDI Box tag details that matter when debugging QIDI
rich-tag reads.

## Tag Hardware

- Chip: FM11RF08S, MIFARE Classic 1K compatible
- RF protocol: ISO/IEC 14443-A
- Frequency: 13.56 MHz
- EEPROM layout: 16 sectors, 4 blocks per sector, 16 bytes per block

## QIDI Data Location

QIDI stores the filament payload in sector 1, block 0. This is absolute block
number 4.

The first three bytes of block 4 are:

| Byte | Meaning | Range / Notes |
| --- | --- | --- |
| 0 | Material code | 1-50 |
| 1 | Color code | 1-24 |
| 2 | Manufacturer code | Default value is 1 |

The current parser reads this as offsets `raw[64]`, `raw[65]`, and `raw[66]`
because absolute block 4 starts at byte offset `4 * 16 = 64` in a flat MIFARE
block dump.

## Material Codes

The parser follows QIDI's published assignments. Unlisted values inside the
valid `1-50` range are preserved as `Unknown(<code>)` instead of guessed.

| Codes | Materials |
|---|---|
| 1-8 | PLA, PLA Matte, PLA Metal, PLA Silk, PLA-CF, PLA-Wood, PLA Basic, PLA Matte Basic |
| 11-14 | ABS, ABS-GF, ABS-Metal, ABS-Odorless |
| 18-19 | ASA, ASA-AERO |
| 24-27 | UltraPA, PA-CF, UltraPA-CF25, PA12-CF |
| 30-34 | PAHT-CF, PAHT-GF, Support For PAHT, Support For PET/PA, PC/ABS-FR |
| 37-45 | PET-CF, PET-GF, PETG Basic, PETG Tough, PETG Rapido, PETG-CF, PETG-GF, PPS-CF, PETG Translucent |
| 47, 49-50 | PVA, TPU-Aero, TPU |

Color codes `1-24` map to QIDI's published RGB values. The parser retains the
raw `material_code`, `color_code`, and `manufacturer_code` in metadata so an
unknown or newly assigned value can be diagnosed without losing the tag data.

## Auth Notes

If QIDI tags fail to rich-read, validate the sector 1 Key A path:

- Primary Key A reported for QIDI: `D3 F7 D3 F7 D3 F7`
- Fallback/factory Key A: `FF FF FF FF FF FF`

The current reader pipeline implements the factory-key fallback. It does not
yet issue a dedicated retry with `D3 F7 D3 F7 D3 F7`; that value is documented
here for diagnosis and a future sector-1-specific retry. A real tag that uses
only the QIDI-specific key will currently fall back to UID-only behavior.

QIDI data is only in sector 1, so a QIDI-specific retry should read sector 1
only. This avoids reader-specific behavior where a failed sector 0 auth can
prevent PN7160/RC522 from reaching sector 1.

## Manufacturer Code

The tag stores a numeric manufacturer code, not a manufacturer name string.
QIDI's wiki documents the default manufacturer value as `1`. BoxRFID-Touch
maps manufacturer IDs through its active manufacturer database, where `0` is
Generic and `1` is QIDI by default.
