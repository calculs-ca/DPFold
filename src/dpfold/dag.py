import os.path
import traceback
import zipfile
from pathlib import Path
import json

from dry_pipe import DryPipe, TaskConf

from dpfold import colabfold_analysis
from dpfold.multimer import parse_multimer_list_from_samplesheet
from dpfold.multimer import file_path as multimer_code_file


def parse_and_validate_input_files(pipeline_instance_dir):

    errors, samplesheet, multimers, pipeline_instance_args = parse_and_validate_input_files_for_ui(pipeline_instance_dir)

    if len(errors) > 0:
        raise Exception(f"Error parsing input files: {errors}")

    def conf_func(slurm_allocation=None):
        if slurm_allocation is None:
            slurm_allocation = pipeline_instance_args["cc_allocation"]

        return generic_conf(slurm_allocation)

    return multimers, samplesheet, conf_func

def parse_and_validate_input_files_for_ui(pipeline_instance_dir, failsafe=False):

    samplesheet = os.path.join(pipeline_instance_dir, "samplesheet.tsv")
    pipeline_instance_args_file = os.path.join(pipeline_instance_dir, "args.json")

    if os.path.exists(pipeline_instance_args_file):
        with open(pipeline_instance_args_file) as f:
            pipeline_instance_args = json.loads(f.read())
    else:
        pipeline_instance_args = None

    samplesheet_parse_exception = None

    try:
        multimers = parse_multimer_list_from_samplesheet(samplesheet)
    except Exception as e:
        multimers = None
        samplesheet_parse_exception = e
        if not failsafe:
            raise e

    def go():

        if pipeline_instance_args is None:
            yield "MISSING_ARG_FILE", f"could not find pipeline_instance_args_file {pipeline_instance_args_file}"

        #if "cc_project" not in pipeline_instance_args:
        #    yield "MISSING_ARG", "'cc_project' must be specified in Pipeline Args"

        if samplesheet_parse_exception is not None:
            stack_trace_string = "".join(traceback.format_exception(samplesheet_parse_exception))
            yield "ERROR_PARSING_SAMPLESHEET", f"could not parse {stack_trace_string}"


    return dict(go()), samplesheet, multimers, pipeline_instance_args



@DryPipe.python_call()
def generate_fasta_colabfold(samplesheet, multimer_name, fa_out):
    multimer_batch = parse_multimer_list_from_samplesheet(samplesheet)

    multimer = multimer_batch.multimer_by_name(multimer_name)

    multimer.generate_fasta_colabfold(fa_out)


@DryPipe.python_call()
def generate_query_fasta(samplesheet, query_fa):
    multimer_batch = parse_multimer_list_from_samplesheet(samplesheet)
    with open(query_fa, "w") as query_fa:
        for multimer in multimer_batch:
            multimer.append_colabfold_seq_to_fasta(query_fa)

    return {
        "sequence_count": len(multimer_batch.sequence_count()),
    }

@DryPipe.python_call()
def download_pdbs(samplesheet, pdb_folder):

    multimer_batch = parse_multimer_list_from_samplesheet(samplesheet)

    pdb_dir = Path(pdb_folder)
    if not pdb_dir.exists():
        pdb_dir.mkdir(parents=False)

    try:
        bad_pdbs = multimer_batch.download_pdbs(pdb_dir)
        for bad_pdb_msg in bad_pdbs:
            print(f"WEB_GASKET_ERROR: {bad_pdb_msg}")
        if len(bad_pdbs) > 0:
            raise Exception(f"samplesheet.tsv contains bad PDBs, please correct it. Only single model PDBs are supported.")
    except Exception as e:
        print(f"WEB_GASKET_ERROR: {e}")
        raise e


@DryPipe.python_call()
def generate_aggregate_report(__pipeline_instance_dir, interfaces_csv, summary_csv, contacts_csv, all_zip, __task_output_dir):

    def concat_files_keep_first_header(glob_exp, out_file, remove_headers=True):
        out_line_counter = 0
        with open(out_file, "w") as out_f:
            for file_to_concat in Path(__pipeline_instance_dir, "output").glob(glob_exp):
                with open(file_to_concat) as f_f:
                    for line in f_f:
                        if line.startswith("complex_name,"):
                            if out_line_counter == 0:
                                if remove_headers:
                                    continue
                                else:
                                    out_f.write(line)

                        else:
                            out_f.write(line)
                        out_line_counter += 1


    concat_files_keep_first_header("*/interfaces.csv", interfaces_csv, remove_headers=False)

    concat_files_keep_first_header("*/summary.csv", summary_csv)

    concat_files_keep_first_header("*/contacts.csv", contacts_csv)

    zip_root = Path(__pipeline_instance_dir, "output")

    excluded_files = [
        "0_predicted_aligned_error_v1.json",
        "fake_home"
    ]

    with zipfile.ZipFile(all_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        fold_outfile = Path(__pipeline_instance_dir, "output").glob("cf-fold.*/*")
        for fof in fold_outfile:
            if fof.name.endswith(".done.txt") or fof.name in excluded_files:
                print(f"will skip {fof}")
                continue

            if not fof.exists():
            # rsync sometimes downloads symlinks
                continue

            zipf.write(fof, arcname=fof.relative_to(zip_root))
            print(f"added {fof} to zip")


        zipf.write(interfaces_csv, arcname="interfaces.csv")
        zipf.write(summary_csv, arcname="summary.csv")
        zipf.write(contacts_csv, arcname="contacts.csv")


def mmseqs_create_index(dsl):

    for db_name, profile_db in [
        ("pdb100_230517", "pdb100_230517"),
        ("uniref30_2302", "uniref30_2302_db"),
        ("colabfold_envdb_202108", "colabfold_envdb_202108_db")
    ]:
        yield dsl.task(
            key=f"create-idx-{db_name}",
            task_conf=generic_conf("def-rodrigu1").override(sbatch_options=[
                "--time=24:00:00", "--mem=125G", f"--cpus-per-task=32"
            ])).inputs(
            src_db="/project/def-marechal/colabfold_chunked_db",
            db_name=db_name,
            profile_db=profile_db
        ).calls(
            f"""
            #!/bin/bash
            set -ex                    
            
            mkdir -p $HOME/.licenses/
            touch $HOME/.licenses/intel            
            module load StdEnv/2020 mmseqs2/14-7e284
            
            cd $src_db
            
            {'mmseqs tsv2exprofiledb $db_name $profile_db' if db_name != "pdb100_230517" else ''}
            
            mmseqs createindex $profile_db \\
                $SLURM_TMPDIR --remove-tmp-files 1 --threads $SLURM_CPUS_PER_TASK --split-memory-limit 100G
            """
    )()


def required_cpus_and_time(n_seqs):

    def f():
        if n_seqs <= 16:
            return 2, 6
        elif n_seqs <= 32:
            return 2, 8
        elif n_seqs <= 128:
            return 3, 10
        elif n_seqs <= 256:
            return 4, 10
        else:
            c = round((n_seqs / 256) * 4)
            h = round((n_seqs / 256) * 8)
            return c, h

    n_cpus, h = f()

    return n_cpus, h


def dag_perf_test(dsl):
    """
    performance test run on pre generated fastas with many sequences
    will create one search task per fasta
    """
    for query_fasta in Path(dsl.pipeline_instance_dir()).glob("*.fasta"):
        dsl.logger.info("sheet: %s", query_fasta)

        # batch-6_200_4.fasta
        batch_idx, seq_count, cpus = query_fasta.stem.split("-")[1].split("_")

        cpus = int(cpus)
        batch_idx = int(batch_idx)
        seq_count = int(seq_count)

        yield colabfold_search(dsl, seq_count, query_fasta.absolute(), batch_suffix=f"-{batch_idx}_{seq_count}_{cpus}")


def prepare_pipeline(dsl, samplesheet):
    return dsl.task(
        key=f"t-prepare"
    ).inputs(
        samplesheet=dsl.file(samplesheet)
    ).outputs(
        pdb_folder=dsl.file("pdbs"),
        query_fa=dsl.file("query.fasta"),
        sequence_count=int
    ).calls(
        download_pdbs
    ).calls(
        generate_query_fasta
    )()


def colabfold_search(dsl, seq_count, query_fa, batch_suffix=""):

    n_cpus, wall_time_hours = required_cpus_and_time(seq_count)

    sbatch_options = [
        f"--time={wall_time_hours}:00:00",
        f"--cpus-per-task={n_cpus}",
        "--mem=125G", "--tmp=800G"
    ]

    return dsl.task(
        key=f"t-search{batch_suffix}",
        task_conf=generic_conf(slurm_allocation="def-rodrigu1").override(sbatch_options=sbatch_options)
    ).inputs(
        query_fa=query_fa,
        collabfold_db="/project/def-marechal/colabfold_chunked_db"
    ).calls(
        """
        #!/usr/bin/bash

        set -ex

        rm -Rf $__task_output_dir/*                                

        df -h "$SLURM_TMPDIR"

        start=$SECONDS

        local_collabfold_db="$SLURM_TMPDIR/collabfold_db"
        mkdir -p $local_collabfold_db
        ln -s "$collabfold_db"/* "$local_collabfold_db"/

        rm ${local_collabfold_db}/*.idx.*
        rm ${local_collabfold_db}/*.index
        rm ${local_collabfold_db}/*.dbtype
        rm ${local_collabfold_db}/pdb100_230517*        

        rclone_args="copy --multi-thread-streams=$SLURM_CPUS_PER_TASK --ignore-checksum --copy-links --log-level=INFO --stats=10s --stats-one-line --log-file=$__task_control_dir/rclone.log --buffer-size=4G"
        
        rclone_fail() {                        
            df -h "$SLURM_TMPDIR"
            df -i "$SLURM_TMPDIR"                        
            du -sh "$SLURM_TMPDIR"                        
            exit 1
        }        

        trap 'rclone_fail' ERR
        
        rclone $rclone_args $collabfold_db/  $local_collabfold_db/ \\
            --include="*.idx.*" \\
            --include="*.index" \\
            --include="*.dbtype" \\
            --include="pdb100_230517*"
            
        trap - ERR

        duration=$(( SECONDS - start ))
        echo "T__INIT_COPY: $duration"

        mkdir -p $HOME/.licenses/
        touch $HOME/.licenses/intel

        module load StdEnv/2020 gcc/9.3.0 cuda/11.4 openmpi/4.0.3 openmm/8.0.0 hh-suite/3.3.0 hmmer/3.2.1 mmseqs2/14-7e284

        TE=$TASK_VENV/bin/activate                      
        echo "will activate env: $TE"
        source $TE

        start=$SECONDS

        export MMSEQS_SPLIT_MEMORY_LIMIT="--split-memory-limit 100G"                

        python3 -u -m dpfold.patched_colabfold_search \\
           --threads $SLURM_CPUS_PER_TASK --use-env 1 --db-load-mode 0 \\
           --mmseqs mmseqs \\
           --db1 $local_collabfold_db/uniref30_2302_db \\
           --db2 $local_collabfold_db/pdb100_230517 \\
           --db3 $local_collabfold_db/colabfold_envdb_202108_db \\
           $query_fa $local_collabfold_db $__task_output_dir

        duration=$(( SECONDS - start ))
        echo "T__SEARCH: $duration"

        echo "done"    
        """)()


def collabfold_dag(dsl):


    multimer_batch, samplesheet, create_task_conf = parse_and_validate_input_files(dsl.pipeline_instance_dir())

    pipeline_instance_dir_basename = os.path.basename(dsl.pipeline_instance_dir())

    prepare_pipeline_task = prepare_pipeline(dsl, samplesheet)

    for _ in dsl.query_all_or_nothing(prepare_pipeline_task.key, state="completed"):

        colabfold_fold_slurm_options = ["--time=8:00:00", "--mem=40G", "--cpus-per-task=4", "--gpus-per-node=1"]

        search_task = colabfold_search(
            dsl,
            int(prepare_pipeline_task.outputs.sequence_count),
            prepare_pipeline_task.outputs.query_fa
        )

        yield search_task

        for _ in dsl.query_all_or_nothing(search_task.key, state="completed"):

            a3m_idx = 0

            for multimer in multimer_batch:

                multimer_name = multimer.multimer_name()

                colabfold_search_task = dsl.task(
                    key=f"cf-fold.{multimer_name}",
                    is_slurm_array_child=True,
                    task_conf=TaskConf(
                        extra_env=tc.extra_env,
                        python_bin=tc.python_bin
                    )
                ).inputs(
                    samplesheet=dsl.file(samplesheet),
                    multimer_name=multimer_name,
                    pdb_folder=prepare_pipeline.outputs.pdb_folder,
                    fold_name=str(multimer.fold_name()),
                    colabfold_analysis_script=dsl.file(colabfold_analysis.code_path()),
                    has_pdbs=str("True" if multimer_batch.multimer_by_name(multimer_name).has_pdbs() else "False")
                ).outputs(
                    fa_out=dsl.file(f'fold.fa'),
                    a3m=dsl.file(f'{a3m_idx}.a3m'),
                    all_results=dsl.file_set("**/*", exclude_pattern="*.pkl|*.pickle|*fake_home*")
                ).calls("""
                    #!/usr/bin/bash
    
                    set -ex
                    
                    mkdir -p $HOME/.licenses/
                    touch $HOME/.licenses/intel                
                    
                    module load StdEnv/2020 gcc/9.3.0 cuda/11.4 openmpi/4.0.3 openmm/8.0.0 hh-suite/3.3.0 hmmer/3.2.1 mmseqs2/14-7e284
    
                    source $TASK_VENV/bin/activate
    
                    export TF_FORCE_UNIFIED_MEMORY="1"
                    export XLA_PYTHON_CLIENT_MEM_FRACTION="4.0"
                    export XLA_PYTHON_CLIENT_ALLOCATOR="platform"
                    export TF_FORCE_GPU_ALLOW_GROWTH="true"
                    
                    echo "pdb_folder: $pdb_folder"                    
                                    
                    if [[ "$has_pdbs" == "True" ]]; then
                       template_args="--templates --custom-template-path $pdb_folder"
                    else
                       template_args=""
                    fi
                    
                    echo "template_args: $template_args"
                    
                    echo "pb1: $python_bin"
                    echo "pb2: $TASK_VENV/bin/python3"
    
                    echo "running colabfold fold"
                    colabfold_batch $template_args \\
                      --use-gpu-relax --amber --num-relax 3 \\
                      --num-models 3 \\
                      --num-recycle 30 --recycle-early-stop-tolerance 0.5 \\
                      --model-type auto \\
                      --data $collabfold_db \\
                      $a3m \\
                      $__task_output_dir                            
    
                    echo "running AF2multimer-analysis on $__task_output_dir"                                                                
                    
                    python3 -u $colabfold_analysis_script \\
                        --pred_folder=$__task_output_dir \\
                        --out_folder=$__task_output_dir \\
                        --multimer_name=$multimer_name
                    
                    # fasta arg is now obsolete    
                    # --fasta=$fa_out
    
                    echo "done"
                    """,
                    sbatch_options=colabfold_fold_slurm_options
                )()

                yield colabfold_search_task

            for match in dsl.query_all_or_nothing("cf-fold.*", state="ready"):
                cf_fold_array = dsl.task(
                    key="cf-fold-array",
                    task_conf=collabfold_task_conf_func(colabfold_search_slurm_options),
                    downstream_resets=["cf-aggregate-report"]
                ).slurm_array_parent(
                    children_tasks=match.tasks
                )()

                yield cf_fold_array

                if cf_fold_array.has_ended():

                    yield dsl.task(
                        key="cf-aggregate-report"
                    ).outputs(
                        interfaces_csv=dsl.file(f"{pipeline_instance_dir_basename}.interfaces.csv"),
                        summary_csv=dsl.file(f"{pipeline_instance_dir_basename}.summary.csv"),
                        contacts_csv=dsl.file(f"{pipeline_instance_dir_basename}.contacts.csv"),
                        all_zip=dsl.file(f"{pipeline_instance_dir_basename}.all.zip"),
                    ).calls(
                        generate_aggregate_report
                    )()
                    dsl.logger.debug("array has ended")
                else:
                    dsl.logger.debug("some array child tasks are still running")


def colabfold_pipeline():

    def p(dsl):
        yield from collabfold_dag(dsl)

    return DryPipe.create_pipeline(p)


def generate_balanced_batches(sequence_generator, max_residues_per_node=300000):

    def calculate_cores(n_residues):
        if n_residues <= 10000:
            return 8
        elif n_residues <= 50000:
            return 16
        elif n_residues <= 150000:
            return 32
        else:
            return 64

    current_batch = []
    current_residues = 0

    for header, sequence in sequence_generator:
        seq_len = len(sequence)

        if current_residues + seq_len > max_residues_per_node and len(current_batch) > 0:
            yield current_batch, calculate_cores(current_residues)
            current_batch = []
            current_residues = 0

        current_batch.append(f">{header}\n{sequence}")
        current_residues += seq_len

    if len(current_batch) > 0:
        yield current_batch, calculate_cores(current_residues)



def generic_conf(slurm_allocation, remote_base_dir=None, ssh_remote_dest=None):

    python_path = str(Path(__file__).parent.parent)


    collabfold_base = "/project/def-marechal/programs"

    task_venv = f"{collabfold_base}/colabfold_af2.3.2_env"

    ee = {
        "MUGQIC_INSTALL_HOME": "/cvmfs/soft.mugqic/CentOS6",
        #"DRYPIPE_TASK_DEBUG": "True",
        "PYTHONPATH": python_path,
        "TASK_VENV": task_venv,
        "collabfold_db": f"{collabfold_base}/colabfold_db_fixed",
        "HOME": "$__task_output_dir/fake_home"
    }

    if remote_base_dir is not None:
        ee["remote_base_dir"] = remote_base_dir

    return TaskConf(
        executer_type="slurm",
        slurm_account=slurm_allocation,
        extra_env=ee,
        ssh_remote_dest=ssh_remote_dest,
        python_bin=f"{task_venv}/bin/python3",
        #TODO: make this work:
        #run_as_group=slurm_account
        run_as_group=None,
        auto_restart_condition_regexp_per_log_file={
            "drypipe.log": [".*BrokenPipeError.*"],
            "out.log": [
                ".*Bus\\ error.*",
                ".*CUDA_ERROR_.*",
                None
            ]
        }
    )


def prepare_instance_for_perf_test():
    def do_it(pid: Path, samplesheet: Path):

        print(f"pid: {pid}")
        print(f"samplesheet: {samplesheet}")

        if not pid.exists():
            pid.mkdir()

        multimer_batch = parse_multimer_list_from_samplesheet(samplesheet)

        with open(samplesheet) as f:
            header = f.readline()

        sorted_multimers = list(sorted(multimer_batch.multimer_list, key=lambda m: - m.sequence_length()))

        batch_idx = 0
        for batch_size in [8, 16, 32, 64, 128, 200, 300, 400, 500, len(sorted_multimers) -1]:
            batch_idx += 1
            cpus, time = required_cpus_and_time(batch_size)
            fa = Path(pid, f"batch-{batch_idx}_{batch_size}_{cpus}.fasta")
            with open(fa, "w") as f_:
                for i in range(0, batch_size):
                    m = sorted_multimers[i]
                    m.append_colabfold_seq_to_fasta(f_)
            print(f"{fa.absolute()}")
    return do_it


def test():
    def do_it():
        for i in (8,16,32,64,128, 256, 300, 400, 500, 600):
            p = required_cpus_and_time(i)
            print(f"{i}: {p}")
    return do_it

perf_results = """
t-search-4_64_3	5:37:13	20232.71
t-search-8_400_6	6:26:57	23217.12
t-search-9_500_8	6:53:12	24792.19
t-search-5_128_3	8:02:44	28964.3
t-search-10_589_9	7:38:30	27510.08
t-search-7_300_5	7:27:45	26865.09
t-search-2_16_2	3:58:26	14306.14
t-search-6_200_4	7:21:34	26493.82
t-search-1_8_2	3:41:12	13271.52
t-search-3_32_2	5:50:21	21020.89
"""

def chart_per_results():

    def g():
        for row in perf_results.strip().split("\n"):
            task_key, time_min, time_seconds = row.split("\t")
            s = task_key[9:]
            idx, batch_size, num_cpu = s.split("_")

            yield int(batch_size), int(num_cpu), float(time_seconds)/(60*60)

    res = sorted(g(), key=lambda x: x[0])

    for batch_size, num_cpu, actual_time in res:
        _, estimated_time = required_cpus_and_time(batch_size)
        print(f"{batch_size}\t{num_cpu}\t{estimated_time}\t{actual_time}")

if __name__ == "__main__":
    #p = FunkyArgParse(prepare_instance_for_perf_test, test)
    #p.invoke()
    #est()()
    #prepare_instance_for_perf_test()(Path("/home/maxl/dev/DPFold/zaz"), Path("/home/maxl/dev/DPFold/test-samplesheets/big-perf.tsv"))
    #with open("/home/maxl/dev/DPFold/zaz/batch-1_8_2.fasta") as f:
    #    parse_fasta(str(f.read()))

    #prepare_instance_for_perf_test()(Path(sys.argv[1]), Path(sys.argv[2]))
    chart_per_results()
