"""
This Python package regionalizes processes from the ecoinvent database using trade date from the UN COMTRADE database.
In a first time (that I call first_order_regionalization) electricity, heat and municipal solid waste processes inputs
are adapted to the geographical context. In a second time, all created processes are linked to the rest of the database.

file name: regioinvent.py
author: Maxime Agez
e-mail: maxime.agez@polymtl.ca
date created: 06-04-24
"""

import json
import logging

import bw2data as bd
import pandas as pd
from importlib.resources import files, as_file
from regioinvent.wurst_compat import extract_brightway2_databases_compat
from regioinvent.workflows.lcia_methods import (
    import_fully_regionalized_impact_method as workflow_import_fully_regionalized_impact_method,
)
from regioinvent.workflows.regionalization import (
    connect_ecoinvent_to_regioinvent as workflow_connect_ecoinvent_to_regioinvent,
)
from regioinvent.workflows.regionalization import (
    format_trade_data as workflow_format_trade_data,
)
from regioinvent.workflows.regionalization import (
    write_database as workflow_write_database,
)
from regioinvent.workflows.regionalization import (
    write_regioinvent_to_database as workflow_write_regioinvent_to_database,
)
from regioinvent.workflows.regionalization import (
    regionalize_ecoinvent_with_trade as workflow_regionalize_ecoinvent_with_trade,
)
from regioinvent.workflows.regionalization import (
    create_consumption_markets as workflow_create_consumption_markets,
)
from regioinvent.workflows.regionalization import (
    spatialize_elem_flows as workflow_spatialize_elem_flows,
)
from regioinvent.workflows.regionalization import (
    first_order_regionalization as workflow_first_order_regionalization,
)
from regioinvent.workflows.regionalization import (
    second_order_regionalization as workflow_second_order_regionalization,
)
from regioinvent.workflows.spatialization import (
    spatialize_my_ecoinvent as workflow_spatialize_my_ecoinvent,
)
from regioinvent.workflows.regionalization import (
    change_aluminium_electricity as workflow_change_aluminium_electricity,
)
from regioinvent.workflows.regionalization import (
    change_cobalt_electricity as workflow_change_cobalt_electricity,
)
from regioinvent.workflows.regionalization import (
    change_electricity as workflow_change_electricity,
)
from regioinvent.workflows.regionalization import (
    change_heat as workflow_change_heat,
)
from regioinvent.workflows.regionalization import (
    change_waste as workflow_change_waste,
)
from regioinvent.workflows.regionalization import (
    test_input_presence as workflow_test_input_presence,
)


class Regioinvent:
    def __init__(self, bw_project_name, ecoinvent_database_name, ecoinvent_version):
        """
        :param bw_project_name:         [str] the name of a brightway2 project containing an ecoinvent database.
        :param ecoinvent_database_name: [str] the name of the ecoinvent database within the brightway2 project.
        :param ecoinvent_version:       [str] the version of the ecoinvent database within the brightway2 project,
                                            values can be "3.10" or "3.10.1". "3.11", "3.12".
        """

        # set up logging tool
        self.logger = logging.getLogger("Regioinvent")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        self.logger.propagate = False

        # set up brightway project
        if bw_project_name not in bd.projects:
            raise KeyError(
                "The brightway project name passed does not match with any existing brightway projects."
            )
        bd.projects.set_current(bw_project_name)
        if ecoinvent_database_name not in bd.databases:
            raise KeyError(
                "The ecoinvent database name passed does not match with the existing databases within the brightway project."
            )

        self.source_db_name = ecoinvent_database_name
        self.regionalized_ecoinvent_db_name = f"{ecoinvent_database_name} - regionalized"
        if ecoinvent_version not in ["3.10", "3.10.1", "3.11", "3.12"]:
            raise KeyError(
                "The version of ecoinvent you provided is not supported by Regioinvent."
                "Supported versions are:  3.10/3.10.1, 3.11, 3.12"
            )

        if ecoinvent_version in ["3.10", "3.10.1"]:
            self.ecoinvent_version = "3.10"
        elif ecoinvent_version in ["3.11"]:
            self.ecoinvent_version = "3.11"
        elif ecoinvent_version in ["3.12"]:
            self.ecoinvent_version = "3.12"
        # name is fixed
        self.name_spatialized_biosphere = "biosphere3_spatialized_flows"

        # load data from the different mapping files and such
        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/ecoinvent_to_HS.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.eco_to_hs_class = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/HS_to_exiobase_name.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.hs_class_to_exio = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/country_to_ecoinvent_regions.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.country_to_ecoinvent_regions = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/electricity_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.electricity_geos = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/electricity_aluminium_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.electricity_aluminium_geos = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/waste_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.waste_geos = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/heat_industrial_ng_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.heat_district_ng = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/heat_industrial_non_ng_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.heat_district_non_ng = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/heat_small_scale_non_ng_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.heat_small_scale_non_ng = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/COMTRADE_to_ecoinvent_geographies.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.convert_ecoinvent_geos = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/COMTRADE_to_exiobase_geographies.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.convert_exiobase_geos = json.load(f)

        with as_file(
            files("regioinvent").joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/no_inputs_processes.json"
            )
        ) as file_path:
            with open(file_path, "r") as f:
                self.no_inputs_processes = json.load(f)

        # initialize attributes used within package
        self.assigned_random_geography = []
        self.regioinvent_in_wurst = []
        self.regioinvent_in_dict = {}
        self.ei_regio_data = {}
        self.ei_wurst = []
        self.ei_in_dict = {}
        self.distribution_technologies = {}
        self.transportation_modes = {}
        self.created_geographies = dict.fromkeys(self.eco_to_hs_class.keys())
        self.unit = dict.fromkeys(self.eco_to_hs_class.keys())
        self.domestic_production = pd.DataFrame()
        self.consumption_data = pd.DataFrame()
        self.production_data = pd.DataFrame()
        self.trade_conn = ""
        self.target_db_name = ""
        self.cutoff = 0
        self._spatialized_in_memory_ready = False
        self._final_database_in_memory = None

    def _extract_brightway2_databases(self, database_name):
        """
        Return a wurst extraction of a Brightway database with compatibility fallback.
        """
        return extract_brightway2_databases_compat(database_name, add_identifiers=True)

    def spatialize_my_ecoinvent(self):
        return workflow_spatialize_my_ecoinvent(self)

    def spatialize_ecoinvent(self):
        return self.spatialize_my_ecoinvent()

    def import_fully_regionalized_impact_method(self, lcia_method="all"):
        return workflow_import_fully_regionalized_impact_method(self, lcia_method)

    def regionalize_ecoinvent_with_trade(self, trade_database_path, target_database_name, cutoff):
        return workflow_regionalize_ecoinvent_with_trade(self, trade_database_path, target_database_name, cutoff)

    def format_trade_data(self):
        return workflow_format_trade_data(self)

    def first_order_regionalization(self):
        return workflow_first_order_regionalization(self)

    def create_consumption_markets(self):
        return workflow_create_consumption_markets(self)

    def second_order_regionalization(self):
        return workflow_second_order_regionalization(self)

    def spatialize_elem_flows(self):
        return workflow_spatialize_elem_flows(self)

    def write_regioinvent_to_database(self):
        return workflow_write_regioinvent_to_database(self)

    def write_database(self):
        return workflow_write_database(self)

    def connect_ecoinvent_to_regioinvent(self):
        return workflow_connect_ecoinvent_to_regioinvent(self)

    # -------------------------------------------Supporting functions---------------------------------------------------

    def change_electricity(self, process, export_country):
        return workflow_change_electricity(self, process, export_country)

    def change_aluminium_electricity(self, process, export_country):
        return workflow_change_aluminium_electricity(self, process, export_country)

    def change_cobalt_electricity(self, process):
        return workflow_change_cobalt_electricity(self, process)

    def change_waste(self, process, export_country):
        return workflow_change_waste(self, process, export_country)

    def change_heat(self, process, export_country, heat_flow):
        return workflow_change_heat(self, process, export_country, heat_flow)

    def test_input_presence(self, process, input_name, extra=None):
        return workflow_test_input_presence(self, process, input_name, extra=extra)
