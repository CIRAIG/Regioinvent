import copy
import json
import uuid
from collections import defaultdict
from importlib.resources import as_file, files

import wurst.searching as ws
from tqdm import tqdm


def _clone_process_template(process):
    """Fast clone for ecoinvent process templates used in regionalization loops."""
    cloned = process.copy()
    cloned["exchanges"] = [exc.copy() for exc in process.get("exchanges", [])]
    return cloned


def first_order_regionalization(regio):
    """
    Function to regionalized the key inputs of each process: electricity, municipal solid waste and heat.
    :return: regio.regioinvent_in_wurst with new regionalized processes
    """

    regio.logger.info(
        "Regionalizing main inputs of internationally-traded products of ecoinvent..."
    )

    # Build in-memory indices once to avoid repeated full scans over regio.ei_wurst.
    non_market_by_product = defaultdict(list)
    market_by_product = defaultdict(list)
    exact_process_lookup = {}
    market_candidates_lookup = defaultdict(list)
    for ds in regio.ei_wurst:
        product = ds.get("reference product")
        if not product:
            continue
        name = ds.get("name", "")
        location = ds.get("location")
        database = ds.get("database")
        is_market = ("market for" in name) or ("market group for" in name)
        is_generic = "generic market" in name
        is_import = "import from" in name
        is_to_market = "to market" in name

        if not is_market and not is_generic and not is_import:
            non_market_by_product[product].append(ds)
            exact_process_lookup[(product, name, location, database)] = ds

        if is_market:
            market_by_product[product].append(ds)

        if is_market and not is_generic and not is_to_market:
            market_candidates_lookup[(product, location, database)].append(ds)

    # Cache repeated transport code -> reference product lookups.
    transport_ref_product_cache = {}
    code_to_ref_product = {
        ds.get("code"): ds.get("reference product")
        for ds in regio.ei_wurst
        if ds.get("code") and ds.get("reference product")
    }
    # Cache template input-presence flags to avoid repeated exchange scans.
    template_input_flags_cache = {}
    # Speed up irrelevant-process checks.
    no_inputs_processes_set = {tuple(item) for item in regio.no_inputs_processes}

    # -----------------------------------------------------------------------------------------------------------
    # first, we regionalize internationally-traded products, these require the creation of markets and are selected
    # based on national production volumes
    for product in tqdm(regio.eco_to_hs_class, leave=True):
        # filter commodity code from production_data
        cmd_prod_data = regio.production_data[
            regio.production_data.cmdCode.isin([regio.eco_to_hs_class[product]])
        ].copy("deep")
        # calculate the average production volume over the available years for each country
        cmd_prod_data = cmd_prod_data.groupby("exporter").agg({"quantity (t)": "mean"})
        producers = (
            cmd_prod_data.loc[:, "quantity (t)"] / cmd_prod_data.loc[:, "quantity (t)"].sum()
        ).sort_values(ascending=False)
        # only keep the countries representing XX% of global production of the product and create a RoW from that
        limit = producers.index.get_loc(producers[producers.cumsum() > regio.cutoff].index[0]) + 1
        remainder = producers.iloc[limit:].sum()
        producers = producers.iloc[:limit]
        if "RoW" in producers.index:
            producers.loc["RoW"] += remainder
        else:
            producers.loc["RoW"] = remainder

        # register the information about created geographies for each product
        regio.created_geographies[product] = [i for i in producers.index]

        # identify the processes producing the product
        filter_processes = non_market_by_product.get(product, [])
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
        possibilities_set = {tech: set(geos) for tech, geos in possibilities.items()}

        # determine the market share of each technology that produces the product, also determine the transportation
        regio.transportation_modes[product] = {}
        regio.distribution_technologies[product] = {tech: 0 for tech in available_technologies}
        market_processes = market_by_product.get(product, [])
        number_of_markets = 0
        for ds in market_processes:
            number_of_markets += 1
            for exc in ds["exchanges"]:
                if exc["product"] == product:
                    if exc["name"] in possibilities.keys():
                        regio.distribution_technologies[product][exc["name"]] += exc["amount"]
                if (
                    ("transport" in exc["name"])
                    & ("ton kilometer" == exc["unit"])
                    & ("market for" in exc["name"] or "market group for" in exc["name"])
                ):
                    regio.transportation_modes[product][exc["code"]] = exc["amount"]
        # average the technology market share
        sum_ = sum(regio.distribution_technologies[product].values())
        if sum_ != 0:
            regio.distribution_technologies[product] = {
                k: v / sum_ for k, v in regio.distribution_technologies[product].items()
            }
        else:
            regio.distribution_technologies[product] = {
                k: 1 / len(regio.distribution_technologies[product])
                for k, v in regio.distribution_technologies[product].items()
            }
        # average the transportation modes
        if number_of_markets > 1:
            regio.transportation_modes[product] = {
                k: v / number_of_markets for k, v in regio.transportation_modes[product].items()
            }

        # create the global production market process within regioinvent
        global_market_activity = copy.deepcopy(dataset)

        # rename activity
        global_market_activity["name"] = f"""production market for {product}"""

        # Precompute source text once per cmdCode.
        sources = set(zip(regio.domestic_production.cmdCode, regio.domestic_production.source))

        source_by_cmd = {}
        # Loop through your zipped data
        for code, source in sources:
            # Check if "PRODCOM" is in the source string
            if "PRODCOM" in source:
                source_by_cmd[code] = "PRODCOM"
            else:
                # Only assign if the code isn't already set to "PRODCOM"
                # (This prevents a non-PRODCOM source from overwriting a PRODCOM one)
                if source_by_cmd.get(code) != "PRODCOM":
                    source_by_cmd[code] = source
        replacements = {
            "FAOSTAT": "FAOSTAT (https://www.fao.org/faostat/en/#data)",
            "USGS": "USGS (https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries)",
            "OICA": "OICA (https://oica.net/production-statistics/)",
            "World Steel": "World Steel Association (https://worldsteel.org/data/annual-production-steel-data)",
            "PRODCOM": "PRODCOM (https://ec.europa.eu/eurostat/databrowser/bulk) & EXIOBASE (https://doi.org/10.5281/zenodo.3583070)"
        }

        source_by_cmd = {
            code: next((target for sub, target in replacements.items() if sub in source),
                       "EXIOBASE (https://doi.org/10.5281/zenodo.3583070)")
            for code, source in source_by_cmd.items()
        }

        global_market_activity["comment"] = (
            f"""This process represents the global production market for {product}. The shares come from export data from the BACI database for the commodity {regio.eco_to_hs_class[product]}. Data from BACI is already in physical units. An average of the 5 last years of export trade available data is taken (in general from 2020 to 2024). Domestic production was extracted/estimated from {source_by_cmd.get(product)}. Countries are taken until {regio.cutoff*100}% of the global production amounts are covered. The rest of the data is aggregated in a RoW (Rest-of-the-World) region."""
        )

        # location will be global (it's a global market)
        global_market_activity["location"] = "GLO"

        # new code needed
        global_market_activity["code"] = uuid.uuid4().hex

        # change database
        global_market_activity["database"] = regio.target_db_name

        # reset exchanges with only the production exchange
        global_market_activity["exchanges"] = [
            {
                "amount": 1.0,
                "type": "production",
                "product": global_market_activity["reference product"],
                "name": global_market_activity["name"],
                "unit": global_market_activity["unit"],
                "location": global_market_activity["location"],
                "database": regio.target_db_name,
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
        regio.unit[product] = global_market_activity["unit"]

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
            process = exact_process_lookup[
                (product, activity, region, regio.regionalized_ecoinvent_db_name)
            ]
            regio_process = _clone_process_template(process)
            # change location
            regio_process["location"] = prod_country
            # change code
            regio_process["code"] = uuid.uuid4().hex
            # change database
            regio_process["database"] = regio.target_db_name
            # add a type to the process (to differentiate from biosphere flows)
            regio_process["type"] = "process"
            # add comment
            regio_process["comment"] = (
                f"""This process is a regionalized adaptation of the following process of the ecoinvent database: {activity} | {product} | {region}. No amount values were modified in the regionalization process, only the origin of the flows."""
            )
            # update production exchange
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["code"] = (
                regio_process["code"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["database"] = (
                regio_process["database"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["location"] = (
                regio_process["location"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["input"] = (
                regio_process["database"],
                regio_process["code"],
            )
            # put the regionalized process' share into the global production market
            global_market_activity["exchanges"].append(
                {
                    "amount": producers.loc[prod_country]
                    * regio.distribution_technologies[product][activity],
                    "type": "technosphere",
                    "name": regio_process["name"],
                    "product": regio_process["reference product"],
                    "unit": regio_process["unit"],
                    "location": prod_country,
                    "database": regio.target_db_name,
                    "code": global_market_activity["code"],
                    "input": (regio_process["database"], regio_process["code"]),
                    "output": (
                        global_market_activity["database"],
                        global_market_activity["code"],
                    ),
                }
            )
            return regio_process

        def get_template_input_flags(product, activity, region):
            cache_key = ("intl", product, activity, region)
            if cache_key in template_input_flags_cache:
                return template_input_flags_cache[cache_key]
            process = exact_process_lookup[
                (product, activity, region, regio.regionalized_ecoinvent_db_name)
            ]
            names = [exc.get("name", "") for exc in process["exchanges"]]
            products = [exc.get("product", "") for exc in process["exchanges"]]
            flags = {
                "alu_elec": any(("electricity" in n and "aluminium" in n) for n in names),
                "cobalt_elec": any(("electricity" in n and "cobalt" in n) for n in names),
                "voltage_elec": any(("electricity" in n and "voltage" in n) for n in names),
                "waste": "municipal solid waste" in products,
                "heat_ng": "heat, district or industrial, natural gas" in products,
                "heat_non_ng": ("heat, district or industrial, other than natural gas" in products),
                "heat_small_non_ng": (
                    "heat, central or small-scale, other than natural gas" in products
                ),
            }
            template_input_flags_cache[cache_key] = flags
            return flags

        # loop through technologies and producers
        for technology in possibilities.keys():
            for producer in producers.index:
                # reset regio_process variable
                regio_process = None
                template_region = None
                # if the producing country is available in the geographies of the ecoinvent production technologies
                if producer in possibilities_set[technology] and producer not in ["RoW"]:
                    regio_process = copy_process(product, technology, producer, producer)
                    template_region = producer
                # if a region associated with producing country is available in the geographies of the ecoinvent production technologies
                elif producer in regio.country_to_ecoinvent_regions:
                    for potential_region in regio.country_to_ecoinvent_regions[producer]:
                        if potential_region in possibilities_set[technology]:
                            regio_process = copy_process(
                                product, technology, potential_region, producer
                            )
                            template_region = potential_region
                # otherwise, take either RoW, GLO or a random available geography
                if not regio_process:
                    if "RoW" in possibilities_set[technology]:
                        regio_process = copy_process(product, technology, "RoW", producer)
                        template_region = "RoW"
                    elif "GLO" in possibilities_set[technology]:
                        regio_process = copy_process(product, technology, "GLO", producer)
                        template_region = "GLO"
                    else:
                        if possibilities[technology]:
                            # if no RoW/GLO processes available, take the first available geography by default...
                            regio_process = copy_process(
                                product,
                                technology,
                                possibilities[technology][0],
                                producer,
                            )
                            template_region = possibilities[technology][0]
                            regio.assigned_random_geography.append([product, technology, producer])

                # for each input, we test the presence of said inputs and regionalize that input
                # testing the presence allows to save time if the input in question is just not used by the process
                if regio_process:
                    # aluminium specific electricity input
                    flags = get_template_input_flags(product, technology, template_region)
                    if flags["alu_elec"]:
                        regio_process = regio.change_aluminium_electricity(regio_process, producer)
                    # cobalt specific electricity input
                    elif flags["cobalt_elec"]:
                        regio_process = regio.change_cobalt_electricity(regio_process)
                    # normal electricity input
                    elif flags["voltage_elec"]:
                        regio_process = regio.change_electricity(regio_process, producer)
                    # municipal solid waste input
                    if flags["waste"]:
                        regio_process = regio.change_waste(regio_process, producer)
                    # heat, district or industrial, natural gas input
                    if flags["heat_ng"]:
                        regio_process = regio.change_heat(
                            regio_process,
                            producer,
                            "heat, district or industrial, natural gas",
                        )
                    # heat, district or industrial, other than natural gas input
                    if flags["heat_non_ng"]:
                        regio_process = regio.change_heat(
                            regio_process,
                            producer,
                            "heat, district or industrial, other than natural gas",
                        )
                    # heat, central or small-scale, other than natural gas input
                    if flags["heat_small_non_ng"]:
                        regio_process = regio.change_heat(
                            regio_process,
                            producer,
                            "heat, central or small-scale, other than natural gas",
                        )
                # register the regionalized process within the wurst database
                if regio_process:
                    regio.regioinvent_in_wurst.append(regio_process)

        # add transportation to production market
        for transportation_mode in regio.transportation_modes[product]:
            if transportation_mode not in transport_ref_product_cache:
                transport_ref_product_cache[transportation_mode] = code_to_ref_product.get(
                    transportation_mode
                )
            if not transport_ref_product_cache[transportation_mode]:
                continue
            global_market_activity["exchanges"].append(
                {
                    "amount": regio.transportation_modes[product][transportation_mode],
                    "type": "technosphere",
                    "database": regio.regionalized_ecoinvent_db_name,
                    "code": transportation_mode,
                    "product": transport_ref_product_cache[transportation_mode],
                    "input": (
                        regio.regionalized_ecoinvent_db_name,
                        transportation_mode,
                    ),
                }
            )
        # and register the production market in the wurst database
        regio.regioinvent_in_wurst.append(global_market_activity)

    # -----------------------------------------------------------------------------------------------------------
    # in a second time, we regionalize the most relevant other products, see doc/ to see how we selected those
    with as_file(
        files("regioinvent").joinpath(
            f"data/Regionalization/ei{regio.ecoinvent_version}/relevant_non_traded_products.json"
        )
    ) as file_path:
        with open(file_path, "r") as f:
            relevant_non_traded_products = json.load(f)

    # get all the geographies of regioinvent
    with as_file(
        files("regioinvent").joinpath(
            f"data/Spatialization_of_elementary_flows/ei{regio.ecoinvent_version}/geographies_of_regioinvent.json"
        )
    ) as file_path:
        with open(file_path, "r") as f:
            geographies_needed = json.load(f)

    regio.logger.info(
        "Regionalizing main inputs of non-internationally traded processes of ecoinvent..."
    )
    for product in tqdm(relevant_non_traded_products, leave=True):
        filter_processes = non_market_by_product.get(product, [])

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
        possibilities_set = {tech: set(geos) for tech, geos in possibilities.items()}

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
            process = exact_process_lookup[
                (product, activity, region, regio.regionalized_ecoinvent_db_name)
            ]
            regio_process = _clone_process_template(process)
            # change location
            regio_process["location"] = prod_country
            # change code
            regio_process["code"] = uuid.uuid4().hex
            # change database
            regio_process["database"] = regio.target_db_name
            # add comment
            regio_process["comment"] = (
                f"""This process is a regionalized adaptation of the following process of the ecoinvent database: {activity} | {product} | {region}. No amount values were modified in the regionalization process, only the origin of the flows."""
            )
            # update production exchange
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["code"] = (
                regio_process["code"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["database"] = (
                regio_process["database"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["location"] = (
                regio_process["location"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["input"] = (
                regio_process["database"],
                regio_process["code"],
            )
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
            market_candidates = market_candidates_lookup.get(
                (product, region, regio.regionalized_ecoinvent_db_name), []
            )
            if not market_candidates:
                raise ws.NoResults
            market_process = market_candidates[0]

            regio_process = _clone_process_template(market_process)
            # change location
            regio_process["location"] = prod_country
            # change code
            regio_process["code"] = uuid.uuid4().hex
            # change database
            regio_process["database"] = regio.target_db_name
            # add comment
            regio_process["comment"] = (
                f"""This process is a regionalized adaptation of the following process of the ecoinvent database: {regio_process['name']} | {product} | {region}. No amount values were modified in the regionalization process, only the origin of the flows."""
            )
            # we rename the activity because just having "market for..." is confusing
            regio_process["name"] = "technology mix for " + product
            # update production exchange
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["code"] = (
                regio_process["code"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["database"] = (
                regio_process["database"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["location"] = (
                regio_process["location"]
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["name"] = (
                "technology mix for " + product
            )
            [i for i in regio_process["exchanges"] if i["type"] == "production"][0]["input"] = (
                regio_process["database"],
                regio_process["code"],
            )
            return regio_process

        def get_template_input_flags_non_traded(product, activity, region):
            cache_key = ("nontraded", product, activity, region)
            if cache_key in template_input_flags_cache:
                return template_input_flags_cache[cache_key]
            process = exact_process_lookup[
                (product, activity, region, regio.regionalized_ecoinvent_db_name)
            ]
            names = [exc.get("name", "") for exc in process["exchanges"]]
            products = [exc.get("product", "") for exc in process["exchanges"]]
            flags = {
                "alu_elec": any(("electricity" in n and "aluminium" in n) for n in names),
                "cobalt_elec": any(("electricity" in n and "cobalt" in n) for n in names),
                "voltage_elec": any(("electricity" in n and "voltage" in n) for n in names),
                "waste": "municipal solid waste" in products,
                "heat_ng": "heat, district or industrial, natural gas" in products,
                "heat_non_ng": ("heat, district or industrial, other than natural gas" in products),
                "heat_small_non_ng": (
                    "heat, central or small-scale, other than natural gas" in products
                ),
            }
            template_input_flags_cache[cache_key] = flags
            return flags

        # loop through technologies
        for technology in possibilities.keys():
            # do not regionalize irrelevant processes
            if (product, technology) not in no_inputs_processes_set:
                # loop through geos
                for geo in geographies_needed:
                    # reset regio_process variable
                    regio_process = None
                    template_region = None
                    # if the producing country is available in the geographies of the ecoinvent production technologies
                    if geo in possibilities_set[technology] and geo not in ["RoW"]:
                        regio_process = copy_process(product, technology, geo, geo)
                        template_region = geo
                    # if a region associated with producing country is available in the geographies of the ecoinvent production technologies
                    elif geo in regio.country_to_ecoinvent_regions:
                        for potential_region in regio.country_to_ecoinvent_regions[geo]:
                            if potential_region in possibilities_set[technology]:
                                regio_process = copy_process(
                                    product, technology, potential_region, geo
                                )
                                template_region = potential_region
                    # otherwise, take either RoW, GLO or a random available geography
                    if not regio_process:
                        if "RoW" in possibilities_set[technology]:
                            regio_process = copy_process(product, technology, "RoW", geo)
                            template_region = "RoW"
                        elif "GLO" in possibilities_set[technology]:
                            regio_process = copy_process(product, technology, "GLO", geo)
                            template_region = "GLO"
                        else:
                            if possibilities[technology]:
                                # if no RoW/GLO processes available, take the first available geography by default...
                                regio_process = copy_process(
                                    product,
                                    technology,
                                    possibilities[technology][0],
                                    geo,
                                )
                                template_region = possibilities[technology][0]
                                regio.assigned_random_geography.append([product, technology, geo])

                    # for each input, we test the presence of said inputs and regionalize that input
                    # testing the presence allows to save time if the input in question is just not used by the process
                    if regio_process:
                        # aluminium specific electricity input
                        flags = get_template_input_flags_non_traded(
                            product, technology, template_region
                        )
                        if flags["alu_elec"]:
                            regio_process = regio.change_aluminium_electricity(regio_process, geo)
                        # cobalt specific electricity input
                        elif flags["cobalt_elec"]:
                            regio_process = regio.change_cobalt_electricity(regio_process)
                        # normal electricity input
                        elif flags["voltage_elec"]:
                            regio_process = regio.change_electricity(regio_process, geo)
                        # municipal solid waste input
                        if flags["waste"]:
                            regio_process = regio.change_waste(regio_process, geo)
                        # heat, district or industrial, natural gas input
                        if flags["heat_ng"]:
                            regio_process = regio.change_heat(
                                regio_process,
                                geo,
                                "heat, district or industrial, natural gas",
                            )
                        # heat, district or industrial, other than natural gas input
                        if flags["heat_non_ng"]:
                            regio_process = regio.change_heat(
                                regio_process,
                                geo,
                                "heat, district or industrial, other than natural gas",
                            )
                        # heat, central or small-scale, other than natural gas input
                        if flags["heat_small_non_ng"]:
                            regio_process = regio.change_heat(
                                regio_process,
                                geo,
                                "heat, central or small-scale, other than natural gas",
                            )
                    # register the regionalized process within the wurst database
                    if regio_process:
                        regio.regioinvent_in_wurst.append(regio_process)

        # copy markets and rename them as technology mix
        for geo in geographies_needed:
            # check that this is not a market full or irrelevant products/processes
            if {
                k: v
                for k, v in possibilities.items()
                if (product, k) not in no_inputs_processes_set
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
                            for potential_region in regio.country_to_ecoinvent_regions[geo]:
                                try:
                                    regio_market = copy_market(product, potential_region, geo)
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
                                regio.assigned_random_geography.append([product, "market for", geo])
                # register the regionalized technology mix within the wurst database
                if regio_market:
                    regio.regioinvent_in_wurst.append(regio_market)
