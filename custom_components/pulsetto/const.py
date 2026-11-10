"""Constants for the Pulsetto BLE integration.

Protocol follows the community documentation linked in the README. The
device exposes a standard Nordic UART Service; commands are single ASCII
bytes Base64-encoded and written to the RX characteristic. Notifications
arrive Base64-encoded on TX. There is no pairing/bonding/auth on the radio.
"""

DOMAIN = "pulsetto"
MANUFACTURER = "Pulsetto"

NORDIC_UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
CHAR_RX_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
CHAR_TX_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Bootloader-mode device advertises under this local name.
DFU_LOCAL_NAME = "PulsUp"

SCAN_TIMEOUT = 10.0
CONNECT_TIMEOUT = 30.0

NOTIF_TIMEOUT = 3.0

CONF_ADDRESS = "address"
