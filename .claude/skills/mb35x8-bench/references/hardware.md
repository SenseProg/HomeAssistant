# MB35x8 hardware reference

## Debug chain

- U9: CP2102N USB-to-UART bridge.
- P18: Type-C debug connector.
- P25: three-pin 2.54 mm UART header.
- P25 pin 1: `UART2_TX_M0` (board output).
- P25 pin 2: `UART2_RX_M0` (board input).
- P25 pin 3: GND.
- Serial: 115200 baud, 8 data bits, no parity, one stop bit, no flow control.

The schematic cross-over is correct, but PCB routing of U9 pins 25/26 is known
bad on tested v1.1 boards. Board 4 worked from P25 with output only. Board 5 had
a hand repair for bidirectional Type-C debug but its Ethernet chips were removed.
The production board is v1.0 board 1, so verify rather than inherit those results.

## Important known defects from v1.1 test material

- Debug Type-C RX/TX routing.
- I2C2/NFC/touch routing concerns around U7.
- CAN1 U44 pin 2 ground issue.
- SATA connector/power pin reversal concern.
- AP6256 Wi-Fi/Bluetooth needs kernel work; Ethernet is the proven path.
- PoE power section has missing/DNP assemblies on some builds.
- Image download/recovery was inconsistent on tested board/SoM combinations.

These are hypotheses for board 1 until physically verified.

## Source material

The repository contains extracted MB35x8/Rockchip material under
`nas-materials/` and software findings under `mb35x8-software/`. Large firmware
images remain on CloudMate NAS and are intentionally excluded from Git.
