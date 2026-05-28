import collections
import uuid

import bw2data as bd
import pandas as pd


_MISSING = object()


def _as_bw_database_dict(datasets):
    """
    Normalize an in-memory database into the mapping shape expected by Brightway.
    """

    data = {(ds["database"], ds["code"]): ds for ds in datasets}

    for ds in data.values():
        for exc in ds.get("exchanges", []):
            if "input" not in exc and "database" in exc and "code" in exc:
                exc["input"] = (exc["database"], exc["code"])
            if exc.get("type") == "production" and "output" not in exc:
                exc["output"] = (ds["database"], ds["code"])

        ds.pop("categories", None)
        ds.pop("parameters", None)

    return data


def _write_databases_unprocessed_then_process(regio, dbs_to_write):
    """
    Write mutually dependent Brightway databases in two phases:
    raw rows first, processing only after both exist in the project.
    """

    preferences = bd.preferences
    had_allow_incomplete = "allow incomplete imports" in preferences
    original_allow_incomplete = preferences.get("allow incomplete imports", _MISSING)

    preferences["allow incomplete imports"] = True
    if hasattr(preferences, "flush"):
        preferences.flush()

    try:
        for db_name, data in dbs_to_write:
            regio.logger.info(
                f"Writing Brightway database {db_name!r} without processing..."
            )
            bd.Database(db_name).write(data, process=False)

        for db_name, _ in dbs_to_write:
            regio.logger.info(f"Processing Brightway database {db_name!r}...")
            bd.Database(db_name).process()
    finally:
        if had_allow_incomplete:
            preferences["allow incomplete imports"] = original_allow_incomplete
        else:
            preferences.pop("allow incomplete imports", None)
        if hasattr(preferences, "flush"):
            preferences.flush()


def format_trade_data(regio):
    """
    Function extracts and formats the export/import and domestic production data from the trade database
    :return: self.production_data / self.consumption_data
    """

    regio.logger.info("Extracting and formatting trade data...")

    # load import data corrected for re-exports
    import_data = pd.read_sql("SELECT * FROM [Import data]", regio.trade_conn).drop(
        "source", axis=1
    )

    # load export data (that's actually net exports, as in exports - imports)
    net_exports_data = pd.read_sql("SELECT * FROM [Export data]", regio.trade_conn).drop(
        "source", axis=1
    )

    # load domestic production
    regio.domestic_production = pd.read_sql(
        "SELECT * FROM [Domestic production data]", regio.trade_conn
    )

    # concatenate import and domestic data into consumption data
    regio.consumption_data = pd.concat(
        [import_data, regio.domestic_production.drop("source", axis=1)]
    )

    # concatenate net exports and domestic data into production data
    regio.production_data = pd.concat(
        [
            net_exports_data,
            regio.domestic_production.drop(["source"], axis=1),
        ]
    )
    regio.production_data = (
        regio.production_data.groupby(["cmdCode", "refYear", "exporter"]).sum().reset_index()
    )


def write_database_romain(regio, target_db_name=None):
    """
    Write the final in-memory database to Brightway as a single database.
    """

    if not getattr(regio, "_final_database_in_memory", None):
        raise ValueError(
            "No in-memory final database found. Run regionalize_ecoinvent_with_trade() first."
        )

    regio.target_db_name = target_db_name or f"{regio.source_db_name} - regionalized"

    regio.logger.info("Write in-memory database to brightway...")
    regio.logger.info("Normalizing in-memory datasets before write...")

    final_data = {(ds["database"], ds["code"]): ds for ds in regio._final_database_in_memory}

    # Assign fresh UUID codes to every dataset and keep mapping from old -> new.
    old_to_new = {}
    code_to_new_candidates = collections.defaultdict(set)
    for old_key, ds in final_data.items():
        new_code = uuid.uuid4().hex
        old_to_new[old_key] = (regio.target_db_name, new_code)
        if old_key[1] is not None:
            code_to_new_candidates[old_key[1]].add((regio.target_db_name, new_code))
        ds["database"] = regio.target_db_name
        ds["code"] = new_code

    # Resolve code-only fallback only when unambiguous.
    code_to_new = {
        old_code: list(targets)[0]
        for old_code, targets in code_to_new_candidates.items()
        if len(targets) == 1
    }

    # Export as a single database: normalize links to target DB.
    normalized_data = {}
    for _, ds in final_data.items():
        for exc in ds["exchanges"]:
            if exc["type"] in ["technosphere", "production"]:
                exc["database"] = regio.target_db_name
                if exc["type"] == "production":
                    exc["code"] = ds["code"]
                    exc["input"] = (regio.target_db_name, ds["code"])
                else:
                    target = None
                    old_input = exc.get("input")
                    if isinstance(old_input, tuple) and len(old_input) == 2:
                        target = old_to_new.get((old_input[0], old_input[1]))
                    if target is None and "database" in exc and "code" in exc:
                        target = old_to_new.get((exc["database"], exc["code"]))
                    if target is None and "code" in exc:
                        target = code_to_new.get(exc["code"])
                    if target is not None:
                        exc["code"] = target[1]
                        exc["input"] = target
                    elif "code" in exc:
                        # Fallback: still populate an input in target database namespace.
                        exc["input"] = (regio.target_db_name, exc["code"])
            elif "input" not in exc and "database" in exc and "code" in exc:
                exc["input"] = (exc["database"], exc["code"])
            if exc["type"] == "production":
                exc["output"] = (regio.target_db_name, ds["code"])
        ds.pop("categories", None)
        ds.pop("parameters", None)
        normalized_data[(regio.target_db_name, ds["code"])] = ds

    # Ensure biosphere exchanges point to valid flow codes in either biosphere database.
    spatialized_records = [flow.as_dict() for flow in bd.Database(regio.name_spatialized_biosphere)]
    base_biosphere_name = "biosphere3"
    base_records = [flow.as_dict() for flow in bd.Database(base_biosphere_name)]

    spatialized_codes = {flow["code"] for flow in spatialized_records}
    base_codes = {flow["code"] for flow in base_records}

    spatialized_by_name_cat = {
        (flow.get("name"), flow.get("categories")): flow["code"] for flow in spatialized_records
    }
    base_by_name_cat = {
        (flow.get("name"), flow.get("categories")): flow["code"] for flow in base_records
    }
    spatialized_by_name = {}
    for flow in spatialized_records:
        spatialized_by_name.setdefault(flow.get("name"), flow["code"])
    base_by_name = {}
    for flow in base_records:
        base_by_name.setdefault(flow.get("name"), flow["code"])

    for ds in normalized_data.values():
        for exc in ds["exchanges"]:
            if exc.get("type") != "biosphere":
                continue
            code = exc.get("code")
            if code in spatialized_codes:
                exc["database"] = regio.name_spatialized_biosphere
                exc["input"] = (regio.name_spatialized_biosphere, code)
                continue
            if code in base_codes:
                exc["database"] = base_biosphere_name
                exc["input"] = (base_biosphere_name, code)
                continue

            key = (exc.get("name"), exc.get("categories"))
            if key in spatialized_by_name_cat:
                code = spatialized_by_name_cat[key]
                exc["database"] = regio.name_spatialized_biosphere
            elif key in base_by_name_cat:
                code = base_by_name_cat[key]
                exc["database"] = base_biosphere_name
            elif exc.get("name") in spatialized_by_name:
                code = spatialized_by_name[exc.get("name")]
                exc["database"] = regio.name_spatialized_biosphere
            elif exc.get("name") in base_by_name:
                code = base_by_name[exc.get("name")]
                exc["database"] = base_biosphere_name
            else:
                raise KeyError(
                    "Could not resolve biosphere flow code for exchange "
                    f"name={exc.get('name')!r}, categories={exc.get('categories')!r}"
                )
            exc["code"] = code
            exc["input"] = (exc["database"], exc["code"])

    if regio.target_db_name in bd.databases:
        del bd.databases[regio.target_db_name]

    regio.logger.info("Starting Brightway write...")
    bd.Database(regio.target_db_name).write(normalized_data)


def write_database(regio):
    if not getattr(regio, "_spatialized_in_memory_ready", False) or not regio.ei_wurst:
        raise ValueError(
            "No in-memory spatialized ecoinvent found. Run spatialize_my_ecoinvent() first."
        )

    regio.logger.info("Write linked in-memory databases to brightway...")

    dbs_to_write = [
        (
            regio.regionalized_ecoinvent_db_name,
            _as_bw_database_dict(regio.ei_wurst),
        )
    ]

    if regio.regioinvent_in_wurst:
        if not regio.target_db_name:
            raise ValueError(
                "No regioinvent target database name set. "
                "Run regionalize_ecoinvent_with_trade() first."
            )
        dbs_to_write.append(
            (
                regio.target_db_name,
                _as_bw_database_dict(regio.regioinvent_in_wurst),
            )
        )

    _write_databases_unprocessed_then_process(regio, dbs_to_write)


def _connect_ecoinvent_to_regioinvent_in_memory(regio):
    """
    Relink the in-memory spatialized ecoinvent copy to the in-memory regioinvent
    datasets before either database is written to Brightway.
    """

    regio.logger.info("Connecting ecoinvent to regioinvent processes...")

    # as dictionary to speed searching for information
    consumption_markets_data = {
        (i["name"], i["location"]): i
        for i in regio.regioinvent_in_wurst
        if "consumption market" in i["name"]
    }
    regionalized_products = set([i["reference product"] for i in regio.regioinvent_in_wurst])
    techno_mixes = {
        (i["name"], i["location"]): i["code"]
        for i in regio.regioinvent_in_wurst
        if "technology mix" in i["name"]
    }

    for process in regio.ei_wurst:
        # find country/sub-country locations for process, we ignore regions
        location = None
        # for countries (e.g., CA)
        if process["location"] in regio.country_to_ecoinvent_regions.keys():
            location = process["location"]
        # for sub-countries (e.g., CA-QC)
        elif process["location"].split("-")[0] in regio.country_to_ecoinvent_regions.keys():
            location = process["location"].split("-")[0]
        # check if location is not None and not Switzerland
        if location and location != "CH":
            # loop through technosphere exchanges
            for exc in process["exchanges"]:
                if exc.get("type") != "technosphere":
                    continue
                # if the product of the exchange is among the internationally traded commodities
                if exc["product"] in regio.eco_to_hs_class.keys():
                    # get the name of the corresponding consumtion market
                    exc["name"] = "consumption market for " + exc["product"]
                    # get the location of the process
                    exc["location"] = location
                    # if the consumption market exists for the process location
                    if (
                        "consumption market for " + exc["product"],
                        location,
                    ) in consumption_markets_data.keys():
                        exc["database"] = consumption_markets_data[
                            ("consumption market for " + exc["product"], location)
                        ]["database"]
                        exc["code"] = consumption_markets_data[
                            ("consumption market for " + exc["product"], location)
                        ]["code"]
                    # if the consumption market does not exist for the process location, take RoW
                    else:
                        exc["database"] = consumption_markets_data[
                            ("consumption market for " + exc["product"], "RoW")
                        ]["database"]
                        exc["code"] = consumption_markets_data[
                            ("consumption market for " + exc["product"], "RoW")
                        ]["code"]
                    exc["input"] = (exc["database"], exc["code"])
                # if the product of the exchange is among the non-international traded commodities
                elif (
                    exc["product"] in regionalized_products
                    and exc["product"] not in regio.eco_to_hs_class.keys()
                ):
                    tech_key = ("technology mix for " + exc["product"], location)
                    if tech_key not in techno_mixes:
                        tech_key = ("technology mix for " + exc["product"], "RoW")
                    if tech_key in techno_mixes:
                        exc["code"] = techno_mixes[tech_key]
                        exc["database"] = regio.target_db_name
                        exc["name"] = tech_key[0]
                        exc["location"] = tech_key[1]
                        exc["input"] = (exc["database"], exc["code"])

    # aggregating duplicate inputs (e.g., multiple consumption markets RoW callouts)
    for process in regio.ei_wurst:
        # Some technosphere exchanges can still miss an input tuple at this stage.
        # Reconstruct from available database/code metadata before deduplication.
        for exc in process["exchanges"]:
            if (
                exc.get("type") == "technosphere"
                and "input" not in exc
                and "database" in exc
                and "code" in exc
            ):
                exc["input"] = (exc["database"], exc["code"])

        duplicates = [
            item
            for item, count in collections.Counter(
                [
                    (
                        i["input"],
                        i["name"],
                        i["product"],
                        i["location"],
                        i["database"],
                        i["code"],
                    )
                    for i in process["exchanges"]
                    if i.get("type") == "technosphere"
                ]
            ).items()
            if count > 1
        ]

        for duplicate in duplicates:
            total = sum(
                [
                    i["amount"]
                    for i in process["exchanges"]
                    if i.get("type") == "technosphere" and i["input"] == duplicate[0]
                ]
            )
            process["exchanges"] = [
                i
                for i in process["exchanges"]
                if not (i.get("type") == "technosphere" and i["input"] == duplicate[0])
            ]
            process["exchanges"].append(
                {
                    "amount": total,
                    "type": "technosphere",
                    "input": duplicate[0],
                    "name": duplicate[1],
                    "product": duplicate[2],
                    "location": duplicate[3],
                    "database": duplicate[4],
                    "code": duplicate[5],
                }
            )

    # we also change production processes of ecoinvent for regionalized production processes of regioinvent
    regio_dict = {
        (
            i["reference product"],
            i["name"],
            i["location"],
        ): i["code"]
        for i in regio.regioinvent_in_wurst
    }

    for process in regio.ei_wurst:
        for exc in process["exchanges"]:
            if exc.get("type") != "technosphere":
                continue
            if exc["product"] in regio.eco_to_hs_class.keys():
                # same thing, we don't touch Swiss processes
                if exc["location"] not in ["RoW", "CH"]:
                    match_key = (exc["product"], exc["name"], exc["location"])
                    if match_key in regio_dict:
                        exc["database"] = regio.target_db_name
                        exc["code"] = regio_dict[match_key]
                        exc["input"] = (exc["database"], exc["code"])

    # Build final in-memory database that can later be inspected or written.
    regio._final_database_in_memory = list(regio.ei_wurst) + list(regio.regioinvent_in_wurst)


def connect_ecoinvent_to_regioinvent_romain(regio):
    return _connect_ecoinvent_to_regioinvent_in_memory(regio)


def connect_ecoinvent_to_regioinvent(regio):
    """
    Relink the in-memory spatialized ecoinvent copy to regioinvent before the
    two dependent databases are written and processed.
    """

    return _connect_ecoinvent_to_regioinvent_in_memory(regio)


def write_regioinvent_to_database(regio):
    """Backward-compatible alias for write_database()."""
    return write_database(regio)
