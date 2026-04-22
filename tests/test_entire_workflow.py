import os
from dataclasses import dataclass
from pathlib import Path

import bw2calc as bc
import bw2data as bd
import pytest

import regioinvent

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class ActivitySpec:
    key: str
    name: str
    reference_product: str
    location: str
    expected_score: float


TARGET_ACTIVITIES: tuple[ActivitySpec, ...] = (
    ActivitySpec(
        key="ventilation_system_decentralized_in",
        name="consumption market for ventilation system, decentralized, 6 x 120 m3/h, polyethylene ducts, with earth tube heat exchanger",
        reference_product="ventilation system, decentralized, 6 x 120 m3/h, polyethylene ducts, with earth tube heat exchanger",
        location="IN",
        expected_score=11111.221433415523,
    ),
    ActivitySpec(
        key="gold_zw",
        name="consumption market for gold",
        reference_product="gold",
        location="ZW",
        expected_score=49751.99391503114,
    ),
    ActivitySpec(
        key="ventilation_dwellings_central_tz",
        name="consumption market for ventilation of dwellings, central, 1 x 720 m3/h",
        reference_product="ventilation of dwellings, central, 1 x 720 m3/h",
        location="TZ",
        expected_score=3.0292988252818187,
    ),
    ActivitySpec(
        key="pv_slanted_roof_fr",
        name="consumption market for photovoltaic slanted-roof installation, 3kWp, single-Si, laminated, integrated, on roof",
        reference_product="photovoltaic slanted-roof installation, 3kWp, single-Si, laminated, integrated, on roof",
        location="FR",
        expected_score=8066.13128068786,
    ),
    ActivitySpec(
        key="isoproturon_ie",
        name="consumption market for isoproturon",
        reference_product="isoproturon",
        location="IE",
        expected_score=6.717140836099581,
    ),
    ActivitySpec(
        key="anthranilic_acid_cz",
        name="consumption market for anthranilic acid",
        reference_product="anthranilic acid",
        location="CZ",
        expected_score=5.532117529197189,
    ),
)


def _pick_method() -> tuple:

    return ('IPCC 2021', 'climate change: fossil, including SLCFs', 'global warming potential (GWP100)')


def _find_activity(database_name: str, spec: ActivitySpec):
    db = bd.Database(database_name)
    for act in db:
        ds = act.as_dict()
        if (
            ds.get("name") == spec.name
            and ds.get("reference product") == spec.reference_product
            and ds.get("location") == spec.location
        ):
            return act
    raise AssertionError(
        f"Activity not found in {database_name!r}: "
        f"name={spec.name!r}, reference product={spec.reference_product!r}, "
        f"location={spec.location!r}"
    )


@pytest.fixture(scope="session")
def configured_regio():
    if os.getenv("RUN_REGIOINVENT_E2E") != "1":
        pytest.skip("Set RUN_REGIOINVENT_E2E=1 to run this slow integration test.")

    project_name = os.getenv("REGIO_TEST_BW_PROJECT", "bw2project")
    ecoinvent_db = os.getenv("REGIO_TEST_ECOINVENT_DB", "ecoinvent-3.10.1-cutoff")
    ecoinvent_version = os.getenv("REGIO_TEST_ECOINVENT_VERSION", "3.10.1")
    regio_db_name = os.getenv("REGIO_TEST_REGIO_DB_NAME", "Regioinvent")
    trade_db_path = os.getenv("REGIO_TEST_TRADE_DB_PATH")
    cutoff = float(os.getenv("REGIO_TEST_CUTOFF", "0.99"))

    if not trade_db_path:
        pytest.skip("Set REGIO_TEST_TRADE_DB_PATH to the trade SQLite database path.")
    if not Path(trade_db_path).exists():
        pytest.skip(f"Trade DB file not found: {trade_db_path}")

    bd.projects.set_current(project_name)

    regio = regioinvent.Regioinvent(
        bw_project_name=project_name,
        ecoinvent_database_name=ecoinvent_db,
        ecoinvent_version=ecoinvent_version,
    )

    # Same workflow as doc/demo.ipynb
    regio.spatialize_my_ecoinvent()
    regio.import_fully_regionalized_impact_method()
    regio.regionalize_ecoinvent_with_trade(
        trade_database_path=trade_db_path,
        cutoff=cutoff,
    )
    regio.write_database(target_db_name=regio_db_name)

    return regio


def test_demo_workflow_lca_regression(configured_regio):
    method = _pick_method()
    regio_db_name = configured_regio.target_db_name
    db_len = len(bd.Database(regio_db_name))
    assert db_len == 251593, f"Unexpected {regio_db_name} size: {db_len}"

    if os.getenv("REGIO_TEST_ASSERT_SCORES", "0") != "1":
        pytest.skip(
            "Set REGIO_TEST_ASSERT_SCORES=1 to run slow LCA score regression checks."
        )

    for i, spec in enumerate(TARGET_ACTIVITIES):
        act = _find_activity(regio_db_name, spec)
        if i == 0:
            lca = bc.LCA({act: 1}, method)
            lca.lci(factorize=True)
            lca.lcia()
        else:
            lca.redo_lcia({act: 1})
        score = float(lca.score)
        print(f"Activity: {spec.name}, {spec.reference_product}, {spec.location} - Score: {score}")
        assert score == pytest.approx(spec.expected_score, rel=1e-8, abs=1e-12)
