import os
from pathlib import Path

from dry_pipe import TaskConf


this_python_root = Path(__file__).parent.parent


def cc_remote_task_conf_func_func(pipeline_instance_args):
    slurm_allocation = pipeline_instance_args["cc_allocation"]
    cc_username = os.environ["cc_username"]
    use_cc_robot = os.environ.get("USE_CC_ROBOT") == "True"

    cc_cluster = pipeline_instance_args["cc_cluster"]

    if use_cc_robot:
        cc_host = f"robot.{cc_cluster}.computecanada.ca"
    else:
        cc_host = f"{cc_cluster}.computecanada.ca"

    #cc_project = pipeline_instance_args["cc_project"]

    cc_project = slurm_allocation

    remote_base_dir = f"/home/{cc_username}/projects/{cc_project}"

    remote_pipeline_base_dir = f"{remote_base_dir}/dpfold-pipelines-work-dir"

    collabfold_base = f"/home/{cc_username}/projects/def-marechal"

    task_venv = f"{collabfold_base}/programs/colabfold_af2.3.2_env"

    # /home/maxl/projects/def-marechal/programs/colabfold_af2.3.2_env

    return lambda sbatch_options: TaskConf(
        executer_type="slurm",
        slurm_account=slurm_allocation,
        sbatch_options=sbatch_options,
        extra_env={
            "MUGQIC_INSTALL_HOME": "/cvmfs/soft.mugqic/CentOS6",
            #"DRYPIPE_TASK_DEBUG": "True",
            "PYTHONPATH": f"$__pipeline_instance_dir/external-file-deps{this_python_root}",
            "TASK_VENV": task_venv,
            "remote_base_dir": remote_base_dir,
            "collabfold_db": f"{collabfold_base}/programs/colabfold_db",
            "HOME": "$__task_output_dir/fake_home"
        },
        ssh_remote_dest=f"{cc_username}@{cc_host}:{remote_pipeline_base_dir}",
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





def narval_task_conf(sbatch_options):
    remote_login = os.environ["REMOTE_LOGIN"]

    user = remote_login.split("@")[0].strip()

    remote_base_dir = f"/home/{user}/projects/def-marechal"

    remote_pipeline_base_dir = f"{remote_base_dir}/pipelines-work-dir"

    return TaskConf(
        executer_type="slurm",
        slurm_account=os.environ["SLURM_ACCOUNT"],
        sbatch_options=sbatch_options,
        extra_env={
            "MUGQIC_INSTALL_HOME": "/cvmfs/soft.mugqic/CentOS6",
            "DRYPIPE_TASK_DEBUG": "True",
            "PYTHONPATH": f"$__pipeline_instance_dir/external-file-deps{this_python_root}",
            "TASK_VENV": f"{remote_base_dir}/programs/colabfold_af2.3.2_env",
            "remote_base_dir": remote_base_dir,
            "collabfold_db": f"{remote_base_dir}/programs/colabfold_db",
            "HOME": "$__task_output_dir/fake_home"
        },
        ssh_remote_dest=f"{remote_login}:{remote_pipeline_base_dir}",
        python_bin=f"{remote_base_dir}/programs/colabfold_af2.3.2_env/bin/python3",
        run_as_group=os.environ["SLURM_ACCOUNT"]
    )

def gh_task_conf(sbatch_options):

    #remote_pipeline_base_dir = "/tank/maxl"

    ssh_host_dir = os.environ.get("DPFOLD_REMOTE_SSH_HOST_DIR")

    if ssh_host_dir is None:
        raise Exception("DPFOLD_REMOTE_SSH_HOST_DIR environment variable not set")

    if ":" not in ssh_host_dir:
        raise Exception("bad format of DPFOLD_REMOTE_SSH_HOST_DIR, must be <ssh_user_and_host>:<remote_dir>")

    ssh_host, remote_pipeline_base_dir = ssh_host_dir.split(":")

    programs_base_dir = "/home/def-marechal/programs"
    conda_env_path = f"{programs_base_dir}/conda/envs/openfold_env_1.13"
    openfold_home = f"{programs_base_dir}/openfold"

    return TaskConf(
        executer_type="slurm",
        slurm_account=None,
        sbatch_options=sbatch_options + ["--nodelist=gh1301  -p c-gh"],
        extra_env={
            "PYTHONPATH": f"$__pipeline_instance_dir/external-file-deps{this_python_root}",
            "python_bin": f"{conda_env_path}/bin/python3",
            "remote_base_dir": remote_pipeline_base_dir,
            "collabfold_db": "/tank/jflucier/mmseqs_dbs",
            "OPENFOLD_HOME": openfold_home,
            "PATH": f"{conda_env_path}/bin:{programs_base_dir}/MMseqs2/build/bin:$PATH",
            "HOME": "$__task_output_dir/fake_home",
            "DRYPIPE_TASK_DEBUG": "True",
            "CUDA_LAUNCH_BLOCKING": "1"
        },
        ssh_remote_dest=f"{ssh_host}:{remote_pipeline_base_dir}",
        python_bin=f"{conda_env_path}/bin/python3",
        run_as_group="def-marechal"
    )
