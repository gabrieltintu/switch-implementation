#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
import os
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

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

def create_vlan_tag(vlan_id):
	# 0x8100 for the Ethertype for 802.1Q
	# vlan_id & 0x0FFF ensures that only the last 12 bits are used
	return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec():
	while True:
		# TODO Send BDPU every second if necessary
		time.sleep(1)

def main():
	# init returns the max interface number. Our interfaces
	# are 0, 1, 2, ..., init_ret value + 1
	MAC_Table = {}
	switch_id = sys.argv[1]

	num_interfaces = wrapper.init(sys.argv[2:])
	interfaces = range(0, num_interfaces)

	print("# Starting switch with id {}".format(switch_id), flush=True)
	print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

	# Create and start a new thread that deals with sending BDPU
	t = threading.Thread(target=send_bdpu_every_sec)
	t.start()
	
	# Printing interface names
	for i in interfaces:
		print(get_interface_name(i))

	# Open the file in read mode
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


	while True:
		# Note that data is of type bytes([...]).
		# b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
		# b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
		# b3 = b1[0:2] + b[3:4].
		interface, data, length = recv_from_any_link()

		dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)
		print(f"interfata {get_interface_name(interface)}")
		# Print the MAC src and MAC dst in human readable format
		dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
		src_mac = ':'.join(f'{b:02x}' for b in src_mac)

		# Note. Adding a VLAN tag can be as easy as
		# tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]
		
		print(f'Destination MAC: {dest_mac}')
		print(f'Source MAC: {src_mac}')
		print(f'EtherType: {ethertype}')
		
		print("Received frame of size {} on interface {}".format(length, interface), flush=True)

		# TODO: Implement forwarding with learning

		# Am aflat portul pentru adresa MAC src
		MAC_Table[src_mac] = interface

		# # TODO: Implement VLAN support
		# if_vlan = {}


		# aflu vlan de pe portul pe care a fost primit cadrul
		# recv_vlan = if_vlan[get_interface_name(interface)] === vlan_id ???
		print(f"vlan_id {vlan_id}")

		# if dest_mac in MAC_Table:
        #     out_interface = MAC_Table[dest_mac]
        #     if if_vlan[get_interface_name(out_interface)] == "T" or vlan_id == int(if_vlan[get_interface_name(out_interface)]):
        #         send_to_link(out_interface, length, data)
        #     elif vlan_id != -1:
        #         tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
        #         send_to_link(out_interface, length + 4, tagged_frame)
        # else:
        #     for i in interfaces:
        #         if i != interface:
        #             if_vlan_id = if_vlan.get(get_interface_name(i), -1)
        #             if if_vlan_id == "T" or vlan_id == int(if_vlan_id):
        #                 send_to_link(i, length, data)
        #             elif vlan_id != -1:
        #                 new_data = data[0:12] + data[16:]
        #                 send_to_link(i, length - 4, new_data)

		# if dest_mac in MAC_Table:
		# 	print("in dest mac")
		# 	if vlan_id != -1:

		# 		print("trunk??>?>>")
		# 		if if_vlan[get_interface_name(MAC_Table[dest_mac])] == "T":
		# 			send_to_link(MAC_Table[dest_mac], length, data)
		# 		else:
		# 			if vlan_id == int(if_vlan[get_interface_name(MAC_Table[dest_mac])]):
		# 				new_data = data[0:12] + data[16:]
		# 				send_to_link(MAC_Table[dest_mac], length - 4, new_data)
		# 	else:
		# 		if if_vlan[get_interface_name(MAC_Table[dest_mac])] == "T":
		# 			tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
		# 			send_to_link(MAC_Table[dest_mac], length + 4, tagged_frame)
		# 		else:
		# 			if vlan_id == int(if_vlan[get_interface_name(MAC_Table[dest_mac])]):
		# 				send_to_link(MAC_Table[dest_mac], length, data)
		# else:
		# 	if vlan_id == -1:
		# 		vlan_id = if_vlan[get_interface_name(interface)]

		# 		print(f"aici  >?>? new vlan id {vlan_id}")
		# 		for i in interfaces:
		# 			if i != interface:
		# 				if vlan_id != -1:
		# 					if if_vlan[get_interface_name(i)] == "T":
		# 						send_to_link(i, length, data)
		# 					else:
		# 						if vlan_id == if_vlan[get_interface_name(i)]:
		# 							new_data = data[0:12] + data[16:]
		# 							send_to_link(i, length, new_data)
		# 				else:
		# 					if if_vlan[get_interface_name(i)] == "T":
		# 						print("ok 1???")
		# 						tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
		# 						send_to_link(i, length + 4, tagged_frame)
		# 					else:
		# 						print("ok2222 ???")
		# 						if vlan_id == int(if_vlan[get_interface_name(i)]):
		# 							print("vlan_id ===== vlan dest")
		# 							send_to_link(i, length, data)
		# 	else:
		# 		for i in interfaces:
		# 			if i != interface:
						
		# 				if vlan_id != -1:
		# 					if if_vlan[get_interface_name(i)] == "T":
		# 						send_to_link(i, length, data)
		# 					else:
		# 						if vlan_id == if_vlan[get_interface_name(i)]:
		# 							new_data = data[0:12] + data[16:]
		# 							send_to_link(i, length, new_data)
		# 				else:
		# 					if if_vlan[get_interface_name(i)] == "T":
		# 						print("ok 1???")
		# 						send_to_link(i, length, data)
		# 					else:
		# 						print("ok2222 ???")
		# 						if vlan_id == int(if_vlan[get_interface_name(i)]):
		# 							print("vlan_id ===== vlan dest")
		# 							new_data = data[0:12] + data[16:]
		# 							send_to_link(i, length - 4, new_data)
						
		
		if dest_mac in MAC_Table:
			out_interface = MAC_Table[dest_mac]

			if if_vlan[get_interface_name(out_interface)] == 'T':
				if if_vlan[get_interface_name(interface)] == 'T':
					send_to_link(out_interface, length, data)
				else:
					tagged_frame = data[0:12] + create_vlan_tag(int(if_vlan[get_interface_name(interface)])) + data[12:]
					send_to_link(out_interface, length + 4, tagged_frame)
			else:
				if if_vlan[get_interface_name(interface)] == 'T':
					if vlan_id == int(if_vlan[get_interface_name(out_interface)]):
						print("a intrat aici cand se intoare")
						new_data = data[0:12] + data[16:]
						send_to_link(out_interface, length - 4, new_data)
				elif int(if_vlan[get_interface_name(interface)]) == int(if_vlan[get_interface_name(out_interface)]):
					send_to_link(out_interface, length, data)

		else:
			print("broadcast")
			for i in interfaces:
				if i != interface:
					if if_vlan[get_interface_name(i)] == 'T':
						if if_vlan[get_interface_name(interface)] == 'T':
							send_to_link(i, length, data)
						else:
							tagged_frame = data[0:12] + create_vlan_tag(int(if_vlan[get_interface_name(interface)])) + data[12:]
							send_to_link(i, length + 4, tagged_frame)
					else:
						print("broadcast else")
						if if_vlan[get_interface_name(interface)] == 'T':
							if vlan_id == int(if_vlan[get_interface_name(i)]):
								print("a intrat bine raw")
								new_data = data[0:12] + data[16:]
								send_to_link(i, length - 4, new_data)
						elif int(if_vlan[get_interface_name(interface)]) == int(if_vlan[get_interface_name(i)]):
							print(f"vlan_ID PARSAT ??!! {vlan_id}")
							print(f"vlan_id din DICTONAR>>?? {if_vlan[get_interface_name(interface)]}")
							send_to_link(i, length, data)



		# if dest_mac in MAC_Table:
		# 	send_to_link(MAC_Table[dest_mac], length, data)
		# else:
		# 	for i in interfaces:
		# 		if i != interface:
		# 			send_to_link(i, length, data)

		# TODO: Implement STP support

		# data is of type bytes.
		# send_to_link(i, length, data)

if __name__ == "__main__":
	main()
