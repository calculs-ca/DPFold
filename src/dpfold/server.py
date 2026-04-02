import json
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect, WebSocket

from dpfold.multimer import parse_multimer_list_from_samplesheet
from dpfold.pipeline_conf import gen_conf
from dry_pipe.service import PipelineRunner
from web_gasket.globus_auth import GlobusAuthenticator

from web_gasket.routes import init_page_and_upload_routes, create_sub_api
from web_gasket.auth import SqliteAuthenticator


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



def init_app():

    app = FastAPI()

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

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_text(f"Message text was: {data}")
        except WebSocketDisconnect:
            print("WebSocket disconnected")
            pass

    WEB_GASKET_TEMP_FILE_UPLOAD_DIR = os.environ.get("WEB_GASKET_TEMP_FILE_UPLOAD_DIR")

    if WEB_GASKET_TEMP_FILE_UPLOAD_DIR is None:
        WEB_GASKET_TEMP_FILE_UPLOAD_DIR = "/tmp/ibio-reception-dir"

    Path(WEB_GASKET_TEMP_FILE_UPLOAD_DIR).mkdir(exist_ok=True, parents=True)

    pipeline_runner = PipelineRunner(gen_conf(), sleep_schedule=[])

    api = create_sub_api(pipeline_runner)

    @api.get("/cc_allocations")
    async def cc_allocations(request: Request):

        return slurm_commands.list_accounts()
        """
        sess = request.state.session

        user_email = sess.get("user_email")

        af = os.environ.get("CC_ALLOCATIONS_FILE")
        if af is None:
            raise Exception(f"missing env var CC_ALLOCATIONS_FILE")

        if not Path(af).exists():
            raise Exception(f"CC_ALLOCATIONS_FILE does not exist")

        with open(af, "r") as f:
            cc_allocs = json.load(f)

        return cc_allocs.get(user_email)
        """


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


    #user_auth_db = os.environ.get("USER_AUTH_DB")

    #if user_auth_db is None:
    #    raise Exception(f"missing env var USER_AUTH_DB")

    session_key = os.environ.get("WEB_SESSION_KEY")

    if session_key is None:
        raise Exception(f"missing env var WEB_SESSION_KEY")

    #authenticator = SqliteAuthenticator(
    #    user_auth_db,
    #    session_key,
    #    60*30
    #)

    #authenticator.init_routes(api, app)
    #init_page_and_upload_routes(app, authenticator)

    globus_authenticator = GlobusAuthenticator(api, uses_local_ssh_globus_for_file_transfers_only=True)

    def page_func():
        return f"""
        <script>
            var ____pipeline_instances_collection_id='{globus_authenticator.pipeline_instances_collection_id}'
            var ____pipeline_instances_collection_base_dir='{globus_authenticator.globus_pipeline_instances_dir}'
            var ____webgastket_globus_client_id='{globus_authenticator.globus_client_id}'
        </script>        
        """

    globus_authenticator.init_routes(api, app, page_func())

    init_page_and_upload_routes(app, globus_authenticator, page_func())

    app.mount("/api", api)

    return app


def run():

    WEB_APP_PORT = os.environ.get("WEB_APP_PORT")

    port = 8000 if WEB_APP_PORT is None else int(WEB_APP_PORT)

    logger = logging.getLogger(__name__)
    logger.info(f"starting web app on port {port}")

    uvicorn.run(app="dpfold.server:init_app", host="0.0.0.0", port=port, workers=2)

if __name__ == '__main__':

    run()