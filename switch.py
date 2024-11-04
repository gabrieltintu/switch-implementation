#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
import os
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

bpdu_dst_mac = bytes([0x01, 0x80, 0xC2, 0x00, 0x00, 0x00])
bpdu_src_mac = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

def parse_ethernet_header(data):
	# Unpack the header fields from the byte array
	#dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
	dest_mac = data[0:6]
	src_mac = data[6:12]
	
	# Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
	ether_type = (data[12] << 8) + data[13]

	vlan_id = -1
	# Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
	if ether_type == 0x8200:
		vlan_tci = int.from_bytes(data[14:16], byteorder='big')
		vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
		ether_type = (data[16] << 8) + data[17]

	return dest_mac, src_mac, ether_type, vlan_id

# Unpack the BPDU frame
def parse_bpdu_frame(data):
	bpdu_root_bridge_id, bpdu_own_bridge_id, bpdu_path_cost = struct.unpack('!III', data[12:])
	return bpdu_root_bridge_id, bpdu_own_bridge_id, bpdu_path_cost


def create_vlan_tag(vlan_id):
	# 0x8100 for the Ethertype for 802.1Q
	# vlan_id & 0x0FFF ensures that only the last 12 bits are used
	return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

# Create the BPDU frame
def create_bpdu_frame(root_bridge_id, sender_bridge_id, sender_path_cost):
	bpdu_data = struct.pack('!III', root_bridge_id, sender_bridge_id, sender_path_cost)
	bpdu_frame = bpdu_dst_mac + bpdu_src_mac + bpdu_data

	return bpdu_frame


def send_bdpu_every_sec():
	while True:
		root_bridge_id = own_bridge_id
		sender_bridge_id = own_bridge_id
		sender_path_cost = 0

		bpdu_frame = create_bpdu_frame(root_bridge_id, sender_bridge_id, sender_path_cost)
		for t_port in trunk_port_states:
			for i in interfaces:
				if t_port == get_interface_name(i):
					send_to_link(i, len(bpdu_frame), bpdu_frame)

		time.sleep(1)

# Get switch's priority, interfaces & VLANs from the switch's file
def parse_file(switch_id):
	if_vlan = {}
	file = "switch" + switch_id + ".cfg"
	file_path = os.path.join("configs", file)
	with open(file_path, 'r') as f:
		lines = f.readlines()
		
		switch_priority = lines[0].strip() 
		
		for line in lines[1:]:
			value = line.strip().split()
			
			interface_name = value[0]
			interface_vlan = value[1]
			if_vlan[interface_name] = interface_vlan
	
	return switch_priority, if_vlan

# Forward the received frame
def send_frame(out_interface, interface, if_vlan, length, data, vlan_id):
	# Forward on trunk
	if if_vlan[get_interface_name(out_interface)] == 'T':
		# Received on trunk; send the frame as received if possible
		if if_vlan[get_interface_name(interface)] == 'T':
			if trunk_port_states[get_interface_name(interface)] == "Listening":
				send_to_link(out_interface, length, data)
		else:
			# Received on access; must include vlan tag
			tagged_frame = data[0:12] + create_vlan_tag(int(if_vlan[get_interface_name(interface)])) + data[12:]
			send_to_link(out_interface, length + 4, tagged_frame)
	# Forward on access
	else:
		# Received on trunk; remove the vlan tag and forward if possible
		if if_vlan[get_interface_name(interface)] == 'T':
			if trunk_port_states[get_interface_name(interface)] == "Listening":
				if vlan_id == int(if_vlan[get_interface_name(out_interface)]):
					new_data = data[0:12] + data[16:]
					send_to_link(out_interface, length - 4, new_data)
		# Received on access; send the frame as received if vlan tags match
		elif if_vlan[get_interface_name(interface)] == if_vlan[get_interface_name(out_interface)]:
			send_to_link(out_interface, length, data)

def main():
	MAC_Table = {}
	acc_port_states = {}
	switch_priority = None
	if_vlan = {}
	switch_id = sys.argv[1]
	global trunk_port_states
	global interfaces
	global root_bridge_id, own_bridge_id
	num_interfaces = wrapper.init(sys.argv[2:])
	interfaces = range(0, num_interfaces)

	switch_priority, if_vlan = parse_file(switch_id)
	
	trunk_port_states = {}
	
	# Initialize for STP
	for if_name in if_vlan:
		if if_vlan[if_name] == 'T':
			trunk_port_states[if_name] = "Blocking"
		else:
			acc_port_states[if_name] = "Listening"
	
	own_bridge_id =  int(switch_priority)
	root_bridge_id = own_bridge_id
	root_path_cost = 0

	# Set the ports designated if the port becomes root bridge
	if own_bridge_id == root_bridge_id:
		for t_port in trunk_port_states:
			trunk_port_states[t_port] = "Listening"

	# Create and start a new thread that deals with sending BDPU
	t = threading.Thread(target=send_bdpu_every_sec)
	t.start()
	
	
	while True:
		interface, data, length = recv_from_any_link()

		dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

		# Received a BPDU frame
		if (dest_mac == bpdu_dst_mac):
			bpdu_root_bridge_id, bpdu_sender_bridge_id, sender_path_cost = parse_bpdu_frame(data)

			if bpdu_root_bridge_id < root_bridge_id:
				i_was_root_bridge = False

				if (root_bridge_id == own_bridge_id):
					i_was_root_bridge = True

				root_bridge_id = bpdu_root_bridge_id
				root_path_cost = sender_path_cost + 10 
				root_port = get_interface_name(interface)

				if i_was_root_bridge:
					for t_port in trunk_port_states:
						if t_port != root_port:
							trunk_port_states[t_port] = "Blocking"

				if trunk_port_states[root_port] == "Blocking":
					trunk_port_states[root_port] = "Listening"


				# Update and send the BPDU frame to all other trunk ports
				bpdu_sender_bridge_id = own_bridge_id
				sender_path_cost = root_path_cost
				bpdu_frame = create_bpdu_frame(root_bridge_id, bpdu_sender_bridge_id, sender_path_cost)

				for t_port in trunk_port_states:
					for i in interfaces:
						if t_port == get_interface_name(i) and t_port != get_interface_name(interface):
							send_to_link(i, len(bpdu_frame), bpdu_frame)

			elif bpdu_root_bridge_id == root_bridge_id:
				if get_interface_name(interface) == root_port and sender_path_cost + 10 < root_path_cost:
					root_path_cost = sender_path_cost + 10

				elif get_interface_name(interface) != root_port:
					if sender_path_cost > root_path_cost:
						if trunk_port_states[get_interface_name(interface)] != "Listening":
							trunk_port_states[get_interface_name(interface)] = "Listening"
			
			elif bpdu_sender_bridge_id == own_bridge_id:
				trunk_port_states[get_interface_name(interface)] = "Blocking"

			else:
				continue

			if own_bridge_id == root_bridge_id:
				for t_port in trunk_port_states:
					trunk_port_states[t_port] = "Listening"

		else:
			dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
			src_mac = ':'.join(f'{b:02x}' for b in src_mac)

			MAC_Table[src_mac] = interface
			
			if dest_mac in MAC_Table:
				out_interface = MAC_Table[dest_mac]
				send_frame(out_interface, interface, if_vlan, length, data, vlan_id)
			else:
				for i in interfaces:
					if i != interface:
						send_frame(i, interface, if_vlan, length, data, vlan_id)
	

if __name__ == "__main__":
	main()
