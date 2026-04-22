import json
from importlib.resources import as_file, files

import bw2data as bd


def spatialize_elem_flows(regio):
    """
    Function spatializes the elementary flows of the regioinvent processes to the location of process.
    """

    regio.logger.info("Regionalizing the elementary flows of the regioinvent database...")

    # the list of all spatialized flows
    with as_file(
        files("regioinvent").joinpath(
            f"data/Spatialization_of_elementary_flows/ei{regio.ecoinvent_version}/spatialized_elementary_flows.json"
        )
    ) as file_path:
        with open(file_path, "r") as f:
            spatialized_elem_flows = json.load(f)

    # a dictionary with all the associated uuids of the spatialized flows
    regionalized_flows = {
        (i.as_dict()["name"], i.as_dict()["categories"]): i.as_dict()["code"]
        for i in bd.Database(regio.name_spatialized_biosphere)
    }

    # loop through regioinvent processes
    for process in regio.regioinvent_in_wurst:
        # loop through exchanges of process
        for exc in process["exchanges"]:
            # if the exchange is a biosphere exchange
            if exc["type"] == "biosphere":
                # strip the potential region from the spatialized flow name and check if it's a spatialized flow
                # if region had a comma in the name it would be a problem, but it's not happening as the geographies
                # used for copies in regioinvent don't contain commas
                if ", ".join(exc["name"].split(", ")[:-1]) in spatialized_elem_flows.keys():
                    base_name_flow = ", ".join(exc["name"].split(", ")[:-1])
                    # check that the flow is spatialized for the compartment
                    if exc["categories"][0] in spatialized_elem_flows[base_name_flow]:
                        # get code of spatialized flow for process['location']
                        exc["code"] = regionalized_flows[
                            (
                                base_name_flow + ", " + process["location"],
                                exc["categories"],
                            )
                        ]
                        # change database name of exchange
                        exc["database"] = regio.name_spatialized_biosphere
                        # change name of exchange
                        exc["name"] = base_name_flow + ", " + process["location"]
                        # change input key of exchange
                        exc["input"] = (exc["database"], exc["code"])
