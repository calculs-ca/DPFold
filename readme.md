



Long on Narval with forwarding of port 8000 :  

```
ssh -L 8000:127.0.0.1:8000 user@narval.computecanada.ca
```


Init local DPFold home : 

```
/project/def-marechal/dpfold.sh init 
```

Start server : 

```
/project/def-marechal/dpfold.sh 
```

On your local machine, point your browser to http://127.0.0.1:8000