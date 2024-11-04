### Gabriel-Claudiu TINTU 333CAb - 2024-2025

# Switch Implementation

Simulated a network switch that offers VLAN support and basic STP functionality.

Solved all tasks (1, 2, 3).

## Forward with learning

The switch checks if the destination MAC address is in the MAC Table:

- if yes, then forward it to the destination
- if no, broadcast, send on all interfaces


## VLAN support

Updated the implementation from task 1 to include VLAN handling. The switch checks whether the receiving and sending ports are trunk or access, leading to four possible scenarios:

- **trunk to trunk**: send the frame as it is
- **trunk to access**: if VLAN matches, remove the VLAN tag and send the new frame
- **access to trunk**: add the VLAN tag and send the new frame
- **access to access**: if VLAN matches, send the frame as it is

## STP support

Implemented the STP support to avoid loops between switches:

- initialized port states, bridge IDs and path cost
- created BPDU frames to send every second
- implemented functionality to receive and process BPDUs from other switches
- completed the VLAN support by checking if the trunk port is in the "Listening" state

