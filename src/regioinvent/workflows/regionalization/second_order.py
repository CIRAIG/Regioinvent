import collections
import copy


def second_order_regionalization(regio):
    """
    Function that links newly created consumption markets to inputs of the different processes of the regionalized
    ecoinvent database.
    :return:  regio.regioinvent_in_wurst with new regionalized processes
    """

    regio.logger.info("Link regioinvent processes to each other...")

    # as dictionaries to speed up searching for info
    consumption_markets_data = {
        (i["name"], i["location"]): i
        for i in regio.regioinvent_in_wurst
        if "consumption market" in i["name"]
    }

    # store available processes of non-internationally traded commodities
    other_processes_data = collections.defaultdict(list)
    for i in regio.regioinvent_in_wurst:
        if (
            "consumption market" not in i["name"]
            and "production market" not in i["name"]
            and i["reference product"] not in regio.eco_to_hs_class
        ):
            key = (i["reference product"], i["location"])
            other_processes_data[key].append(i)

    regionalized_products = set([i["reference product"] for i in regio.regioinvent_in_wurst])

    techno_mixes = {
        (i["name"], i["location"]): i["code"]
        for i in regio.regioinvent_in_wurst
        if "technology mix" in i["name"]
    }

    # loop through created processes and link to internationally traded commodities
    for process in regio.regioinvent_in_wurst:
        # only for internationally traded commodities
        if (
            "consumption market" not in process["name"]
            and "production market" not in process["name"]
            and "technology mix" not in process["name"]
            and process["reference product"] in regio.eco_to_hs_class.keys()
        ):
            # loop through exchanges
            for exc in process["exchanges"]:
                if exc["product"] in regio.eco_to_hs_class.keys() and exc["type"] == "technosphere":
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
                elif exc["product"] in regionalized_products and exc["type"] == "technosphere":
                    # connect to technology mix for the country
                    exc["name"] = "technology mix for " + exc["product"]
                    exc["location"] = process["location"]
                    exc["code"] = techno_mixes[
                        (
                            "technology mix for " + exc["product"],
                            process["location"],
                        )
                    ]
                    exc["database"] = regio.target_db_name
                    exc["input"] = (exc["database"], exc["code"])
        elif "technology mix" in process["name"]:
            for exc in process["exchanges"]:
                for i in range(
                    0,
                    len(other_processes_data[(exc["product"], process["location"])]),
                ):
                    # find correct technology for production
                    if (
                        other_processes_data[(exc["product"], process["location"])][i]["name"]
                        == exc["name"]
                    ):
                        # change info
                        exc["code"] = other_processes_data[(exc["product"], process["location"])][
                            i
                        ]["code"]
                        exc["database"] = regio.target_db_name
                        exc["location"] = process["location"]
                        exc["input"] = (exc["database"], exc["code"])

    # reduce the size of the database by culling processes unused by internationally traded commodities
    used_techno_mixes = []

    for process in regio.regioinvent_in_wurst:
        if (
            "consumption market" not in process["name"]
            and "production market" not in process["name"]
            and process["reference product"] in regio.eco_to_hs_class.keys()
        ):
            for exc in process["exchanges"]:
                if "technology mix" in exc["name"]:
                    if (
                        exc["name"],
                        exc["product"],
                        exc["location"],
                    ) not in used_techno_mixes:
                        used_techno_mixes.append((exc["name"], exc["product"], exc["location"]))
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
    for ds in regio.regioinvent_in_wurst:
        if "technology mix" in ds["name"]:
            if (
                ds["name"],
                ds["reference product"],
                ds["location"],
            ) in used_techno_mixes:
                reduced_regioinvent.append(ds)
        else:
            reduced_regioinvent.append(ds)

    regio.regioinvent_in_wurst = copy.copy(reduced_regioinvent)

    # redetermine available techno mixes, since we culled some of them
    techno_mixes = {
        (i["name"], i["location"]): i["code"]
        for i in regio.regioinvent_in_wurst
        if "technology mix" in i["name"]
    }

    used_prod_processes = []
    for process in regio.regioinvent_in_wurst:
        if "technology mix" in process["name"]:
            for exc in process["exchanges"]:
                if (
                    exc["type"] == "technosphere"
                    and exc["product"] in regionalized_products
                    and exc["product"] not in regio.eco_to_hs_class.keys()
                    and "technology mix" not in exc["name"]
                ):
                    if (
                        exc["name"],
                        exc["product"],
                        exc["location"],
                    ) not in used_prod_processes:
                        used_prod_processes.append((exc["name"], exc["product"], exc["location"]))

    even_more_reduced_regioinvent = []
    for ds in regio.regioinvent_in_wurst:
        if (
            "technology mix" not in ds["name"]
            and "consumption market" not in ds["name"]
            and "production market" not in ds["name"]
            and ds["reference product"] not in regio.eco_to_hs_class.keys()
        ):
            if (
                ds["name"],
                ds["reference product"],
                ds["location"],
            ) in used_prod_processes:
                even_more_reduced_regioinvent.append(ds)
        else:
            even_more_reduced_regioinvent.append(ds)

    regio.regioinvent_in_wurst = copy.copy(even_more_reduced_regioinvent)

    # loop through created processes and link to non-internationally traded commodities
    for process in regio.regioinvent_in_wurst:
        # only for internationally traded commodities
        if (
            "consumption market" not in process["name"]
            and "production market" not in process["name"]
            and "technology mix" not in process["name"]
            and process["reference product"] not in regio.eco_to_hs_class.keys()
        ):
            # loop through exchanges
            for exc in process["exchanges"]:
                if exc["product"] in regio.eco_to_hs_class.keys() and exc["type"] == "technosphere":
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
                elif exc["product"] in regionalized_products and exc["type"] == "technosphere":
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
                        exc["database"] = regio.target_db_name
                        exc["input"] = (exc["database"], exc["code"])
                    except KeyError:
                        pass

    regio.logger.info("Aggregate duplicates together...")

    # aggregating duplicate inputs (e.g., multiple consumption markets RoW callouts)
    for process in regio.regioinvent_in_wurst:
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
            total = sum([i["amount"] for i in process["exchanges"] if i["input"] == duplicate])
            name = [i["name"] for i in process["exchanges"] if i["input"] == duplicate][0]
            product = [i["product"] for i in process["exchanges"] if i["input"] == duplicate][0]
            database = [i["database"] for i in process["exchanges"] if i["input"] == duplicate][0]
            location = [i["location"] for i in process["exchanges"] if i["input"] == duplicate][0]

            process["exchanges"] = [i for i in process["exchanges"] if i["input"] != duplicate] + [
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
