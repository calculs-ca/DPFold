

export const getDPFoldCustomFilesStatus = pid =>
    fetch(`/api/dpFoldFilesStatus${pid}`)

export const getCCAllocations = () =>
    fetch(`/api/cc_allocations`)

export const preDownloadPDBs = pid =>
    fetch(`/api/preDownloadPDBs${pid}`)