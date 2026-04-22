import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from dpfold.multimer import parse_multimer_list_from_samplesheet
from dpfold.pipeline_conf import gen_conf
from dry_pipe.service import PipelineRunner
from web_gasket.dry_pipe_web_socket_runner import DryPipeWebSocketRunner

from web_gasket.routes import init_page_and_upload_routes, create_sub_api


import logging
import logging.config

from web_gasket import slurm_commands


def parse_permissions(user_email):

    ppf = os.environ.get("PIPELINE_PERMISSIONS_FILE")

    if ppf is None:
        raise RuntimeError("variable PIPELINE_PERMISSIONS_FILE not set")

    if not Path(ppf).exists():
        raise RuntimeError(f"file '{ppf}' refered by env var PIPELINE_PERMISSIONS_FILE does not exist")

    with open(ppf, "r") as f:
        c = 1
        for line in f.readlines():
            line = line.strip()
            if line == "":

                c += 1

            try:
                _user_email, pipelines, allocations = line.split("\t")
                _user_email = user_email.strip()

                if _user_email != user_email:
                    continue

                pipelines = pipelines.strip()
                allocations = allocations.strip()

                def vals(s):
                    return [s0.strip() for s0 in s.split(",")]

                return vals(pipelines), vals(allocations)

            except Exception as e:
                raise RuntimeError(f"invalid line '{line}' in PIPELINE_PERMISSIONS_FILE {ppf} {e}")

    return []


runner = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner

    await runner.start()
    print("DryPipe service started")

    yield  # This is where uvicorn runs

    # Shutdown: clean up runner
    if runner:
        await runner.stop()
        print("DryPipe service stopped")

def init_app():
    logging_config = {
        'version': 1,
        'disable_existing_loggers': False, # Keep existing loggers active
        'root': {
            'level': 'INFO',
            'handlers': ['console'],
        },
        "formatters": {
            "simple": {
                "format": "%(levelname)s: - %(name)s - %(message)s"
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                "formatter": "simple"
            },
        },
    }

    logging.config.dictConfig(logging_config)


    app = FastAPI(lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Location",
            "Upload-Offset",
            "Tus-Resumable",
            "Tus-Version",
            "Tus-Extension",
            "Tus-Max-Size",
            "Upload-Expires",
            "Upload-Length",
        ]
    )

    WEB_GASKET_TEMP_FILE_UPLOAD_DIR = os.environ.get("WEB_GASKET_TEMP_FILE_UPLOAD_DIR")

    if WEB_GASKET_TEMP_FILE_UPLOAD_DIR is None:
        WEB_GASKET_TEMP_FILE_UPLOAD_DIR = "/tmp/ibio-reception-dir"

    Path(WEB_GASKET_TEMP_FILE_UPLOAD_DIR).mkdir(exist_ok=True, parents=True)

    pipeline_runner = PipelineRunner(gen_conf(), sleep_schedule=[])

    api = create_sub_api(pipeline_runner)

    @api.get("/cc_allocations")
    async def cc_allocations(request: Request):
        return slurm_commands.list_accounts()


    @api.get("/dpFoldFilesStatus/{pid:path}")
    async def dp_files_status(pid: str):

        samplesheet = Path(f"/{pid}", "samplesheet.tsv")

        if samplesheet.exists():

            try:
                parse_multimer_list_from_samplesheet(samplesheet)
                samplesheet_parse_exception = None
            except Exception as e:
                samplesheet_parse_exception = e

            return {
                "name": "samplesheet.tsv",
                "exists": True,
                "isValid": samplesheet_parse_exception is None,
                "errors": None if samplesheet_parse_exception is None else str(samplesheet_parse_exception)
            }

        return {
            "name": "samplesheet.tsv",
            "exists": False
        }

    #session_key = os.environ.get("WEB_SESSION_KEY")
    #if session_key is None:
    #    session_key = "insecure-key"

    #globus_authenticator = GlobusAuthenticator(api, uses_local_ssh_globus_for_file_transfers_only=True)

    #def page_func():
    #    return f"""
    #    <script>
    #        var ____pipeline_instances_collection_id='{globus_authenticator.pipeline_instances_collection_id}'
    #        var ____pipeline_instances_collection_base_dir='{globus_authenticator.globus_pipeline_instances_dir}'
    #        var ____webgastket_globus_client_id='{globus_authenticator.globus_client_id}'
    #    </script>
    #    """

    #globus_authenticator.init_routes(api, app, page_func())

    runner.create_dry_pipe_runner_home()

    init_page_and_upload_routes(app, None, dry_pipe_runner=runner)

    app.mount("/api", api)

    return app


def run():

    os.environ["DRYPIPE_SERVICE_CONFIG_GENERATOR"] = "dpfold.pipeline_conf:gen_conf"
    os.environ["FAST_API_MAIN_PID"] = str(os.getpid())


    cwd = Path(os.getcwd())

    if not cwd.joinpath("web-gasket-env.sh").exists():
        print("current directory is NOT a valid DPFold home ")
        exit(1)


    cwd = str(cwd.absolute())
    os.environ["WEB_GASKET_HOME"] = cwd
    os.environ["DRYPIPE_PIPELINE_INSTANCES_DIR"] = cwd

    WEB_APP_PORT = os.environ.get("WEB_GASKET_PORT")


    t = f'Tunnel:  "ssh -L {WEB_APP_PORT}:127.0.0.1:{WEB_APP_PORT} narval"'

    print(f"Tunnel : {t}")

    port = 8000 if WEB_APP_PORT is None else int(WEB_APP_PORT)

    logger = logging.getLogger(__name__)
    logger.info(f"starting web app on port {port}")

    global runner

    h = os.environ.get("WEB_GASKET_HOME")
    host_address = os.environ.get("WEB_GASKET_HOST_ADDRESS")

    runner = DryPipeWebSocketRunner(home_directory=h)

    app = init_app()
    uvicorn.run(app, host=host_address or "0.0.0.0", port=port, workers=1)


def init_home():

    cwd = os.getcwd()

    answer = input(f"create DPFold home in {cwd} ? Y, or type other directory")
    if answer.lower() in ["y", "yes"]:
        home = Path(cwd)
    else:
        home = Path(answer)
        home.mkdir(exist_ok=True, parents=True)

    runner = DryPipeWebSocketRunner(home_directory=home)

    dry_pipe_env = [
        f"export DRYPIPE_PIPELINE_INSTANCES_DIR={home.absolute()}",
        f"export DRYPIPE_SERVICE_CONFIG_GENERATOR=dpfold.pipeline_conf:gen_conf",
        f"export DRYPIPE_LOGGING_CONF={home.absolute()}/log-conf.json",
    ]
    with open(home.joinpath("drypipe-env.sh")) as env_file:
        env_file.writelines(dry_pipe_env)

    with open(home.joinpath("web-gasket-env.sh")) as env_file:
        env_file.writelines(dry_pipe_env)
        env_file.writelines([
            f"export WEB_GASKET_HOST_ADDRESS=127.0.0.1",
            f"export WEB_GASKET_PORT=8001",
        ])

    runner.create_dry_pipe_runner_home()


if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_home()
    else:
        run()