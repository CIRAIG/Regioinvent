"""
This Python package regionalizes processes from the ecoinvent database using trade date from the UN COMTRADE database.
In a first time (that I call first_order_regionalization) electricity, heat and municipal solid waste processes inputs
are adapted to the geographical context. In a second time, all created processes are linked to the rest of the database.

file name: regioinvent.py
author: Maxime Agez
e-mail: maxime.agez@polymtl.ca
date created: 06-04-24
"""

import collections
import copy
import json
import logging
import pickle
import sqlite3
import uuid

import brightway2 as bw2
import pandas as pd
import wurst
import wurst.searching as ws
from tqdm import tqdm
from importlib.resources import files, as_file


class Regioinvent:
    def __init__(self, bw_project_name, ecoinvent_database_name, ecoinvent_version):
        """
        :param bw_project_name:         [str] the name of a brightway2 project containing an ecoinvent database.
        :param ecoinvent_database_name: [str] the name of the ecoinvent database within the brightway2 project.
        :param ecoinvent_version:       [str] the version of the ecoinvent database within the brightway2 project,
                                            values can be "3.9", "3.9.1", "3.10" or "3.10.1".
        """

        # set up logging tool
        self.logger = logging.getLogger("Regioinvent")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        self.logger.propagate = False

        # set up brightway project
        if bw_project_name not in bw2.projects:
            raise KeyError(
                "The brightway project name passed does not match with any existing brightway projects."
            )
        bw2.projects.set_current(bw_project_name)
        if ecoinvent_database_name not in bw2.databases:
            raise KeyError(
                "The ecoinvent database name passed does not match with the existing databases within the brightway project."
            )

        # set up necessary variables
        self.ecoinvent_database_name = ecoinvent_database_name
        self.name_ei_with_regionalized_biosphere = (
            ecoinvent_database_name + " regionalized"
        )
        if ecoinvent_version not in ["3.9", "3.9.1", "3.10", "3.10.1"]:
            raise KeyError(
                "The version of ecoinvent you provided is not supported by Regioinvent."
                "Supported versions are: 3.9, 3.9.1, 3.10 or 3.10.1"
            )
        if ecoinvent_version in ["3.9", "3.9.1"]:
            self.ecoinvent_version = "3.9"
        elif ecoinvent_version in ["3.10", "3.10.1"]:
            self.ecoinvent_version = "3.10"
        # name is fixed
        self.name_spatialized_biosphere = "biosphere3_spatialized_flows"

        # load data from the different mapping files and such
        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/ecoinvent_to_HS.json")) as file_path:
            with open(file_path, "r") as f:
                self.eco_to_hs_class = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/HS_to_exiobase_name.json")) as file_path:
            with open(file_path, "r") as f:
                self.hs_class_to_exio = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/country_to_ecoinvent_regions.json")) as file_path:
            with open(file_path, "r") as f:
                self.country_to_ecoinvent_regions = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/electricity_processes.json")) as file_path:
            with open(file_path, "r") as f:
                self.electricity_geos = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/electricity_aluminium_processes.json")) as file_path:
            with open(file_path, "r") as f:
                self.electricity_aluminium_geos = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/waste_processes.json")) as file_path:
            with open(file_path, "r") as f:
                self.waste_geos = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/heat_industrial_ng_processes.json")) as file_path:
            with open(file_path, "r") as f:
                self.heat_district_ng = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/heat_industrial_non_ng_processes.json")) as file_path:
            with open(file_path, "r") as f:
                self.heat_district_non_ng = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/heat_small_scale_non_ng_processes.json")) as file_path:
            with open(file_path, "r") as f:
                self.heat_small_scale_non_ng = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/COMTRADE_to_ecoinvent_geographies.json")) as file_path:
            with open(file_path, "r") as f:
                self.convert_ecoinvent_geos = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/COMTRADE_to_exiobase_geographies.json")) as file_path:
            with open(file_path, "r") as f:
                self.convert_exiobase_geos = json.load(f)

        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/no_inputs_processes.json")) as file_path:
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
        self.regioinvent_database_name = ""
        self.cutoff = 0

    def spatialize_my_ecoinvent(self):
        """
        Function creates a copy of the original ecoinvent database and modifies this copy to spatialize the elementary
        flows used by ecoinvent. It also creates additional technosphere water processes to remediate imbalances due to
        technosphere misrepresentations.

        :return: nothing but creates multiple databases in your brightway2 project
        """

        # ---------------------------- Create the spatialized biosphere ----------------------------

        if "biosphere3_spatialized_flows" not in bw2.databases:
            self.logger.info("Creating spatialized biosphere flows...")
            # load the correct pickle file with the different spatialized elementary flows metadata
            with as_file(files('regioinvent').joinpath(
                    f"data/Spatialization_of_elementary_flows/ei{self.ecoinvent_version}/spatialized_biosphere_database.pickle")) as file_path:
                with open(file_path, "rb") as f:
                    spatialized_biosphere = pickle.load(f)

            # create the new biosphere3 database with spatialized elementary flows
            bw2.Database(self.name_spatialized_biosphere).write(spatialized_biosphere)
        else:
            self.logger.info(
                "biosphere3_spatialized_flows already exists in this project."
            )

        # ---------------------------- Spatialize ecoinvent ----------------------------

        if self.name_ei_with_regionalized_biosphere not in bw2.databases:
            # transform format of ecoinvent to wurst format for speed-up
            self.logger.info("Extracting ecoinvent to wurst...")
            self.ei_wurst = wurst.extract_brightway2_databases(
                self.ecoinvent_database_name, add_identifiers=True
            )

            # also get ecoinvent in a format for more efficient searching
            self.ei_in_dict = {
                (i["reference product"], i["location"], i["name"]): i
                for i in self.ei_wurst
            }

            # load the list of the base name of all spatialized elementary flows
            with as_file(files('regioinvent').joinpath(
                    f"data/Spatialization_of_elementary_flows/ei{self.ecoinvent_version}/spatialized_elementary_flows.json")) as file_path:
                with open(file_path, "r") as f:
                    base_spatialized_flows = json.load(f)

            # store the codes of the spatialized flows in a dictionary
            spatialized_flows = {
                (i.as_dict()["name"], i.as_dict()["categories"]): i.as_dict()["code"]
                for i in bw2.Database(self.name_spatialized_biosphere)
            }

            self.logger.info("Spatializing ecoinvent...")
            # loop through the whole ecoinvent database
            for process in self.ei_wurst:
                # if you have more than 1000 exchanges -> aggregated process (S) -> should not be spatialized
                if len(process["exchanges"]) < 1000:
                    # create a copy, but in the new ecoinvent database
                    process["database"] = self.name_ei_with_regionalized_biosphere
                    # loop through exchanges of a process
                    for exc in process["exchanges"]:
                        # if it's a biosphere exchange
                        if exc["type"] == "biosphere":
                            # check if it's a flow that should be spatialized
                            if exc["name"] in base_spatialized_flows:
                                # check if the category makes sense (don't regionalize mineral resources for instance)
                                if (
                                    exc["categories"][0]
                                    in base_spatialized_flows[exc["name"]]
                                ):
                                    # to spatialize it, we need to get the uuid of the existing spatialized flow
                                    exc["code"] = spatialized_flows[
                                        (
                                            exc["name"] + ", " + process["location"],
                                            exc["categories"],
                                        )
                                    ]
                                    # change the database of the exchange as well
                                    exc["database"] = self.name_spatialized_biosphere
                                    # update its name
                                    exc["name"] = (
                                        exc["name"] + ", " + process["location"]
                                    )
                                    # and finally its input key
                                    exc["input"] = (exc["database"], exc["code"])
                        # if it's a technosphere exchange, just update the database value
                        else:
                            exc["database"] = self.name_ei_with_regionalized_biosphere
                # if you are an aggregated process (S)
                elif len(process["exchanges"]) > 1000:
                    # simply change the name of the database
                    process["database"] = self.name_ei_with_regionalized_biosphere
                    for exc in process["exchanges"]:
                        exc["database"] = self.name_ei_with_regionalized_biosphere

            # sometimes input keys disappear with wurst, make sure there is always one
            for pr in self.ei_wurst:
                for exc in pr["exchanges"]:
                    try:
                        exc["input"]
                    except KeyError:
                        exc["input"] = (exc["database"], exc["code"])

            # modify structure of data from wurst to bw2
            self.ei_regio_data = {(i["database"], i["code"]): i for i in self.ei_wurst}

            # same as before, ensure input key is here
            for pr in self.ei_regio_data:
                for exc in self.ei_regio_data[pr]["exchanges"]:
                    try:
                        exc["input"]
                    except KeyError:
                        exc["input"] = (exc["database"], exc["code"])
            # wurst creates empty categories for technosphere activities, delete those
            for pr in self.ei_regio_data:
                try:
                    del self.ei_regio_data[pr]["categories"]
                except KeyError:
                    pass
            # same with parameters
            for pr in self.ei_regio_data:
                try:
                    del self.ei_regio_data[pr]["parameters"]
                except KeyError:
                    pass

            # write the ecoinvent-regionalized database to brightway
            bw2.Database(self.name_ei_with_regionalized_biosphere).write(
                self.ei_regio_data
            )
        else:
            self.logger.info(
                "There is already a spatialized version of ecoinvent in your project. If you want to redo "
                "spatialization, please delete it and re-run."
            )

    def import_fully_regionalized_impact_method(self, lcia_method="all"):
        """
        Function to import a fully regionalized impact method into your brightway project, to-be-used with the
        spatialized version of ecoinvent. You can choose between IMPACT World+, EF and ReCiPe, or simply all of them.

        :param lcia_method: [str] the name of the LCIA method to be imported to be used with the spatialized ecoinvent,
                                available methods are "IW v2.1", "EF v3.1", "ReCiPe 2016 v1.03 (H)" or "all".
        :return:
        """

        if lcia_method not in ["IW v2.1", "EF v3.1", "ReCiPe 2016 v1.03 (H)", "all"]:
            raise KeyError(
                "Available LCIA methods are: 'IW v2.1', 'EF v3.1', 'ReCiPe 2016 v1.03 (H)' or 'all'"
            )

        # just load the correct BW2Package file from Data storage folder
        if lcia_method == "all" and self.ecoinvent_version == "3.10":
            self.logger.info(
                "Importing all available fully regionalized lcia methods for ecoinvent3.10."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/IW/impact_world_plus_21_regionalized-for-ecoinvent-v310.0fffd5e3daa5f4cf11ef83e49c375827.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

            with as_file(files('regioinvent').joinpath(
                    "data/EF/EF31_regionalized-for-ecoinvent-v310.87ec66ed7e5775d0132d1129fb5caf03.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

            with as_file(files('regioinvent').joinpath(
                    "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v310.dd7e66b1994d898394e3acfbed8eef83.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        if lcia_method == "all" and self.ecoinvent_version == "3.9":
            self.logger.info(
                "Importing all available fully regionalized lcia methods for ecoinvent3.9."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/IW/impact_world_plus_21_regionalized-for-ecoinvent-v39.af770e84bfd0f4365d509c026796639a.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

            with as_file(files('regioinvent').joinpath(
                    "data/EF/EF31_regionalized-for-ecoinvent-v39.ff0965b0f9793fbd2a351c9155946122.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

            with as_file(files('regioinvent').joinpath(
                    "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v39.d03db1f1699b4f0b4d72626e52a40647.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        if lcia_method == "IW v2.1" and self.ecoinvent_version == "3.10":
            self.logger.info(
                "Importing the fully regionalized version of IMPACT World+ v2.1 for ecoinvent3.10."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/IW/impact_world_plus_21_regionalized-for-ecoinvent-v310.0fffd5e3daa5f4cf11ef83e49c375827.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        elif lcia_method == "IW v2.1" and self.ecoinvent_version == "3.9":
            self.logger.info(
                "Importing the fully regionalized version of IMPACT World+ v2.1 for ecoinvent3.9."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/IW/impact_world_plus_21_regionalized-for-ecoinvent-v39.af770e84bfd0f4365d509c026796639a.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        elif lcia_method == "EF v3.1" and self.ecoinvent_version == "3.10":
            self.logger.info(
                "Importing the fully regionalized version of EF v3.1 for ecoinvent 3.10."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/EF/EF31_regionalized-for-ecoinvent-v310.87ec66ed7e5775d0132d1129fb5caf03.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        elif lcia_method == "EF v3.1" and self.ecoinvent_version == "3.9":
            self.logger.info(
                "Importing the fully regionalized version of EF v3.1 for ecoinvent 3.9."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/EF/EF31_regionalized-for-ecoinvent-v39.ff0965b0f9793fbd2a351c9155946122.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        elif (
            lcia_method == "ReCiPe 2016 v1.03 (H)" and self.ecoinvent_version == "3.10"
        ):
            self.logger.info(
                "Importing the fully regionalized version of ReCiPe 2016 v1.03 (H) for ecoinvent 3.10."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v310.dd7e66b1994d898394e3acfbed8eef83.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

        elif lcia_method == "ReCiPe 2016 v1.03 (H)" and self.ecoinvent_version == "3.9":
            self.logger.info(
                "Importing the fully regionalized version of ReCiPe 2016 v1.03 (H) for ecoinvent 3.9."
            )

            with as_file(files('regioinvent').joinpath(
                    "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v39.d03db1f1699b4f0b4d72626e52a40647.bw2package")
            ) as file_path:
                bw2.BW2Package.import_file(file_path)

    def regionalize_ecoinvent_with_trade(
        self, trade_database_path, regioinvent_database_name, cutoff
    ):
        """
        Function runs all the necessary sub-functions to incorporate trade data within ecoinvent supply chains
        descriptions
        :param trade_database_path: [str] the path to the trade database
        :param regioinvent_database_name: [str] the name to be given to the generated regioinvent database in brightway2
        :param cutoff: [float] the amount (between 0 and 1) after which exports/imports values of countries will be aggregated
                        into a Rest-of-theWorld aggregate.
        :return:
        """

        self.trade_conn = sqlite3.connect(trade_database_path)
        self.regioinvent_database_name = regioinvent_database_name
        self.cutoff = cutoff

        if cutoff > 0.99 or cutoff < 0:
            raise KeyError("cutoff must be between 0 and 0.99")

        if self.name_ei_with_regionalized_biosphere not in bw2.databases:
            raise KeyError(
                "You need to run the function spatialize_my_ecoinvent() first."
            )

        if not self.ei_wurst:
            self.ei_wurst = wurst.extract_brightway2_databases(
                self.name_ei_with_regionalized_biosphere, add_identifiers=True
            )
        if not self.ei_in_dict:
            self.ei_in_dict = {
                (i["reference product"], i["location"], i["name"]): i
                for i in self.ei_wurst
            }

        self.format_trade_data()
        self.first_order_regionalization()
        self.create_consumption_markets()
        self.second_order_regionalization()
        self.spatialize_elem_flows()
        self.write_regioinvent_to_database()
        self.connect_ecoinvent_to_regioinvent()

    # TODO we use this function for showing the influence of spatialization for the article, after that, remove it
    def create_ecoinvent_copy_without_regionalized_biosphere_flows(self):
        """
        In case the user does not want to regionalize biosphere flows, we still need a copy of ecoinvent to be able to
        regionalize it later on. The goal is to always keep a "pristine" ecoinvent version.
        """

        # change the database name everywhere
        for pr in self.ei_wurst:
            pr["database"] = self.name_ei_with_regionalized_biosphere
            for exc in pr["exchanges"]:
                if exc["type"] in ["technosphere", "production"]:
                    exc["input"] = (
                        self.name_ei_with_regionalized_biosphere,
                        exc["code"],
                    )
                    exc["database"] = self.name_ei_with_regionalized_biosphere

        # add input key to each exchange
        for pr in self.ei_wurst:
            for exc in pr["exchanges"]:
                try:
                    exc["input"]
                except KeyError:
                    exc["input"] = (exc["database"], exc["code"])

        # modify structure of data from wurst to bw2
        self.ei_regio_data = {(i["database"], i["code"]): i for i in self.ei_wurst}

        # recreate inputs in edges (exchanges)
        for pr in self.ei_regio_data:
            for exc in self.ei_regio_data[pr]["exchanges"]:
                try:
                    exc["input"]
                except KeyError:
                    exc["input"] = (exc["database"], exc["code"])
        # wurst creates empty categories for activities, this creates an issue when you try to write the bw2 database
        for pr in self.ei_regio_data:
            try:
                del self.ei_regio_data[pr]["categories"]
            except KeyError:
                pass
        # same with parameters
        for pr in self.ei_regio_data:
            try:
                del self.ei_regio_data[pr]["parameters"]
            except KeyError:
                pass

        # write ecoinvent-regionalized database
        bw2.Database(self.name_ei_with_regionalized_biosphere).write(self.ei_regio_data)

    def format_trade_data(self):
        """
        Function extracts and formats the export/import and domestic production data from the trade database
        :return: self.production_data / self.consumption_data
        """

        self.logger.info("Extracting and formatting trade data...")

        # load import data corrected for re-exports
        import_data = pd.read_sql("SELECT * FROM [Import data]", self.trade_conn).drop(
            "source", axis=1
        )

        # load export data (that's actually net exports, as in exports - imports)
        net_exports_data = pd.read_sql(
            "SELECT * FROM [Export data]", self.trade_conn
        ).drop("source", axis=1)

        # load domestic production
        self.domestic_production = pd.read_sql(
            "SELECT * FROM [Domestic production data]", self.trade_conn
        )

        # concatenate import and domestic data into consumption data
        self.consumption_data = pd.concat(
            [import_data, self.domestic_production.drop("source", axis=1)]
        )

        # concatenate net exports and domestic data into production data
        self.production_data = pd.concat(
            [
                net_exports_data,
                self.domestic_production.drop(["source", "importer"], axis=1),
            ]
        )
        self.production_data = (
            self.production_data.groupby(["cmdCode", "refYear", "exporter"])
            .sum()
            .reset_index()
        )

    def first_order_regionalization(self):
        """
        Function to regionalized the key inputs of each process: electricity, municipal solid waste and heat.
        :return: self.regioinvent_in_wurst with new regionalized processes
        """

        self.logger.info(
            "Regionalizing main inputs of internationally-traded products of ecoinvent..."
        )

        # -----------------------------------------------------------------------------------------------------------
        # first, we regionalize internationally-traded products, these require the creation of markets and are selected
        # based on national production volumes
        for product in tqdm(self.eco_to_hs_class, leave=True):
            # filter commodity code from production_data
            cmd_prod_data = self.production_data[
                self.production_data.cmdCode.isin([self.eco_to_hs_class[product]])
            ].copy("deep")
            # calculate the average production volume over the available years for each country
            cmd_prod_data = cmd_prod_data.groupby("exporter").agg(
                {"quantity (t)": "mean"}
            )
            producers = (
                cmd_prod_data.loc[:, "quantity (t)"]
                / cmd_prod_data.loc[:, "quantity (t)"].sum()
            ).sort_values(ascending=False)
            # only keep the countries representing XX% of global production of the product and create a RoW from that
            limit = (
                producers.index.get_loc(
                    producers[producers.cumsum() > self.cutoff].index[0]
                )
                + 1
            )
            remainder = producers.iloc[limit:].sum()
            producers = producers.iloc[:limit]
            if "RoW" in producers.index:
                producers.loc["RoW"] += remainder
            else:
                producers.loc["RoW"] = remainder

            # register the information about created geographies for each product
            self.created_geographies[product] = [i for i in producers.index]

            # identify the processes producing the product
            filter_processes = ws.get_many(
                self.ei_wurst,
                ws.equals("reference product", product),
                ws.exclude(ws.contains("name", "market for")),
                ws.exclude(ws.contains("name", "market group for")),
                ws.exclude(ws.contains("name", "generic market")),
                ws.exclude(ws.contains("name", "import from")),
            )
            # there can be multiple technologies to produce the same product, register all possibilities
            available_geographies = []
            available_technologies = []
            for dataset in filter_processes:
                available_geographies.append(dataset["location"])
                available_technologies.append(dataset["name"])
            # extract each available geography processes of ecoinvent, per technology of production
            possibilities = {tech: [] for tech in available_technologies}
            for i, geo in enumerate(available_geographies):
                possibilities[available_technologies[i]].append(geo)

            # determine the market share of each technology that produces the product, also determine the transportation
            self.transportation_modes[product] = {}
            self.distribution_technologies[product] = {
                tech: 0 for tech in available_technologies
            }
            market_processes = ws.get_many(
                self.ei_wurst,
                ws.equals("reference product", product),
                ws.either(
                    ws.contains("name", "market for"),
                    ws.contains("name", "market group for"),
                ),
            )
            number_of_markets = 0
            for ds in market_processes:
                number_of_markets += 1
                for exc in ds["exchanges"]:
                    if exc["product"] == product:
                        if exc["name"] in possibilities.keys():
                            self.distribution_technologies[product][exc["name"]] += exc[
                                "amount"
                            ]
                    if (
                            ("transport" in exc["name"])
                            & ("ton kilometer" == exc["unit"])
                            & ("market for" in exc["name"] or "market group for" in exc["name"])
                    ):
                        self.transportation_modes[product][exc["code"]] = exc["amount"]
            # average the technology market share
            sum_ = sum(self.distribution_technologies[product].values())
            if sum_ != 0:
                self.distribution_technologies[product] = {
                    k: v / sum_
                    for k, v in self.distribution_technologies[product].items()
                }
            else:
                self.distribution_technologies[product] = {
                    k: 1 / len(self.distribution_technologies[product])
                    for k, v in self.distribution_technologies[product].items()
                }
            # average the transportation modes
            if number_of_markets > 1:
                self.transportation_modes[product] = {
                    k: v / number_of_markets
                    for k, v in self.transportation_modes[product].items()
                }

            # create the global production market process within regioinvent
            global_market_activity = copy.deepcopy(dataset)

            # rename activity
            global_market_activity["name"] = f"""production market for {product}"""

            # add a comment
            try:
                source = (
                    self.domestic_production.loc[
                        self.domestic_production.cmdCode
                        == self.eco_to_hs_class[product],
                        "source",
                    ]
                    .iloc[0]
                    .split(" - ")[0]
                )
            # if IndexError -> product is only consumed domestically and not exported according to exiobase
            except IndexError:
                source = "EXIOBASE"
            global_market_activity["comment"] = (
                f"""This process represents the global production market for {product}. The shares come from export data from the BACI database for the commodity {self.eco_to_hs_class[product]}. Data from BACI is already in physical units. An average of the 5 last years of export trade available data is taken (in general from 2018 to 2022). Domestic production was extracted/estimated from {source}. Countries are taken until {self.cutoff*100}% of the global production amounts are covered. The rest of the data is aggregated in a RoW (Rest-of-the-World) region."""
            )

            # location will be global (it's a global market)
            global_market_activity["location"] = "GLO"

            # new code needed
            global_market_activity["code"] = uuid.uuid4().hex

            # change database
            global_market_activity["database"] = self.regioinvent_database_name

            # reset exchanges with only the production exchange
            global_market_activity["exchanges"] = [
                {
                    "amount": 1.0,
                    "type": "production",
                    "product": global_market_activity["reference product"],
                    "name": global_market_activity["name"],
                    "unit": global_market_activity["unit"],
                    "location": global_market_activity["location"],
                    "database": self.regioinvent_database_name,
                    "code": global_market_activity["code"],
                    "input": (
                        global_market_activity["database"],
                        global_market_activity["code"],
                    ),
                    "output": (
                        global_market_activity["database"],
                        global_market_activity["code"],
                    ),
                }
            ]
            # store unit of the product, need it later on
            self.unit[product] = global_market_activity["unit"]

            def copy_process(product, activity, region, prod_country):
                """
                Fonction that copies a process from ecoinvent
                :param product: [str] name of the reference product
                :param activity: [str] name of the activity
                :param region: [str] name of the location of the original ecoinvent process
                :param prod_country: [str] name of the location of the created regioinvent process
                :return: a copied and modified process of ecoinvent
                """
                # filter the process to-be-copied
                process = ws.get_one(
                    self.ei_wurst,
                    ws.equals("reference product", product),
                    ws.equals("name", activity),
                    ws.equals("location", region),
                    ws.equals("database", self.name_ei_with_regionalized_biosphere),
                    ws.exclude(ws.contains("name", "market for")),
                    ws.exclude(ws.contains("name", "market group for")),
                    ws.exclude(ws.contains("name", "generic market")),
                    ws.exclude(ws.contains("name", "import from")),
                )
                regio_process = copy.deepcopy(process)
                # change location
                regio_process["location"] = prod_country
                # change code
                regio_process["code"] = uuid.uuid4().hex
                # change database
                regio_process["database"] = self.regioinvent_database_name
                # add comment
                regio_process["comment"] = (
                    f"""This process is a regionalized adaptation of the following process of the ecoinvent database: {activity} | {product} | {region}. No amount values were modified in the regionalization process, only the origin of the flows."""
                )
                # update production exchange
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "code"
                ] = regio_process["code"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "database"
                ] = regio_process["database"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "location"
                ] = regio_process["location"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "input"
                ] = (regio_process["database"], regio_process["code"])
                # put the regionalized process' share into the global production market
                global_market_activity["exchanges"].append(
                    {
                        "amount": producers.loc[prod_country]
                        * self.distribution_technologies[product][activity],
                        "type": "technosphere",
                        "name": regio_process["name"],
                        "product": regio_process["reference product"],
                        "unit": regio_process["unit"],
                        "location": prod_country,
                        "database": self.regioinvent_database_name,
                        "code": global_market_activity["code"],
                        "input": (regio_process["database"], regio_process["code"]),
                        "output": (
                            global_market_activity["database"],
                            global_market_activity["code"],
                        ),
                    }
                )
                return regio_process

            # loop through technologies and producers
            for technology in possibilities.keys():
                for producer in producers.index:
                    # reset regio_process variable
                    regio_process = None
                    # if the producing country is available in the geographies of the ecoinvent production technologies
                    if producer in possibilities[technology] and producer not in [
                        "RoW"
                    ]:
                        regio_process = copy_process(
                            product, technology, producer, producer
                        )
                    # if a region associated with producing country is available in the geographies of the ecoinvent production technologies
                    elif producer in self.country_to_ecoinvent_regions:
                        for potential_region in self.country_to_ecoinvent_regions[
                            producer
                        ]:
                            if potential_region in possibilities[technology]:
                                regio_process = copy_process(
                                    product, technology, potential_region, producer
                                )
                    # otherwise, take either RoW, GLO or a random available geography
                    if not regio_process:
                        if "RoW" in possibilities[technology]:
                            regio_process = copy_process(
                                product, technology, "RoW", producer
                            )
                        elif "GLO" in possibilities[technology]:
                            regio_process = copy_process(
                                product, technology, "GLO", producer
                            )
                        else:
                            if possibilities[technology]:
                                # if no RoW/GLO processes available, take the first available geography by default...
                                regio_process = copy_process(
                                    product,
                                    technology,
                                    possibilities[technology][0],
                                    producer,
                                )
                                self.assigned_random_geography.append(
                                    [product, technology, producer]
                                )

                    # for each input, we test the presence of said inputs and regionalize that input
                    # testing the presence allows to save time if the input in question is just not used by the process
                    if regio_process:
                        # aluminium specific electricity input
                        if self.test_input_presence(
                            regio_process, "electricity", extra="aluminium/electricity"
                        ):
                            regio_process = self.change_aluminium_electricity(
                                regio_process, producer
                            )
                        # cobalt specific electricity input
                        elif self.test_input_presence(
                            regio_process, "electricity", extra="cobalt/electricity"
                        ):
                            regio_process = self.change_cobalt_electricity(
                                regio_process
                            )
                        # normal electricity input
                        elif self.test_input_presence(
                            regio_process, "electricity", extra="voltage"
                        ):
                            regio_process = self.change_electricity(
                                regio_process, producer
                            )
                        # municipal solid waste input
                        if self.test_input_presence(
                            regio_process, "municipal solid waste"
                        ):
                            regio_process = self.change_waste(regio_process, producer)
                        # heat, district or industrial, natural gas input
                        if self.test_input_presence(
                            regio_process, "heat, district or industrial, natural gas"
                        ):
                            regio_process = self.change_heat(
                                regio_process,
                                producer,
                                "heat, district or industrial, natural gas",
                            )
                        # heat, district or industrial, other than natural gas input
                        if self.test_input_presence(
                            regio_process,
                            "heat, district or industrial, other than natural gas",
                        ):
                            regio_process = self.change_heat(
                                regio_process,
                                producer,
                                "heat, district or industrial, other than natural gas",
                            )
                        # heat, central or small-scale, other than natural gas input
                        if self.test_input_presence(
                            regio_process,
                            "heat, central or small-scale, other than natural gas",
                        ):
                            regio_process = self.change_heat(
                                regio_process,
                                producer,
                                "heat, central or small-scale, other than natural gas",
                            )
                    # register the regionalized process within the wurst database
                    if regio_process:
                        self.regioinvent_in_wurst.append(regio_process)

            # add transportation to production market
            for transportation_mode in self.transportation_modes[product]:
                global_market_activity["exchanges"].append(
                    {
                        "amount": self.transportation_modes[product][
                            transportation_mode
                        ],
                        "type": "technosphere",
                        "database": self.name_ei_with_regionalized_biosphere,
                        "code": transportation_mode,
                        "product": bw2.Database(
                            self.name_ei_with_regionalized_biosphere
                        )
                        .get(transportation_mode)
                        .as_dict()["reference product"],
                        "input": (
                            self.name_ei_with_regionalized_biosphere,
                            transportation_mode,
                        ),
                    }
                )
            # and register the production market in the wurst database
            self.regioinvent_in_wurst.append(global_market_activity)

        # -----------------------------------------------------------------------------------------------------------
        # in a second time, we regionalize the most relevant other products, see doc/ to see how we selected those
        with as_file(files('regioinvent').joinpath(
                f"data/Regionalization/ei{self.ecoinvent_version}/relevant_non_traded_products.json")) as file_path:
            with open(file_path, "r") as f:
                relevant_non_traded_products = json.load(f)

        # get all the geographies of regioinvent
        with as_file(files('regioinvent').joinpath(
                f"data/Spatialization_of_elementary_flows/ei{self.ecoinvent_version}/geographies_of_regioinvent.json")) as file_path:
            with open(file_path, "r") as f:
                geographies_needed = json.load(f)

        self.logger.info(
            "Regionalizing main inputs of non-internationally traded processes of ecoinvent..."
        )
        for product in tqdm(relevant_non_traded_products, leave=True):
            filter_processes = ws.get_many(
                self.ei_wurst,
                ws.equals("reference product", product),
                ws.exclude(ws.contains("name", "market for")),
                ws.exclude(ws.contains("name", "market group for")),
                ws.exclude(ws.contains("name", "generic market")),
                ws.exclude(ws.contains("name", "import from")),
            )

            # there can be multiple technologies to produce the same product, register all possibilities
            available_geographies = []
            available_technologies = []
            for dataset in filter_processes:
                available_geographies.append(dataset["location"])
                available_technologies.append(dataset["name"])
            # extract each available geography processes of ecoinvent, per technology of production
            possibilities = {tech: [] for tech in available_technologies}
            for i, geo in enumerate(available_geographies):
                possibilities[available_technologies[i]].append(geo)

            def copy_process(product, activity, region, prod_country):
                """
                Fonction that copies a process from ecoinvent
                :param product: [str] name of the reference product
                :param activity: [str] name of the activity
                :param region: [str] name of the location of the original ecoinvent process
                :param prod_country: [str] name of the location of the created regioinvent process
                :return: a copied and modified process of ecoinvent
                """
                # filter the process to-be-copied
                process = ws.get_one(
                    self.ei_wurst,
                    ws.equals("reference product", product),
                    ws.equals("name", activity),
                    ws.equals("location", region),
                    ws.equals("database", self.name_ei_with_regionalized_biosphere),
                    ws.exclude(ws.contains("name", "market for")),
                    ws.exclude(ws.contains("name", "market group for")),
                    ws.exclude(ws.contains("name", "generic market")),
                    ws.exclude(ws.contains("name", "import from")),
                )
                regio_process = copy.deepcopy(process)
                # change location
                regio_process["location"] = prod_country
                # change code
                regio_process["code"] = uuid.uuid4().hex
                # change database
                regio_process["database"] = self.regioinvent_database_name
                # add comment
                regio_process["comment"] = (
                    f"""This process is a regionalized adaptation of the following process of the ecoinvent database: {activity} | {product} | {region}. No amount values were modified in the regionalization process, only the origin of the flows."""
                )
                # update production exchange
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "code"
                ] = regio_process["code"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "database"
                ] = regio_process["database"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "location"
                ] = regio_process["location"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "input"
                ] = (regio_process["database"], regio_process["code"])
                return regio_process

            def copy_market(product, region, prod_country):
                """
                Fonction that copies a market process from ecoinvent
                :param product: [str] name of the reference product
                :param region: [str] name of the location of the original ecoinvent process
                :param prod_country: [str] name of the location of the created regioinvent process
                :return: a copied and modified market process of ecoinvent
                """

                # filter the process to-be-copied
                market_process = ws.get_one(
                    self.ei_wurst,
                    ws.equals("reference product", product),
                    ws.equals("location", region),
                    ws.equals("database", self.name_ei_with_regionalized_biosphere),
                    ws.either(
                        ws.contains("name", "market for"),
                        ws.contains("name", "market group for"),
                    ),
                    ws.exclude(ws.contains("name", "generic market")),
                    ws.exclude(ws.contains("name", "to market")),
                )

                regio_process = copy.deepcopy(market_process)
                # change location
                regio_process["location"] = prod_country
                # change code
                regio_process["code"] = uuid.uuid4().hex
                # change database
                regio_process["database"] = self.regioinvent_database_name
                # add comment
                regio_process["comment"] = (
                    f"""This process is a regionalized adaptation of the following process of the ecoinvent database: {regio_process['name']} | {product} | {region}. No amount values were modified in the regionalization process, only the origin of the flows."""
                )
                # we rename the activity because just having "market for..." is confusing
                regio_process["name"] = "technology mix for " + product
                # update production exchange
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "code"
                ] = regio_process["code"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "database"
                ] = regio_process["database"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "location"
                ] = regio_process["location"]
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "name"
                ] = ("technology mix for " + product)
                [i for i in regio_process["exchanges"] if i["type"] == "production"][0][
                    "input"
                ] = (regio_process["database"], regio_process["code"])
                return regio_process

            # loop through technologies
            for technology in possibilities.keys():
                # do not regionalize irrelevant processes
                if [product, technology] not in self.no_inputs_processes:
                    # loop through geos
                    for geo in geographies_needed:
                        # reset regio_process variable
                        regio_process = None
                        # if the producing country is available in the geographies of the ecoinvent production technologies
                        if geo in possibilities[technology] and geo not in ["RoW"]:
                            regio_process = copy_process(product, technology, geo, geo)
                        # if a region associated with producing country is available in the geographies of the ecoinvent production technologies
                        elif geo in self.country_to_ecoinvent_regions:
                            for potential_region in self.country_to_ecoinvent_regions[
                                geo
                            ]:
                                if potential_region in possibilities[technology]:
                                    regio_process = copy_process(
                                        product, technology, potential_region, geo
                                    )
                        # otherwise, take either RoW, GLO or a random available geography
                        if not regio_process:
                            if "RoW" in possibilities[technology]:
                                regio_process = copy_process(
                                    product, technology, "RoW", geo
                                )
                            elif "GLO" in possibilities[technology]:
                                regio_process = copy_process(
                                    product, technology, "GLO", geo
                                )
                            else:
                                if possibilities[technology]:
                                    # if no RoW/GLO processes available, take the first available geography by default...
                                    regio_process = copy_process(
                                        product,
                                        technology,
                                        possibilities[technology][0],
                                        geo,
                                    )
                                    self.assigned_random_geography.append(
                                        [product, technology, geo]
                                    )

                        # for each input, we test the presence of said inputs and regionalize that input
                        # testing the presence allows to save time if the input in question is just not used by the process
                        if regio_process:
                            # aluminium specific electricity input
                            if self.test_input_presence(
                                regio_process,
                                "electricity",
                                extra="aluminium/electricity",
                            ):
                                regio_process = self.change_aluminium_electricity(
                                    regio_process, geo
                                )
                            # cobalt specific electricity input
                            elif self.test_input_presence(
                                regio_process, "electricity", extra="cobalt/electricity"
                            ):
                                regio_process = self.change_cobalt_electricity(
                                    regio_process
                                )
                            # normal electricity input
                            elif self.test_input_presence(
                                regio_process, "electricity", extra="voltage"
                            ):
                                regio_process = self.change_electricity(
                                    regio_process, geo
                                )
                            # municipal solid waste input
                            if self.test_input_presence(
                                regio_process, "municipal solid waste"
                            ):
                                regio_process = self.change_waste(regio_process, geo)
                            # heat, district or industrial, natural gas input
                            if self.test_input_presence(
                                regio_process,
                                "heat, district or industrial, natural gas",
                            ):
                                regio_process = self.change_heat(
                                    regio_process,
                                    geo,
                                    "heat, district or industrial, natural gas",
                                )
                            # heat, district or industrial, other than natural gas input
                            if self.test_input_presence(
                                regio_process,
                                "heat, district or industrial, other than natural gas",
                            ):
                                regio_process = self.change_heat(
                                    regio_process,
                                    geo,
                                    "heat, district or industrial, other than natural gas",
                                )
                            # heat, central or small-scale, other than natural gas input
                            if self.test_input_presence(
                                regio_process,
                                "heat, central or small-scale, other than natural gas",
                            ):
                                regio_process = self.change_heat(
                                    regio_process,
                                    geo,
                                    "heat, central or small-scale, other than natural gas",
                                )
                        # register the regionalized process within the wurst database
                        if regio_process:
                            self.regioinvent_in_wurst.append(regio_process)

            # copy markets and rename them as technology mix
            for geo in geographies_needed:
                # check that this is not a market full or irrelevant products/processes
                if {
                    k: v
                    for k, v in possibilities.items()
                    if [product, k] not in self.no_inputs_processes
                }:
                    # reset regio_market variable
                    regio_market = None

                    # now we work on finding the technology mix to copy
                    if not regio_market:
                        # try to find the national technology mix from ecoinvent if it exists
                        try:
                            regio_market = copy_market(product, geo, geo)
                        except ws.NoResults:
                            if geo != "RoW":
                                # if it does not, try your luck with the regions the country belongs to
                                for (
                                    potential_region
                                ) in self.country_to_ecoinvent_regions[geo]:
                                    try:
                                        regio_market = copy_market(
                                            product, potential_region, geo
                                        )
                                    except ws.NoResults:
                                        pass
                        if not regio_market:
                            try:
                                # still no luck? let's go for RoW and GLO
                                regio_market = copy_market(product, "RoW", geo)
                            except ws.NoResults:
                                try:
                                    regio_market = copy_market(product, "GLO", geo)
                                except ws.NoResults:
                                    # waw really unlucky... well let's just take a random one then
                                    regio_market = copy_market(
                                        product, possibilities[technology][0], geo
                                    )
                                    self.assigned_random_geography.append(
                                        [product, "market for", geo]
                                    )
                    # register the regionalized technology mix within the wurst database
                    if regio_market:
                        self.regioinvent_in_wurst.append(regio_market)

    def create_consumption_markets(self):
        """
        Function creating consumption markets for each regionalized process
        :return:  self.regioinvent_in_wurst with new regionalized processes
        """

        self.logger.info(
            "Creating consumption markets for internationally-traded products..."
        )

        # change to dictionary to speed searching for info
        self.regioinvent_in_dict = {
            tech: []
            for tech in [
                (i["reference product"], i["location"])
                for i in self.regioinvent_in_wurst
            ]
        }
        # populate the empty dictionary
        for process in self.regioinvent_in_wurst:
            self.regioinvent_in_dict[
                (process["reference product"], process["location"])
            ].append({process["name"]: process})

        for product in tqdm(self.eco_to_hs_class, leave=True):
            # filter the product in self.consumption_data
            cmd_consumption_data = self.consumption_data[
                self.consumption_data.cmdCode == self.eco_to_hs_class[product]
            ].copy("deep")
            # calculate the average consumption volume for each country
            cmd_consumption_data = cmd_consumption_data.groupby(
                ["importer", "exporter"]
            ).agg({"quantity (t)": "mean"})
            # change to relative values
            consumers = (
                cmd_consumption_data.groupby(level=0).sum()
                / cmd_consumption_data.sum().sum()
            ).sort_values(by="quantity (t)", ascending=False)
            # only keep consumers till the user-defined cut-off of total consumption
            limit = (
                consumers.index.get_loc(
                    consumers[consumers.cumsum() > self.cutoff].dropna().index[0]
                )
                + 1
            )
            # aggregate the rest
            remainder = (
                cmd_consumption_data.loc[consumers.index[limit:]].groupby(level=1).sum()
            )
            cmd_consumption_data = cmd_consumption_data.loc[consumers.index[:limit]]
            # assign the aggregate to RoW location
            cmd_consumption_data = pd.concat(
                [cmd_consumption_data, pd.concat([remainder], keys=["RoW"])]
            )
            cmd_consumption_data.index = pd.MultiIndex.from_tuples(
                [i for i in cmd_consumption_data.index]
            )
            cmd_consumption_data = cmd_consumption_data.sort_index()

            # loop through each selected consumers of the commodity
            for consumer in cmd_consumption_data.index.levels[0]:
                # change to relative values
                cmd_consumption_data.loc[consumer, "quantity (t)"] = (
                    cmd_consumption_data.loc[consumer, "quantity (t)"]
                    / cmd_consumption_data.loc[consumer, "quantity (t)"].sum()
                ).values
                # we need to add the aggregate to potentially already existing RoW exchanges
                cmd_consumption_data = pd.concat(
                    [
                        cmd_consumption_data.drop("RoW", level=0),
                        pd.concat(
                            [cmd_consumption_data.loc["RoW"].groupby(level=0).sum()],
                            keys=["RoW"],
                        ),
                    ]
                )
                cmd_consumption_data = cmd_consumption_data.fillna(0)

                try:
                    source = (
                        self.domestic_production.loc[
                            self.domestic_production.cmdCode
                            == self.eco_to_hs_class[product],
                            "source",
                        ]
                        .iloc[0]
                        .split(" - ")[0]
                    )
                # if IndexError -> product is only consumed domestically and not exported according to exiobase
                except IndexError:
                    source = "EXIOBASE"

                # create the process information
                new_import_data = {
                    "name": "consumption market for " + product,
                    "reference product": product,
                    "location": consumer,
                    "type": "process",
                    "unit": self.unit[product],
                    "code": uuid.uuid4().hex,
                    "comment": f"""This process represents the consumption market of {product} in {consumer}. The shares were determined based on two aspects. The imports of the commodity {self.eco_to_hs_class[product]} taken from the BACI database (average over the years 2018, 2019, 2020, 2021, 2022). The domestic consumption data was extracted/estimated from {source}.""",
                    "database": self.regioinvent_database_name,
                    "exchanges": [],
                }

                # create the production exchange
                new_import_data["exchanges"].append(
                    {
                        "amount": 1,
                        "type": "production",
                        "input": (
                            self.regioinvent_database_name,
                            new_import_data["code"],
                        ),
                    }
                )
                # identify regionalized processes that were created in self.first_order_regionalization()
                available_trading_partners = self.created_geographies[product]
                # loop through the selected consumers
                for trading_partner in cmd_consumption_data.loc[consumer].index:
                    # check if a regionalized process exist for that consumer
                    if trading_partner in available_trading_partners:
                        # loop through available technologies to produce the commodity
                        for technology in self.distribution_technologies[product]:
                            # get the uuid
                            code = [
                                i
                                for i in self.regioinvent_in_dict[
                                    (product, trading_partner)
                                ]
                                if list(i.keys())[0] == technology
                            ][0][technology]["code"]
                            # get the share
                            share = self.distribution_technologies[product][technology]
                            # create the exchange
                            new_import_data["exchanges"].append(
                                {
                                    "amount": cmd_consumption_data.loc[
                                        (consumer, trading_partner), "quantity (t)"
                                    ]
                                    * share,
                                    "type": "technosphere",
                                    "input": (self.regioinvent_database_name, code),
                                    "name": product,
                                }
                            )
                    # if a regionalized process does not exist for consumer, take the RoW aggregate
                    else:
                        # loop through available technologies to produce the commodity
                        for technology in self.distribution_technologies[product]:
                            # get the uuid
                            code = [
                                i
                                for i in self.regioinvent_in_dict[(product, "RoW")]
                                if list(i.keys())[0] == technology
                            ][0][technology]["code"]
                            # get the share
                            share = self.distribution_technologies[product][technology]
                            # create the exchange
                            new_import_data["exchanges"].append(
                                {
                                    "amount": cmd_consumption_data.loc[
                                        (consumer, trading_partner), "quantity (t)"
                                    ]
                                    * share,
                                    "type": "technosphere",
                                    "input": (self.regioinvent_database_name, code),
                                    "name": product,
                                }
                            )
                # add transportation to consumption market
                for transportation_mode in self.transportation_modes[product]:
                    new_import_data["exchanges"].append(
                        {
                            "amount": self.transportation_modes[product][
                                transportation_mode
                            ],
                            "type": "technosphere",
                            "input": (
                                self.name_ei_with_regionalized_biosphere,
                                transportation_mode,
                            ),
                        }
                    )

                # check for duplicate input codes with different values (coming from RoW)
                duplicates = [
                    item
                    for item, count in collections.Counter(
                        [i["input"] for i in new_import_data["exchanges"]]
                    ).items()
                    if count > 1
                ]
                # add duplicates into one single flow
                for duplicate in duplicates:
                    total = sum(
                        [
                            i["amount"]
                            for i in new_import_data["exchanges"]
                            if i["input"] == duplicate
                        ]
                    )
                    new_import_data["exchanges"] = [
                        i
                        for i in new_import_data["exchanges"]
                        if i["input"] != duplicate
                    ] + [
                        {
                            "amount": total,
                            "name": product,
                            "type": "technosphere",
                            "input": duplicate,
                        }
                    ]
                # add to database in wurst
                self.regioinvent_in_wurst.append(new_import_data)

    def second_order_regionalization(self):
        """
        Function that links newly created consumption markets to inputs of the different processes of the regionalized
        ecoinvent database.
        :return:  self.regioinvent_in_wurst with new regionalized processes
        """

        self.logger.info("Link regioinvent processes to each other...")

        # as dictionaries to speed up searching for info
        consumption_markets_data = {
            (i["name"], i["location"]): i
            for i in self.regioinvent_in_wurst
            if "consumption market" in i["name"]
        }

        # store available processes of non-internationally traded commodities
        other_processes_data = collections.defaultdict(list)
        for i in self.regioinvent_in_wurst:
            if (
                "consumption market" not in i["name"]
                and "production market" not in i["name"]
                and i["reference product"] not in self.eco_to_hs_class
            ):
                key = (i["reference product"], i["location"])
                other_processes_data[key].append(i)

        regionalized_products = set(
            [i["reference product"] for i in self.regioinvent_in_wurst]
        )

        techno_mixes = {
            (i["name"], i["location"]): i["code"]
            for i in self.regioinvent_in_wurst
            if "technology mix" in i["name"]
        }

        # loop through created processes and link to internationally traded commodities
        for process in self.regioinvent_in_wurst:
            # only for internationally traded commodities
            if (
                "consumption market" not in process["name"]
                and "production market" not in process["name"]
                and "technology mix" not in process["name"]
                and process["reference product"] in self.eco_to_hs_class.keys()
            ):
                # loop through exchanges
                for exc in process["exchanges"]:
                    if (
                        exc["product"] in self.eco_to_hs_class.keys()
                        and exc["type"] == "technosphere"
                    ):
                        # then get the name of the created consumption market for that product
                        exc["name"] = "consumption market for " + exc["product"]
                        # and get its location (same as the process)
                        exc["location"] = process["location"]
                        # if the consumption market exists for the location of process
                        if (
                            "consumption market for " + exc["product"],
                            process["location"],
                        ) in consumption_markets_data.keys():
                            # change database
                            exc["database"] = consumption_markets_data[
                                (
                                    "consumption market for " + exc["product"],
                                    process["location"],
                                )
                            ]["database"]
                            # change code
                            exc["code"] = consumption_markets_data[
                                (
                                    "consumption market for " + exc["product"],
                                    process["location"],
                                )
                            ]["code"]
                        # if the consumption market does not exist for the location of process, use RoW
                        else:
                            # change database
                            exc["database"] = consumption_markets_data[
                                ("consumption market for " + exc["product"], "RoW")
                            ]["database"]
                            # change code
                            exc["code"] = consumption_markets_data[
                                ("consumption market for " + exc["product"], "RoW")
                            ]["code"]
                        exc["input"] = (exc["database"], exc["code"])
                    elif (
                        exc["product"] in regionalized_products
                        and exc["type"] == "technosphere"
                    ):
                        # connect to technology mix for the country
                        exc["name"] = "technology mix for " + exc["product"]
                        exc["location"] = process["location"]
                        exc["code"] = techno_mixes[
                            (
                                "technology mix for " + exc["product"],
                                process["location"],
                            )
                        ]
                        exc["database"] = self.regioinvent_database_name
                        exc["input"] = (exc["database"], exc["code"])
            elif "technology mix" in process["name"]:
                for exc in process["exchanges"]:
                    for i in range(
                        0,
                        len(
                            other_processes_data[(exc["product"], process["location"])]
                        ),
                    ):
                        # find correct technology for production
                        if (
                            other_processes_data[(exc["product"], process["location"])][
                                i
                            ]["name"]
                            == exc["name"]
                        ):
                            # change info
                            exc["code"] = other_processes_data[
                                (exc["product"], process["location"])
                            ][i]["code"]
                            exc["database"] = self.regioinvent_database_name
                            exc["location"] = process["location"]
                            exc["input"] = (exc["database"], exc["code"])

        # reduce the size of the database by culling processes unused by internationally traded commodities
        used_techno_mixes = []

        for process in self.regioinvent_in_wurst:
            if (
                "consumption market" not in process["name"]
                and "production market" not in process["name"]
                and process["reference product"] in self.eco_to_hs_class.keys()
            ):
                for exc in process["exchanges"]:
                    if "technology mix" in exc["name"]:
                        if (
                            exc["name"],
                            exc["product"],
                            exc["location"],
                        ) not in used_techno_mixes:
                            used_techno_mixes.append(
                                (exc["name"], exc["product"], exc["location"])
                            )
            # we want to make sure we always have the RoW technology mix for a default option
            if "technology mix" in process["name"] and "RoW" == process["location"]:
                if (
                    process["name"],
                    process["reference product"],
                    process["location"],
                ) not in used_techno_mixes:
                    used_techno_mixes.append(
                        (
                            process["name"],
                            process["reference product"],
                            process["location"],
                        )
                    )

        reduced_regioinvent = []
        for ds in self.regioinvent_in_wurst:
            if "technology mix" in ds["name"]:
                if (
                    ds["name"],
                    ds["reference product"],
                    ds["location"],
                ) in used_techno_mixes:
                    reduced_regioinvent.append(ds)
            else:
                reduced_regioinvent.append(ds)

        self.regioinvent_in_wurst = copy.copy(reduced_regioinvent)

        # redetermine available techno mixes, since we culled some of them
        techno_mixes = {
            (i["name"], i["location"]): i["code"]
            for i in self.regioinvent_in_wurst
            if "technology mix" in i["name"]
        }

        used_prod_processes = []
        for process in self.regioinvent_in_wurst:
            if "technology mix" in process["name"]:
                for exc in process["exchanges"]:
                    if (
                        exc["type"] == "technosphere"
                        and exc["product"] in regionalized_products
                        and exc["product"] not in self.eco_to_hs_class.keys()
                        and "technology mix" not in exc["name"]
                    ):
                        if (
                            exc["name"],
                            exc["product"],
                            exc["location"],
                        ) not in used_prod_processes:
                            used_prod_processes.append(
                                (exc["name"], exc["product"], exc["location"])
                            )

        even_more_reduced_regioinvent = []
        for ds in self.regioinvent_in_wurst:
            if (
                "technology mix" not in ds["name"]
                and "consumption market" not in ds["name"]
                and "production market" not in ds["name"]
                and ds["reference product"] not in self.eco_to_hs_class.keys()
            ):
                if (
                    ds["name"],
                    ds["reference product"],
                    ds["location"],
                ) in used_prod_processes:
                    even_more_reduced_regioinvent.append(ds)
            else:
                even_more_reduced_regioinvent.append(ds)

        self.regioinvent_in_wurst = copy.copy(even_more_reduced_regioinvent)

        # loop through created processes and link to non-internationally traded commodities
        for process in self.regioinvent_in_wurst:
            # only for internationally traded commodities
            if (
                "consumption market" not in process["name"]
                and "production market" not in process["name"]
                and "technology mix" not in process["name"]
                and process["reference product"] not in self.eco_to_hs_class.keys()
            ):
                # loop through exchanges
                for exc in process["exchanges"]:
                    if (
                        exc["product"] in self.eco_to_hs_class.keys()
                        and exc["type"] == "technosphere"
                    ):
                        # then get the name of the created consumption market for that product
                        exc["name"] = "consumption market for " + exc["product"]
                        # and get its location (same as the process)
                        exc["location"] = process["location"]
                        # if the consumption market exists for the location of process
                        if (
                            "consumption market for " + exc["product"],
                            process["location"],
                        ) in consumption_markets_data.keys():
                            # change database
                            exc["database"] = consumption_markets_data[
                                (
                                    "consumption market for " + exc["product"],
                                    process["location"],
                                )
                            ]["database"]
                            # change code
                            exc["code"] = consumption_markets_data[
                                (
                                    "consumption market for " + exc["product"],
                                    process["location"],
                                )
                            ]["code"]
                        # if the consumption market does not exist for the location of process, use RoW
                        else:
                            # change database
                            exc["database"] = consumption_markets_data[
                                ("consumption market for " + exc["product"], "RoW")
                            ]["database"]
                            # change code
                            exc["code"] = consumption_markets_data[
                                ("consumption market for " + exc["product"], "RoW")
                            ]["code"]
                        exc["input"] = (exc["database"], exc["code"])
                    elif (
                        exc["product"] in regionalized_products
                        and exc["type"] == "technosphere"
                    ):
                        # connect to technology mix for the country
                        try:
                            exc["code"] = techno_mixes[
                                (
                                    "technology mix for " + exc["product"],
                                    process["location"],
                                )
                            ]
                            exc["name"] = "technology mix for " + exc["product"]
                            exc["location"] = process["location"]
                            exc["database"] = self.regioinvent_database_name
                            exc["input"] = (exc["database"], exc["code"])
                        except KeyError:
                            pass

        self.logger.info("Aggregate duplicates together...")

        # aggregating duplicate inputs (e.g., multiple consumption markets RoW callouts)
        for process in self.regioinvent_in_wurst:
            for exc in process["exchanges"]:
                try:
                    exc["input"]
                except KeyError:
                    exc["input"] = (exc["database"], exc["code"])

            duplicates = [
                item
                for item, count in collections.Counter(
                    [i["input"] for i in process["exchanges"]]
                ).items()
                if count > 1
            ]

            for duplicate in duplicates:
                total = sum(
                    [
                        i["amount"]
                        for i in process["exchanges"]
                        if i["input"] == duplicate
                    ]
                )
                name = [
                    i["name"] for i in process["exchanges"] if i["input"] == duplicate
                ][0]
                product = [
                    i["product"]
                    for i in process["exchanges"]
                    if i["input"] == duplicate
                ][0]
                database = [
                    i["database"]
                    for i in process["exchanges"]
                    if i["input"] == duplicate
                ][0]
                location = [
                    i["location"]
                    for i in process["exchanges"]
                    if i["input"] == duplicate
                ][0]

                process["exchanges"] = [
                    i for i in process["exchanges"] if i["input"] != duplicate
                ] + [
                    {
                        "amount": total,
                        "type": "technosphere",
                        "input": duplicate,
                        "name": name,
                        "database": database,
                        "product": product,
                        "location": location,
                    }
                ]

    def spatialize_elem_flows(self):
        """
        Function spatializes the elementary flows of the regioinvent processes to the location of process.
        """

        self.logger.info(
            "Regionalizing the elementary flows of the regioinvent database..."
        )

        # the list of all spatialized flows
        with as_file(files('regioinvent').joinpath(
                f"data/Spatialization_of_elementary_flows/ei{self.ecoinvent_version}/spatialized_elementary_flows.json")) as file_path:
            with open(file_path, "r") as f:
                spatialized_elem_flows = json.load(f)

        # a dictionary with all the associated uuids of the spatialized flows
        regionalized_flows = {
            (i.as_dict()["name"], i.as_dict()["categories"]): i.as_dict()["code"]
            for i in bw2.Database(self.name_spatialized_biosphere)
        }

        # loop through regioinvent processes
        for process in self.regioinvent_in_wurst:
            # loop through exchanges of process
            for exc in process["exchanges"]:
                # if the exchange is a biosphere exchange
                if exc["type"] == "biosphere":
                    # strip the potential region from the spatialized flow name and check if it's a spatialized flow
                    # if region had a comma in the name it would be a problem, but it's not happening as the geographies
                    # used for copies in regioinvent don't contain commas
                    if (
                        ", ".join(exc["name"].split(", ")[:-1])
                        in spatialized_elem_flows.keys()
                    ):
                        base_name_flow = ", ".join(exc["name"].split(", ")[:-1])
                        # check that the flow is spatialized for the compartment
                        if (
                            exc["categories"][0]
                            in spatialized_elem_flows[base_name_flow]
                        ):
                            # get code of spatialized flow for process['location']
                            exc["code"] = regionalized_flows[
                                (
                                    base_name_flow + ", " + process["location"],
                                    exc["categories"],
                                )
                            ]
                            # change database name of exchange
                            exc["database"] = self.name_spatialized_biosphere
                            # change name of exchange
                            exc["name"] = base_name_flow + ", " + process["location"]
                            # change input key of exchange
                            exc["input"] = (exc["database"], exc["code"])

    def write_regioinvent_to_database(self):
        """
        Function write a dictionary of datasets to the brightway2 SQL database
        """

        self.logger.info("Write regioinvent database to brightway...")

        # change regioinvent data from wurst to bw2 structure
        regioinvent_data = {
            (i["database"], i["code"]): i for i in self.regioinvent_in_wurst
        }

        # recreate inputs in edges (exchanges)
        for pr in regioinvent_data:
            for exc in regioinvent_data[pr]["exchanges"]:
                try:
                    exc["input"]
                except KeyError:
                    exc["input"] = (exc["database"], exc["code"])
        # wurst creates empty categories for activities, this creates an issue when you try to write the bw2 database
        for pr in regioinvent_data:
            try:
                del regioinvent_data[pr]["categories"]
            except KeyError:
                pass

        # write regioinvent database in brightway2
        bw2.Database(self.regioinvent_database_name).write(regioinvent_data)

    def connect_ecoinvent_to_regioinvent(self):
        """
        Now that regioinvent exists, we can make ecoinvent use regioinvent processes to further deepen the
        regionalization. Only countries and sub-countries are connected to regioinvent, simply because in regioinvent
        we do not have consumption mixes for the different regions of ecoinvent (e.g., RER, RAS, etc.).
        However, Swiss processes are not affected, as ecoinvent was already tailored for the Swiss case.
        I am not sure regioinvent would bring more precision in that specific case.
        """

        # Here we are directly manipulating (through bw2) the already-written ecoinvent database [self.name_ei_with_regionalized_biosphere]
        self.logger.info("Connecting ecoinvent to regioinvent processes...")

        # as dictionary to speed searching for information
        consumption_markets_data = {
            (i["name"], i["location"]): i
            for i in self.regioinvent_in_wurst
            if "consumption market" in i["name"]
        }
        regionalized_products = set(
            [i["reference product"] for i in self.regioinvent_in_wurst]
        )
        techno_mixes = {
            (i["name"], i["location"]): i["code"]
            for i in self.regioinvent_in_wurst
            if "technology mix" in i["name"]
        }

        for process in bw2.Database(self.name_ei_with_regionalized_biosphere):
            # find country/sub-country locations for process, we ignore regions
            location = None
            # for countries (e.g., CA)
            if (
                process.as_dict()["location"]
                in self.country_to_ecoinvent_regions.keys()
            ):
                location = process.as_dict()["location"]
            # for sub-countries (e.g., CA-QC)
            elif (
                process.as_dict()["location"].split("-")[0]
                in self.country_to_ecoinvent_regions.keys()
            ):
                location = process.as_dict()["location"].split("-")[0]
            # check if location is not None and not Switzerland
            if location and location != "CH":
                # loop through technosphere exchanges
                for exc in process.technosphere():
                    # if the product of the exchange is among the internationally traded commodities
                    if exc.as_dict()["product"] in self.eco_to_hs_class.keys():
                        # get the name of the corresponding consumtion market
                        exc.as_dict()["name"] = (
                            "consumption market for " + exc.as_dict()["product"]
                        )
                        # get the location of the process
                        exc.as_dict()["location"] = location
                        # if the consumption market exists for the process location
                        if (
                            "consumption market for " + exc.as_dict()["product"],
                            location,
                        ) in consumption_markets_data.keys():
                            exc.as_dict()["database"] = consumption_markets_data[
                                (
                                    "consumption market for "
                                    + exc.as_dict()["product"],
                                    location,
                                )
                            ]["database"]
                            exc.as_dict()["code"] = consumption_markets_data[
                                (
                                    "consumption market for "
                                    + exc.as_dict()["product"],
                                    location,
                                )
                            ]["code"]
                        # if the consumption market does not exist for the process location, take RoW
                        else:
                            exc.as_dict()["database"] = consumption_markets_data[
                                (
                                    "consumption market for "
                                    + exc.as_dict()["product"],
                                    "RoW",
                                )
                            ]["database"]
                            exc.as_dict()["code"] = consumption_markets_data[
                                (
                                    "consumption market for "
                                    + exc.as_dict()["product"],
                                    "RoW",
                                )
                            ]["code"]
                        exc.as_dict()["input"] = (
                            exc.as_dict()["database"],
                            exc.as_dict()["code"],
                        )
                        exc.save()
                    # if the product of the exchange is among the non-international traded commodities
                    elif (
                        exc.as_dict()["product"] in regionalized_products
                        and exc.as_dict()["product"] not in self.eco_to_hs_class.keys()
                    ):
                        try:
                            # if techno mix for location exists
                            exc.as_dict()["code"] = techno_mixes[
                                (
                                    "technology mix for " + exc.as_dict()["product"],
                                    location,
                                )
                            ]
                            exc.as_dict()["database"] = self.regioinvent_database_name
                            exc.as_dict()["name"] = (
                                "technology mix for " + exc.as_dict()["product"]
                            )
                            exc.as_dict()["location"] = location
                            exc.as_dict()["input"] = (
                                exc.as_dict()["database"],
                                exc.as_dict()["code"],
                            )
                            exc.save()
                        except KeyError:
                            # if not, link to RoW
                            exc.as_dict()["code"] = techno_mixes[
                                (
                                    "technology mix for " + exc.as_dict()["product"],
                                    "RoW",
                                )
                            ]
                            exc.as_dict()["database"] = self.regioinvent_database_name
                            exc.as_dict()["name"] = (
                                "technology mix for " + exc.as_dict()["product"]
                            )
                            exc.as_dict()["location"] = "RoW"
                            exc.as_dict()["input"] = (
                                exc.as_dict()["database"],
                                exc.as_dict()["code"],
                            )
                            exc.save()

        # aggregating duplicate inputs (e.g., multiple consumption markets RoW callouts)
        for process in bw2.Database(self.name_ei_with_regionalized_biosphere):
            duplicates = [
                item
                for item, count in collections.Counter(
                    [
                        (
                            i.as_dict()["input"],
                            i.as_dict()["name"],
                            i.as_dict()["product"],
                            i.as_dict()["location"],
                            i.as_dict()["database"],
                            i.as_dict()["code"],
                        )
                        for i in process.technosphere()
                    ]
                ).items()
                if count > 1
            ]

            for duplicate in duplicates:
                total = sum(
                    [
                        i["amount"]
                        for i in process.technosphere()
                        if i["input"] == duplicate[0]
                    ]
                )
                [
                    i.delete()
                    for i in process.technosphere()
                    if i["input"] == duplicate[0]
                ]
                new_exc = process.new_exchange(
                    amount=total,
                    type="technosphere",
                    input=duplicate[0],
                    name=duplicate[1],
                    product=duplicate[2],
                    location=duplicate[3],
                    database=duplicate[4],
                    code=duplicate[5],
                )
                new_exc.save()

        # we also change production processes of ecoinvent for regionalized production processes of regioinvent
        regio_dict = {
            (
                i.as_dict()["reference product"],
                i.as_dict()["name"],
                i.as_dict()["location"],
            ): i
            for i in bw2.Database(self.regioinvent_database_name)
        }

        for process in bw2.Database(self.name_ei_with_regionalized_biosphere):
            for exc in process.technosphere():
                if exc.as_dict()["product"] in self.eco_to_hs_class.keys():
                    # same thing, we don't touch Swiss processes
                    if exc.as_dict()["location"] not in ["RoW", "CH"]:
                        try:
                            exc.as_dict()["database"] = self.regioinvent_database_name
                            exc.as_dict()["code"] = regio_dict[
                                (
                                    exc.as_dict()["product"],
                                    exc.as_dict()["name"],
                                    exc.as_dict()["location"],
                                )
                            ].as_dict()["code"]
                            exc.as_dict()["input"] = (
                                exc.as_dict()["database"],
                                exc.as_dict()["code"],
                            )
                        except KeyError:
                            pass

    # -------------------------------------------Supporting functions---------------------------------------------------

    def change_electricity(self, process, export_country):
        """
        This function changes an electricity input of a process by the national (or regional) electricity mix
        :param process: the copy of the regionalized process as a dictionnary
        :param export_country: the country of the newly regionalized process
        """
        # identify electricity related exchanges
        electricity_product_names = list(
            set(
                [
                    i["product"]
                    for i in process["exchanges"]
                    if "electricity" in i["name"]
                    and "aluminium" not in i["name"]
                    and "cobalt" not in i["name"]
                    and "voltage" in i["name"]
                    and "network" not in i["name"]
                ]
            )
        )
        # loop through the identified process
        for electricity_product_name in electricity_product_names:
            unit_name = list(
                set(
                    [
                        i["unit"]
                        for i in process["exchanges"]
                        if "electricity" in i["name"]
                        and "aluminium" not in i["name"]
                        and "cobalt" not in i["name"]
                        and "voltage" in i["name"]
                        and "network" not in i["name"]
                    ]
                )
            )
            # if somehow different units used for electricity flows -> problem
            assert len(unit_name) == 1
            unit_name = unit_name[0]
            # sum quantity of all electricity exchanges
            qty_of_electricity = sum(
                [
                    i["amount"]
                    for i in process["exchanges"]
                    if electricity_product_name == i["product"]
                ]
            )

            # remove electricity flows from non-appropriated geography
            for exc in process["exchanges"][:]:
                if (
                    electricity_product_name == exc["product"]
                    and "aluminium" not in exc["name"]
                    and "cobalt" not in exc["name"]
                    and "voltage" in exc["name"]
                    and "network" not in exc["name"]
                ):
                    process["exchanges"].remove(exc)

            electricity_region = None
            # if the country of the process has a specific electricity market defined in ecoinvent
            if export_country in self.electricity_geos:
                electricity_region = export_country
            # if it's a sub-country (e.g., CA-QC)
            elif "-" in export_country:
                # look for the national market group for electricity
                if export_country.split("-")[0] in self.electricity_geos:
                    electricity_region = export_country.split("-")[0]
            # if there is no electricity market for the country, take the one for the region it belongs to
            elif (
                export_country != "RoW"
                and export_country in self.country_to_ecoinvent_regions
                and not electricity_region
            ):
                for potential_region in self.country_to_ecoinvent_regions[
                    export_country
                ]:
                    if potential_region in self.electricity_geos:
                        electricity_region = potential_region
            # if nothing works, take global electricity market
            if not electricity_region:
                electricity_region = "GLO"

            # store the name of the electricity process. Some countries have market groups and not just markets
            if electricity_region in [
                "BR",
                "CA",
                "CN",
                "GLO",
                "IN",
                "RAF",
                "RAS",
                "RER",
                "RLA",
                "RME",
                "RNA",
                "US",
            ]:
                electricity_activity_name = (
                    "market group for " + electricity_product_name
                )
            else:
                electricity_activity_name = "market for " + electricity_product_name

            # special cases for special Swiss grid mixes
            if ", for Swiss Federal Railways" in electricity_product_name:
                electricity_product_name = electricity_product_name.split(
                    ", for Swiss Federal Railways"
                )[0]
                electricity_activity_name = electricity_activity_name.split(
                    ", for Swiss Federal Railways"
                )[0]
            if ", renewable energy products" in electricity_product_name:
                electricity_product_name = electricity_product_name.split(
                    ", renewable energy products"
                )[0]
                electricity_activity_name = electricity_activity_name.split(
                    ", renewable energy products"
                )[0]

            # get the uuid
            electricity_code = self.ei_in_dict[
                (
                    electricity_product_name,
                    electricity_region,
                    electricity_activity_name,
                )
            ]["code"]

            # create the regionalized flow for electricity
            process["exchanges"].append(
                {
                    "amount": qty_of_electricity,
                    "product": electricity_product_name,
                    "name": electricity_activity_name,
                    "location": electricity_region,
                    "unit": unit_name,
                    "database": process["database"],
                    "code": electricity_code,
                    "type": "technosphere",
                    "input": (
                        self.name_ei_with_regionalized_biosphere,
                        electricity_code,
                    ),
                    "output": (process["database"], process["code"]),
                }
            )

        return process

    def change_aluminium_electricity(self, process, export_country):
        """
        This function changes an electricity input of a process by the national (or regional) electricity mix
        specifically for aluminium electricity mixes
        :param process: the copy of the regionalized process as a dictionnary
        :param export_country: the country of the newly regionalized process
        """
        # identify aluminium-specific electricity related exchanges
        electricity_product_names = list(
            set(
                [
                    i["product"]
                    for i in process["exchanges"]
                    if "electricity" in i["name"]
                    and "aluminium" in i["name"]
                    and "voltage" in i["name"]
                ]
            )
        )
        # loop through the identified process
        for electricity_product_name in electricity_product_names:
            unit_name = list(
                set(
                    [
                        i["unit"]
                        for i in process["exchanges"]
                        if "electricity" in i["name"]
                        and "aluminium" in i["name"]
                        and "voltage" in i["name"]
                    ]
                )
            )
            # if somehow different units used for electricity flows -> problem
            assert len(unit_name) == 1
            unit_name = unit_name[0]
            # sum quantity of all electricity exchanges
            qty_of_electricity = sum(
                [
                    i["amount"]
                    for i in process["exchanges"]
                    if electricity_product_name == i["product"]
                ]
            )

            # remove electricity flows from non-appropriated geography
            for exc in process["exchanges"][:]:
                if (
                    electricity_product_name == exc["product"]
                    and "aluminium" in exc["name"]
                ):
                    process["exchanges"].remove(exc)

            electricity_region = None
            # if the country of the process has a specific electricity market defined in ecoinvent
            if export_country in self.electricity_aluminium_geos:
                electricity_region = export_country
            # if there is no electricity market for the country, take the one for the region it belongs to
            elif (
                export_country != "RoW"
                and export_country in self.country_to_ecoinvent_regions
                and not electricity_region
            ):
                for potential_region in self.country_to_ecoinvent_regions[
                    export_country
                ]:
                    if potential_region in self.electricity_aluminium_geos:
                        electricity_region = potential_region
            # if nothing works, take RoW electricity market
            if not electricity_region:
                electricity_region = "RoW"

            # store the name of the electricity process
            electricity_activity_name = "market for " + electricity_product_name
            # get the uuid code
            electricity_code = self.ei_in_dict[
                (
                    electricity_product_name,
                    electricity_region,
                    electricity_activity_name,
                )
            ]["code"]

            # create the regionalized flow for electricity
            process["exchanges"].append(
                {
                    "amount": qty_of_electricity,
                    "product": electricity_product_name,
                    "name": electricity_activity_name,
                    "location": electricity_region,
                    "unit": unit_name,
                    "database": process["database"],
                    "code": electricity_code,
                    "type": "technosphere",
                    "input": (
                        self.name_ei_with_regionalized_biosphere,
                        electricity_code,
                    ),
                    "output": (process["database"], process["code"]),
                }
            )

        return process

    def change_cobalt_electricity(self, process):
        """
        This function changes an electricity input of a process by the national (or regional) electricity mix
        specifically for the cobalt electricity mix
        :param process: the copy of the regionalized process as a dictionnary
        """
        # identify cobalt-specific electricity related exchanges
        electricity_product_names = list(
            set(
                [
                    i["product"]
                    for i in process["exchanges"]
                    if "electricity" in i["name"] and "cobalt" in i["name"]
                ]
            )
        )
        # loop through the identified process
        for electricity_product_name in electricity_product_names:
            unit_name = list(
                set(
                    [
                        i["unit"]
                        for i in process["exchanges"]
                        if "electricity" in i["name"] and "cobalt" in i["name"]
                    ]
                )
            )
            # if somehow different units used for electricity flows -> problem
            assert len(unit_name) == 1
            unit_name = unit_name[0]
            # sum quantity of all electricity exchanges
            qty_of_electricity = sum(
                [
                    i["amount"]
                    for i in process["exchanges"]
                    if electricity_product_name == i["product"]
                ]
            )

            # remove electricity flows from non-appropriated geography
            for exc in process["exchanges"][:]:
                if (
                    electricity_product_name == exc["product"]
                    and "cobalt" in exc["name"]
                ):
                    process["exchanges"].remove(exc)

            # GLO is the only geography available for electricity, cobalt industry in ei3.9 and 3.10
            electricity_region = "GLO"
            # store the name of the electricity process
            electricity_activity_name = "market for " + electricity_product_name
            # get the uuid code
            electricity_code = self.ei_in_dict[
                (
                    electricity_product_name,
                    electricity_region,
                    electricity_activity_name,
                )
            ]["code"]

            # create the regionalized flow for electricity
            process["exchanges"].append(
                {
                    "amount": qty_of_electricity,
                    "product": electricity_product_name,
                    "name": electricity_activity_name,
                    "location": electricity_region,
                    "unit": unit_name,
                    "database": process["database"],
                    "code": electricity_code,
                    "type": "technosphere",
                    "input": (
                        self.name_ei_with_regionalized_biosphere,
                        electricity_code,
                    ),
                    "output": (process["database"], process["code"]),
                }
            )

        return process

    def change_waste(self, process, export_country):
        """
        This function changes a municipal solid waste treatment input of a process by the national (or regional) mix
        :param process: the copy of the regionalized process as a dictionnary
        :param export_country: the country of the newly regionalized process
        """
        # municipal solid waste exchanges all have the same name
        waste_product_name = "municipal solid waste"
        unit_name = list(
            set(
                [
                    i["unit"]
                    for i in process["exchanges"]
                    if waste_product_name == i["product"]
                ]
            )
        )
        # if somehow different units used for MSW flows -> problem
        assert len(unit_name) == 1
        unit_name = unit_name[0]
        # sum quantity of all MSW exchanges
        qty_of_waste = sum(
            [
                i["amount"]
                for i in process["exchanges"]
                if waste_product_name == i["product"]
            ]
        )

        # remove waste flows from non-appropriated geography
        for exc in process["exchanges"][:]:
            if waste_product_name == exc["product"]:
                process["exchanges"].remove(exc)

        # if the country of the process has a specific MSW market defined in ecoinvent
        if export_country in self.waste_geos:
            waste_region = export_country
        # if there is no MSW market for the country, take the one for the region it belongs to
        elif (
            export_country in self.country_to_ecoinvent_regions
            and self.country_to_ecoinvent_regions[export_country][0] == "RER"
        ):
            waste_region = "Europe without Switzerland"
        # if nothing works, take global MSW market
        else:
            waste_region = "RoW"

        # store the name of the electricity process
        if waste_region == "Europe without Switzerland":
            waste_activity_name = "market group for " + waste_product_name
        else:
            waste_activity_name = "market for " + waste_product_name

        # get the uuid code
        waste_code = self.ei_in_dict[
            (waste_product_name, waste_region, waste_activity_name)
        ]["code"]

        # create the regionalized flow for waste
        process["exchanges"].append(
            {
                "amount": qty_of_waste,
                "product": waste_product_name,
                "name": waste_activity_name,
                "location": waste_region,
                "unit": unit_name,
                "database": process["database"],
                "code": waste_code,
                "type": "technosphere",
                "input": (self.name_ei_with_regionalized_biosphere, waste_code),
                "output": (process["database"], process["code"]),
            }
        )

        return process

    def change_heat(self, process, export_country, heat_flow):
        """
        This function changes a heat input of a process by the national (or regional) mix
        :param process: the copy of the regionalized process as a dictionnary
        :param export_country: the country of the newly regionalized process
        :param heat_flow: the heat flow being regionalized (could be industrial, natural gas, or industrial other than
                          natural gas, or small-scale other than natural gas)
        """
        # depending on the heat process, the geographies covered in ecoinvent are different
        if heat_flow == "heat, district or industrial, natural gas":
            heat_process_countries = self.heat_district_ng
        if heat_flow == "heat, district or industrial, other than natural gas":
            heat_process_countries = self.heat_district_non_ng
        if heat_flow == "heat, central or small-scale, other than natural gas":
            heat_process_countries = self.heat_small_scale_non_ng

        unit_name = list(
            set([i["unit"] for i in process["exchanges"] if heat_flow == i["product"]])
        )
        # if somehow different units used for electricity flows -> problem
        assert len(unit_name) == 1
        unit_name = unit_name[0]
        # sum quantity of all heat exchanges
        qty_of_heat = sum(
            [i["amount"] for i in process["exchanges"] if heat_flow == i["product"]]
        )

        # remove heat flows from non-appropriated geography
        for exc in process["exchanges"][:]:
            if heat_flow == exc["product"]:
                process["exchanges"].remove(exc)

        # determine qty of heat for national mix through its share of the regional mix (e.g., DE in RER market for heat)
        # CH is its own market
        if export_country == "CH":
            region_heat = export_country
        elif (
            export_country in self.country_to_ecoinvent_regions
            and self.country_to_ecoinvent_regions[export_country][0] == "RER"
        ):
            region_heat = "Europe without Switzerland"
        else:
            region_heat = "RoW"

        # check if the country has a national production heat process, if not take the region or RoW
        if export_country not in heat_process_countries:
            if (
                export_country in self.country_to_ecoinvent_regions
                and self.country_to_ecoinvent_regions[export_country][0] == "RER"
            ):
                export_country = "Europe without Switzerland"
            else:
                export_country = "RoW"

        # select region heat market process
        region_heat_process = ws.get_many(
            self.ei_wurst,
            ws.equals("reference product", heat_flow),
            ws.equals("location", region_heat),
            ws.equals("database", self.name_ei_with_regionalized_biosphere),
            ws.contains("name", "market for"),
        )

        # countries with sub-region markets of heat require a special treatment
        if export_country in ["CA", "US", "CN", "BR", "IN"]:
            region_heat_process = ws.get_many(
                self.ei_wurst,
                ws.equals("reference product", heat_flow),
                ws.equals("location", region_heat),
                ws.equals("database", self.name_ei_with_regionalized_biosphere),
                ws.either(
                    ws.contains("name", "market for"),
                    ws.contains("name", "market group for"),
                ),
            )

            # extracting amount of heat of country within region heat market process
            heat_exchanges = {}
            for ds in region_heat_process:
                for exc in ws.technosphere(
                    ds,
                    *[
                        ws.equals("product", heat_flow),
                        ws.contains("location", export_country),
                    ],
                ):
                    heat_exchanges[exc["name"], exc["location"]] = exc["amount"]

            # special case for some Quebec heat flows
            if (
                export_country == "CA"
                and heat_flow != "heat, central or small-scale, other than natural gas"
            ):
                if self.name_ei_with_regionalized_biosphere in bw2.databases:
                    global_heat_process = ws.get_one(
                        self.ei_wurst,
                        ws.equals("reference product", heat_flow),
                        ws.equals("location", "GLO"),
                        ws.equals("database", self.name_ei_with_regionalized_biosphere),
                        ws.either(
                            ws.contains("name", "market for"),
                            ws.contains("name", "market group for"),
                        ),
                    )
                else:
                    global_heat_process = ws.get_one(
                        self.ei_wurst,
                        ws.equals("reference product", heat_flow),
                        ws.equals("location", "GLO"),
                        ws.equals("database", self.ecoinvent_database_name),
                        ws.either(
                            ws.contains("name", "market for"),
                            ws.contains("name", "market group for"),
                        ),
                    )

                heat_exchanges = {
                    k: v
                    * [
                        i["amount"]
                        for i in global_heat_process["exchanges"]
                        if i["location"] == "RoW"
                    ][0]
                    for k, v in heat_exchanges.items()
                }
                heat_exchanges[
                    (
                        [
                            i
                            for i in global_heat_process["exchanges"]
                            if i["location"] == "CA-QC"
                        ][0]["name"],
                        "CA-QC",
                    )
                ] = [
                    i
                    for i in global_heat_process["exchanges"]
                    if i["location"] == "CA-QC"
                ][
                    0
                ][
                    "amount"
                ]
            # make it relative amounts
            heat_exchanges = {
                k: v / sum(heat_exchanges.values()) for k, v in heat_exchanges.items()
            }
            # scale the relative amount to the qty of heat of process
            heat_exchanges = {k: v * qty_of_heat for k, v in heat_exchanges.items()}

            # add regionalized exchange of heat
            for heat_exc in heat_exchanges.keys():
                process["exchanges"].append(
                    {
                        "amount": heat_exchanges[heat_exc],
                        "product": heat_flow,
                        "name": heat_exc[0],
                        "location": heat_exc[1],
                        "unit": unit_name,
                        "database": process["database"],
                        "code": self.ei_in_dict[(heat_flow, heat_exc[1], heat_exc[0])][
                            "code"
                        ],
                        "type": "technosphere",
                        "input": (
                            self.name_ei_with_regionalized_biosphere,
                            self.ei_in_dict[(heat_flow, heat_exc[1], heat_exc[0])][
                                "code"
                            ],
                        ),
                        "output": (process["database"], process["code"]),
                    }
                )

        else:
            # extracting amount of heat of country within region heat market process
            heat_exchanges = {}
            for ds in region_heat_process:
                for exc in ws.technosphere(
                    ds,
                    *[
                        ws.equals("product", heat_flow),
                        ws.equals("location", export_country),
                    ],
                ):
                    heat_exchanges[exc["name"]] = exc["amount"]
            # make it relative amounts
            heat_exchanges = {
                k: v / sum(heat_exchanges.values()) for k, v in heat_exchanges.items()
            }
            # scale the relative amount to the qty of heat of process
            heat_exchanges = {k: v * qty_of_heat for k, v in heat_exchanges.items()}

            # add regionalized exchange of heat
            for heat_exc in heat_exchanges.keys():

                process["exchanges"].append(
                    {
                        "amount": heat_exchanges[heat_exc],
                        "product": heat_flow,
                        "name": heat_exc,
                        "location": export_country,
                        "unit": unit_name,
                        "database": process["database"],
                        "code": self.ei_in_dict[(heat_flow, export_country, heat_exc)][
                            "code"
                        ],
                        "type": "technosphere",
                        "input": (
                            self.name_ei_with_regionalized_biosphere,
                            self.ei_in_dict[(heat_flow, export_country, heat_exc)][
                                "code"
                            ],
                        ),
                        "output": (process["database"], process["code"]),
                    }
                )

        return process

    def test_input_presence(self, process, input_name, extra=None):
        """
        Function that checks if an input is present in a given process
        :param process: The process to check whether the input is in it or not
        :param input_name: The name of the input to check
        :param extra: Extra information to look for very specific inputs
        :return: a boolean of whether the input is present or not
        """
        if extra == "aluminium/electricity":
            for exc in ws.technosphere(
                process,
                ws.contains("name", input_name),
                ws.contains("name", "aluminium"),
            ):
                return True
        elif extra == "cobalt/electricity":
            for exc in ws.technosphere(
                process, ws.contains("name", input_name), ws.contains("name", "cobalt")
            ):
                return True
        elif extra == "voltage":
            for exc in ws.technosphere(
                process, ws.contains("name", input_name), ws.contains("name", "voltage")
            ):
                return True
        else:
            for exc in ws.technosphere(process, ws.equals("product", input_name)):
                return True
