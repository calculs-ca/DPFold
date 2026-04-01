
import React, {useReducer, useEffect} from 'react'
import {useApi} from "@web-gasket/ApiSession.jsx";
import {DefaultButton} from "@web-gasket/widgets/Buttons.jsx"
import FileManager from "@web-gasket/components/FileManager.jsx";
import DocLink from "@web-gasket/components/DocLink.jsx";
import ModalWindow from "@web-gasket/widgets/ModalWindow.jsx";
import PipelineInstanceStartButton from "@web-gasket/components/PipelineInstanceStartButton.jsx"
import PipelineInstancePreRunButton from "@web-gasket/components/PipelineInstancePreRunButton.jsx"
import  {dpFoldArgsReducer} from "./dpFoldArgsReducer.js"


const ClusterSelect = ({value, onSelect, clusters}) => {
    return <>
        <label
            className="block mb-2 text-sm font-medium text-gray-900 dark:text-white"
        >Select a cluster</label>
        <select
            className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
            onChange={e => onSelect(e.target.value)}
            value={value}
        >
            <option value={""}>Choose a cluster</option>
            {
                clusters.map(c => <option key={c} value={c}>{c}</option>)
            }
        </select>
        </>
}

const AllocationSelect = ({value, onSelect, allocs}) => {

    return <>
        <label
            className="block mb-2 text-sm font-medium text-gray-900 dark:text-white"
        >Select allocation</label>
        <select
            className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
            onChange={e => onSelect(e.target.value)}
            value={value}
        >
            <option value={""}>Choose an allocation</option>
            {
                allocs && allocs.map(c => <option key={c} value={c}>{c}</option>)
            }
        </select>
    </>
}


const DPFoldArgsEditor = ({pipelineInstance, pipelineArgsDispatcher}) => {


    const [dpFoldArgsView, dpFoldArgsDispatcher] = useReducer(
        dpFoldArgsReducer,
        dpFoldArgsReducer(null, {
            name: 'init',
            schema: pipelineInstance.argsSchema,
            args: pipelineInstance.args
        })
    )

    const api = useApi()

    useEffect(() => {

        api.getDPFoldCustomFilesStatus(pipelineInstance.pid).then(s => {
            dpFoldArgsDispatcher({
                name: "updateCustomFileStatus",
                status: s
            })
        })
    }, [`-${dpFoldArgsView.c}`])

    useEffect(() => {
        api.getCCAllocations().then(allocations => {
            dpFoldArgsDispatcher({
                name: "setCCallocations", allocations
            })
        })
    },[])

    useEffect(() => {

        latestPipelineInstance()

    },[])


    const latestPipelineInstance = () =>
        api.latestPipelineInstance(pipelineInstance.pid).then(res => {
            dpFoldArgsDispatcher({name: "refreshTaskStates", tasks: res.tasks})
        })

    const readyStatus = () => {

        if(! dpFoldArgsView.customFilesStatus) {
            return 0
        }

        if(!dpFoldArgsView.customFilesStatus.exists) {
            return 0
        }

        if(!dpFoldArgsView.customFilesStatus.isValid) {
            return 0
        }

        if(dpFoldArgsView.isDirty) {
            return 0
        }

        if(!dpFoldArgsView.args.cc_allocation) {
            return 0
        }

        if(!dpFoldArgsView.args.cc_cluster) {
            return 0
        }

        if(dpFoldArgsView.args.isPrepared) {
            return 2
        }

        return 1
    }

    const canPrepare = () => {

        const s = readyStatus()

        return s > 0
    }

    const canStart = () => {

        const s = readyStatus()
        return s >= 1
    }


    const saveArgs = () =>
        api.savePipelineInstanceArgs(pipelineInstance.pid, dpFoldArgsView.args).then(
            () => dpFoldArgsDispatcher({name: "saved"})
        )

    const errorPanel = () => {

        if(dpFoldArgsView.customFilesStatus && dpFoldArgsView.customFilesStatus.exists) {
            if (dpFoldArgsView.customFilesStatus.isValid) {
                return null
            }

            return <pre>
                {dpFoldArgsView.customFilesStatus.errors}
            </pre>

        }

        return null
    }

    const sampleSheetStatusDisplay = () => {

        if(dpFoldArgsView.customFilesStatus === null) {
            return "[...status loading]"
        }

        if(dpFoldArgsView.customFilesStatus.exists) {
            if(dpFoldArgsView.customFilesStatus.isValid) {
                return "[valid]"
            }
            return "[has errors]"
        }
        else {
            return "[file missing]"
        }

    }

    const sampleSheetField = () => {

        if(dpFoldArgsView.customFilesStatus === null) {
            return "...status loading"
        }

        if(dpFoldArgsView.customFilesStatus.exists) {
            return "samplesheet.tsv"
        }

        return ""

    }

    const clusters =
        dpFoldArgsView.ccAllocations ?
        Object.keys(dpFoldArgsView.ccAllocations) : []

    const saveDisabled = !dpFoldArgsView.isDirty

    const fileManagerModal = () => {
        if(! dpFoldArgsView.fileManagerVisible) {
            return
        }
        const closeFileManager = () => dpFoldArgsDispatcher({name: "closeFileManager"})

        return <ModalWindow
            title={"Manage Pipeline Files"}
            largeGrid={true}
            onClose={closeFileManager}
            footer={<>
                <DefaultButton caption={"Close"} onClick={closeFileManager}/>
            </>}
        >
            <FileManager pipelineInstanceDir={pipelineInstance.pid}/>
        </ModalWindow>
    }

    const popFileManager = () => dpFoldArgsDispatcher({name: "popFileManager"})


    const formatDocModal = () => {
        if(! dpFoldArgsView.formatDocModal) {
            return
        }
        const closeFileManager = () => dpFoldArgsDispatcher({name: "closeFormatDoc"})

        return <ModalWindow
            title={"Sample Sheet Format"}
            largeGrid={true}
            onClose={closeFileManager}
            footer={<>
                <DefaultButton caption={"Close"} onClick={closeFileManager}/>
            </>}
        >
            <DPFoldSampleSheetFormatDoc/>
        </ModalWindow>
    }


    return <div className="grid gap-6 mb-6 md:grid-cols-1">
            <div>
                <DocLink pipelineType={'DPFold'} markdownFile={'doc.samplesheet.md'}/>
            </div>
            {fileManagerModal()}
            <div>
                <ClusterSelect
                    value={dpFoldArgsView.args.cc_cluster}
                    clusters={clusters}
                    onSelect={cluster => dpFoldArgsDispatcher({
                        name: "update",
                        fieldName: "cc_cluster",
                        value: cluster
                    })}
                />
            </div>
            <div>
                <AllocationSelect
                    value={dpFoldArgsView.args.cc_allocation || ""}
                    allocs={dpFoldArgsView.ccAllocations ? dpFoldArgsView.ccAllocations[dpFoldArgsView.args.cc_cluster] : []}
                    onSelect={alloc => dpFoldArgsDispatcher({
                        name: "update",
                        fieldName: "cc_allocation",
                        value: alloc
                    })}
                />
            </div>
            <div className={"flex flex-row"}>

                <div className={"basis-1/3"}>
                    <label className="block mb-2 text-sm font-medium text-gray-900 dark:text-white">
                    sample sheet { sampleSheetStatusDisplay() }
                    </label>
                    <input
                        type="text"
                        className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                        placeholder="samplesheet.tsv"
                        value={sampleSheetField()}
                        disabled={true}
                    />
                    {errorPanel()}
                </div>
                <div className={"pt-10 ml-4 basis-1/3"}>
                    upload "samplesheet.tsv" file
                </div>
                <div className={"basis-1/3 pt-7 ml-6"}>
                    <DefaultButton onClick={popFileManager} caption={"Manage pipeline Files"}/>
                </div>
            </div>
            <div className={"flex flex-row"}>
                <div>
                    <DefaultButton
                    caption={"Save"}
                    isDisabled={saveDisabled}
                    onClick={saveArgs}
                    />
                </div>
                <div className={"ml-4"}>
                    <PipelineInstancePreRunButton
                        pipelineInstance={pipelineInstance}
                        isReady={ canPrepare()}
                        onReceivePreRunResponse={res => {
                            dpFoldArgsDispatcher({name: "preRunResults", res})
                        }}
                    />
                </div>
                <div className={"ml-4"}>
                    <PipelineInstanceStartButton
                        pipelineInstance={pipelineInstance}
                        isReady={ canStart()}
                        beforeStart={() => {
                            return saveArgs().then(() => true)
                        }}
                        onReceiveStartResponse={res => {
                            console.log(res, 0)
                        }}
                    />
                </div>
            </div>
        </div>
}


export default DPFoldArgsEditor



const DPFoldSampleSheetFormatDoc = () => <div>

</div>
