import os
from io import StringIO
from itertools import islice, groupby
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Protein:
    name: str
    n_occurences: int
    pdb: str
    seq: str


class Multimer:

    def __init__(self, proteins, line_number_in_samplesheet):
        self.proteins = proteins
        self.line_number_in_samplesheet = line_number_in_samplesheet


    def has_pdbs(self):
        return len(list(self.all_pdbs())) > 0

    def protein_count(self):
        return len(self.proteins)

    def multimer_name(self):
        def s(protein):
            pdb_name = self.pdb_names()
            if pdb_name == "":
                return f"{protein.name}_{protein.n_occurences}"
            else:
                return f"{protein.name}_{protein.n_occurences}_{pdb_name}"

        return "-".join([
            s(protein)
            for protein in self.proteins
        ])

    def fold_name(self):
        names = []
        for protein in self.proteins:
            for x in range(1, protein.n_occurences + 1):
                names.extend([f"{protein.name}_{x}"])
        return "-".join(names)



    def __str__(self):
        return self.multimer_name()

    def generate_fasta_colabfold(self, fa_out):

        fa_header = "_".join([
            f"{protein.name}_{protein.n_occurences}"
            for protein in self.proteins
        ])

        fa_seqs = []
        for protein in self.proteins:
            fa_seqs.extend([protein.seq] * protein.n_occurences)

        with open(fa_out, 'w') as f:
            f.write(f">{fa_header}\n")
            f.write(":".join(fa_seqs))
            f.write("\n")

    def sequence_length(self):
        res = 0
        for protein in self.proteins:
            res += len(protein.seq) * protein.n_occurences
        return res

    def generate_openfold_fold_name(self):

        fa_header = []

        for protein in self.proteins:
            for x in range(1, protein.n_occurences + 1):
                fa_header.extend([f"{protein.name}_{x}"])

        return "-".join(fa_header)

    def generate_fasta_openfold(self, fa_out):

        fa_header = []
        fa_seq = []

        for protein in self.proteins:
            for x in range(1, protein.n_occurences + 1):
                fa_header.extend([f"{protein.name}_{x}"])
            fa_seq.extend([protein.seq] * protein.n_occurences)

        with open(fa_out, 'w') as f:
            f.write("\n".join(
                [f">{h}\n{s}" for h, s in zip(fa_header, fa_seq)]
            ))


    def pdb_names(self):
        def g():
            for p in self.proteins:
                if p.pdb is not None and p.pdb != "":
                    for pdb in p.pdb.split(","):
                        yield pdb

        return "_".join(g())

    def all_pdbs(self):
        for protein in self.proteins:
            pdb_list = protein.pdb.split(",")
            for pdb in pdb_list:
                if pdb == "":
                    continue
                else:
                    yield pdb

    def has_pdb(self, pdb_name):
        for pdb in self.all_pdbs():
            if pdb.casefold() == pdb_name.casefold():
                return True
        return False

    def generate_pdbs(self, output_dir):

        import requests
        from Bio.PDB import MMCIFParser

        multi_model_pdbs = []

        for pdb in self.all_pdbs():
            # download pdb if pdb id is provided
            pdb_out = os.path.join(output_dir, f"{pdb.lower()}.cif")
            if os.path.exists(pdb_out):
                pass
            else:
                print(f"Downloading and generating pdb: {pdb}")
                URL = f"https://files.rcsb.org/download/{pdb}.cif"
                response = requests.get(URL)

                out = StringIO()
                out.write(response.text)
                # modify cif file to include new section. Change name to pdb
                # https://github.com/sokrypton/ColabFold/issues/177
                out.write('#\n')
                out.write('loop_\n')
                out.write('_pdbx_audit_revision_history.ordinal\n')
                out.write('_pdbx_audit_revision_history.data_content_type\n')
                out.write('_pdbx_audit_revision_history.major_revision\n')
                out.write('_pdbx_audit_revision_history.minor_revision\n')
                out.write('_pdbx_audit_revision_history.revision_date\n')
                out.write('1 \'Structure model\' 1 0 1971-01-01\n')
                out.write('#\n')


                # validate PDBs, examples of bad (multi model) : 2KHW,2KTF

                pdb_as_string = out.getvalue()
                parser = MMCIFParser(QUIET=True)
                structure = parser.get_structure("none", StringIO(pdb_as_string))
                models = list(structure.get_models())
                model_count = len(models)
                if model_count != 1:
                    yield f"{pdb} on line {self.line_number_in_samplesheet} has {model_count} models"
                else:
                    with open(pdb_out, "w") as f:
                       f.write(pdb_as_string)


def parse_multimer_list_from_samplesheet(samplesheet, single_multimer_name=None, include_single_prots=True):

    def rows():
        with open(samplesheet) as f:
            c = 1
            for line in f.readlines():
                line = line.rstrip()
                if c == 1:
                    pass
                elif line.startswith("#"):
                    pass
                else:
                    yield c, [field.strip('"') for field in line.split("\t")]

                c +=1

    def g():
        for line_number, row in rows():
            def prots_in_row():
                i = iter(row)
                while prot_rows := list(islice(i, 4)):
                    name = prot_rows[0]
                    if "-" in name:
                        raise Exception(f"illegal prot name on line {line_number}, can't use '-' ")
                    if " " in name:
                        raise Exception(f"illegal prot name on line {line_number}, can't use ' ' ")
                    try:
                        n_occurences = int(prot_rows[1])
                        pdb = prot_rows[2]
                        seq = prot_rows[3]
                        yield Protein(name, n_occurences, pdb, seq)
                    except IndexError:
                        raise Exception(f"to few columns in line {line_number}")

            m = Multimer(list(prots_in_row()), line_number)

            if not include_single_prots:
                if m.protein_count() == 1:
                    print(
                        f"Warning: line {m.line_number_in_samplesheet} ({m.multimer_name()}) excluded, " +
                        "because it contains only one prot"
                    )
                    continue

            if single_multimer_name is None:
                yield m
            else:
                if m.multimer_name() == single_multimer_name:
                    yield m
                    break

    res = list(g())

    def check_duplicates():
        def mn(m):
            return m.multimer_name()
        for n, multimers in groupby(sorted(res, key=mn), key=mn):
            multimers = list(multimers)
            if len(multimers) > 1:
                lines = [str(m.line_number_in_samplesheet) for m in multimers]
                raise Exception(
                    f"duplicate multimer names {n} in {samplesheet}, at lines {','.join(lines)}"
                )

    check_duplicates()

    if single_multimer_name is None:
        return MultimerBatch(res)

    if len(res) == 0:
        raise Exception(f"multimer {single_multimer_name} not found in {samplesheet}")
    elif len(res) > 1:
        lines = [m.line_number_in_samplesheet for m in res]
        raise Exception(f"multiple multimer with name {single_multimer_name} found in {samplesheet}, lines: {lines}")

    return MultimerBatch(res)


class MultimerBatch:

    def __init__(self, multimer_list):
        self.multimer_list = multimer_list

    def multimer_by_name(self, name):
        for m in self.multimer_list:
            if m.multimer_name() == name:
                return m
        raise Exception(f"could not find multimer with name {name}")

    def has_pdbs(self):
        for m in self.multimer_list:
            if m.has_pdbs():
                return True
        return False

    def lines_of_pdb(self, pdb_name):
        for m in self.multimer_list:
            if m.has_pdb(pdb_name):
                yield m.line_number_in_samplesheet

    def download_pdbs(self, folder):

        def gen_and_yield_errors():
            for m in self.multimer_list:
                yield from m.generate_pdbs(folder)

        return list(gen_and_yield_errors())

    def all_pdps_in_folder(self, folder):
        for m in self.multimer_list:
            for pdb in m.all_pdbs():
                if not os.path.exists(os.path.join(folder, f"{pdb.lower()}.cif")):
                    return False
        return True

    def __iter__(self):
        yield from self.multimer_list


def file_path():
    return __file__


if __name__ == '__main__':


    multimer_batch = parse_multimer_list_from_samplesheet("/home/maxl/dev/Marechal_pipelines/example/test-case-1/samplesheet.tsv")

    pdb_path = Path("/home/maxl/dev/Marechal_pipelines/tmp/pdbs")

    multimer_batch.download_pdbs(pdb_path)

