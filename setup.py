from setuptools import setup

setup(
    name="SpiNNFrontEndCommon",
    version="3.0.1",
    description="Common Spinnaker Front end functions",
    url="https://github.com/SpiNNakerManchester/SpiNNFrontEndCommon",
    packages=[
        'spinn_front_end_common',
        'spinn_front_end_common.abstract_models',
        'spinn_front_end_common.abstract_models.impl',
        'spinn_front_end_common.common_model_binaries',
        'spinn_front_end_common.interface',
        'spinn_front_end_common.interface.buffer_management',
        'spinn_front_end_common.interface.buffer_management.buffer_models',
        'spinn_front_end_common.interface.buffer_management.storage_objects',
        'spinn_front_end_common.interface.interface_functions',
        'spinn_front_end_common.interface.provenance',
        'spinn_front_end_common.interface.simulation',
        'spinn_front_end_common.mapping_algorithms',
        'spinn_front_end_common'
            '.mapping_algorithms.on_chip_router_table_compression',
        'spinn_front_end_common.utilities',
        'spinn_front_end_common.utilities.connections',
        'spinn_front_end_common.utilities.database',
        'spinn_front_end_common.utilities.notification_protocol',
        'spinn_front_end_common.utilities.reload',
        'spinn_front_end_common.utilities.report_functions',
        'spinn_front_end_common.utilities.scp',
        'spinn_front_end_common.utilities.utility_objs',
        'spinn_front_end_common.utility_models'],
    package_data={
        'spinn_front_end_common.common_model_binaries': ['*.aplx'],
        'spinn_front_end_common.interface.interface_functions': ['*.xml'],
        'spinn_front_end_common.utilities.report_functions': ['*.xml']},
    install_requires=['SpiNNMachine >= 3.0.0, < 4.0.0',
                      'SpiNNMan >= 3.0.0, < 4.0.0',
                      'SpiNNaker_PACMAN >= 3.0.0, < 4.0.0',
                      'SpiNNaker_DataSpecification >= 3.0.0, < 4.0.0',
                      'SpiNNStorageHandlers >= 3.0.0, < 4.0.0',
                      'spalloc >= v0.2.2, < v1.0.0',
                      'requests >= 2.4.1',
                      'numpy', 'six']
)
