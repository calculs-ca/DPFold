



Log on Narval with forwarding of local port 8000 :  

```
ssh -L 8000:127.0.0.1:8000 user@narval.computecanada.ca
```


Init local DPFold home : 

```
mkdir <YOUR_DPFOLD_HOME_DIR>
cd <YOUR_DPFOLD_HOME_DIR>

/project/def-marechal/dpfold.sh init 
```

Start server : 

```
/project/def-marechal/dpfold.sh 
```

On your local machine, point your browser to http://127.0.0.1:8000