"""
I am the basic config file to be used for all the packages
    as a default
all the project level constant are set here.
this is sth to be used for impoet
"""

from os import path
ROOT_PATH = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))
GDEVAL_PATH = ROOT_PATH + '/scholarranking/utils/gdeval.pl'
TMP_DIR = ROOT_PATH + '/tmp/S2Ranking/'


