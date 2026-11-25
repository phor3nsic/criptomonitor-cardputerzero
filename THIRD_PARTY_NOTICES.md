# Third-party notices

CriptoMonitor bundles no third-party code. At runtime it uses these Debian
packages, installed through `apt` dependencies under their own licenses:

| Component | Debian package | License |
|---|---|---|
| Pillow | `python3-pil` | MIT-CMU (HPND) |
| python-evdev | `python3-evdev` | BSD-3-Clause |
| Requests | `python3-requests` | Apache-2.0 |
| DejaVu fonts | `fonts-dejavu-core` | Bitstream Vera / public domain |
| Nunito Sans (optional) | `fonts-nunito-sans` | SIL OFL 1.1 |

The official CardputerZero symbol-layer keymap is read at runtime from
`/usr/share/keymaps/tca8418_keypad_m5stack_keymap.map`; it is not copied.

## Market data

Prices and charts come from public endpoints of Binance
(`api.binance.com`) and CoinGecko (`api.coingecko.com`). No account or API key
is used. The data is informational only and is subject to each provider's
terms of use; it is not financial advice.
