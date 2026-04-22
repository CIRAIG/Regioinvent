import os
from dataclasses import dataclass
from pathlib import Path

import bw2calc as bc
import bw2data as bd
import pytest

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class ActivitySpec:
    name: str
    reference_product: str
    location: str
    expected_score: float


TARGET_ACTIVITIES: tuple[ActivitySpec, ...] = (
    ActivitySpec(
        name="consumption market for ventilation system, decentralized, 6 x 120 m3/h, polyethylene ducts, with earth tube heat exchanger",
        reference_product="ventilation system, decentralized, 6 x 120 m3/h, polyethylene ducts, with earth tube heat exchanger",
        location="IN",
        expected_score=11111.221433415523,
    ),
    ActivitySpec(
        name="consumption market for gold",
        reference_product="gold",
        location="ZW",
        expected_score=49751.99391503114,
    ),
    ActivitySpec(
        name="consumption market for ventilation of dwellings, central, 1 x 720 m3/h",
        reference_product="ventilation of dwellings, central, 1 x 720 m3/h",
        location="TZ",
        expected_score=3.0292988252818187,
    ),
    ActivitySpec(
        name="consumption market for photovoltaic slanted-roof installation, 3kWp, single-Si, laminated, integrated, on roof",
        reference_product="photovoltaic slanted-roof installation, 3kWp, single-Si, laminated, integrated, on roof",
        location="FR",
        expected_score=8066.13128068786,
    ),
    ActivitySpec(
        name="consumption market for isoproturon",
        reference_product="isoproturon",
        location="IE",
        expected_score=6.717140836099581,
    ),
    ActivitySpec(
        name="consumption market for anthranilic acid",
        reference_product="anthranilic acid",
        location="CZ",
        expected_score=5.532117529197189,
    ),
)


def _pick_method() -> tuple[str, ...]:

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


def test_regio_outputs_only_regression():
    project_name = os.getenv("REGIO_TEST_BW_PROJECT", "bw2project")
    regio_db_name = os.getenv("REGIO_TEST_REGIO_DB_NAME", "Regioinvent")

    bd.projects.set_current(project_name)

    if regio_db_name not in bd.databases:
        pytest.skip(
            f"Database {regio_db_name!r} not found in project {project_name!r}. "
            "Run regionalization first."
        )

    db_len = len(bd.Database(regio_db_name))
    assert db_len == 251593, f"Unexpected {regio_db_name} size: {db_len}"

    print("Running regression test for regio outputs only...")
    method = _pick_method()
    for i, spec in enumerate(TARGET_ACTIVITIES):
        act = _find_activity(regio_db_name, spec)
        lca = bc.LCA({act: 1}, method)
        lca.lci(factorize=False)
        lca.lcia()
        score = float(lca.score)
        print(f"Activity: {spec.name}, {spec.reference_product}, {spec.location} - Score: {score}")
        assert score == pytest.approx(spec.expected_score, rel=1e-8, abs=1e-12)
