import collections
import uuid

import pandas as pd
from tqdm import tqdm


def create_consumption_markets(regio):
    """
    Function creating consumption markets for each regionalized process
    :return:  regio.regioinvent_in_wurst with new regionalized processes
    """

    regio.logger.info("Creating consumption markets for internationally-traded products...")

    # change to dictionary to speed searching for info
    regio.regioinvent_in_dict = {
        tech: []
        for tech in [(i["reference product"], i["location"]) for i in regio.regioinvent_in_wurst]
    }
    # populate the empty dictionary
    for process in regio.regioinvent_in_wurst:
        regio.regioinvent_in_dict[(process["reference product"], process["location"])].append(
            {process["name"]: process}
        )

    # Precompute mean trade quantities once for all products to avoid repeated groupby work.
    consumption_by_cmd = (
        regio.consumption_data.groupby(["cmdCode", "importer", "exporter"])["quantity (t)"]
        .mean()
        .sort_index()
    )
    # Precompute source text once per cmdCode.
    sources = set(zip(regio.domestic_production.cmdCode, regio.domestic_production.source))
    source_by_cmd = {}
    # Loop through your zipped data
    for code, source in sources:
        # Check if "PRODCOM" is in the source string
        if "PRODCOM" in source:
            source_by_cmd[code] = "PRODCOM & EXIOBASE"
        else:
            # Only assign if the code isn't already set to "PRODCOM"
            # (This prevents a non-PRODCOM source from overwriting a PRODCOM one)
            if source_by_cmd.get(code) != "PRODCOM & EXIOBASE":
                source_by_cmd[code] = source
    replacements = {
        "FAOSTAT": "FAOSTAT",
        "USGS": "USGS",
        "OICA": "OICA",
        "World Steel Association": "World Steel"
    }

    source_by_cmd = {
        code: next((target for sub, target in replacements.items() if sub in source), "EXIOBASE")
        for code, source in source_by_cmd.items()
    }

    for product in tqdm(regio.eco_to_hs_class, leave=True):
        cmd_code = regio.eco_to_hs_class[product]
        # filter the product in regio.consumption_data
        try:
            cmd_consumption_data = consumption_by_cmd.xs(cmd_code, level=0).to_frame("quantity (t)")
        except KeyError:
            # No trade data for this product.
            continue
        # change to relative values
        consumers = (
            cmd_consumption_data.groupby(level=0).sum() / cmd_consumption_data.sum().sum()
        ).sort_values(by="quantity (t)", ascending=False)
        # only keep consumers till the user-defined cut-off of total consumption
        limit = (
            consumers.index.get_loc(consumers[consumers.cumsum() > regio.cutoff].dropna().index[0])
            + 1
        )
        # aggregate the rest
        remainder = cmd_consumption_data.loc[consumers.index[limit:]].groupby(level=1).sum()
        cmd_consumption_data = cmd_consumption_data.loc[consumers.index[:limit]]
        # assign the aggregate to RoW location
        cmd_consumption_data = pd.concat(
            [cmd_consumption_data, pd.concat([remainder], keys=["RoW"])]
        )
        cmd_consumption_data.index = pd.MultiIndex.from_tuples(
            [i for i in cmd_consumption_data.index]
        )
        cmd_consumption_data = cmd_consumption_data.sort_index()
        consumers_index = cmd_consumption_data.index.get_level_values(0)
        # Normalize import shares once for all consumers.
        cmd_consumption_data["quantity (t)"] = cmd_consumption_data["quantity (t)"] / (
            cmd_consumption_data.groupby(level=0)["quantity (t)"].transform("sum")
        )
        # Aggregate potential duplicate RoW rows once.
        if "RoW" in consumers_index:
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

        # Build O(1) technology->code lookup by trading partner.
        codes_by_partner = {}
        for partner in regio.created_geographies[product]:
            entries = regio.regioinvent_in_dict.get((product, partner), [])
            if not entries:
                continue
            codes_by_partner[partner] = {
                list(item.keys())[0]: list(item.values())[0]["code"] for item in entries
            }
        row_codes = codes_by_partner.get("RoW", {})
        tech_distribution = regio.distribution_technologies[product]

        # loop through each selected consumers of the commodity
        for consumer in cmd_consumption_data.index.levels[0]:
            # create the process information
            new_import_data = {
                "name": "consumption market for " + product,
                "reference product": product,
                "location": consumer,
                "type": "process",
                "unit": regio.unit[product],
                "code": uuid.uuid4().hex,
                "comment": f"""This process represents the consumption market of {product} in {consumer}. The shares were determined based on two aspects. The imports of the commodity {regio.eco_to_hs_class[product]} taken from the BACI database (average over the years 2020, 2021, 2022, 2023, 2024). The domestic consumption data was extracted/estimated from {source_by_cmd.get(cmd_code)}.""",
                "database": regio.target_db_name,
                "exchanges": [],
            }

            # create the production exchange
            new_import_data["exchanges"].append(
                {
                    "amount": 1,
                    "type": "production",
                    "input": (
                        regio.target_db_name,
                        new_import_data["code"],
                    ),
                }
            )
            # identify regionalized processes that were created in regio.first_order_regionalization()
            available_trading_partners = regio.created_geographies[product]
            # loop through the selected consumers
            consumer_shares = cmd_consumption_data.loc[consumer, "quantity (t)"]
            exchange_amounts = collections.defaultdict(float)
            exchange_templates = {}
            for trading_partner, partner_share in consumer_shares.items():
                # check if a regionalized process exist for that consumer
                if trading_partner in available_trading_partners:
                    partner_codes = codes_by_partner.get(trading_partner, row_codes)
                    # loop through available technologies to produce the commodity
                    for technology in tech_distribution:
                        code = partner_codes[technology]
                        # get the share
                        share = tech_distribution[technology]
                        inp = (regio.target_db_name, code)
                        exchange_amounts[inp] += partner_share * share
                        if inp not in exchange_templates:
                            exchange_templates[inp] = {
                                "type": "technosphere",
                                "input": inp,
                                "name": product,
                            }
                # if a regionalized process does not exist for consumer, take the RoW aggregate
                else:
                    partner_codes = row_codes
                    # loop through available technologies to produce the commodity
                    for technology in tech_distribution:
                        code = partner_codes[technology]
                        # get the share
                        share = tech_distribution[technology]
                        inp = (regio.target_db_name, code)
                        exchange_amounts[inp] += partner_share * share
                        if inp not in exchange_templates:
                            exchange_templates[inp] = {
                                "type": "technosphere",
                                "input": inp,
                                "name": product,
                            }
            # add transportation to consumption market
            for transportation_mode in regio.transportation_modes[product]:
                inp = (
                    regio.regionalized_ecoinvent_db_name,
                    transportation_mode,
                )
                exchange_amounts[inp] += regio.transportation_modes[product][transportation_mode]
                if inp not in exchange_templates:
                    exchange_templates[inp] = {
                        "type": "technosphere",
                        "input": inp,
                    }

            for inp, amount in exchange_amounts.items():
                exc = dict(exchange_templates[inp])
                exc["amount"] = amount
                new_import_data["exchanges"].append(exc)
            # add to database in wurst
            regio.regioinvent_in_wurst.append(new_import_data)
