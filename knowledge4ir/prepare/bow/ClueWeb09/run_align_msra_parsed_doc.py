"""
condor run msra pasred doc
"""

import os
import sys
from knowledge4ir.utils.condor import get_cx_job, qsub_job
import time
import ntpath
import json

if 4 != len(sys.argv):
    print "3 para: doc text tokenized parsed dir + doc urldir + out dir"
    sys.exit()

l_doc_text_name = []
for dir_name, sub_dirs, file_names in os.walk(sys.argv[1]):
    l_doc_text_name.extend([os.path.join(dir_name, fname)
                            for fname in file_names if fname.startswith('part')])

url_name = sys.argv[2]


out_dir = os.path.join(sys.argv[3], ntpath.basename(url_name))
if not os.path.exists(out_dir):
    os.makedirs(out_dir)
for text_name in l_doc_text_name:
    out_name = os.path.join(out_dir, text_name)
    l_cmd = ['qsub', 'python', 'align_msra_parsed_doc.py', text_name, url_name, out_name]
    job_id = qsub_job(l_cmd)
    print "submitted %s job %s" % (json.dumps(l_cmd), job_id)


print "all submitted"



