import os.path
import zipfile
from pathlib import Path
import json

from dry_pipe import DryPipe, TaskConf

from dpfold import colabfold_analysis
from dpfold.multimer import parse_multimer_list_from_samplesheet
from dpfold.multimer import file_path as multimer_code_file


def parse_and_validate_input_files(pipeline_instance_dir):

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

    def go():

        if pipeline_instance_args is None:
            yield "MISSING_ARG_FILE", f"could not find pipeline_instance_args_file {pipeline_instance_args_file}"

        #if "cc_project" not in pipeline_instance_args:
        #    yield "MISSING_ARG", "'cc_project' must be specified in Pipeline Args"

        if samplesheet_parse_exception is not None:
            yield "MISSING_ARG_FILE", f"could not parse {samplesheet}"


    return dict(go()), samplesheet, multimers, pipeline_instance_args



@DryPipe.python_call()
def generate_fasta_colabfold(samplesheet, multimer_name, fa_out):
    multimer_batch = parse_multimer_list_from_samplesheet(samplesheet)

    multimer = multimer_batch.multimer_by_name(multimer_name)

    return multimer.generate_fasta_colabfold(fa_out)


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



def collabfold_dag(dsl, multimer_batch, samplesheet, collabfold_task_conf_func):

    pipeline_instance_dir_basename = os.path.basename(dsl.pipeline_instance_dir())

    tc = collabfold_task_conf_func([])

    n_cpu_4_search = 8

    colabfold_search_slurm_options = ["--time=48:00:00","--mem=100G", f"--cpus-per-task={n_cpu_4_search}"]

    colabfold_fold_slurm_options = [
        "--time=12:00:00", "--mem=40G", "--cpus-per-task=4",
        "--gpus-per-node=1", f"--account={tc.slurm_account}"
    ]

    download_pdbs_task = dsl.task(
        key="cf-download-pdbs"
    ).inputs(
        samplesheet=dsl.file(samplesheet)
    ).outputs(
        pdb_folder=dsl.file("pdbs")
    ).calls(download_pdbs)()

    yield download_pdbs_task

    for _ in dsl.query_all_or_nothing("cf-download-pdbs", state="completed"):

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
                pdb_folder=download_pdbs_task.outputs.pdb_folder,
                fold_name=str(multimer.fold_name()),
                code_dep1=dsl.file(__file__),
                code_dep2=dsl.file(multimer_code_file()),
                code_dep3=dsl.file(colabfold_analysis.code_path()),
                colabfold_analysis_script=dsl.file(colabfold_analysis.code_path()),
                has_pdbs=str("True" if multimer_batch.multimer_by_name(multimer_name).has_pdbs() else "False"),
                n_cpu_4_search=int(n_cpu_4_search)
            ).outputs(
                fa_out=dsl.file(f'fold.fa'),
                a3m=dsl.file(f'0.a3m'),
                all_results=dsl.file_set("**/*", exclude_pattern="*.pkl|*.pickle|*fake_home*")
            ).calls(
                generate_fasta_colabfold
            ).calls(
                """
                #!/usr/bin/bash
    
                set -ex
                
                echo "pdb_folder: $pdb_folder"
                
                mkdir -p $HOME/.licenses/
                touch $HOME/.licenses/intel
    
                module load StdEnv/2020 gcc/9.3.0 cuda/11.4 openmpi/4.0.3 openmm/8.0.0 hh-suite/3.3.0 hmmer/3.2.1 mmseqs2/14-7e284
    
                TE=$TASK_VENV/bin/activate                      
                echo "will activate env: $TE"
                source $TE
    
                echo "running colabfold search"
                colabfold_search \\
                  --threads $n_cpu_4_search --use-env 1 --db-load-mode 0 \\
                  --mmseqs mmseqs \\
                  --db1 $collabfold_db/uniref30_2302_db \\
                  --db2 $collabfold_db/pdb100_230517 \\
                  --db3 $collabfold_db/colabfold_envdb_202108_db \\
                  $fa_out $collabfold_db $__task_output_dir
    
                echo "done"
    
            """).calls("""
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
                    --multimer_name=$multimer_name \\
                    --fasta=$fa_out

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


def colabfold_pipeline():

    from dpfold.task_confs import cc_remote_task_conf_func_func

    def p(dsl):

        errors, samplesheet, multimers, pipeline_instance_args = parse_and_validate_input_files(dsl.pipeline_instance_dir())

        tc = cc_remote_task_conf_func_func(pipeline_instance_args)

        yield from collabfold_dag(dsl, multimers, samplesheet, tc)

    return DryPipe.create_pipeline(p)

