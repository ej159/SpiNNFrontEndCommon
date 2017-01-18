from data_specification.data_specification_executor import \
    DataSpecificationExecutor
from spinn_front_end_common.abstract_models. \
    abstract_requires_rewriting_data_regions_application_vertex import \
    AbstractRequiresRewriteDataRegionsApplicationVertex
from spinn_front_end_common.abstract_models. \
    abstract_requires_rewriting_data_regions_machine_vertex import \
    AbstractRequiresRewriteDataRegionsMachineVertex
from spinn_front_end_common.interface.interface_functions. \
    front_end_common_host_execute_data_specification import \
    FrontEndCommonHostExecuteDataSpecification
from spinn_machine.utilities.progress_bar import ProgressBar
from spinn_front_end_common.utilities import exceptions
from spinn_front_end_common.utilities import helpful_functions
from spinn_storage_handlers.file_data_reader import FileDataReader
from spinn_storage_handlers.file_data_writer import FileDataWriter

import os

class FrontEndCommonDSGRegionReloader(object):
    def __call__(
            self, application_graph, machine_graph, transceiver,
            placements, hostname, report_directory, write_text_specs,
            application_data_file_path, graph_mapper, machine):
        """

        :param application_graph:
        :param machine_graph:
        :param transceiver:
        :param placements:
        :param hostname:
        :param report_directory:
        :param write_text_specs:
        :param application_data_file_path:
        :param graph_mapper:
        :param application_has_ran_flag:
        :return:
        """

        progress_bar = ProgressBar(
            len(application_graph.vertices) + len(machine_graph.vertices),
            "Reloading data regions as required")

        reloaded_dsg_data_files_file_path = \
            helpful_functions.generate_unique_folder_name(
                application_data_file_path, "reloaded_data_regions", "")

        reloaded_dsg_report_files_file_path = \
            helpful_functions.generate_unique_folder_name(
                report_directory, "reloaded_data_regions", "")

        # build new folder
        try:
            if not os.path.exists(reloaded_dsg_data_files_file_path):
                os.makedirs(reloaded_dsg_data_files_file_path)
            if not os.path.exists(reloaded_dsg_report_files_file_path):
                os.makedirs(reloaded_dsg_report_files_file_path)

        except Exception as e:
            raise exceptions.ConfigurationException(
                "Couldn't create folder for storing reloaded data regions")

        for vertex in application_graph.vertices:
            if (isinstance(
                    vertex,
                    AbstractRequiresRewriteDataRegionsApplicationVertex) and
                    vertex.requires_memory_regions_to_be_reloaded()):
                self._handle_application_vertex(
                    vertex, transceiver, placements, hostname,
                    reloaded_dsg_report_files_file_path, write_text_specs,
                    graph_mapper, reloaded_dsg_data_files_file_path, machine)
                vertex.mark_regions_reloaded()
            progress_bar.update()

        for vertex in machine_graph.vertices:
            if (isinstance(
                    vertex,
                    AbstractRequiresRewriteDataRegionsMachineVertex) and
                    vertex.requires_memory_regions_to_be_reloaded()):
                self._handle_machine_vertex(
                    vertex, transceiver, placements, hostname,
                    reloaded_dsg_report_files_file_path, write_text_specs,
                    reloaded_dsg_data_files_file_path, machine)
                vertex.mark_regions_reloaded()
            progress_bar.update()
        progress_bar.end()

    def _handle_application_vertex(
            self, application_vertex, transceiver, placements, hostname,
            report_directory, write_text_specs, graph_mapper,
            reloaded_dsg_data_files_file_path, machine):
        """

        :param application_vertex:
        :param transceiver:
        :param placements:
        :param hostname:
        :param report_directory:
        :param write_text_specs:
        :param graph_mapper:
        :param reloaded_dsg_data_files_file_path:
        :return:
        """

        # get machine vertices from the app vertex
        for machine_vertex in graph_mapper.get_machine_vertices(
                application_vertex):
            # get data from the vertex
            dsg_regions_to_data = \
                application_vertex.regions_and_data_spec_to_rewrite(
                    placements.get_placement_of_vertex(machine_vertex),
                    hostname, report_directory, write_text_specs,
                    reloaded_dsg_data_files_file_path, graph_mapper)

            # write the data to the machine
            self._write_data_regions(
                dsg_regions_to_data, transceiver, machine, write_text_specs,
                placements.get_placement_of_vertex(machine_vertex),
                hostname, reloaded_dsg_data_files_file_path)

    def _handle_machine_vertex(
            self, machine_vertex, transceiver, placements, hostname,
            report_directory, write_text_specs,
            reloaded_dsg_data_files_file_path, machine):
        """

        :param machine_vertex:
        :param transceiver:
        :param placements:
        :param hostname:
        :param report_directory:
        :param write_text_specs:
        :param reloaded_dsg_data_files_file_path:
        :return:
        """

        # get data from the vertex
        dsg_regions_to_data = \
            machine_vertex.regions_and_data_spec_to_rewrite(
                placements.get_placement_of_vertex(machine_vertex),
                hostname, report_directory, write_text_specs,
                reloaded_dsg_data_files_file_path)

        # write the data to the machine
        self._write_data_regions(
            dsg_regions_to_data, transceiver, machine, write_text_specs,
            placements.get_placement_of_vertex(machine_vertex),
            hostname, reloaded_dsg_data_files_file_path)

    @staticmethod
    def _write_data_regions(
            dsg_regions_to_data, transceiver, machine, write_text_specs,
            placement, hostname, reloaded_dsg_data_files_file_path):
        """

        :param dsg_regions_to_data:
        :param transceiver:
        :param machine:
        :param write_text_specs:
        :param placement:
        :param hostname:
        :param reloaded_dsg_data_files_file_path:
        :return:
        """

        for dsg_region in dsg_regions_to_data:
            # build reader for the spec written in sdram
            file_path = dsg_regions_to_data[dsg_region]
            data_spec_reader = FileDataReader(dsg_regions_to_data[dsg_region])

            # generate path for where to store the dse
            app_data_file_path = \
                FrontEndCommonHostExecuteDataSpecification. \
                    get_application_data_file_path(
                    placement.x, placement.y, placement.p, hostname,
                    reloaded_dsg_data_files_file_path)

            # create a writer
            data_writer = FileDataWriter(app_data_file_path)

            # get report writer if needed
            report_writer = FrontEndCommonHostExecuteDataSpecification. \
                generate_report_writer(
                write_text_specs, reloaded_dsg_data_files_file_path,
                hostname, placement.x, placement.y, placement.p)

            # execute the dse
            data_spec_executor = DataSpecificationExecutor(
                data_spec_reader, data_writer,
                machine.get_chip_at(placement.x, placement.y).sdram.size,
                report_writer)
            data_spec_executor.execute()
            data_spec_executor.write_dse_region_output_file(dsg_region)

            # close the application data file writer
            data_writer.close()

            # locate where in sdram to write this block of data
            address = helpful_functions.locate_memory_region_for_placement(
                placement, dsg_region, transceiver)

            # the data is written to memory
            file_reader = FileDataReader(app_data_file_path)
            app_data = file_reader.readall()
            transceiver.write_memory(
                placement.x, placement.y, address, app_data)
            file_reader.close()