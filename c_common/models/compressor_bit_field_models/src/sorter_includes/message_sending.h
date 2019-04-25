#ifndef __MESSAGE_SENDING_H__
#define __MESSAGE_SENDING_H__

#include "constants.h"
#include "../common/sdp_formats.h"

//! how many tables the uncompressed router table entries is
#define N_UNCOMPRESSED_TABLE 1

//! \brief sends the sdp message. assumes all params have already been set
void message_sending_send_sdp_message(sdp_msg_pure_data* my_msg){
    uint32_t attempt = 0;
    log_debug("sending message");
    while (!spin1_send_sdp_msg((sdp_msg_t *) my_msg, _SDP_TIMEOUT)) {
        attempt +=1 ;
        log_info("failed to send. trying again");
        if (attempt >= 30) {
            rt_error(RTE_SWERR);
        }
    }
    log_info("sent message");
}

//! \brief stores the addresses for freeing when response code is sent
//! \param[in] n_rt_addresses: how many bit field addresses there are
//! \param[in] comp_core_index: the compressor core
//! \param[in] compressed_address: the addresses for the compressed routing
//! table
//! \return bool stating if stored or not
static bool record_address_data_for_response_functionality(
        int n_rt_addresses, uint32_t comp_core_index,
        address_t compressed_address, uint32_t mid_point,
        comp_core_store_t* comp_cores_bf_tables,
        address_t* bit_field_routing_tables){

    //free previous if there is any
    if (comp_cores_bf_tables[comp_core_index].elements != NULL) {
        bool success = helpful_functions_free_sdram_from_compression_attempt(
            comp_core_index, comp_cores_bf_tables);
        if (!success) {
            log_error("failed to free compressor core elements.");
            return false;
        }
        FREE(comp_cores_bf_tables[comp_core_index].elements);
    }

    // allocate memory for the elements
    comp_cores_bf_tables[comp_core_index].elements =
        MALLOC(n_rt_addresses * sizeof(address_t));
    if (comp_cores_bf_tables[comp_core_index].elements == NULL) {
        log_error("cannot allocate memory for sdram tracker of addresses");
        return false;
    }

    // store the elements. note need to copy over, as this is a central malloc
    // space for the routing tables.
    comp_cores_bf_tables[comp_core_index].n_elements = n_rt_addresses;
    comp_cores_bf_tables[comp_core_index].n_bit_fields = mid_point;
    comp_cores_bf_tables[comp_core_index].compressed_table = compressed_address;
    for (int rt_index = 0; rt_index < n_rt_addresses; rt_index++) {
        comp_cores_bf_tables[comp_core_index].elements[rt_index] =
            bit_field_routing_tables[rt_index];
    }
    return true;
}


//! \brief update the mc message to point at right direction
//! \param[in] comp_core_index: the compressor core id.
static void update_mc_message(
        int comp_core_index, sdp_msg_pure_data* my_msg, int* compressor_cores) {
    log_debug("chip id = %d", spin1_get_chip_id());
    my_msg->srce_addr = spin1_get_chip_id();
    my_msg->dest_addr = spin1_get_chip_id();
    my_msg->flags = REPLY_NOT_EXPECTED;
    log_info("core id =  %d", spin1_get_id());
    my_msg->srce_port = (RANDOM_PORT << PORT_SHIFT) | spin1_get_core_id();
    log_info("compressor core = %d", compressor_cores[comp_core_index]);
    my_msg->dest_port =
        (RANDOM_PORT << PORT_SHIFT) | compressor_cores[comp_core_index];
}

//! \brief figure out how many packets are needed to transfer the addresses over
//! \param[in] n_rt_addresses: how many addresses to send
//! \return the number of packets needed
static int deduce_total_packets(int n_rt_addresses) {
    uint32_t total_packets = 1;
    int n_rt_table_safe = n_rt_addresses;
    int n_addresses_for_start =
        ((ITEMS_PER_DATA_PACKET - sizeof(start_msg_t)) /
        WORD_TO_BYTE_MULTIPLIER);
    int n_addresses_for_extra =
        ((ITEMS_PER_DATA_PACKET - sizeof(extra_msg_t)) /
        WORD_TO_BYTE_MULTIPLIER);
    if (n_addresses_for_start < n_rt_table_safe){
        n_rt_table_safe -= n_addresses_for_start;
        total_packets += n_rt_table_safe / n_addresses_for_extra;
        uint32_t left_over = n_rt_table_safe % n_addresses_for_extra;
        if (left_over != 0) {
            total_packets += 1;
        }
    }
    log_debug("n packets = %d", total_packets);
    return total_packets;
}

//! \brief deduce n elements in this packet
//! \param[in] packet_id: the packet id to consider
//! \param[in] n_rt_addresses: how many bit field packets there are left
//! to send.
//! \param[in] addresses_sent: the amount of addresses already sent by other
//! sdp messages
//! \return: the number of addresses in this packet.
static int deduce_elements_this_packet(
        int packet_id, int n_rt_addresses, int addresses_sent) {
    int n_addresses_this_message = 0;
    int n_addresses_for_start =
        ((ITEMS_PER_DATA_PACKET - sizeof(start_msg_t)) /
        WORD_TO_BYTE_MULTIPLIER);
    int n_addresses_for_extra =
        ((ITEMS_PER_DATA_PACKET - sizeof(extra_msg_t)) /
        WORD_TO_BYTE_MULTIPLIER);

    // if first packet
    if (packet_id == 0) {
        if ((n_rt_addresses - addresses_sent) <= n_addresses_for_start) {
            n_addresses_this_message = n_rt_addresses - addresses_sent;
        } else {
            n_addresses_this_message = n_addresses_for_start;
        }
    } else { // an extra packet
        if ((n_rt_addresses - addresses_sent) < n_addresses_for_extra) {
            n_addresses_this_message = n_rt_addresses - addresses_sent;
        } else {
            n_addresses_this_message = n_addresses_for_extra;
        }
    }
    log_info("n addresses this message is %d", n_addresses_this_message);
    return n_addresses_this_message;
}

//! \brief sets up the first packet to fly to the compressor core
//! \param[in] total_packets: how many packets going to be sent
//! \param[in] compressed_address: the address for compressed routing table
//! \param[in] n_rt_addresses: how many bit field addresses.
//! \param[in] n_addresses_this_message: the addresses to put in this
static void set_up_first_packet(
        int total_packets, address_t compressed_address,
        int n_rt_addresses, int n_addresses_this_message,
        address_t* bit_field_routing_tables, sdp_msg_pure_data* my_msg,
        void *usable_sdram_regions) {

    // create cast
    start_msg_t *data = (start_msg_t*) &my_msg->data;
    data->command = START_DATA_STREAM;

    // fill in
    data->msg.n_sdp_packets_till_delivered = total_packets;
    data->msg.address_for_compressed = compressed_address;
    data->msg.fake_heap_data = usable_sdram_regions;
    data->msg.total_n_tables = n_rt_addresses;
    data->msg.n_tables_in_packet = n_addresses_this_message;
    for (int address_index = 0; address_index < n_addresses_this_message;
            address_index ++){
        data->msg.tables[address_index] =
            bit_field_routing_tables[address_index];
        log_debug(
            "putting address %x in point %d",
            bit_field_routing_tables[address_index], address_index);
    }

    my_msg->length = (
        LENGTH_OF_SDP_HEADER + sizeof(start_msg_t) +
        (n_addresses_this_message * WORD_TO_BYTE_MULTIPLIER));

    log_info(
        "message contains command code %d, n sdp packets till "
        "delivered %d, address for compressed %x, fake heap data "
        "address %x total n tables %d, n tables in packet %d, len of %d",
        data->command, data->msg.n_sdp_packets_till_delivered,
        data->msg.address_for_compressed, data->msg.fake_heap_data,
        data->msg.total_n_tables, data->msg.n_tables_in_packet, my_msg->length);
    for(int rt_id = 0; rt_id < n_addresses_this_message; rt_id++) {
        if (data->msg.tables[rt_id][0] > 256){
            log_info("table address is %x", data->msg.tables[rt_id]);
            log_info(
                "table size for %d is %d", rt_id,
                data->msg.tables[rt_id][0]);
        }
    }
    log_debug("message length = %d", my_msg->length);
}

//! \brief sets up the extra packet format
//! \param[in] n_addresses_this_message: n addresses to put into this message
//! \param[in] addresses_sent: how many addresses have already been sent.
static void set_up_extra_packet(
        int n_addresses_this_message, int addresses_sent,
        address_t* bit_field_routing_tables, sdp_msg_pure_data* my_msg){
    extra_msg_t *data = (extra_msg_t*) &my_msg->data;
    data->command = EXTRA_DATA_STREAM;

    data->msg.n_tables_in_packet = n_addresses_this_message;
    for (int address_index = 0;
            address_index < n_addresses_this_message;
            address_index ++){
        data->msg.tables[address_index] =
            bit_field_routing_tables[address_index + addresses_sent];
        log_debug(
            "putting address %x in point %d in message data in index %d is %x",
            bit_field_routing_tables[address_index + addresses_sent],
            address_index, address_index, data->msg.tables[address_index]);
    }
    my_msg->length = (
        LENGTH_OF_SDP_HEADER + sizeof(extra_msg_t) +
        (n_addresses_this_message * WORD_TO_BYTE_MULTIPLIER));
    log_debug("message length = %d", my_msg->length);
}

//! \brief selects a compression core's index that's not doing anything yet
//! \param[in] midpoint: the midpoint this compressor is going to explore
//! \return the compressor core index for this attempt.
static int select_compressor_core_index(
        int midpoint, int n_compression_cores, int* comp_core_mid_point,
        int *n_available_compression_cores){

    for(int comp_core_index = 0; comp_core_index < n_compression_cores;
            comp_core_index++) {
        if (comp_core_mid_point[comp_core_index] == DOING_NOWT) {
            comp_core_mid_point[comp_core_index] = midpoint;
            *n_available_compression_cores -= 1;
            return comp_core_index;
        }
    }

    log_error("cant find a core to allocate to you");
    terminate(EXIT_FAIL);
    return 0;
}


//! \brief sends a SDP message to a compressor core to do compression with
//!  a number of bitfields
//! \param[in] n_rt_addresses: how many addresses the bitfields merged
//!  into
//! \param[in] mid_point: the mid point in the binary search
static bool message_sending_set_off_bit_field_compression(
        int n_rt_addresses, uint32_t mid_point,
        comp_core_store_t* comp_cores_bf_tables,
        address_t* bit_field_routing_tables, sdp_msg_pure_data* my_msg,
        int* compressor_cores, void *usable_sdram_regions,
        int n_compressor_cores, int* comp_core_mid_point,
        int* n_available_compression_cores){

    // select compressor core to execute this
    int comp_core_index = select_compressor_core_index(
        mid_point, n_compressor_cores, comp_core_mid_point,
        n_available_compression_cores);
    log_info(
        "using core %d for %d rts",
        compressor_cores[comp_core_index], n_rt_addresses);


    // allocate space for the compressed routing entries if required
    address_t compressed_address =
        comp_cores_bf_tables[comp_core_index].compressed_table;
    if (comp_cores_bf_tables[comp_core_index].compressed_table == NULL){
        compressed_address = MALLOC_SDRAM(
            routing_table_sdram_size_of_table(TARGET_LENGTH));
        comp_cores_bf_tables[comp_core_index].compressed_table =
            compressed_address;
        if (compressed_address == NULL) {
            log_error(
                "failed to allocate sdram for compressed routing entries");
            return false;
        }
    }

    // record addresses for response processing code
    bool suc = record_address_data_for_response_functionality(
        n_rt_addresses, comp_core_index, compressed_address, mid_point,
        comp_cores_bf_tables, bit_field_routing_tables);
    if (!suc) {
        log_error("failed to store the addresses for response functionality");
        return false;
    }



    // update sdp to right destination
    update_mc_message(comp_core_index, my_msg, compressor_cores);


    // deduce how many packets
    int total_packets = deduce_total_packets(n_rt_addresses);
    log_info(
        "total packets = %d, n rts is still %d",
        total_packets, n_rt_addresses);

    // generate the packets and fire them to the compressor core
    int addresses_sent = 0;
    for (int packet_id =0; packet_id < total_packets; packet_id++) {
        // if just one packet worth, set to left over addresses
        int n_addresses_this_message = deduce_elements_this_packet(
            packet_id, n_rt_addresses, addresses_sent);

        // set data components
        if (packet_id == 0) {  // first packet
            set_up_first_packet(
                total_packets, compressed_address, n_rt_addresses,
                n_addresses_this_message, bit_field_routing_tables, my_msg,
                usable_sdram_regions);
            log_info("finished setting up first packet");
        }
        else{  // extra packets
            log_debug("sending extra packet id = %d", packet_id);
            set_up_extra_packet(
                n_addresses_this_message, addresses_sent,
                bit_field_routing_tables, my_msg);
        }

        // update location in addresses
        addresses_sent += n_addresses_this_message;

        // send sdp packet
        message_sending_send_sdp_message(my_msg);
    }
    return true;
}

//! \brief sets off the basic compression without any bitfields
bool message_sending_set_off_no_bit_field_compression(
        comp_core_store_t* comp_cores_bf_tables, int* compressor_cores,
        sdp_msg_pure_data* my_msg, void *usable_sdram_regions,
        uncompressed_table_region_data_t *uncompressed_router_table,
        int n_compressor_cores, int* comp_core_mid_point,
        int* n_available_compression_cores){

    // allocate and clone uncompressed entry
    log_debug("start cloning of uncompressed table");
    address_t sdram_clone_of_routing_table =
        helpful_functions_clone_un_compressed_routing_table(
            uncompressed_router_table);
    if (sdram_clone_of_routing_table == NULL){
        log_error("could not allocate memory for uncompressed table for no "
                  "bit field compression attempt.");
        return false;
    }
    log_debug("finished cloning of uncompressed table");

    // set up the bitfield routing tables so that it'll map down below
    log_debug("allocating bf routing tables");
    address_t* bit_field_routing_tables = MALLOC(sizeof(address_t*));
    log_debug("malloc finished");
    if (bit_field_routing_tables == NULL){
        log_error(
            "failed to allocate memory for the bit_field_routing tables");
        return false;
    }
    log_debug("allocate to array");
    bit_field_routing_tables[0] = sdram_clone_of_routing_table;
    log_debug("allocated bf routing tables");

    // run the allocation and set off of a compressor core
    return message_sending_set_off_bit_field_compression(
        N_UNCOMPRESSED_TABLE, 0, comp_cores_bf_tables,
        bit_field_routing_tables, my_msg, compressor_cores,
        usable_sdram_regions, n_compressor_cores, comp_core_mid_point,
        n_available_compression_cores);
}

#endif  // __MESSAGE_SENDING_H__