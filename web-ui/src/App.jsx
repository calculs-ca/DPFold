import React from 'react'
import {ApiProvider, LOG_LEVELS} from "@web-gasket/ApiSession.jsx"
import ReactDOM from "react-dom/client"
import {routes} from "@web-gasket/routes.jsx"
import {PipelineInstanceCustomEditorProvider} from "@web-gasket/PipelineInstanceCustomEditorProvider.jsx"
import {createBrowserRouter, RouterProvider} from "react-router-dom"
import DPFoldArgsEditor from "./DPFoldArgsEditor"
import * as thisApi from "./rest"
import * as allApi from "@web-gasket/rest.js"


const doLogout = () =>
    document.location.href = "/login"


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