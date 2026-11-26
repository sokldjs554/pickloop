# KiCad pressure-input bench circuit

This practice project develops the 150 Ω shunt example in the [PickLoop hardware acceptance plan](../../docs/hardware-acceptance.md). It contains a schematic and a routed 40 × 23 mm two-layer PCB design. Fabrication, assembly, measurements, and robot integration are pending.

- [KiCad project](pressure-bench.kicad_pro) opens the [schematic](pressure-bench.kicad_sch) and [PCB layout](pressure-bench.kicad_pcb).
- [Schematic preview](pressure-bench.svg) and [PCB layout preview](pressure-bench-layout.svg) are KiCad plots. In the layout preview, red is front copper and blue is back copper.

## Current-to-voltage conversion

J1 pin 1 takes current from an external isolated, current-limited bench source. J2 pin 1 exposes `V_SENSE` for a floating high-impedance voltmeter. Pin 2 on both connectors is `BENCH_RETURN`. R1 is a 150 Ω ±1%, 0.25 W through-hole resistor across the two nets. The PCB shares the return between J1 and J2. Source isolation is external to the PCB.

`V_SENSE = I × R`, measured relative to `BENCH_RETURN`. R1 dissipates 60 mW at nominal full scale. A 22 mA source limit yields up to about 73 mW with the resistor at +1% tolerance.

| Applied current | Nominal voltage | Range from resistor tolerance alone |
| ---: | ---: | ---: |
| 4 mA | 0.600 V | 0.594–0.606 V |
| 12 mA | 1.800 V | 1.782–1.818 V |
| 20 mA | 3.000 V | 2.970–3.030 V |

## CAD verification

KiCad 9.0.2 reported **0 ERC errors or warnings**, **0 DRC violations**, **0 unconnected pads**, and **0 schematic parity issues**. The board uses 0.50 mm traces and a 0.20 mm minimum clearance rule. The schematic netlist associates all three pin-1 terminals (`J1.1`, `J2.1`, `R1.1`) with `V_SENSE` and all three pin-2 terminals with `BENCH_RETURN`.

Run from this directory with the standard KiCad symbol and footprint libraries installed.

```sh
kicad-cli sch erc --exit-code-violations -o /tmp/pressure-bench-erc.rpt pressure-bench.kicad_sch
kicad-cli pcb drc --schematic-parity --exit-code-violations -o /tmp/pressure-bench-drc.rpt pressure-bench.kicad_pcb
```

## Proposed bench check

1. With power disconnected, confirm J1 and J2 share continuity pin-for-pin and measure approximately 150 Ω across pins 1 and 2. Check both connector polarities and the R1 markings.
2. Set up an isolated current source in source mode with output disabled, a maximum 22 mA current limit, and at most 5 V compliance. Connect its positive lead to J1 pin 1 and return to J1 pin 2. Connect a floating voltmeter with ≥10 MΩ input impedance across J2. Keep field supplies, sensors, and controllers disconnected.
3. Source 4, 12, and 20 mA, then return to 4 mA. Record the applied current and measured voltage at each point. Allow for source, meter, and resistor accuracy when comparing measurements to the table. Disable the source before disconnecting the leads.
