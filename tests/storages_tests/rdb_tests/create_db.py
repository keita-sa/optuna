"""This script generates assets for testing schema migration.

1. Install Optuna

You can view the current stable schema version by checking `optuna/storages/_rdb/alembic/versions`.

```sh
> ls optuna/storages/_rdb/alembic/versions
v0.9.0.a.py  v1.2.0.a.py  v1.3.0.a.py  v2.4.0.a.py  v2.6.0.a_.py
```

I recommend you to create isolated environment using `venv` for this purpose.

```sh
> deactivate  # if you already use `venv` for development
> python3 -m venv venv_gen
> . venv_gen/bin/activate
> pip install optuna==2.6.0  # it depends on the output of `ls` above
```

2. Generate database

```sh
> python3 create_db.py
[I 2022-02-05 15:39:32,488] A new study created in RDB with name: single_empty
...
>
```

3. Switch Optuna version to the latest one

If you use `venv`, simply `deactivate` and re-activate your development environment.

"""


from argparse import ArgumentParser
from typing import cast
from typing import Tuple

from packaging import version

import optuna


def single_objective_function(trial: optuna.trial.Trial) -> float:
    x = trial.suggest_float("x", -5, 5)  # optuna==0.9.0 does not have suggest_float.
    y = trial.suggest_int("y", 0, 10)
    z = cast(float, trial.suggest_categorical("z", [-5, 0, 5]))
    trial.set_system_attr("a", 0)
    trial.set_user_attr("b", 1)
    trial.report(0.5, step=0)
    return x**2 + y**2 + z**2


def multi_objective_function(trial: optuna.trial.Trial) -> Tuple[float, float]:
    x = trial.suggest_float("x", -5, 5)
    y = trial.suggest_int("y", 0, 10)
    z = cast(float, trial.suggest_categorical("z", [-5, 0, 5]))
    trial.set_system_attr("a", 0)
    trial.set_user_attr("b", 1)
    return x, x**2 + y**2 + z**2


def single_objective_schema_migration(trial: optuna.trial.Trial) -> float:
    x1 = trial.suggest_float("x1", -5, 5)
    x2 = trial.suggest_float("x2", 1e-5, 1e-3, log=True)
    x3 = trial.suggest_float("x3", -6, 6, step=2)
    y1 = trial.suggest_int("y1", 0, 10)
    y2 = trial.suggest_int("y2", 1, 20, log=True)
    y3 = trial.suggest_int("y3", 5, 15, step=3)
    z = cast(float, trial.suggest_categorical("z", [-5, 0, 5]))
    trial.set_system_attr("a", 0)
    trial.set_user_attr("b", 1)
    trial.report(0.5, step=0)
    return x1**2 + x2**2 + x3**2 + y1**2 + y2**2 + y3**2 + z**2


if __name__ == "__main__":
    parser = ArgumentParser(description="Create SQLite database for schema upgrade tests.")
    parser.add_argument(
        "--storage-url", default=f"sqlite:///test_upgrade_assets/{optuna.__version__}.db"
    )
    args = parser.parse_args()

    # Create an empty study.
    optuna.create_study(storage=args.storage_url, study_name="single_empty")

    # Create a study for single-objective optimization.
    study = optuna.create_study(storage=args.storage_url, study_name="single")
    study.set_system_attr("c", 2)
    study.set_user_attr("d", 3)
    study.optimize(single_objective_function, n_trials=1)

    # Create a study for multi-objective optimization.
    try:
        optuna.create_study(
            storage=args.storage_url, study_name="multi_empty", directions=["minimize", "minimize"]
        )
        study = optuna.create_study(
            storage=args.storage_url, study_name="multi", directions=["minimize", "minimize"]
        )
        study.set_system_attr("c", 2)
        study.set_user_attr("d", 3)
        study.optimize(multi_objective_function, n_trials=1)
    except TypeError:
        print(f"optuna=={optuna.__version__} does not support multi-objective optimization.")

    # Create a study for distributions upgrade.
    if version.parse(optuna.__version__) >= version.parse("2.4.0"):
        study = optuna.create_study(storage=args.storage_url, study_name="schema migration")
        study.optimize(single_objective_schema_migration, n_trials=1)

    for s in optuna.get_all_study_summaries(args.storage_url):
        print(f"{s.study_name}, {s.n_trials}")
