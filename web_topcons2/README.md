## Web-server for TOPCONS2

## Description:
This is the web-server implementation of the TOPCONS2 workflow.
The web-server is developed with Django 1.6.4

TOPCONS2 is an updated version of the widely used TOPCONS for predicting
membrane protein topologies using consensus prediction.
It is faster yet more accurate than the old TOPCONS according to our solid
benchmarking. Moreover, it predicts not only the trans-membrane helices,
but also the location of signal peptide

TOPCONS2 may be used for the purpose of academic research only.

TOPCONS2 is available at http://topcons.net


## Reference:
Tsirigos, K.D., Peters, C., Shu, N., Kall, L., Elofsson, A., 2015. The TOPCONS
web server for consensus prediction of membrane protein topology and signal
peptides. Nucleic Acids Res. 43, W401-W407


## Installation

1. init the folder
`$ bash init.sh`

2. bash setup_virtualenv.sh

3. copy the suq file to /usr/bin/
`$ sudo cp misc/suq /usr/bin`


Note: please relink the settings.py to pro_settings.py before you make the
web-sever in public

## How to clone only this sub directory

`
#!/bin/bash
git init web_server
cd web_server
git remote add -f origin https://github.com/ElofssonLab/web_server
git config core.sparseCheckout true
echo "web_topcons2" >> .git/info/sparse-checkout
git pull origin master
`
