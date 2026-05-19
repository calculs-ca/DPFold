import os
import sys
import time


def _do_patch(original_run_mmseqs):


    mmseqs_split_memory_limit = os.environ.get("MMSEQS_SPLIT_MEMORY_LIMIT")

    if mmseqs_split_memory_limit is not None and mmseqs_split_memory_limit != "":
        mmseqs_split_memory_limit = mmseqs_split_memory_limit.split(" ")
    else:
        mmseqs_split_memory_limit = None


    def patched_run_mmseqs(mmseqs, params):

        params = params.copy()
        if mmseqs_split_memory_limit is not None:
            split_capable_commands = ["search", "prefilter"]
            if any(cmd in params for cmd in split_capable_commands):
                if "--split-memory-limit" not in params:
                    params.extend(mmseqs_split_memory_limit)
                    if "--split-mode" not in params:
                        params.extend(["--split-mode", "2"])

        if len(params) > 0:
            arg_1 = str(params[0])
        else:
            arg_1 = ""

        cmd_str = ' '.join([str(p) for p in params])
        print(f"[mmseqs start]: {mmseqs} {cmd_str}")

        start_time = time.time()

        try:
            result = original_run_mmseqs(mmseqs, params)
            return result
        finally:
            end_time = time.time()
            duration = end_time - start_time
            m, s = divmod(duration, 60)
            print(f"[mmseqs end] {arg_1} | duration: {int(m)}m {s:.2f}s")
            sys.stderr.flush()

    return patched_run_mmseqs

if __name__ == "__main__":
    import colabfold.mmseqs.search
    from colabfold.mmseqs.search import main, run_mmseqs as original_run_mmseqs

    colabfold.mmseqs.search.run_mmseqs = _do_patch(original_run_mmseqs)
    main()
