from spinn_front_end_common.utilities.constants import SDP_PORTS
from spinnman.messages.scp import SCPRequestHeader
from spinnman.messages.scp.abstract_messages import AbstractSCPRequest
from spinnman.messages.sdp import SDPFlag, SDPHeader
from spinnman.messages.scp.impl.check_ok_response import CheckOKResponse
from .speedup_in_scp_commands import SpeedupInSCPCommands


class SetSystemMCRoutesMessage(AbstractSCPRequest):
    """ An SCP Request to write the system multicast routes into the router
    """

    __slots__ = []

    def __init__(self, x, y, p):
        """
        :param x: The x-coordinate of a chip, between 0 and 255
        :type x: int
        :param y: The y-coordinate of a chip, between 0 and 255
        :type y: int
        :param p: The processor running the extra monitor vertex, between\
            0 and 17
        :type p: int
        :param command_code: the command code used by the extra monitor \
            vertex for setting system multicast routes.
        """

        super(SetSystemMCRoutesMessage, self).__init__(
            SDPHeader(
                flags=SDPFlag.REPLY_EXPECTED,
                destination_port=(
                    SDP_PORTS.EXTRA_MONITOR_CORE_DATA_IN_SPEED_UP.value),
                destination_cpu=p, destination_chip_x=x,
                destination_chip_y=y),
            SCPRequestHeader(
                command=SpeedupInSCPCommands.LOAD_SYSTEM_MC_ROUTES))

    def get_scp_response(self):
        return CheckOKResponse(
            "load system multicast routes",
            SpeedupInSCPCommands.LOAD_SYSTEM_MC_ROUTES)
