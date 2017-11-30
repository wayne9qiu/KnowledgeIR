"""
data io
"""
import json

import torch
from torch.autograd import Variable
from knowledge4ir.utils import (
    term2lm,
    SPOT_FIELD,
    EVENT_SPOT_FIELD,
    body_field,
    title_field,
    abstract_field,
    salience_gold
)

# use_cuda = torch.cuda.is_available()
use_cuda = False


def padding(ll, filler):
    n = max([len(l) for l in ll])
    for i in xrange(len(ll)):
        ll[i] += [filler] * (n - len(ll[i]))
    return ll


def get_top_k_e(l_e, max_e_per_d):
    h_e_tf = term2lm(l_e)
    l_e_tf = sorted(h_e_tf.items(), key=lambda item: -item[1])[:max_e_per_d]
    l_e = [item[0] for item in l_e_tf]
    z = float(sum([item[1] for item in l_e_tf]))
    l_w = [item[1] / z for item in l_e_tf]
    return l_e, l_w


def raw_io(l_line, spot_field=SPOT_FIELD,
           in_field=body_field, salience_gold_field=salience_gold,
           max_e_per_d=200):
    """
    convert data to the input for the model
    """
    ll_e = []
    ll_w = []
    ll_label = []
    for line in l_line:
        h = json.loads(line)
        l_e = h[spot_field].get(in_field, [])
        l_e, l_w = get_top_k_e(l_e, max_e_per_d)
        s_salient_e = set(h[spot_field].get(salience_gold_field, []))
        l_label = [1 if e in s_salient_e else -1 for e in l_e]
        ll_e.append(l_e)
        ll_w.append(l_w)
        ll_label.append(l_label)

    ll_e = padding(ll_e, 0)
    ll_w = padding(ll_w, 0)
    ll_label = padding(ll_label, 0)
    m_e = Variable(torch.LongTensor(ll_e)).cuda() \
        if use_cuda else Variable(torch.LongTensor(ll_e))
    m_w = Variable(torch.FloatTensor(ll_w)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_w))
    m_label = Variable(torch.FloatTensor(ll_label)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_label))

    h_packed_data = {
        "mtx_e": m_e,
        "mtx_score": m_w
    }
    return h_packed_data, m_label


def get_frequency_mask(ll_feature, max_e_per_d):
    if max_e_per_d is None:
        return range(len(ll_feature))
    sorted_features = sorted(enumerate(ll_feature), key=lambda x: x[1][0],
                             reverse=True)
    return set(zip(*sorted_features[:max_e_per_d])[0])


def apply_mask(l, mask):
    masked = []
    for i, e in enumerate(l):
        if i in mask:
            masked.append(e)
    return masked


def event_raw_io(l_line, spot_field=EVENT_SPOT_FIELD,
                 in_field=body_field, salience_gold_field=salience_gold,
                 max_e_per_d=200):
    """
    convert data to the input for the model, this one does not take features
    """
    ll_h = []
    ll_w = []
    ll_label = []
    f_dim = 0

    for line in l_line:
        h = json.loads(line)
        event_spots = h[spot_field].get(in_field, {})
        l_h = event_spots.get('sparse_features', {}).get('LexicalHead', [])
        ll_feature = event_spots.get('features', [])

        # Take the frequency only (index -2)
        ll_feature = [l[-2:-1] for l in ll_feature]

        test_label = event_spots.get(salience_gold_field, [0] * len(l_h))
        l_label = [1 if label == 1 else -1 for label in test_label]

        l_w = [l[0] for l in ll_feature]

        if not l_h:
            continue

        if ll_feature:
            # Now take the most frequent events based on the frequency.
            most_freq_indices = get_frequency_mask(ll_feature, max_e_per_d)
            l_h = apply_mask(l_h, most_freq_indices)
            ll_feature = apply_mask(ll_feature, most_freq_indices)
            l_label = apply_mask(l_label, most_freq_indices)

            z = float(sum([item[0] for item in ll_feature]))
            l_w = [item[0] / z for item in ll_feature]

            f_dim = max(f_dim, len(ll_feature[0]))

        ll_h.append(l_h)
        ll_w.append(l_w)
        ll_label.append(l_label)

    ll_h = padding(ll_h, 0)
    ll_w = padding(ll_w, 0)
    ll_label = padding(ll_label, 0)
    m_e = Variable(torch.LongTensor(ll_h)).cuda() \
        if use_cuda else Variable(torch.LongTensor(ll_h))
    m_w = Variable(torch.FloatTensor(ll_w)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_w))
    m_label = Variable(torch.FloatTensor(ll_label)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_label))

    h_packed_data = {
        "mtx_e": m_e,
        "mtx_score": m_w
    }
    return h_packed_data, m_label


def joint_raw_io(l_line,
                 entity_spot_field=SPOT_FIELD,
                 event_spot_field=EVENT_SPOT_FIELD,
                 in_field=body_field,
                 salience_gold_field=salience_gold,
                 max_e_per_d=200):
    pass


def joint_feature_io(l_line,
                     entity_spot_field=SPOT_FIELD,
                     event_spot_field=EVENT_SPOT_FIELD,
                     in_field=body_field,
                     salience_gold_field=salience_gold,
                     max_e_per_d=200):
    pass


def event_feature_io(l_line, spot_field=EVENT_SPOT_FIELD, in_field=body_field,
                     salience_gold_field=salience_gold, max_e_per_d=200):
    """
    io with events and corresponding feature matrices
    """
    ll_h = []  # List for frames.
    lll_feature = []
    ll_label = []
    f_dim = 0

    for line in l_line:
        h = json.loads(line)
        event_spots = h[spot_field].get(in_field, {})
        l_h = event_spots.get('sparse_features', {}).get('LexicalHead', [])
        ll_feature = event_spots.get('features', [])

        # Take a subset of event features for memory issue.
        # We put -2 to the first position because it is frequency.
        # headcount, sentence loc, event voting, entity voting,
        # ss entity vote aver, ss entity vote max, ss entity vote min
        ll_feature = [l[-2:] + l[-3:-2] + l[9:13] for l in ll_feature]

        # Take label from salience field.
        test_label = event_spots.get(salience_gold_field, [0] * len(l_h))
        l_label = [1 if label == 1 else -1 for label in test_label]

        if not l_h:
            continue

        if ll_feature:
            # Now take the most frequent events based on the feature.
            # Here we assume the first element in the feature is always
            # frequency count. Otherwise you are filtering the events with some
            # other features.
            most_freq_indices = get_frequency_mask(ll_feature, max_e_per_d)
            l_h = apply_mask(l_h, most_freq_indices)
            ll_feature = apply_mask(ll_feature, most_freq_indices)
            l_label = apply_mask(l_label, most_freq_indices)

            f_dim = max(f_dim, len(ll_feature[0]))

        ll_label.append(l_label)
        ll_h.append(l_h)
        lll_feature.append(ll_feature)

    ll_h = padding(ll_h, 0)
    ll_label = padding(ll_label, 0)
    lll_feature = padding(lll_feature, [0] * f_dim)

    # We use event head word in place of entity id.
    m_h = Variable(torch.LongTensor(ll_h)).cuda() \
        if use_cuda else Variable(torch.LongTensor(ll_h))
    m_label = Variable(torch.FloatTensor(ll_label)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_label))
    ts_feature = Variable(torch.FloatTensor(lll_feature)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(lll_feature))

    h_packed_data = {
        "mtx_e": m_h,
        "ts_feature": ts_feature
    }
    return h_packed_data, m_label


def feature_io(l_line, spot_field=SPOT_FIELD, in_field=body_field,
               salience_gold=salience_gold, max_e_per_d=200):
    """
    io with pre-filtered entity list and feature matrices
    """
    # TODO This function didn't do max_e filter.

    ll_e = []
    lll_feature = []
    ll_label = []
    f_dim = 0

    for line in l_line:
        h = json.loads(line)
        packed = h[spot_field].get(in_field, {})
        l_e = packed.get('entities', [])
        ll_feature = packed.get('features', [])
        if not l_e:
            continue
        if ll_feature:
            f_dim = max(f_dim, len(ll_feature[0]))
        # Take label from salience field.
        test_label = packed.get(salience_gold, [0] * len(l_e))
        l_label = [1 if label == 1 else -1 for label in test_label]
        ll_e.append(l_e)
        ll_label.append(l_label)

        lll_feature.append(ll_feature)

    ll_e = padding(ll_e, 0)
    ll_label = padding(ll_label, 0)
    lll_feature = padding(lll_feature, [0] * f_dim)

    m_e = Variable(torch.LongTensor(ll_e)).cuda() \
        if use_cuda else Variable(torch.LongTensor(ll_e))
    m_label = Variable(torch.FloatTensor(ll_label)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_label))
    ts_feature = Variable(torch.FloatTensor(lll_feature)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(lll_feature))

    h_packed_data = {
        "mtx_e": m_e,
        "ts_feature": ts_feature
    }
    return h_packed_data, m_label


def uw_io(l_line, spot_field=SPOT_FIELD,
          in_field=body_field, salience_field=abstract_field, max_e_per_d=200):
    """
    prepare local words around each entity's location
    :param l_line: hashed data with loc fields
    :param spot_field: together with in_field, to get
    :param in_field:
    :param salience_field: to get label
    :param max_e_per_d:
    :return:
    """
    sent_len = 10
    max_sent_cnt = 0
    max_sent_allowed = 5
    ll_e = []
    ll_label = []
    lll_sent = []  #

    for line in l_line:
        h = json.loads(line)
        packed = h[spot_field].get(in_field, {})
        l_e = packed.get('entities', [])
        ll_loc = packed.get('loc', [])
        l_words = h[in_field]
        ll_sent = [
            _form_local_context(l_loc[:max_sent_allowed], l_words, sent_len)
            for l_loc in ll_loc]

        this_max_sent_cnt = max([len(l_sent) for l_sent in ll_sent])
        max_sent_cnt = max(max_sent_cnt, this_max_sent_cnt)

        s_salient_e = set(
            h[spot_field].get(salience_field, {}).get('entities', []))
        l_label = [1 if e in s_salient_e else -1 for e in l_e]

        ll_e.append(l_e)
        ll_label.append(l_label)
        lll_sent.append(ll_sent)

    for d_p in xrange(len(lll_sent)):
        for e_p in xrange(len(lll_sent[d_p])):
            lll_sent[d_p][e_p] += [[0] * sent_len] * (
                max_sent_cnt - len(lll_sent[d_p][e_p]))

    ll_e = padding(ll_e, 0)
    ll_label = padding(ll_label, 0)

    l_empty_e_sent = [[0] * sent_len] * max_sent_cnt
    lll_sent = padding(lll_sent, l_empty_e_sent)

    m_e = Variable(torch.LongTensor(ll_e)).cuda() \
        if use_cuda else Variable(torch.LongTensor(ll_e))
    m_label = Variable(torch.FloatTensor(ll_label)).cuda() \
        if use_cuda else Variable(torch.FloatTensor(ll_label))
    ts_local_context = Variable(torch.LongTensor(lll_sent)).cuda() \
        if use_cuda else Variable(torch.LongTensor(lll_sent))
    h_packed_data = {
        "mtx_e": m_e,
        "ts_local_context": ts_local_context
    }
    return h_packed_data, m_label


def _form_local_context(l_loc, l_words, sent_len):
    """
    get local UW words
    :param l_loc: positions to get UW words
    :param l_words: content
    :param sent_len: length of UW
    :return:
    """
    l_sent = []
    for st, ed in l_loc:
        uw_st = max(st - sent_len / 2, 0)
        uw_st = min(uw_st, len(l_words) - sent_len)
        sent = l_words[uw_st: uw_st + sent_len]
        sent += [0] * (sent_len - len(sent))
        l_sent.append(sent)
    return l_sent


if __name__ == '__main__':
    """
    unit test tbd
    """
    import sys
    from knowledge4ir.utils import (
        set_basic_log,
        load_py_config,
    )
    from traitlets.config import Configurable
    from traitlets import (
        Unicode,
        List,
        Int
    )

    set_basic_log()


    class IOTester(Configurable):
        in_name = Unicode(help='in data test').tag(config=True)
        io_func = Unicode('uw', help='io function to test').tag(config=True)
