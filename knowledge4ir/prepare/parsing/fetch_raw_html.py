"""
fetch target html for given docno's
use warc package
    for ClueWeb 12, the open source warc will do
    for ClueWeb 09, it is a little triky, will need the modified one

input:
    target doc no, one per line
    folder of raw warc format clueweb doc
do:
    read warc file, dump out html for target docno

output:
    a file, each line:
        docnot \t html
"""

import warccw09
import os
import ntpath
import logging
import sys
reload(sys)  # Reload does the trick!
sys.setdefaultencoding('UTF8')



def get_target_doc_per_file(fname, s_docno):
    s_doc_pre = set(['-'.join(docno.split('-')[1:3]) for docno in s_docno])

    l_res = []
    cw09_pre = ntpath.basename(ntpath.dirname(fname)) + '-' + ntpath.basename(fname.replace('.warc.gz', ""))
    cw12_pre = ntpath.basename(fname).replace('.warc.gz', "")
    if (cw09_pre not in s_doc_pre) & (cw12_pre not in s_doc_pre):
        return l_res

    in_file = warccw09.open(fname)
    logging.info('start reading [%s]', fname)
    cnt = 0
    try:
        for record in in_file:
            if 'warc-trec-id' not in record:
                logging.warn('record has no trec id')
                continue
            cnt += 1
            docno = record['warc-trec-id']
            logging.debug('get doc [%s]', docno)
            if docno not in s_docno:
                continue
            logging.info('get [%s]', docno)
            res = ""
            for line in record.payload:
                res += line + ' '
            res = ' '.join(res.split())
            l_res.append(res)
    except AssertionError:
        logging.error('[%s] assertion error', fname)
    logging.info('[%s] get [%d] target docs in [%d] doc', fname, len(l_res), cnt)
    return l_res


def process_dir(in_dir, target_doc_in, out_name):
    s_docno = set(open(target_doc_in).read().splitlines())
    logging.info('total [%d] target docno', len(s_docno))
    out = open(out_name, 'w')
    for dir_name, sub_dirs, file_names in os.walk(in_dir):
        for fname in file_names:
            in_name = os.path.join(dir_name, fname)
            l_res = get_target_doc_per_file(in_name, s_docno)
            print >> out, '\n'.join(l_res)
    out.close()


if __name__ == '__main__':
    from knowledge4ir.utils import set_basic_log
    set_basic_log(logging.DEBUG)

    if 4 != len(sys.argv):
        print "3 para: in_dir + target docno + output"
        sys.exit(-1)

    process_dir(*sys.argv[1:])







