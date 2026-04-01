
export const dpFoldArgsReducer = (state, action) => {

    switch (action.name) {
        case "init": {
            return {
                args: {
                    cc_cluster: action.args.cc_cluster,
                    cc_allocation: action.args.cc_allocation,
                    cc_project: action.args.cc_project
                },
                customFilesStatus: null,
                isDirty: false,
                fileManagerVisible: false,
                c: 0,
                allTasks: {
                    v: 0
                }
            }
        }
        case "setCCallocations": {
            return {
                ...state,
                ccAllocations: action.allocations
            }
        }
        case "updateCustomFileStatus": {

            return {
                ...state,
                customFilesStatus: {
                    ...action.status
                }
            }
        }
        case "update": {

            const nextState = {
                ...state,
                args: {
                    ...state.args,
                    [action.fieldName]: action.value
                }
            }

            return {
                ...nextState,
                isDirty: true,
                c: state.c + 1
            }
        }
        case "preRunResults": {
            return {
                ...state,
                isPrepared: action.res.status === "ok"
            }
        }
        case "saved": {
            return {
                ...state,
                isDirty: false
            }
        }
        case "popFileManager": {
            return {
                ...state,
                fileManagerVisible: true
            }
        }
        case "closeFileManager": {
            return {
                ...state,
                fileManagerVisible: false,
                c: state.c + 1
            }
        }
        case "refreshTaskStates": {
            return {
                ...state,
                allTasks: action.tasks
            }
        }
        default:
            throw Error(`unknown action ${action.name}`)
    }
}


const tasksToFoldTable = allTasks => {

    function* g() {

        for(const task of allTasks) {
            if(task.key.startsWith("cf-fold.")) {
                yield {
                    name: task.key.substring(8),
                    task: task
                }
            }
        }
    }


    return [...g()]
}