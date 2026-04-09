import React from 'react'
import ReactDOM from "react-dom/client"
import {routes} from "@web-gasket/routes.jsx"
import {GlobusApiProvider} from "@web-gasket/GlobusApiProvider.jsx"
import {ApiProvider} from "@web-gasket/ApiSession.jsx"
import {GlobusAuthProvider, LOG_LEVELS} from "@web-gasket/GlobusAuthProvider.jsx"
import {PipelineInstanceCustomEditorProvider} from "@web-gasket/PipelineInstanceCustomEditorProvider.jsx"
import {createBrowserRouter, RouterProvider} from "react-router-dom"
import DPFoldArgsEditor from "./DPFoldArgsEditor"
import * as thisApi from "./rest"
import * as allApi from "@web-gasket/rest.js"


const doLogout = () =>
    document.location.href = "/login"


const noAuthApp = () =>
    ReactDOM.createRoot(document.getElementById("app")).render(
        <React.StrictMode>
            <ApiProvider
                logLevel={LOG_LEVELS.SILENT}
                apiDict={{
                    ...allApi,
                    ...thisApi
                }}
                afterLogoutFunc={() => {
                    doLogout()
                }}
                onSessionExpired={doLogout}
            >
                <PipelineInstanceCustomEditorProvider customRenderers={{
                    "dp-fold": DPFoldArgsEditor
                }}>
                    <RouterProvider router={createBrowserRouter(routes({}))}/>
                </PipelineInstanceCustomEditorProvider>
            </ApiProvider>
        </React.StrictMode>
    )

noAuthApp()

const globusAuthApp = () => {
    const redirectUrl = `${window.location.protocol}//${window.location.host}/globusAuthCallback`
    ReactDOM.createRoot(document.getElementById("app")).render(
        <React.StrictMode>
            <GlobusAuthProvider
                logLevel={LOG_LEVELS.SILENT}
                clientId={____webgastket_globus_client_id}
                redirect={redirectUrl}
                apiDict={{
                    ...allApi,
                    ...thisApi
                }}
            >
                <GlobusApiProvider
                    pipelineInstanceCollectionId={____pipeline_instances_collection_id}
                    pipelineInstanceCollectionBaseDir={____pipeline_instances_collection_base_dir}
                >
                    <PipelineInstanceCustomEditorProvider customRenderers={{
                        "dp-fold": DPFoldArgsEditor
                    }}>
                        <RouterProvider router={createBrowserRouter(routes({}))}/>
                    </PipelineInstanceCustomEditorProvider>
                </GlobusApiProvider>
            </GlobusAuthProvider>
        </React.StrictMode>
    )
}
