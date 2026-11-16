"""Create the Databricks App (once), build the web interface, upload and deploy.

Run from the repository root, with the work committed:

    python setup/deploy_app.py              build, upload and deploy
    python setup/deploy_app.py --no-deploy  build and upload only

What is uploaded is what git tracks under the paths in ``TRACKED``, plus a fresh
production build of the web interface (``web/dist``, which git does not track).
Databricks Apps then installs ``requirements.txt`` and runs the command in
``app.yaml``.

The app's access comes from the resources declared here, so the platform grants
its service principal exactly these and nothing else. Authentication is left to
the SDK, which reads the profile named in ``.env``.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service import apps
from databricks.sdk.service.workspace import ImportFormat
from dotenv import load_dotenv

from copilot.config import Settings, load_settings

APP_NAME = "frontline-copilot"
APP_DESCRIPTION = "Frontline Copilot demo. Synthetic data only."
ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
# What the app needs at run time. Tests, data, evaluation and pipelines stay out.
TRACKED = ("app.yaml", "requirements.txt", "pyproject.toml", "README.md", "api/", "src/", "config/")
# Folders an earlier deployment uploaded that the app no longer has.
RETIRED = ("app", ".streamlit")


def app_resources(client: WorkspaceClient, settings: Settings) -> list[apps.AppResource]:
    """The least the app needs: no unredacted table is on this list."""
    experiment = client.experiments.get_by_name(settings.mlflow_experiment).experiment
    if experiment is None or experiment.experiment_id is None:
        raise SystemExit(f"MLflow experiment not found: {settings.mlflow_experiment}")

    def table(schema: str, name: str, permission: str) -> apps.AppResource:
        return apps.AppResource(
            name=f"{schema}-{name}".replace("_", "-"),
            uc_securable=apps.AppResourceUcSecurable(
                securable_full_name=settings.table(schema, name),
                securable_type=apps.AppResourceUcSecurableUcSecurableType.TABLE,
                permission=apps.AppResourceUcSecurableUcSecurablePermission(permission),
            ),
        )

    def endpoint(name: str, endpoint_name: str) -> apps.AppResource:
        return apps.AppResource(
            name=name,
            serving_endpoint=apps.AppResourceServingEndpoint(
                name=endpoint_name,
                permission=apps.AppResourceServingEndpointServingEndpointPermission.CAN_QUERY,
            ),
        )

    return [
        apps.AppResource(
            name="sql-warehouse",
            sql_warehouse=apps.AppResourceSqlWarehouse(
                id=settings.sql_warehouse_id,
                permission=apps.AppResourceSqlWarehouseSqlWarehousePermission.CAN_USE,
            ),
        ),
        endpoint("chat-model", settings.llm_endpoint),
        endpoint("embedding-model", settings.embedding_endpoint),
        # The small model that routes a request. Without it the copilot still
        # answers: the router fails and the plain rules decide.
        endpoint("router-model", settings.router_endpoint),
        apps.AppResource(
            name="mlflow-experiment",
            experiment=apps.AppResourceExperiment(
                experiment_id=experiment.experiment_id,
                permission=apps.AppResourceExperimentExperimentPermission.CAN_EDIT,
            ),
        ),
        table("gold", "plans", "SELECT"),
        table("silver", "transcripts_redacted", "SELECT"),
        table("gold", "kb_chunks_index", "SELECT"),
        table("ops", "escalations", "MODIFY"),
        # The app only ever inserts a wrap-up. A table resource is either SELECT or
        # MODIFY, so MODIFY is the least that allows an insert. As an app resource it
        # also lets the app read the table, which holds redacted text only.
        table("ops", "call_wrapups", "MODIFY"),
    ]


def build_web() -> list[Path]:
    """Make a production build of the interface and return its files.

    The build is always made here. ``npm run build:mock`` writes to the same
    folder, and a mock build must never be what gets deployed.
    """
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is not on PATH. Node.js is needed to build web/.")
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)
    dist = WEB / "dist"
    if (dist / "gallery.html").exists():
        raise SystemExit("web/dist holds a mock build. Refusing to deploy it.")
    return sorted(path for path in dist.rglob("*") if path.is_file())


def tracked_files() -> list[Path]:
    """The files git tracks under the paths the app needs."""
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is not on PATH.")
    listed = subprocess.run(
        [git, "ls-files", *TRACKED], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [ROOT / line for line in listed.stdout.splitlines() if line]


def delete_folder(client: WorkspaceClient, path: str) -> None:
    """Remove one workspace folder if it is there."""
    with contextlib.suppress(NotFound):
        client.workspace.delete(path, recursive=True)


def upload(client: WorkspaceClient, source_path: str, files: list[Path]) -> None:
    """Copy the files into the app's source folder in the workspace."""
    made: set[str] = set()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        folder = relative.rpartition("/")[0]
        if folder and folder not in made:
            client.workspace.mkdirs(f"{source_path}/{folder}")
            made.add(folder)
        # RAW keeps every file a file. AUTO would turn an .html page into a notebook.
        client.workspace.upload(
            f"{source_path}/{relative}",
            io.BytesIO(path.read_bytes()),
            format=ImportFormat.RAW,
            overwrite=True,
        )


def wait_for_deployment(client: WorkspaceClient, timeout_seconds: int = 900) -> apps.App:
    """Wait until the app has no deployment in progress, and return the app."""
    deadline = time.time() + timeout_seconds
    while True:
        app = client.apps.get(APP_NAME)
        active = app.active_deployment
        in_progress = active is not None and (
            active.status is None or active.status.state == apps.AppDeploymentState.IN_PROGRESS
        )
        if (app.pending_deployment is None and not in_progress) or time.time() > deadline:
            return app
        time.sleep(10)


def main() -> None:
    load_dotenv(ROOT / ".env")
    settings = load_settings()
    client = WorkspaceClient()
    user = client.current_user.me().user_name
    source_path = f"/Workspace/Users/{user}/apps/{APP_NAME}"

    if APP_NAME not in {app.name for app in client.apps.list()}:
        print("creating the app (this starts its compute and takes a few minutes)", flush=True)
        client.apps.create(
            apps.App(
                name=APP_NAME,
                description=APP_DESCRIPTION,
                resources=app_resources(client, settings),
            )
        ).result()
    else:
        # The app's access is exactly what this file lists. An app made by an earlier
        # version is brought up to date, so that a resource added since (the router's
        # endpoint) is granted to its service principal.
        client.apps.update(
            APP_NAME,
            apps.App(
                name=APP_NAME,
                description=APP_DESCRIPTION,
                resources=app_resources(client, settings),
            ),
        )
    app = client.apps.get(APP_NAME)
    compute = app.compute_status.state if app.compute_status else None
    print(f"app: {app.name} | compute: {compute}", flush=True)

    files = tracked_files() + build_web()
    client.workspace.mkdirs(source_path)
    # Built files carry a hash in their names, so the last build is cleared first.
    delete_folder(client, f"{source_path}/web/dist")
    for folder in RETIRED:
        delete_folder(client, f"{source_path}/{folder}")
    upload(client, source_path, files)
    print(f"uploaded {len(files)} files", flush=True)

    if "--no-deploy" in sys.argv:
        return
    started = time.time()
    if compute != apps.ComputeState.ACTIVE:
        # Free Edition stops an app 24 hours after it starts. A stopped app refuses a
        # deployment, and starting it deploys what is in its source folder anyway.
        print("starting the app, which deploys the uploaded source (a few minutes)", flush=True)
        client.apps.start(APP_NAME).result()
    else:
        print("deploying", flush=True)
        client.apps.deploy(APP_NAME, apps.AppDeployment(source_code_path=source_path)).result()
    app = wait_for_deployment(client)
    deployment = app.active_deployment
    status = deployment.status if deployment else None
    print(
        f"deployment: {status.state if status else None} | "
        f"{status.message if status else None} | {time.time() - started:.0f}s"
    )
    if app.app_status:
        print(f"app status: {app.app_status.state} | {app.app_status.message}")
    print(f"url: {app.url}")
    if status is None or status.state != apps.AppDeploymentState.SUCCEEDED:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
