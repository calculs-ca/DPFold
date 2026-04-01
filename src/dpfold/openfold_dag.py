import os
from pathlib import Path

from dry_pipe import DryPipe
import glob

from dpfold import colabfold_analysis
from dpfold.multimer import parse_multimer_list_from_samplesheet
from dpfold.multimer import file_path as multimer_code_file


@DryPipe.python_call()
def generate_fasta_openfold(samplesheet, multimer_name, fa_out):
    multimer = parse_multimer_list_from_samplesheet(samplesheet, multimer_name)[0]
    return multimer.generate_fasta_openfold(fa_out)


@DryPipe.python_call()
def duplicate_stos(__task_output_dir):

    def sequence_basename_without_index_suffix(sequence_name):
        return "_".join(
            sequence_name.split("_")[:-1]
        )

    stos_by_basename = {
        sequence_basename_without_index_suffix(Path(sto).parent.name): sto
        for sto in glob.glob(os.path.join(__task_output_dir, "*", "uniprot_hits.sto"))
    }

    for d in glob.glob(os.path.join(__task_output_dir, "*", "uniref.a3m")):

        seq_subdir = Path(d).parent
        seq_name = seq_subdir.name
        expected_sto = os.path.join(seq_subdir, "uniprot_hits.sto")

        if not os.path.exists(expected_sto):

            basename = sequence_basename_without_index_suffix(seq_name)

            sto = stos_by_basename.get(basename)

            if sto is None:
                raise Exception(f"could not find uniprot_hits.sto for {seq_name}")

            os.symlink(sto, expected_sto)



def openfold_dag(dsl, list_of_multimers, samplesheet, task_conf_func):
    slurm_options_align = ["--time=4:00:00 --cpus-per-task=8 --mem=100G"]

    slurm_options_fold = ["--time=24:00:00 --gpus-per-node=1 --cpus-per-task=8 --mem=50G"]

    for multimer in list_of_multimers:
        fold_name = multimer.generate_openfold_fold_name()
        multimer_name = multimer.multimer_name()

        yield dsl.task(
            key=f"of-align.{multimer_name}",
            is_slurm_array_child=True,
            task_conf=task_conf_func(slurm_options_align)
        ).inputs(
            samplesheet=dsl.file(samplesheet),
            multimer_name=multimer_name,
            code_dep1=dsl.file(__file__),
            code_dep2=dsl.file(multimer_code_file()),
            fold_name=fold_name,
            colabfold_analysis_script=dsl.file(colabfold_analysis.code_path())
        ).outputs(
            fa_out=dsl.file(f'{fold_name}.fa')
        ).calls(
            generate_fasta_openfold
        ).calls("""
            #!/usr/bin/bash                        
            set -ex

            echo "user home is $HOME"
            mkdir -p $HOME

            cd $OPENFOLD_HOME

            $python_bin -u ${OPENFOLD_HOME}/scripts/precompute_alignments_mmseqs.py \\
               --threads 7 \\
               --hhsearch_binary_path hhsearch \\
               --pdb70 $collabfold_db/pdb100 \\
               --env_db colabfold_envdb_202108_db \\
               $fa_out \\
               $collabfold_db \\
               uniref30_2302_db \\
               $__task_output_dir \\
               mmseqs
        """).calls("""
            #!/usr/bin/bash                        
            set -ex
            cd $OPENFOLD_HOME

            echo "running uniprot alignment on $__task_output_dir"
            $python_bin -u ${OPENFOLD_HOME}/scripts/precompute_alignments.py \\
                $__task_output_dir \\
                $__task_output_dir \\
                --raise_errors \\
                --uniprot_database_path $collabfold_db/uniprot/uniprot.fasta \\
                --jackhmmer_binary_path jackhmmer \\
                --cpus_per_task 7
            """
                   ).calls(
            duplicate_stos
        )()

        def fold_model(model):
            return f"""
              #!/usr/bin/bash                        
              set -ex

              echo "folding using model {model}"

              echo "SLURM_JOB_GPUS: $SLURM_JOB_GPUS"
              echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"                          

              in_dir=$__pipeline_instance_dir/output/of-align.${{multimer_name}}

              echo "OPENFOLD_HOME=$OPENFOLD_HOME"              

              cd $OPENFOLD_HOME

              echo "PATH: $PATH:"

              export PYTORCH_MEM_HISTORY_DUMP=$__task_output_dir/mem_dump_for_model_{model}.pickle

              if [ "$protein_count" = "1" ]; then
                  config_preset="model_{model}_ptm"                  
                  model_pkl=$__task_output_dir/predictions/${{fold_name}}_model_{model}_ptm_output_dict.pkl
              else
                  config_preset="model_{model}_multimer_v3"
                  model_pkl=$__task_output_dir/predictions/${{fold_name}}_model_{model}_multimer_v3_output_dict.pkl
              fi                            

              $python_bin -u $OPENFOLD_HOME/run_pretrained_openfold.py \\
                $in_dir \\
                $collabfold_db/pdb_mmcif/mmcif_files \\
                --use_precomputed_alignments $in_dir \\
                --config_preset $config_preset \\
                --model_device "cuda:$SLURM_JOB_GPUS" \\
                --output_dir $__task_output_dir \\
                --jax_param_path $OPENFOLD_HOME/openfold/resources/params/params_${{config_preset}}.npz \\
                --save_outputs

              echo "generate JSON for model {model}"
              $python_bin -u $OPENFOLD_HOME/scripts/pickle_to_json.py \\
                --model_pkl $model_pkl \\
                --output_dir $__task_output_dir/predictions/ \\
                --basename ${{fold_name}} \\
                --model_nbr {model}                
            """

        yield dsl.task(
            key=f"of-fold.{multimer_name}",
            is_slurm_array_child=True,
            task_conf=task_conf_func(slurm_options_fold)
        ).inputs(
            fold_name=fold_name,
            multimer_name=multimer_name,
            protein_count=str(multimer.protein_count()),
            colabfold_analysis_script=dsl.file(colabfold_analysis.code_path())
        ).outputs(
            all_results=dsl.file_set("**/*"),
        ).calls(
            fold_model(1)
        ).calls(
            fold_model(2)
        ).calls(
            fold_model(3)
        ).calls(
            """
            #!/usr/bin/bash
            set -ex
            echo "generating coverage plots"

            align_task_out=$__pipeline_instance_dir/output/of-align.${multimer_name}

            if [ "$protein_count" = "1" ]; then

               input_pkl=$__task_output_dir/${fold_name}_model_1_ptm_feature_dict.pickle
               plot_basename=$__task_output_dir/${fold_name}_relaxed

               model_1_pkl=$__task_output_dir/predictions/${fold_name}_model_1_ptm_output_dict.pkl
               model_2_pkl=$__task_output_dir/predictions/${fold_name}_model_2_ptm_output_dict.pkl
               model_3_pkl=$__task_output_dir/predictions/${fold_name}_model_3_ptm_output_dict.pkl
            else         
               input_pkl=$__task_output_dir/${fold_name}_model_1_multimer_v3_feature_dict.pickle
               plot_basename = $__task_output_dir/${fold_name}_multimer_v3_relaxed                              

               model_1_pkl=$__task_output_dir/predictions/${fold_name}_model_1_multimer_v3_output_dict.pkl
               model_2_pkl=$__task_output_dir/predictions/${fold_name}_model_2_multimer_v3_output_dict.pkl
               model_3_pkl=$__task_output_dir/predictions/${fold_name}_model_3_multimer_v3_output_dict.pkl
            fi                            

            $python_bin -u ${OPENFOLD_HOME}/scripts/generate_coverage_plot.py \\
              --input_pkl $input_pkl \\
              --output_dir $__task_output_dir/predictions/ \\
              --basename $plot_basename

            echo "running AF2multimer-analysis on $__task_output_dir/predictions/"                        
            touch $__task_output_dir/predictions/${fold_name}.done.txt            
            mkdir -p $__task_output_dir/predictions/unrelaxed            
            mv $__task_output_dir/predictions/*unrelaxed.pdb $__task_output_dir/predictions/unrelaxed/ || true

            if [ "$protein_count" = "1" ]; then
              echo "will skip colabfold_analysis_script"
            else   
              $python_bin -u $colabfold_analysis_script \\
                 --pred_folder=$__task_output_dir/predictions \\
                 --out_folder=$__task_output_dir \\
                 --multimer_name=$multimer_name \\
                 --fasta=$align_task_out/${fold_name}.fa
            fi                              

            echo "generating PAE, plDDT plots and JSON files"
            $python_bin -u ${OPENFOLD_HOME}/scripts/generate_pae_plddt_plot.py \\
              --fasta $align_task_out/${fold_name}.fa \\
              --model1_pkl $model_1_pkl \\
              --model2_pkl $model_2_pkl \\
              --model3_pkl $model_3_pkl \\
              --output_dir $__task_output_dir/predictions/ \\
              --basename "${fold_name}" \\
              --interface $__task_output_dir/interfaces.csv
            """
        )()

    for match in dsl.query_all_or_nothing("of-align.*", state="ready"):
        yield dsl.task(
            key=f"of-align-array",
            task_conf=task_conf_func(slurm_options_align),
        ).slurm_array_parent(
            children_tasks=match.tasks
        )()

    for _ in dsl.query_all_or_nothing("of-align-array", state="completed"):
        for match in dsl.query_all_or_nothing("of-fold.*", state="ready"):
            yield dsl.task(
                key=f"of-fold-array",
                task_conf=task_conf_func(slurm_options_fold)
            ).slurm_array_parent(
                children_tasks=match.tasks
            )()
