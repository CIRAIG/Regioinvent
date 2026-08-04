import sqlite3


def regionalize_ecoinvent_with_trade(
        regio,
        trade_database_path,
        target_database_name,
        cutoff,
        list_locations_to_keep_local_exchanges,
):
    """
    Function runs all the necessary sub-functions to incorporate trade data within ecoinvent supply chains
    descriptions
    :param trade_database_path: [str] the path to the trade database
    :param target_database_name: [str] the name of the target database name for regioinvent
    :param cutoff: [float] the amount (between 0 and 1) after which exports/imports values of countries will be aggregated
                    into a Rest-of-theWorld aggregate.
    :param list_locations_to_keep_local_exchanges: [list of str] list of region/country codes (e.g., ['US', 'CA-QC'])
            for which local exchanges in ecoinvent should be kept unchanged. This is useful when the user wants to keep
            specific regionalization in ecoinvent for some regions/countries (e.g., CA provinces, US states, etc.).
    :return:
    """

    regio.trade_conn = sqlite3.connect(trade_database_path)
    regio.target_db_name = target_database_name
    regio.regionalized_ecoinvent_db_name = f"{regio.source_db_name} - regionalized"
    regio.cutoff = cutoff
    regio.list_locations_to_keep_local_exchanges = list_locations_to_keep_local_exchanges

    if cutoff > 0.99 or cutoff < 0:
        raise KeyError("cutoff must be between 0 and 0.99")

    if not getattr(regio, "_spatialized_in_memory_ready", False) or not regio.ei_wurst:
        raise KeyError("You need to run the function spatialize_my_ecoinvent() first.")

    # Reset in-memory outputs for fresh regionalization.
    regio.regioinvent_in_wurst = []
    regio._final_database_in_memory = None

    if not regio.ei_in_dict:
        regio.ei_in_dict = {
            (i["reference product"], i["location"], i["name"]): i for i in regio.ei_wurst
        }

    stages = [
        regio.format_trade_data,
        regio.first_order_regionalization,
        regio.create_consumption_markets,
        regio.second_order_regionalization,
        regio.spatialize_elem_flows,
        regio.connect_ecoinvent_to_regioinvent,
        regio.write_database,
    ]
    for stage_fn in stages:
        stage_fn()
