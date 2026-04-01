
# Colabfold Pipeline

this is a short overview of the Colabfold pipeline

The samplesheet must be named samplesheet.tsv, format is as follows:

| protein1\_name | protein1\_nbr | protein1\_PDB | protein1\_seq | protein2\_name | protein2\_nbr | protein2\_PDB | protein2\_seq | Comment (not part of the format)                                                                                                                                                                                     |
| :---- | ----- | :---- | :---- | :---- | ----- | :---- | :---- |:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Ubiquitin | 1 |  | MQIFVKTLT... | PTTG1 | 1 |  | MATLIYVDKEN... | <- This will fold Ubiquitin with PTTG1 complex. 1 occurence of each protein will be included in complex.                                                                                                             |
| FoxM1 | 2 |  | MKTSPR... |  |  |  |  | <- This will fold 2 x FoxM1 protein in complex to form homodimer. 2 occurence of foxm1 will be included in complex.                                                                                                     |
| Ubiquitin | 1 |  | MQIFVKTLTGKTI... |  |  |  |  | <- This will fold a single Ubiquitin protein.                                                                                                                                                                           |
| Ubiquitin | 1 | 1YIW | MQIFVKTLTGK... | PTTG1 | 1 |  | MATLIYVD... | <- This will fold Ubiquitin with PTTG1 protein in complex using PDB file as templates to assist in predicting protein structure . 1 occurence of each protein will be included in complex.                              |
| Ubiquitin | 1 |  | MQIFVKTLT... | POLI | 1 |  | MEKLG... | <- This will fold Ubiquitin with POLI protein in complex using PDB file as templates to assist in predicting protein structure . 1 occurence of each protein will be included in complex. 2 PDB entries given for POLI. |
| Ubiquitin | 1 | 1YIW | MQIFV... |  |  |  |  |                                                                                                                                                                                                                      |
| POLQ | 1 | 4X0Q,8E23,6XBU,5A9J | MNLLRRSGKRRRS... |  |  |  |  | <- This will fold a single POLQ protein using multiple PDBs as template                                                                                                                                                 |

### Definitions

+ protein*_name	The name of the protein to fold				
+ protein*_nbr	The number of times a protein must be included in fold complex				
+ protein*_PDB	Comma seperated list of PDB id from https://www.rcsb.org/				
+ protein*_seq	The amino sequence of the protein to fold				
					
### Limitation:					
+ The complex to fold must not excced 2700 amino acids when folding on the narval cluster (A100 GPU with 40GB)					