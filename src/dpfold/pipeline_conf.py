
import os
from pathlib import Path


from dpfold.dag import colabfold_pipeline, parse_and_validate_input_files
from dry_pipe.pipeline import PipelineType


class DPFoldPipelineType(PipelineType):

    def task_sort_key(self, task_key):
        if task_key == "cf-download-pdbs":
            return "000"
        elif task_key.startswith("cf-fold-array"):
            return "010"

        return "020"

    def array_grouper(self, task_key):

        if task_key.startswith("cf-fold."):
            return "cf-fold-array"

        return None

    def doc_root(self):
        return Path(__file__).parent

    def name(self):
        return "DPFold"

    def pipeline(self):
        pipeline_code_dir = str(Path(__file__).parent.parent)
        return colabfold_pipeline()

    def validate_before_run(self, pipeline_instance_dir):
        errors, samplesheet, multimers, _ = parse_and_validate_input_files(pipeline_instance_dir)
        return errors, None

    def default_args(self):
        return {}

    def is_complete(self):
        return None

    def result_files(self, pipeline_instance_dir):
        zipz = list(Path(pipeline_instance_dir, "output", "cf-aggregate-report").glob("*.zip"))
        if len(zipz) > 0:
            csvs = Path(pipeline_instance_dir, "output", "cf-aggregate-report").glob("*.csv")
            res = list(csvs) + zipz
            yield from res
        else:
            yield from []

    def pre_run_filters(self):
        return ["cf-download-pdbs"]

def gen_conf():

    def read_dir_from_env_var(name):

        v = os.environ.get(name)
        if v is None:
            raise Exception(f"missing env var {name}")
        if not os.path.exists(v):
            raise Exception(f"dir {v} specified by {name} must exist")

        return str(v)

    pipeline_run_site = read_dir_from_env_var("PIPELINE_INSTANCES_DIR")
    dp_fold_instances_dir = str(Path(pipeline_run_site, "dp-fold"))
    Path(dp_fold_instances_dir).mkdir(exist_ok=True)


    yield dp_fold_instances_dir, DPFoldPipelineType()
