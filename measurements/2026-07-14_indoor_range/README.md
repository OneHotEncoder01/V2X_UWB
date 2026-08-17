# Indoor UWB range measurements — 2026-07-14

Sequenced CAM packet-delivery tests performed indoors with DW3000 channel 5,
6.8 Mbit/s, 10 Hz transmission rate, and mock GPS data. TX and RX CSV files use
the numeric test ID in their filename and packet `stationId`.

The physical conditions were set manually. Distances are approximate tape
measure values. Unless stated otherwise, antennas were directed toward each
other.

| Test ID | Condition | Packets | RX unique | Loss |
|---:|---|---:|---:|---:|
| 2714 | 2.5 m LOS baseline | 300 | 300 | 0.00% |
| 2715 | 2.5 m, TX rotated 90 degrees | 300 | 300 | 0.00% |
| 2716 | 2.5 m, RX rotated 90 degrees | 300 | 300 | 0.00% |
| 2717 | 2.5 m, human-body blockage | 300 | 300 | 0.00% |
| 2718 | 2.5 m, TX inside unspecified transparent glass enclosure | 300 | 300 | 0.00% |
| 2724 | 7 m, NLOS around wall corner, doors open | 300 | 14 | 95.33% |
| 2726 | 7 m LOS | 300 | 296 | 1.33% |
| 2728 | 8 m LOS, initial configuration | 300 | 0 | 100.00% |
| 2731 | 8 m LOS, initial long run | 1000 | 0 | 100.00% |
| 2733 | 8 m LOS, adjusted configuration run 1 | 1000 | 1000 | 0.00% |
| 2734 | 8 m LOS, adjusted configuration run 2 | 1000 | 1000 | 0.00% |
| 2735 | 8 m, human body directly blocking | 1000 | 0 | 100.00% |
| 2736 | 8 m, path clear after body blockage | 1000 | 533 | 46.70% |

The large variation at nominally 8 m means these rows must be reported as
separate configurations/runs, not averaged into one distance-only packet-loss
value. Small changes around the antennas and indoor multipath are important
uncontrolled variables near the reception boundary.
