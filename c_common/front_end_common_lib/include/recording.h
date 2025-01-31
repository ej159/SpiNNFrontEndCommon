/*
 * Copyright (c) 2017-2019 The University of Manchester
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

/*! \file
 *  \brief interface for recording data into "channels" on the SDRAM in a
 *         standard way, and storing buffers to be extracted during execution
 *
 *
 */

#ifndef _RECORDING_H_
#define _RECORDING_H_

#include <common-typedefs.h>
#include <spin1_api.h>
#include <buffered_eieio_defs.h>

#define RECORDING_DMA_COMPLETE_TAG_ID 15

//! \brief Callback for recording completion.
typedef void (*recording_complete_callback_t)(void);

typedef struct {
    uint16_t eieio_header_command;
    uint16_t chip_id;
} read_request_packet_header;

typedef struct {
    uint8_t processor_and_request;
    uint8_t sequence;
    uint8_t channel;
    uint8_t region;
    uint32_t start_address;
    uint32_t space_to_be_read;
} read_request_packet_data;

typedef struct {
    uint16_t eieio_header_command;
    uint8_t request;
    uint8_t sequence;
} host_data_read_packet_header;

typedef struct {
    uint16_t zero;
    uint8_t channel;
    uint8_t region;
    uint32_t space_read;
} host_data_read_packet_data;

typedef struct {
    uint16_t eieio_header_command;
    uint8_t sequence;
} host_data_read_ack_packet_header;

//! \brief records some data into a specific recording channel.
//! \param[in] channel the channel to store the data into.
//! \param[in] data the data to store into the channel.
//! \param[in] size_bytes the number of bytes that this data will take up.
//! \return boolean which is True if the data has been stored in the channel,
//!         False otherwise.
bool recording_record(
        uint8_t channel, void *data, uint32_t size_bytes);

//! \brief records some data into a specific recording channel, calling a
//!        callback function once complete
//! \param[in] channel the channel to store the data into.
//! \param[in] data the data to store into the channel.
//! \param[in] size_bytes the number of bytes that this data will take up.
//! \param[in] callback callback to call when the recording has completed
//! \return boolean which is True if the data has been stored in the channel,
//!         False otherwise.
bool recording_record_and_notify(
        uint8_t channel, void *data, uint32_t size_bytes,
        recording_complete_callback_t callback);

//! \brief Finishes recording - should only be called if recording_flags is
//!        not 0
void recording_finalise(void);

//! \brief initialises the recording of data
//! \param[in] recording_data_address The start of the data about the recording
//!            Data is {
//!                // number of potential recording regions
//!                uint32_t n_regions;
//!
//!                // tag for live buffer control messages
//!                uint32_t buffering_output_tag;
//!
//!                // size of buffer before a read request is sent
//!                uint32_t buffer_size_before_request;
//!
//!                // minimum time between sending read requests
//!                uint32_t time_between_triggers;
//!
//!                // space that will hold the last sequence number once
//!                // recording is complete
//!                uint32_t last_sequence_number
//!
//!                // pointer to each region to be filled in (can be read
//!                // after recording is complete)
//!                uint32_t* pointer_to_address_of_region[n_regions]
//!
//!                // size of each region to be recorded
//!                uint32_t size_of_region[n_regions];
//!            }
//! \param[out] recording_flags Output of flags which can be used to check if
//!            a channel is enabled for recording
//! \return True if the initialisation was successful, false otherwise
bool recording_initialize(
        address_t recording_data_address, uint32_t *recording_flags);

//! \brief resets recording to the state just after initialisation
void recording_reset(void);

//! \brief Call once per timestep to ensure buffering is done - should only
//!        be called if recording flags is not 0
void recording_do_timestep_update(uint32_t time);

#endif // _RECORDING_H_
