#!/usr/bin/env python3
"""
Try iterative solvers for a very large sparse technosphere system A x = b.

Focus:
- GMRES / BiCGSTAB (nonsymmetric Krylov)
- Optional preconditioning: Jacobi (diag) and ILU (spilu)

Notes:
- For 500k x 500k, ILU may or may not be feasible depending on memory/fill.
- Always start with cheap preconditioners (Jacobi) and a looser tolerance,
  then tighten if needed.

Brightway matrix build path (SQL -> sparse matrix):
1. `bw2data.backends.base.SQLiteBackend.process` reads Activity/Exchange rows from SQLite
   (`ActivityDataset`, `ExchangeDataset`) via `get_technosphere_*_qs`.
2. Exchanges are written to a processed `bw_processing` datapackage (`processed/*.zip`) as
   `technosphere_matrix` vectors with row/col integer ids and values.
3. `bw2calc.LCA.load_lci_data` builds `matrix_utils.MappedMatrix(matrix='technosphere_matrix')`.
4. `MappedMatrix` maps integer ids to contiguous matrix coordinates and materializes a SciPy
   sparse matrix (`coo` -> `csr`) available as `lca.technosphere_matrix`.
"""

from __future__ import annotations

import argparse
import ast
import random
import time
import warnings

import numpy as np
import scipy.sparse as sps
import scipy.sparse.linalg as spla


def _as_csc(A: sps.spmatrix) -> sps.csc_matrix:
    """Ensure CSC + clean structure for solvers."""
    if not sps.isspmatrix(A):
        raise TypeError("A must be a SciPy sparse matrix.")
    A = A.tocsc(copy=False)
    A.sum_duplicates()
    A.eliminate_zeros()
    A.sort_indices()
    return A


def _residual_norm(A: sps.spmatrix, x: np.ndarray, b: np.ndarray) -> float:
    r = b - A @ x
    return float(np.linalg.norm(r))


def _report(header: str, t: float, info: int, res: float, bnorm: float) -> None:
    rel = res / (bnorm + 1e-300)
    print(f"\n=== {header} ===")
    print(f"wall time: {t:,.2f} s")
    print(f"info code: {info}  (0 means converged; >0 means iter limit; <0 breakdown)")
    print(f"||r||2   : {res: .3e}")
    print(f"||r||/||b||: {rel: .3e}")


def solve_with_brightway_direct(A: sps.spmatrix, b: np.ndarray) -> tuple[np.ndarray, int, float]:
    """Direct sparse solve using bw2calc's configured backend (PARDISO/UMFPACK/SciPy)."""
    from bw2calc import spsolve as bw_spsolve

    t0 = time.time()
    x = bw_spsolve(A, b)
    t = time.time() - t0
    if not isinstance(x, np.ndarray):
        x = np.asarray(x, dtype=np.float64)
    return x, 0, t


def solve_with_gmres(
    A: sps.spmatrix,
    b: np.ndarray,
    M: spla.LinearOperator | None = None,
    rtol: float = 1e-8,
    atol: float = 0.0,
    restart: int = 50,
    maxiter: int = 500,
) -> tuple[np.ndarray, int, float]:
    """GMRES solve with optional preconditioner."""
    it = {"k": 0}

    def cb(_):
        it["k"] += 1
        if it["k"] % 10 == 0:
            print(f"  GMRES iter ~{it['k']}")

    t0 = time.time()
    x, info = spla.gmres(
        A,
        b,
        M=M,
        restart=restart,
        maxiter=maxiter,
        rtol=rtol,
        atol=atol,
        callback=cb,
        callback_type="legacy",
    )
    t = time.time() - t0
    return x, info, t


def solve_with_bicgstab(
    A: sps.spmatrix,
    b: np.ndarray,
    M: spla.LinearOperator | None = None,
    rtol: float = 1e-8,
    atol: float = 0.0,
    maxiter: int = 2000,
) -> tuple[np.ndarray, int, float]:
    """BiCGSTAB solve with optional preconditioner."""
    it = {"k": 0}

    def cb(_):
        it["k"] += 1
        if it["k"] % 50 == 0:
            print(f"  BiCGSTAB iter ~{it['k']}")

    t0 = time.time()
    x, info = spla.bicgstab(A, b, M=M, maxiter=maxiter, rtol=rtol, atol=atol, callback=cb)
    t = time.time() - t0
    return x, info, t


def make_jacobi_precond(A: sps.csc_matrix) -> spla.LinearOperator:
    """Jacobi (diagonal) preconditioner: M^{-1} x = x / diag(A)."""
    d = A.diagonal().astype(np.float64, copy=False)
    if np.any(d == 0):
        raise ValueError("Zero on diagonal: cannot build Jacobi preconditioner.")
    dinv = 1.0 / d

    def mv(x: np.ndarray) -> np.ndarray:
        return dinv * x

    return spla.LinearOperator(A.shape, matvec=mv, dtype=np.float64)


def make_ilu_precond(
    A: sps.csc_matrix,
    drop_tol: float = 1e-3,
    fill_factor: float = 5.0,
    diag_pivot_thresh: float = 0.0,
) -> tuple[spla.LinearOperator, float]:
    """
    ILU preconditioner via spilu.

    Parameters to tune:
    - drop_tol: larger => sparser ILU (cheaper, weaker)
    - fill_factor: larger => denser ILU (more memory, stronger)
    - diag_pivot_thresh: can help stability for some matrices (0..1)

    Returns:
    - M: LinearOperator for preconditioning
    - build_time: seconds
    """
    # spilu can emit warnings; capture them but show if needed
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        ilu = spla.spilu(
            A,
            drop_tol=drop_tol,
            fill_factor=fill_factor,
            diag_pivot_thresh=diag_pivot_thresh,
        )
    build_time = time.time() - t0

    def mv(x: np.ndarray) -> np.ndarray:
        return ilu.solve(x)

    M = spla.LinearOperator(A.shape, matvec=mv, dtype=np.float64)
    return M, build_time


def _load_from_brightway(
    project: str,
    demand_db: str,
    demand_code: str | None,
    demand_amount: float,
    method_key: tuple | None = None,
    random_seed: int | None = None,
) -> tuple[object, sps.spmatrix, np.ndarray, tuple[str, str]]:
    """Build technosphere matrix and RHS using Brightway's native pipeline."""
    from bw2calc import LCA
    from bw2data import Database
    from bw2data import projects

    projects.set_current(project)

    if demand_code is None:
        db = Database(demand_db)

        # bw2data.Database.random() uses Python's global `random` module and has no
        # explicit seed parameter, so seed locally and restore state if requested.
        rng_state = random.getstate()
        if random_seed is not None:
            random.seed(random_seed)

        try:
            node = db.random()
            if node is not None:
                demand_code = node["code"]
                print(
                    "Using random demand dataset via Database.random(): "
                    f"({demand_db}, {demand_code}), type={node.get('type')}"
                )
        finally:
            if random_seed is not None:
                random.setstate(rng_state)

        if demand_code is None:
            raise ValueError(
                f"Could not sample a dataset with Database.random() from '{demand_db}'; "
                "please pass --demand-code explicitly."
            )

    demand = {(demand_db, demand_code): demand_amount}

    lca = LCA(demand=demand, method=method_key)
    lca.load_lci_data()  # Builds `lca.technosphere_matrix` via matrix_utils.MappedMatrix
    lca.build_demand_array()

    return (
        lca,
        lca.technosphere_matrix,
        np.asarray(lca.demand_array, dtype=np.float64),
        (demand_db, demand_code),
    )


def _solution_distance(x: np.ndarray, x_ref: np.ndarray) -> tuple[float, float]:
    delta = x - x_ref
    abs_norm = float(np.linalg.norm(delta))
    rel_norm = abs_norm / (float(np.linalg.norm(x_ref)) + 1e-300)
    return abs_norm, rel_norm


def _compute_score(
    supply: np.ndarray, biosphere_matrix: sps.spmatrix, characterization_matrix: sps.spmatrix
) -> float:
    inventory = biosphere_matrix @ supply
    characterized_inventory = characterization_matrix @ inventory
    return float(np.asarray(characterized_inventory).sum())


def _parse_method_arg(method_str: str | None) -> tuple | None:
    if method_str is None:
        return None

    try:
        parsed = ast.literal_eval(method_str)
    except Exception as exc:
        raise ValueError(
            "--method must be a Python tuple literal, e.g. "
            "\"('IPCC 2021', 'climate change', 'global warming potential (GWP100)')\""
        ) from exc

    if not isinstance(parsed, tuple):
        raise ValueError("--method must evaluate to a tuple.")

    return parsed


def _parse_rtol_values(value: str | None) -> list[float]:
    if value is None:
        return [1e-6, 1e-8, 1e-10]

    parsed = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        parsed.append(float(part))

    if len(parsed) < 2:
        raise ValueError("--rtol-values must contain at least two comma-separated values.")
    return parsed


def _pick_default_method() -> tuple:
    from bw2data import methods

    primary = []
    for method in methods:
        text = str(method).lower()
        if "ipcc 2021" in text and "fossil" in text:
            primary.append(method)

    if primary:
        return sorted(primary)[0]

    raise ValueError(
        "Couldn't find any method containing both 'ipcc 2021' and 'fossil' in this project."
    )


def _print_all_methods() -> None:
    from bw2data import methods

    print("\nAvailable LCIA methods in project:")
    for method in sorted(methods):
        print(f"  {method}")


def _pick_random_activity_codes(
    demand_db: str, count: int, random_seed: int | None = None
) -> list[str]:
    from bw2data import Database

    if count < 1:
        raise ValueError("--num-activities must be >= 1.")

    db = Database(demand_db)
    codes: list[str] = []
    seen: set[str] = set()

    rng_state = random.getstate()
    if random_seed is not None:
        random.seed(random_seed)

    try:
        attempts = 0
        max_attempts = max(1000, count * 200)
        while len(codes) < count and attempts < max_attempts:
            attempts += 1
            node = db.random()
            if node is None:
                continue
            code = node["code"]
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
            print(
                f"Selected random activity {len(codes)}/{count}: "
                f"({demand_db}, {code}), type={node.get('type')}"
            )
    finally:
        if random_seed is not None:
            random.setstate(rng_state)

    if len(codes) < count:
        raise ValueError(
            f"Could only sample {len(codes)} unique activities from '{demand_db}' "
            f"after {max_attempts} attempts (requested {count})."
        )

    return codes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Brightway project name")
    parser.add_argument("--demand-db", help="Demand dataset database name")
    parser.add_argument(
        "--demand-code",
        help="Demand dataset code. If omitted, a random dataset code from --demand-db is used.",
    )
    parser.add_argument(
        "--demand-amount",
        type=float,
        default=1.0,
        help="Demand amount (default: 1.0)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible random demand-code selection.",
    )
    parser.add_argument(
        "--num-activities",
        type=int,
        default=3,
        help="Number of random activities to benchmark when --demand-code is not set (default: 3).",
    )
    parser.add_argument(
        "--solver",
        choices=("direct", "iterative", "all"),
        default="all",
        help="`direct`: direct only; `iterative`: GMRES+Jacobi only; `all`: both.",
    )
    parser.add_argument(
        "--method",
        default=None,
        help=(
            "LCIA method tuple literal used for final score comparison, e.g. "
            "\"('IPCC 2021', 'climate change', 'global warming potential (GWP100)')\"."
        ),
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=1e-8,
        help="Legacy single tolerance for iterative solver; ignored if --rtol-values is given.",
    )
    parser.add_argument(
        "--rtol-values",
        default="1e-6,1e-8,1e-10",
        help="Comma-separated GMRES tolerances to sweep (e.g. '1e-6,1e-8,1e-10').",
    )
    parser.add_argument(
        "--solution-rtol",
        type=float,
        default=1e-5,
        help="Relative tolerance for iterative solution check vs direct solve (default: 1e-5).",
    )
    parser.add_argument(
        "--solution-atol",
        type=float,
        default=1e-8,
        help="Absolute tolerance for iterative solution check vs direct solve (default: 1e-8).",
    )
    parser.add_argument(
        "--show-xsim",
        action="store_true",
        help="Show x-vector similarity columns in the final summary table.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    method_key = _parse_method_arg(args.method)
    rtol_values = _parse_rtol_values(args.rtol_values) if args.rtol_values else [args.rtol]
    from bw2data import projects

    if not (args.project and args.demand_db):
        raise NotImplementedError(
            "Provide --project and --demand-db. --demand-code is optional."
        )

    projects.set_current(args.project)


    if method_key is None:
        method_key = _pick_default_method()
        print(f"Auto-selected LCIA method: {method_key}")
    else:
        print(f"Using LCIA method from --method: {method_key}")

    if args.demand_code:
        demand_codes = [args.demand_code]
        print(f"Using explicit demand activity: ({args.demand_db}, {args.demand_code})")
    else:
        demand_codes = _pick_random_activity_codes(
            demand_db=args.demand_db,
            count=args.num_activities,
            random_seed=args.random_seed,
        )
        print(f"Benchmarking {len(demand_codes)} random activities.")
    for idx, demand_code in enumerate(demand_codes, start=1):
        print("\n" + "=" * 88)
        print(
            f"Activity {idx}/{len(demand_codes)}: ({args.demand_db}, {demand_code}), "
            f"amount={args.demand_amount}"
        )
        print("=" * 88)

        # -----------------------------------------------------------------
        # 1) Load A and b with Brightway (SQL -> datapackage -> MappedMatrix)
        # -----------------------------------------------------------------
        lca, A, b, selected_key = _load_from_brightway(
            project=args.project,
            demand_db=args.demand_db,
            demand_code=demand_code,
            demand_amount=args.demand_amount,
            method_key=method_key,
            random_seed=None,
        )
        print(f"Demand used for all strategies: {selected_key}, amount={args.demand_amount}")

        # -----------------------------------------------------------------
        # 2) Preprocess
        # -----------------------------------------------------------------
        A = _as_csc(A)
        b = np.asarray(b, dtype=np.float64)
        assert A.shape[0] == A.shape[1] == b.shape[0]

        n = A.shape[0]
        nnz = A.nnz
        print(f"A: {n:,} x {n:,}, nnz={nnz:,}, density={nnz/(n*n):.3e}")

        bnorm = float(np.linalg.norm(b))
        print(f"||b||2 = {bnorm:.3e}")

        biosphere_matrix = lca.biosphere_matrix
        lca.load_lcia_data()
        characterization_matrix: sps.spmatrix = lca.characterization_matrix
        print(f"LCIA method used for score comparison: {method_key}")

        rows: list[tuple[str, float, float, int, float, float, float, float, str, float, float, str]] = []
        x_direct: np.ndarray | None = None
        score_direct: float | None = None

        def record_result(
            label: str,
            x: np.ndarray,
            info: int,
            solve_time: float,
            build_time: float = 0.0,
        ) -> None:
            total_time = solve_time + build_time
            res = _residual_norm(A, x, b)
            rel = res / (bnorm + 1e-300)

            if x_direct is not None and not label.startswith("Direct"):
                abs_dx, rel_dx = _solution_distance(x, x_direct)
                similar = np.allclose(
                    x,
                    x_direct,
                    rtol=args.solution_rtol,
                    atol=args.solution_atol,
                )
                sim_text = "PASS" if similar else "FAIL"
            else:
                abs_dx, rel_dx, sim_text = np.nan, np.nan, "n/a"

            score = _compute_score(x, biosphere_matrix, characterization_matrix)
            if score_direct is not None and not label.startswith("Direct"):
                abs_ds = abs(score - score_direct)
                rel_ds = abs_ds / (abs(score_direct) + 1e-300)
                score_close = np.isclose(
                    score,
                    score_direct,
                    rtol=args.solution_rtol,
                    atol=args.solution_atol,
                )
                score_text = "PASS" if score_close else "FAIL"
            else:
                rel_ds, score_text = np.nan, "n/a"

            rows.append(
                (
                    label,
                    solve_time,
                    total_time,
                    info,
                    res,
                    rel,
                    abs_dx,
                    rel_dx,
                    sim_text,
                    score,
                    rel_ds,
                    score_text,
                )
            )
            _report(label, total_time, info, res, bnorm)
            if x_direct is not None and not label.startswith("Direct"):
                print(
                    f"solution check [{label}] vs direct: "
                    f"{sim_text} (||dx||2={abs_dx:.3e}, ||dx||/||x_direct||={rel_dx:.3e})"
                )
            print(f"score [{label}]: {score:.12e}")
            if score_direct is not None and not label.startswith("Direct"):
                print(
                    f"score check [{label}] vs direct: {score_text} "
                    f"(|ds|/|s_direct|={rel_ds:.3e})"
                )

        if args.solver in ("direct", "all"):
            x, info, t = solve_with_brightway_direct(A, b)
            x_direct = x.copy()
            score_direct = _compute_score(x_direct, biosphere_matrix, characterization_matrix)
            record_result("Direct (bw2calc.spsolve)", x, info, solve_time=t)

        if args.solver in ("iterative", "all") and x_direct is None:
            x_ref, info_ref, t_ref = solve_with_brightway_direct(A, b)
            x_direct = x_ref.copy()
            score_direct = _compute_score(x_direct, biosphere_matrix, characterization_matrix)
            print(
                f"\nComputed direct reference for solution checks "
                f"(time: {t_ref:.2f} s, info: {info_ref})."
            )
            record_result("Direct reference (check only)", x_ref, info_ref, solve_time=t_ref)

        if args.solver in ("iterative", "all"):
            Mj = make_jacobi_precond(A)
            print(f"GMRES + Jacobi tolerance sweep: {rtol_values}")
            for tol in rtol_values:
                x, info, t = solve_with_gmres(A, b, M=Mj, rtol=tol, restart=50, maxiter=300)
                record_result(f"GMRES + Jacobi (rtol={tol:.0e})", x, info, solve_time=t)

        if rows:
            print("\n=== Summary ===")
            if args.show_xsim:
                print(
                    f"{'strategy':44s} {'solve[s]':>9s} {'total[s]':>9s} {'info':>6s} "
                    f"{'||r||2':>12s} {'||r||/||b||':>12s} {'score':>14s} {'||dx||/||x*||':>13s} {'xsim':>5s} "
                    f"{'|ds|/|s*|':>10s} {'ssim':>5s}"
                )
                print("-" * 156)
            else:
                print(
                    f"{'strategy':44s} {'solve[s]':>9s} {'total[s]':>9s} {'info':>6s} "
                    f"{'||r||2':>12s} {'||r||/||b||':>12s} {'score':>14s} {'|ds|/|s*|':>10s} {'ssim':>5s}"
                )
                print("-" * 136)

            rank = {"PASS": 0, "n/a": 1, "FAIL": 2}
            for label, solve_t, total_t, info, res, rel, _, rel_dx, sim, score, rel_ds, ssim in sorted(
                rows, key=lambda row: (rank.get(row[11], 3), row[2])
            ):
                rel_dx_str = "n/a" if np.isnan(rel_dx) else f"{rel_dx:.3e}"
                score_str = "n/a" if np.isnan(score) else f"{score:.6e}"
                rel_ds_str = "n/a" if np.isnan(rel_ds) else f"{rel_ds:.3e}"
                if args.show_xsim:
                    print(
                        f"{label[:44]:44s} {solve_t:9.2f} {total_t:9.2f} {info:6d} "
                        f"{res:12.3e} {rel:12.3e} {score_str:>14s} {rel_dx_str:>13s} {sim:>5s} {rel_ds_str:>10s} {ssim:>5s}"
                    )
                else:
                    print(
                        f"{label[:44]:44s} {solve_t:9.2f} {total_t:9.2f} {info:6d} "
                        f"{res:12.3e} {rel:12.3e} {score_str:>14s} {rel_ds_str:>10s} {ssim:>5s}"
                    )

    print("\nDone.")


if __name__ == "__main__":
    main()
