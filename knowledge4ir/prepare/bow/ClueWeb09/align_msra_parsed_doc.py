"""
read and align the parsed result from MSRA
input:
    one partition of CW09 url - docno
    one partition of CW09 tokenized
output:
    docno \t url \t doctext
"""

import sys
reload(sys)  # Reload does the trick!
sys.setdefaultencoding('UTF8')


def align_doc_url(doc_text_in, doc_url_in, out_name):
    s_url_no = set([line.split('\t')[0] for line in open(doc_text_in)])
    h_url_no = {}
    for line in open(doc_url_in):
        url, docno = line.strip().split('\t')
        if url in s_url_no:
            h_url_no[url] = docno

    out = open(out_name, "w")
    cnt = 0
    for line in open(doc_text_in):
        url, text = line.strip().split('\t')
        if url in h_url_no:
            docno = h_url_no[url]
            print >> out, docno + "\t" + line.strip()
            cnt += 1
    out.close()
    print "finished [%s][%s] with [%d] found" %(doc_text_in, doc_url_in, cnt)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print "3 para: doc text in, doc url in, out_name"
        sys.exit()

    align_doc_url(*sys.argv[1:])

