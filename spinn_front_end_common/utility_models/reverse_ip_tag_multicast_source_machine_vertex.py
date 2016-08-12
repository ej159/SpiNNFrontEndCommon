from pacman.executor.injection_decorator import inject, supports_injection, \
    requires_injection
from pacman.model.constraints.key_allocator_constraints\
    .key_allocator_fixed_key_and_mask_constraint \
    import KeyAllocatorFixedKeyAndMaskConstraint
from pacman.model.decorators.overrides import overrides
from pacman.model.resources.iptag_resource import IPtagResource
from pacman.model.resources.reverse_iptag_resource import ReverseIPtagResource
from pacman.model.routing_info.base_key_and_mask import BaseKeyAndMask
from pacman.model.graphs.machine.impl.machine_vertex import MachineVertex
from pacman.model.constraints.placer_constraints\
    .placer_board_constraint import PlacerBoardConstraint

from spinn_front_end_common.abstract_models.impl.\
    uses_simulation_needs_total_runtime_data_specable_vertex import \
    UsesSimulationNeedsTotalRuntimeDataSpecableVertex
from spinn_front_end_common.interface.buffer_management.buffer_models\
    .sends_buffers_from_host_pre_buffered_impl \
    import SendsBuffersFromHostPreBufferedImpl
from spinn_front_end_common.interface.buffer_management.buffer_models\
    .receives_buffers_to_host_basic_impl import ReceiveBuffersToHostBasicImpl
from spinn_front_end_common.interface.buffer_management.storage_objects\
    .buffered_sending_region import BufferedSendingRegion
from spinn_front_end_common.utilities import constants

from spinn_front_end_common.utilities.exceptions import ConfigurationException
from spinn_front_end_common.abstract_models\
    .abstract_provides_outgoing_partition_constraints \
    import AbstractProvidesOutgoingPartitionConstraints
from spinn_front_end_common.abstract_models.abstract_recordable \
    import AbstractRecordable
from spinn_front_end_common.interface.provenance\
    .provides_provenance_data_from_machine_impl import \
    ProvidesProvenanceDataFromMachineImpl

from spinnman.messages.eieio.eieio_prefix import EIEIOPrefix

from enum import Enum
import math
import copy

_DEFAULT_MALLOC_REGIONS = 2


@supports_injection
class ReverseIPTagMulticastSourceMachineVertex(
        MachineVertex, UsesSimulationNeedsTotalRuntimeDataSpecableVertex,
        ProvidesProvenanceDataFromMachineImpl,
        AbstractProvidesOutgoingPartitionConstraints,
        SendsBuffersFromHostPreBufferedImpl,
        ReceiveBuffersToHostBasicImpl, AbstractRecordable):
    """ A model which allows events to be injected into spinnaker and\
        converted in to multicast packets
    """

    _REGIONS = Enum(
        value="_REGIONS",
        names=[('SYSTEM', 0),
               ('CONFIGURATION', 1),
               ('SEND_BUFFER', 2),
               ('RECORDING_BUFFER', 3),
               ('RECORDING_BUFFER_STATE', 4),
               ('PROVENANCE_REGION', 5)])

    _CONFIGURATION_REGION_SIZE = 40

    def __init__(
            self, n_keys, resources_required, machine_time_step,
            timescale_factor, label, constraints=None,

            # General input and output parameters
            board_address=None,

            # Live input parameters
            receive_port=None,
            receive_sdp_port=(
                constants.SDP_PORTS.INPUT_BUFFERING_SDP_PORT.value),
            receive_tag=None,

            # Key parameters
            virtual_key=None, prefix=None,
            prefix_type=None, check_keys=False,

            # Send buffer parameters
            send_buffer_times=None,
            send_buffer_partition_id=None,
            send_buffer_max_space=(
                constants.MAX_SIZE_OF_BUFFERED_REGION_ON_CHIP),
            send_buffer_space_before_notify=640,
            send_buffer_notification_ip_address=None,
            send_buffer_notification_port=None,
            send_buffer_notification_tag=None):
        """

        :param n_keys: The number of keys to be sent via this multicast source
        :param resources_required: The resources required by the vertex
        :type resources_required: `pacman.model.resources.resource_container.ResourceContainer`
        :param machine_time_step: The time step to be used on the machine
        :param timescale_factor: The time scaling to be used in the simulation
        :param label: The label of this vertex
        :param constraints: Any initial constraints to this vertex
        :param board_address: The IP address of the board on which to place\
                this vertex if receiving data, either buffered or live (by\
                default, any board is chosen)
        :param receive_port: The port on the board that will listen for\
                incoming event packets (default is to disable this feature;\
                set a value to enable it)
        :param receive_sdp_port: The SDP port to listen on for incoming event\
                packets (defaults to 1)
        :param receive_tag: The IP tag to use for receiving live events\
                (uses any by default)
        :param virtual_key: The base multicast key to send received events\
                with (assigned automatically by default)
        :param prefix: The prefix to "or" with generated multicast keys\
                (default is no prefix)
        :param prefix_type: Whether the prefix should apply to the upper or\
                lower half of the multicast keys (default is upper half)
        :param check_keys: True if the keys of received events should be\
                verified before sending (default False)
        :param send_buffer_times: An array of arrays of times at which keys\
                should be sent (one array for each key, default disabled)
        :param send_buffer_max_space: The maximum amount of space to use of\
                the SDRAM on the machine (default is 1MB)
        :param send_buffer_space_before_notify: The amount of space free in\
                the sending buffer before the machine will ask the host for\
                more data (default setting is optimised for most cases)
        :param send_buffer_notification_ip_address: The IP address of the host\
                that will send new buffers (must be specified if a send buffer\
                is specified)
        :param send_buffer_notification_port: The port that the host that will\
                send new buffers is listening on (must be specified if a\
                send buffer is specified)
        :param send_buffer_notification_tag: The IP tag to use to notify the\
                host about space in the buffer (default is to use any tag)
        """
        ReceiveBuffersToHostBasicImpl.__init__(self)

        constraints = copy.deepcopy(constraints)
        # Set up super types
        MachineVertex.__init__(
            self, resources_required, label, constraints)
        UsesSimulationNeedsTotalRuntimeDataSpecableVertex.__init__(
            self, machine_time_step, timescale_factor)
        ProvidesProvenanceDataFromMachineImpl.__init__(
            self, self._REGIONS.PROVENANCE_REGION.value, 0)
        AbstractProvidesOutgoingPartitionConstraints.__init__(self)

        # storage objects
        self._graph_mapper = None
        self._machine_graph = None
        self._routing_info = None
        self._iptags = None

        # Set up for receiving live packets
        if receive_port is not None:
            resources_required.add_to_reverse_iptags(
                ReverseIPtagResource(
                    port=receive_port, sdp_port=receive_sdp_port,
                    tag=receive_tag))
            if board_address is not None:
                self.add_constraint(PlacerBoardConstraint(board_address))

        # Work out if buffers are being sent
        self._first_machine_time_step = 0
        self._send_buffer = None
        self._send_buffer_partition_id = send_buffer_partition_id
        if send_buffer_times is None:
            self._send_buffer_times = None
            self._send_buffer_max_space = send_buffer_max_space
            SendsBuffersFromHostPreBufferedImpl.__init__(
                self, None)
        else:
            self._send_buffer_max_space = send_buffer_max_space
            self._send_buffer = BufferedSendingRegion(send_buffer_max_space)
            self._send_buffer_times = send_buffer_times

            resources_required.add_to_iptag_usage(IPtagResource(
                send_buffer_notification_ip_address,
                send_buffer_notification_port, True,
                send_buffer_notification_tag))
            if board_address is not None:
                self.add_constraint(PlacerBoardConstraint(board_address))
            SendsBuffersFromHostPreBufferedImpl.__init__(
                self, {self._REGIONS.SEND_BUFFER.value: self._send_buffer})

        # buffered out parameters
        self._send_buffer_space_before_notify = send_buffer_space_before_notify
        self._send_buffer_notification_ip_address = \
            send_buffer_notification_ip_address
        self._send_buffer_notification_port = send_buffer_notification_port
        self._send_buffer_notification_tag = send_buffer_notification_tag
        if self._send_buffer_space_before_notify > send_buffer_max_space:
            self._send_buffer_space_before_notify = send_buffer_max_space

        # Set up for recording (if requested)
        self._record_buffer_size = 0
        self._buffer_size_before_receive = 0

        # set flag for checking if in injection mode
        self._in_injection_mode = receive_port is not None

        # Sort out the keys to be used
        self._n_keys = n_keys
        self._virtual_key = virtual_key
        self._mask = None
        self._prefix = prefix
        self._prefix_type = prefix_type
        self._check_keys = check_keys

        # Work out the prefix details
        if self._prefix is not None:
            if self._prefix_type is None:
                self._prefix_type = EIEIOPrefix.UPPER_HALF_WORD
            if self._prefix_type == EIEIOPrefix.UPPER_HALF_WORD:
                self._prefix = prefix << 16

        # If the user has specified a virtual key
        if self._virtual_key is not None:

            # check that virtual key is valid
            if self._virtual_key < 0:
                raise ConfigurationException(
                    "Virtual keys must be positive")

            # Get a mask and maximum number of keys for the number of keys
            # requested
            self._mask, max_key = self._calculate_mask(n_keys)

            # Check that the number of keys and the virtual key don't interfere
            if n_keys > max_key:
                raise ConfigurationException(
                    "The mask calculated from the number of keys will "
                    "not work with the virtual key specified")

            if self._prefix is not None:

                # Check that the prefix doesn't change the virtual key in the
                # masked area
                masked_key = (self._virtual_key | self._prefix) & self._mask
                if self._virtual_key != masked_key:
                    raise ConfigurationException(
                        "The number of keys, virtual key and key prefix"
                        " settings don't work together")
            else:

                # If no prefix was generated, generate one
                self._prefix_type = EIEIOPrefix.UPPER_HALF_WORD
                self._prefix = self._virtual_key

    @staticmethod
    def n_regions_to_allocate(send_buffering, recording):
        """ Get the number of regions that will be allocated
        """
        if recording and send_buffering:
            return 5
        elif recording or send_buffering:
            return 4
        return 3

    @property
    def send_buffer_times(self):
        return self._send_buffer_times

    @send_buffer_times.setter
    def send_buffer_times(self, send_buffer_times):
        self._send_buffer_times = send_buffer_times

    @inject("FirstMachineTimeStep")
    def first_machine_time_step(self, first_machine_time_step):
        self._first_machine_time_step = first_machine_time_step
        self._fill_send_buffer()

    def _is_in_range(self, time_stamp_in_ticks):
        return (
            (self._no_machine_time_steps is None) or (
                self._first_machine_time_step <= time_stamp_in_ticks <
                self._no_machine_time_steps))

    def set_no_machine_time_steps(self, new_value):
        self._no_machine_time_steps = new_value

    def _fill_send_buffer(self):
        """ Fill the send buffer with keys to send
        """

        # Skip if the virtual key is not yet defined
        key_to_send = self._virtual_key
        if self._virtual_key is None:
            key_to_send = 0

        if self._send_buffer is not None:
            self._send_buffer.clear()
        if (self._send_buffer_times is not None and
                len(self._send_buffer_times) != 0):
            if hasattr(self._send_buffer_times[0], "__len__"):

                # Works with a list-of-lists
                for key in range(self._n_keys):
                    for timeStamp in sorted(self._send_buffer_times[key]):
                        time_stamp_in_ticks = int(math.ceil(
                            float(int(timeStamp * 1000.0)) /
                            self._machine_time_step))
                        if self._is_in_range(time_stamp_in_ticks):
                            self._send_buffer.add_key(
                                time_stamp_in_ticks, key_to_send + key)
            else:

                # Work with a single list
                key_list = [
                    key + key_to_send for key in range(self._n_keys)]
                for timeStamp in sorted(self._send_buffer_times):
                    time_stamp_in_ticks = int(math.ceil(
                        float(int(timeStamp * 1000.0)) /
                        self._machine_time_step))

                    # add to send_buffer collection
                    if self._is_in_range(time_stamp_in_ticks):
                        self._send_buffer.add_keys(
                            time_stamp_in_ticks, key_list)

    @staticmethod
    def _generate_prefix(virtual_key, prefix_type):
        if prefix_type == EIEIOPrefix.LOWER_HALF_WORD:
            return virtual_key & 0xFFFF
        return (virtual_key >> 16) & 0xFFFF

    @staticmethod
    def _calculate_mask(n_neurons):
        if n_neurons == 1:
            return 0xFFFFFFFF, 1
        temp_value = int(math.ceil(math.log(n_neurons, 2)))
        max_key = (int(math.pow(2, temp_value)) - 1)
        mask = 0xFFFFFFFF - max_key
        return mask, max_key

    def enable_recording(
            self, buffering_ip_address, buffering_port,
            board_address=None, notification_tag=None,
            record_buffer_size=constants.MAX_SIZE_OF_BUFFERED_REGION_ON_CHIP,
            buffer_size_before_receive=(constants.
                                        DEFAULT_BUFFER_SIZE_BEFORE_RECEIVE),
            minimum_sdram_for_buffering=0, buffered_sdram_per_timestep=0):

        self.activate_buffering_output(
            buffering_ip_address, buffering_port, board_address,
            minimum_sdram_for_buffering, buffered_sdram_per_timestep)

        self._record_buffer_size = record_buffer_size
        self._recording_enabled = True
        self._buffer_size_before_receive = buffer_size_before_receive

    def _reserve_regions(self, spec):

        # Reserve system and configuration memory regions:
        spec.reserve_memory_region(
            region=self._REGIONS.SYSTEM.value,
            size=((constants.DATA_SPECABLE_BASIC_SETUP_INFO_N_WORDS * 4) +
                  self.get_recording_data_size(1)), label='SYSTEM')
        spec.reserve_memory_region(
            region=self._REGIONS.CONFIGURATION.value,
            size=self._CONFIGURATION_REGION_SIZE, label='CONFIGURATION')

        # Reserve send buffer region if required
        if self._send_buffer_times is not None:
            max_buffer_size = self.get_max_buffer_size_possible(
                self._REGIONS.SEND_BUFFER.value)
            spec.reserve_memory_region(
                region=self._REGIONS.SEND_BUFFER.value,
                size=max_buffer_size, label="SEND_BUFFER", empty=True)

        # Reserve recording buffer regions if required
        self.reserve_buffer_regions(
            spec, self._REGIONS.RECORDING_BUFFER_STATE.value,
            [self._REGIONS.RECORDING_BUFFER.value], [self._record_buffer_size])

        self.reserve_provenance_data_region(spec)

    def _update_virtual_key(self, routing_info, machine_graph):
        if self._virtual_key is None:
            if self._send_buffer_partition_id is not None:

                rinfo = routing_info.get_routing_info_from_pre_vertex(
                    self, self._send_buffer_partition_id)
                self._virtual_key = rinfo.first_key
                self._mask = rinfo.first_mask

            else:
                partitions = machine_graph\
                    .get_outgoing_edge_partitions_starting_at_vertex(self)
                if len(partitions) == 1:
                    rinfo = routing_info.get_routing_info_from_partition(
                        partitions[0])
                    self._virtual_key = rinfo.first_key
                    self._mask = rinfo.first_mask

        if self._virtual_key is not None and self._prefix is None:
            self._prefix_type = EIEIOPrefix.UPPER_HALF_WORD
            self._prefix = self._virtual_key

    def _write_configuration(self, spec, ip_tags):
        spec.switch_write_focus(region=self._REGIONS.CONFIGURATION.value)

        # Write apply_prefix and prefix and prefix_type
        if self._prefix is None:
            spec.write_value(data=0)
            spec.write_value(data=0)
            spec.write_value(data=0)
        else:
            spec.write_value(data=1)
            spec.write_value(data=self._prefix)
            spec.write_value(data=self._prefix_type.value)

        # Write check
        if self._check_keys:
            spec.write_value(data=1)
        else:
            spec.write_value(data=0)

        # Write if you have a key to transmit write it and the mask,
        # otherwise write flags to fill in space
        if self._virtual_key is None:
            spec.write_value(data=0)
            spec.write_value(data=0)
            spec.write_value(data=0)
        else:
            spec.write_value(data=1)
            spec.write_value(data=self._virtual_key)
            spec.write_value(data=self._mask)

        # Write send buffer data
        if self._send_buffer_times is not None:

            this_tag = None
            for tag in ip_tags:
                if (tag.ip_address ==
                        self._send_buffer_notification_ip_address and
                        tag.port == self._send_buffer_notification_port):
                    this_tag = tag
            if this_tag is None:
                raise Exception("Could not find tag for send buffering")

            buffer_space = self.get_max_buffer_size_possible(
                self._REGIONS.SEND_BUFFER.value)

            spec.write_value(data=buffer_space)
            spec.write_value(data=self._send_buffer_space_before_notify)
            spec.write_value(data=this_tag.tag)
        else:
            spec.write_value(data=0)
            spec.write_value(data=0)
            spec.write_value(data=0)

    @requires_injection([
        "MemoryIpTags", "MemoryMachineGraph", "MemoryRoutingInfos"])
    @overrides(UsesSimulationNeedsTotalRuntimeDataSpecableVertex.
               generate_data_specification)
    def generate_data_specification(self, spec, placement):

        self._update_virtual_key(self._routing_info, self._machine_graph)
        self._fill_send_buffer()

        # Reserve regions
        self._reserve_regions(spec)

        # Write the system region
        spec.switch_write_focus(self._REGIONS.SYSTEM.value)
        spec.write_array(self.data_for_simulation_data())

        # Write the additional recording information
        self.write_recording_data(
            spec, self._iptags, [self._record_buffer_size],
            self._buffer_size_before_receive)

        # Write the configuration information
        self._write_configuration(spec, self._iptags)

        # End spec
        spec.end_specification()

    @overrides(UsesSimulationNeedsTotalRuntimeDataSpecableVertex.
               get_binary_file_name)
    def get_binary_file_name(self):
        return "reverse_iptag_multicast_source.aplx"

    @property
    @overrides(MachineVertex.model_name)
    def model_name(self):
        return "ReverseIPTagMulticastSourceMachineVertex"

    @overrides(AbstractProvidesOutgoingPartitionConstraints.
               get_outgoing_partition_constraints)
    def get_outgoing_partition_constraints(self, partition):
        if self._virtual_key is not None:
            return list([KeyAllocatorFixedKeyAndMaskConstraint(
                [BaseKeyAndMask(self._virtual_key, self._mask)])])
        return list()

    @property
    def virtual_key(self):
        return self._virtual_key

    @property
    def mask(self):
        return self._mask

    @property
    def is_in_injection_mode(self):
        return self._in_injection_mode

    def is_recording(self):
        return self._record_buffer_size > 0

    @inject("MemoryGraphMapper")
    def set_graph_mapper(self, graph_mapper):
        self._graph_mapper = graph_mapper

    @inject("MemoryMachineGraph")
    def set_machine_graph(self, machine_graph):
        self._machine_graph = machine_graph

    @inject("MemoryRoutingInfos")
    def set_routing_info(self, routing_info):
        self._routing_info = routing_info

    @inject("MemoryIpTags")
    def set_iptags(self, iptags):
        self._iptags = iptags
