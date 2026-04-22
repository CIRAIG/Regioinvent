import wurst.searching as ws


def change_electricity(regio, process, export_country):
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
            [i["amount"] for i in process["exchanges"] if electricity_product_name == i["product"]]
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

        if not hasattr(regio, "_electricity_region_cache"):
            regio._electricity_region_cache = {}
        if export_country in regio._electricity_region_cache:
            electricity_region = regio._electricity_region_cache[export_country]
        else:
            electricity_region = None
            # if the country of the process has a specific electricity market defined in ecoinvent
            if export_country in regio.electricity_geos:
                electricity_region = export_country
            # if it's a sub-country (e.g., CA-QC)
            elif "-" in export_country:
                # look for the national market group for electricity
                if export_country.split("-")[0] in regio.electricity_geos:
                    electricity_region = export_country.split("-")[0]
            # if there is no electricity market for the country, take the one for the region it belongs to
            elif (
                export_country != "RoW"
                and export_country in regio.country_to_ecoinvent_regions
                and not electricity_region
            ):
                for potential_region in regio.country_to_ecoinvent_regions[export_country]:
                    if potential_region in regio.electricity_geos:
                        electricity_region = potential_region
            # if nothing works, take global electricity market
            if not electricity_region:
                electricity_region = "GLO"
            regio._electricity_region_cache[export_country] = electricity_region

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
            electricity_activity_name = "market group for " + electricity_product_name
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
        electricity_code = regio.ei_in_dict[
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
                    regio.regionalized_ecoinvent_db_name,
                    electricity_code,
                ),
                "output": (process["database"], process["code"]),
            }
        )

    return process


def change_aluminium_electricity(regio, process, export_country):
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
            [i["amount"] for i in process["exchanges"] if electricity_product_name == i["product"]]
        )

        # remove electricity flows from non-appropriated geography
        for exc in process["exchanges"][:]:
            if electricity_product_name == exc["product"] and "aluminium" in exc["name"]:
                process["exchanges"].remove(exc)

        if not hasattr(regio, "_aluminium_electricity_region_cache"):
            regio._aluminium_electricity_region_cache = {}
        if export_country in regio._aluminium_electricity_region_cache:
            electricity_region = regio._aluminium_electricity_region_cache[export_country]
        else:
            electricity_region = None
            # if the country of the process has a specific electricity market defined in ecoinvent
            if export_country in regio.electricity_aluminium_geos:
                electricity_region = export_country
            # if there is no electricity market for the country, take the one for the region it belongs to
            elif (
                export_country != "RoW"
                and export_country in regio.country_to_ecoinvent_regions
                and not electricity_region
            ):
                for potential_region in regio.country_to_ecoinvent_regions[export_country]:
                    if potential_region in regio.electricity_aluminium_geos:
                        electricity_region = potential_region
            # if nothing works, take RoW electricity market
            if not electricity_region:
                electricity_region = "RoW"
            regio._aluminium_electricity_region_cache[export_country] = electricity_region

        # store the name of the electricity process
        electricity_activity_name = "market for " + electricity_product_name
        # get the uuid code
        electricity_code = regio.ei_in_dict[
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
                    regio.regionalized_ecoinvent_db_name,
                    electricity_code,
                ),
                "output": (process["database"], process["code"]),
            }
        )

    return process


def change_cobalt_electricity(regio, process):
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
            [i["amount"] for i in process["exchanges"] if electricity_product_name == i["product"]]
        )

        # remove electricity flows from non-appropriated geography
        for exc in process["exchanges"][:]:
            if electricity_product_name == exc["product"] and "cobalt" in exc["name"]:
                process["exchanges"].remove(exc)

        # GLO is the only geography available for electricity, cobalt industry in ei3.9 and 3.10
        electricity_region = "GLO"
        # store the name of the electricity process
        electricity_activity_name = "market for " + electricity_product_name
        # get the uuid code
        electricity_code = regio.ei_in_dict[
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
                    regio.regionalized_ecoinvent_db_name,
                    electricity_code,
                ),
                "output": (process["database"], process["code"]),
            }
        )

    return process


def change_waste(regio, process, export_country):
    """
    This function changes a municipal solid waste treatment input of a process by the national (or regional) mix
    :param process: the copy of the regionalized process as a dictionnary
    :param export_country: the country of the newly regionalized process
    """
    # municipal solid waste exchanges all have the same name
    waste_product_name = "municipal solid waste"
    unit_name = list(
        set([i["unit"] for i in process["exchanges"] if waste_product_name == i["product"]])
    )
    # if somehow different units used for MSW flows -> problem
    assert len(unit_name) == 1
    unit_name = unit_name[0]
    # sum quantity of all MSW exchanges
    qty_of_waste = sum(
        [i["amount"] for i in process["exchanges"] if waste_product_name == i["product"]]
    )

    # remove waste flows from non-appropriated geography
    for exc in process["exchanges"][:]:
        if waste_product_name == exc["product"]:
            process["exchanges"].remove(exc)

    if not hasattr(regio, "_waste_region_cache"):
        regio._waste_region_cache = {}
    if export_country in regio._waste_region_cache:
        waste_region = regio._waste_region_cache[export_country]
    else:
        # if the country of the process has a specific MSW market defined in ecoinvent
        if export_country in regio.waste_geos:
            waste_region = export_country
        # if there is no MSW market for the country, take the one for the region it belongs to
        elif (
            export_country in regio.country_to_ecoinvent_regions
            and regio.country_to_ecoinvent_regions[export_country][0] == "RER"
        ):
            waste_region = "Europe without Switzerland"
        # if nothing works, take global MSW market
        else:
            waste_region = "RoW"
        regio._waste_region_cache[export_country] = waste_region

    # store the name of the electricity process
    if waste_region == "Europe without Switzerland":
        waste_activity_name = "market group for " + waste_product_name
    else:
        waste_activity_name = "market for " + waste_product_name

    # get the uuid code
    waste_code = regio.ei_in_dict[(waste_product_name, waste_region, waste_activity_name)]["code"]

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
            "input": (regio.regionalized_ecoinvent_db_name, waste_code),
            "output": (process["database"], process["code"]),
        }
    )

    return process


def change_heat(regio, process, export_country, heat_flow):
    """
    This function changes a heat input of a process by the national (or regional) mix
    :param process: the copy of the regionalized process as a dictionnary
    :param export_country: the country of the newly regionalized process
    :param heat_flow: the heat flow being regionalized (could be industrial, natural gas, or industrial other than
                      natural gas, or small-scale other than natural gas)
    """
    # depending on the heat process, the geographies covered in ecoinvent are different
    if heat_flow == "heat, district or industrial, natural gas":
        heat_process_countries = regio.heat_district_ng
    if heat_flow == "heat, district or industrial, other than natural gas":
        heat_process_countries = regio.heat_district_non_ng
    if heat_flow == "heat, central or small-scale, other than natural gas":
        heat_process_countries = regio.heat_small_scale_non_ng

    unit_name = list(set([i["unit"] for i in process["exchanges"] if heat_flow == i["product"]]))
    # if somehow different units used for electricity flows -> problem
    assert len(unit_name) == 1
    unit_name = unit_name[0]
    # sum quantity of all heat exchanges
    qty_of_heat = sum([i["amount"] for i in process["exchanges"] if heat_flow == i["product"]])

    # remove heat flows from non-appropriated geography
    for exc in process["exchanges"][:]:
        if heat_flow == exc["product"]:
            process["exchanges"].remove(exc)

    # determine qty of heat for national mix through its share of the regional mix (e.g., DE in RER market for heat)
    # CH is its own market
    if export_country == "CH":
        region_heat = export_country
    elif (
        export_country in regio.country_to_ecoinvent_regions
        and regio.country_to_ecoinvent_regions[export_country][0] == "RER"
    ):
        region_heat = "Europe without Switzerland"
    else:
        region_heat = "RoW"

    # check if the country has a national production heat process, if not take the region or RoW
    if export_country not in heat_process_countries:
        if (
            export_country in regio.country_to_ecoinvent_regions
            and regio.country_to_ecoinvent_regions[export_country][0] == "RER"
        ):
            export_country = "Europe without Switzerland"
        else:
            export_country = "RoW"

    # Cache relative heat mixes by (heat_flow, region heat market, export country).
    if not hasattr(regio, "_heat_mix_cache"):
        regio._heat_mix_cache = {}
    cache_key = (heat_flow, region_heat, export_country)

    if cache_key not in regio._heat_mix_cache:
        use_subregion_heat_markets = export_country in ["CA", "US", "CN", "BR", "IN"]

        if use_subregion_heat_markets:
            region_heat_process = ws.get_many(
                regio.ei_wurst,
                ws.equals("reference product", heat_flow),
                ws.equals("location", region_heat),
                ws.equals("database", regio.regionalized_ecoinvent_db_name),
                ws.either(
                    ws.contains("name", "market for"),
                    ws.contains("name", "market group for"),
                ),
            )
        else:
            region_heat_process = ws.get_many(
                regio.ei_wurst,
                ws.equals("reference product", heat_flow),
                ws.equals("location", region_heat),
                ws.equals("database", regio.regionalized_ecoinvent_db_name),
                ws.contains("name", "market for"),
            )

        if use_subregion_heat_markets:
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
                    heat_exchanges[(exc["name"], exc["location"])] = exc["amount"]

            # special case for some Quebec heat flows
            if (
                export_country == "CA"
                and heat_flow != "heat, central or small-scale, other than natural gas"
            ):
                global_heat_process = ws.get_one(
                    regio.ei_wurst,
                    ws.equals("reference product", heat_flow),
                    ws.equals("location", "GLO"),
                    ws.equals("database", regio.regionalized_ecoinvent_db_name),
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
                        [i for i in global_heat_process["exchanges"] if i["location"] == "CA-QC"][
                            0
                        ]["name"],
                        "CA-QC",
                    )
                ] = [i for i in global_heat_process["exchanges"] if i["location"] == "CA-QC"][0][
                    "amount"
                ]
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
                    heat_exchanges[(exc["name"], export_country)] = exc["amount"]

        total = sum(heat_exchanges.values())
        if total:
            mix_entries = [
                (name, location, amount / total)
                for (name, location), amount in heat_exchanges.items()
            ]
        else:
            mix_entries = []
        regio._heat_mix_cache[cache_key] = mix_entries

    # add regionalized exchange of heat from cached relative mix
    for heat_name, heat_location, relative_share in regio._heat_mix_cache[cache_key]:
        amount = relative_share * qty_of_heat
        code = regio.ei_in_dict[(heat_flow, heat_location, heat_name)]["code"]
        process["exchanges"].append(
            {
                "amount": amount,
                "product": heat_flow,
                "name": heat_name,
                "location": heat_location,
                "unit": unit_name,
                "database": process["database"],
                "code": code,
                "type": "technosphere",
                "input": (regio.regionalized_ecoinvent_db_name, code),
                "output": (process["database"], process["code"]),
            }
        )

    return process


def test_input_presence(regio, process, input_name, extra=None):
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
