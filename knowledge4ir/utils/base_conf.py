"""
I am the basic config file to be used for all the packages
    as a default
all the project level constant are set here.
this is sth to be used for impoet
"""

from os import path
ROOT_PATH = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))
GDEVAL_PATH = ROOT_PATH + '/knowledge4ir/utils/gdeval.pl'
RANKSVM_PATH = ROOT_PATH + '/knowledge4ir/model/rank_svm'
TMP_DIR = ROOT_PATH + '/tmp/S2Ranking/'
DATA_PATH = "/bos/usr0/cx/tmp/knowledge4ir/data/"
TARGET_TEXT_FIELDS = ['title', 'bodyText',]
MS_ENTITY_KEY = '3c552f84af52430482da7285e4da8ad9'
