import json
import pickle
from importlib.resources import as_file, files

import bw2data as bd

from regioinvent.wurst_compat import extract_brightway2_databases_compat


def spatialize_my_ecoinvent(regio):
    """
    Function creates a copy of the original ecoinvent database and modifies this copy to spatialize the elementary
    flows used by ecoinvent. It also creates additional technosphere water processes to remediate imbalances due to
    technosphere misrepresentations.

    :return: nothing but prepares an in-memory spatialized copy of ecoinvent
    """

    # ---------------------------- Create the spatialized biosphere ----------------------------

    if "biosphere3_spatialized_flows" not in bd.databases:
        regio.logger.info("Creating spatialized biosphere flows...")
        # load the correct pickle file with the different spatialized elementary flows metadata
        with as_file(
            files("regioinvent").joinpath(
                f"data/Spatialization_of_elementary_flows/ei{regio.ecoinvent_version}/spatialized_biosphere_database.pickle"
            )
        ) as file_path:
            with open(file_path, "rb") as f:
                spatialized_biosphere = pickle.load(f)

        # create the new biosphere3 database with spatialized elementary flows
        bd.Database(regio.name_spatialized_biosphere).write(spatialized_biosphere)
    else:
        regio.logger.info("biosphere3_spatialized_flows already exists in this project.")

    # ---------------------------- Spatialize ecoinvent (in memory) ----------------------------
    if getattr(regio, "_spatialized_in_memory_ready", False):
        regio.logger.info("In-memory spatialized ecoinvent already prepared.")
        return

    # transform format of ecoinvent to wurst format for speed-up
    regio.logger.info("Extracting ecoinvent to wurst...")
    regio.ei_wurst = extract_brightway2_databases_compat(regio.source_db_name, add_identifiers=True)

    # also get ecoinvent in a format for more efficient searching
    regio.ei_in_dict = {
        (i["reference product"], i["location"], i["name"]): i for i in regio.ei_wurst
    }

    # load the list of the base name of all spatialized elementary flows
    with as_file(
        files("regioinvent").joinpath(
            f"data/Spatialization_of_elementary_flows/ei{regio.ecoinvent_version}/spatialized_elementary_flows.json"
        )
    ) as file_path:
        with open(file_path, "r") as f:
            base_spatialized_flows = json.load(f)

    # store the codes of the spatialized flows in a dictionary
    spatialized_flows = {
        (i.as_dict()["name"], i.as_dict()["categories"]): i.as_dict()["code"]
        for i in bd.Database(regio.name_spatialized_biosphere)
    }

    regio.logger.info("Spatializing ecoinvent...")
    # loop through the whole ecoinvent database
    for process in regio.ei_wurst:
        # if you have more than 1000 exchanges -> aggregated process (S) -> should not be spatialized
        if len(process["exchanges"]) < 1000:
            # create a copy, but in the new ecoinvent database
            process["database"] = regio.regionalized_ecoinvent_db_name
            # loop through exchanges of a process
            for exc in process["exchanges"]:
                # if it's a biosphere exchange
                if exc["type"] == "biosphere":
                    # check if it's a flow that should be spatialized
                    if exc["name"] in base_spatialized_flows:
                        # check if the category makes sense (don't regionalize mineral resources for instance)
                        if exc["categories"][0] in base_spatialized_flows[exc["name"]]:
                            # to spatialize it, we need to get the uuid of the existing spatialized flow
                            exc["code"] = spatialized_flows[
                                (
                                    exc["name"] + ", " + process["location"],
                                    exc["categories"],
                                )
                            ]

                            # change the database of the exchange as well
                            exc["database"] = regio.name_spatialized_biosphere
                            # update its name
                            exc["name"] = exc["name"] + ", " + process["location"]
                            # and finally its input key
                            exc["input"] = (exc["database"], exc["code"])
                # if it's a technosphere exchange, just update the database value
                else:
                    exc["database"] = regio.regionalized_ecoinvent_db_name
        # if you are an aggregated process (S)
        elif len(process["exchanges"]) > 1000:
            # simply change the name of the database
            process["database"] = regio.regionalized_ecoinvent_db_name
            for exc in process["exchanges"]:
                exc["database"] = regio.regionalized_ecoinvent_db_name

    # sometimes input keys disappear with wurst, make sure there is always one
    for pr in regio.ei_wurst:
        for exc in pr["exchanges"]:
            try:
                exc["input"]
            except KeyError:
                exc["input"] = (exc["database"], exc["code"])

    # modify structure of data from wurst to bw2 (in-memory only)
    regio.ei_regio_data = {(i["database"], i["code"]): i for i in regio.ei_wurst}

    # wurst creates empty categories for technosphere activities, delete those
    for pr in regio.ei_regio_data:
        try:
            del regio.ei_regio_data[pr]["categories"]
        except KeyError:
            pass
    # same with parameters
    for pr in regio.ei_regio_data:
        try:
            del regio.ei_regio_data[pr]["parameters"]
        except KeyError:
            pass

    regio._spatialized_in_memory_ready = True
