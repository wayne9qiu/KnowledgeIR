"""
generate locally term and entity embedding from PRF docs
input:
    tagme's linked results
output:
    for each doc, two lines:
        body text
        body text with entity replaced
"""

import sys


if 3 != len(sys.argv):
    print "generate locally trained term entity embedding file"
    print "2 para: tagme Doc info + outname"
    sys.exit()

out = open(sys.argv[2], 'w')
err_cnt = 0
for cnt, line in enumerate(open(sys.argv[1])):
    d_info = '\t'.join(line.strip().split('\t')[1:])
    text = d_info.split('#')[0].strip()
    ana_str = d_info.split('#')[-1].strip()
    l_col = ana_str.split('\t')
    l_ana = []
    p = 0
    while p + 8 <= len(l_col):
        try:
            ana = [l_col[p + 6], int(l_col[p + 2]), int(l_col[p + 3])]
            l_ana.append(ana)
        except TypeError:
            err_cnt += 1
        p += 8
    print >> out, text
    e_text = ""
    p = 0
    for ana in l_ana:
        st, ed = ana[1], ana[2]
        e_text += text[p:st] + ana[0]
        p = ed
    print >> out, e_text

out.close()




