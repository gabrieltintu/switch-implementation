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

def parse_bpdu_frame(data):
	bpdu_root_bridge_id, bpdu_own_bridge_id, bpdu_path_cost = struct.unpack('!III', data[12:])
	return bpdu_root_bridge_id, bpdu_own_bridge_id, bpdu_path_cost


def create_vlan_tag(vlan_id):
	# 0x8100 for the Ethertype for 802.1Q
	# vlan_id & 0x0FFF ensures that only the last 12 bits are used
	return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def create_bpdu_frame(root_bridge_id, sender_bridge_id, sender_path_cost):
	# Pack the 3 values directly into the frame, each as 64-bit unsigned integers
	bpdu_data = struct.pack('!III', root_bridge_id, sender_bridge_id, sender_path_cost)
	bpdu_frame = bpdu_dst_mac + bpdu_src_mac + bpdu_data
	return bpdu_frame


def send_bdpu_every_sec():
	while True:
		# TODO Send BDPU every second if necessary
		root_bridge_id = own_bridge_id
		sender_bridge_id = own_bridge_id
		sender_path_cost = 0

		bpdu_frame = create_bpdu_frame(root_bridge_id, sender_bridge_id, sender_path_cost)
		for t_port in trunk_ports_state:
			for i in interfaces:
				if t_port == get_interface_name(i):
					send_to_link(i, len(bpdu_frame), bpdu_frame)

		time.sleep(1)

def parse_file(switch_id):
	if_vlan = {}
	file = "switch" + switch_id + ".cfg"
	file_path = os.path.join("configs", file)
	with open(file_path, 'r') as f:
		# Read all lines from the file
		lines = f.readlines()
		
		# Process the first line separately (if needed)
		switch_priority = lines[0].strip()  # First line content
		
		# Process subsequent lines
		for line in lines[1:]:
			# Strip whitespace and split by space
			value = line.strip().split()
			
			interface_name = value[0]  # The first part is the key
			interface_vlan = value[1]  # The second part is the value
			if_vlan[interface_name] = interface_vlan
	
	return switch_priority, if_vlan

def send_frame(out_interface, interface, if_vlan, length, data, vlan_id):
	if if_vlan[get_interface_name(out_interface)] == 'T':
		if if_vlan[get_interface_name(interface)] == 'T':
			if trunk_ports_state[get_interface_name(interface)] == "Listening":
				send_to_link(out_interface, length, data)
		else:
			tagged_frame = data[0:12] + create_vlan_tag(int(if_vlan[get_interface_name(interface)])) + data[12:]
			send_to_link(out_interface, length + 4, tagged_frame)
	else:
		if if_vlan[get_interface_name(interface)] == 'T':
			if trunk_ports_state[get_interface_name(interface)] == "Listening":
				if vlan_id == int(if_vlan[get_interface_name(out_interface)]):
					new_data = data[0:12] + data[16:]
					send_to_link(out_interface, length - 4, new_data)
		elif if_vlan[get_interface_name(interface)] == if_vlan[get_interface_name(out_interface)]:
			send_to_link(out_interface, length, data)

def main():
	# init returns the max interface number. Our interfaces
	# are 0, 1, 2, ..., init_ret value + 1
	MAC_Table = {}
	acc_ports_state = {}
	switch_priority = None
	if_vlan = {}
	switch_id = sys.argv[1]
	global trunk_ports_state
	global interfaces
	global root_bridge_id, own_bridge_id
	num_interfaces = wrapper.init(sys.argv[2:])
	interfaces = range(0, num_interfaces)

	# print("# Starting switch with id {}".format(switch_id), flush=True)
	# print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))


	# Open the file in read mode
	switch_priority, if_vlan = parse_file(switch_id)
	
	trunk_ports_state = {}
	# print(switch_priority)

	for if_name in if_vlan:
		if if_vlan[if_name] == 'T':
			trunk_ports_state[if_name] = "Blocking"
		else:
			acc_ports_state[if_name] = "Listening"
	
	own_bridge_id =  int(switch_priority)
	root_bridge_id = own_bridge_id
	root_path_cost = 0

	if own_bridge_id == root_bridge_id:
		# For each port on the bridge:
		#     Set port state to DESIGNATED_PORT
		for t_port in trunk_ports_state:
			trunk_ports_state[t_port] = "Listening"
			# print(f"port {port} {port_state[port]}")

	# Create and start a new thread that deals with sending BDPU
	t = threading.Thread(target=send_bdpu_every_sec)
	t.start()
	
	# Printing interface names
	# fint(get_interface_name(i))
	
	
	while True:
		# Note that data is of type bytes([...]).
		# b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
		# b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
		# b3 = b1[0:2] + b[3:4].
		interface, data, length = recv_from_any_link()

		dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

		# print(dest_mac)
		# print(bpdu_dst_mac)
		# print("muiee")
		if (dest_mac == bpdu_dst_mac):
			# print(f"root bridge id {root_bridge_id}")

			# for t_port in trunk_ports_state:
			# 	print(f"{t_port} {trunk_ports_state[t_port]}")

			bpdu_root_bridge_id, bpdu_sender_bridge_id, sender_path_cost = parse_bpdu_frame(data)

			if bpdu_root_bridge_id < root_bridge_id:
				i_was_root_bridge = root_bridge_id == own_bridge_id
				root_bridge_id = bpdu_root_bridge_id
				root_path_cost = sender_path_cost + 10 
				root_port = get_interface_name(interface)

				if i_was_root_bridge:
					for t_port in trunk_ports_state:
						if t_port != root_port:
							trunk_ports_state[t_port] = "Blocking"

				if trunk_ports_state[root_port] == "Blocking":
					trunk_ports_state[root_port] = "Listening"


				bpdu_sender_bridge_id = own_bridge_id
				sender_path_cost = root_path_cost
				bpdu_frame = create_bpdu_frame(root_bridge_id, bpdu_sender_bridge_id, sender_path_cost)

				for t_port in trunk_ports_state:
					for i in interfaces:
						if t_port == get_interface_name(i) and t_port != get_interface_name(interface):
							send_to_link(i, len(bpdu_frame), bpdu_frame)

			elif bpdu_root_bridge_id == root_bridge_id:
				if get_interface_name(interface) == root_port and sender_path_cost + 10 < root_path_cost:
					root_path_cost = sender_path_cost + 10

				elif get_interface_name(interface) != root_port:
					if sender_path_cost > root_path_cost:
						if trunk_ports_state[get_interface_name(interface)] != "Listening":
							trunk_ports_state[get_interface_name(interface)] = "Listening"
			
			elif bpdu_sender_bridge_id == own_bridge_id:
				trunk_ports_state[get_interface_name(interface)] = "Blocking"

			else:
				continue

			if own_bridge_id == root_bridge_id:
				# For each port on the bridge:
				# 	Set port as DESIGNATED_PORT
				for t_port in trunk_ports_state:
					trunk_ports_state[t_port] = "Listening"

		else:
			# print(f"interfata {get_interface_name(interface)}")
			# Print the MAC src and MAC dst in human readable format
			dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
			src_mac = ':'.join(f'{b:02x}' for b in src_mac)

			# if
			# Note. Adding a VLAN tag can be as easy as
			# tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]
			
			# print(f'Destination MAC: {dest_mac}')
			# print(f'Source MAC: {src_mac}')
			# print(f'EtherType: {ethertype}')
			
			print("Received frame of size {} on interface {}".format(length, interface), flush=True)

			# TODO: Implement forwarding with learning

			# Am aflat portul pentru adresa MAC src
			MAC_Table[src_mac] = interface

			# # TODO: Implement VLAN support
			# if_vlan = {}


			# aflu vlan de pe portul pe care a fost primit cadrul
			# recv_vlan = if_vlan[get_interface_name(interface)] === vlan_id ???
			# print(f"vlan_id {vlan_id}")					
			
			if dest_mac in MAC_Table:
				out_interface = MAC_Table[dest_mac]
				if get_interface_name(out_interface) in trunk_ports_state:
					if trunk_ports_state[get_interface_name(out_interface)] != "Blocking":
						send_frame(out_interface, interface, if_vlan, length, data, vlan_id)
						print(f"Sending on interface  {get_interface_name(out_interface)}")
				else:
					send_frame(out_interface, interface, if_vlan, length, data, vlan_id)
					print(f"Sending on interface  {get_interface_name(out_interface)}")


			else:
				for i in interfaces:
					if i != interface:
						if get_interface_name(i) in trunk_ports_state:
							if trunk_ports_state[get_interface_name(i)] != "Blocking":
								send_frame(i, interface, if_vlan, length, data, vlan_id)
								print(f"Sending on interface broadcast  {get_interface_name(i)}")
						else:
							send_frame(i, interface, if_vlan, length, data, vlan_id)
							print(f"Sending on interface broadcast  {get_interface_name(i)}")

			# TODO: Implement STP support



			# data is of type bytes.
			# send_to_link(i, length, data)

if __name__ == "__main__":
	main()
