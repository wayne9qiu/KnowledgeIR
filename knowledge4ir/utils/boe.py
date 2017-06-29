"""
q info and doc info basic operations
include entity and sf form features
"""

import json
from knowledge4ir.utils import (
    QUERY_FIELD,
    TARGET_TEXT_FIELDS,
    SPOT_FIELD
)
import numpy as np
from scipy import stats
import logging


def form_boe_per_field(h_info, field):
    l_ana = h_info.get(SPOT_FIELD, {}).get(field, [])
    l_e = []
    for ana in l_ana:
        sf = ana['surface']
        loc = ana['loc']
        e = ana['entities'][0]['id']
        h = {'surface': sf, 'loc': loc, 'id': e}
        l_e.append(h)
    return l_e


def form_boe_tagme_field(h_info, field):
    l_ana = h_info.get('tagme', {}).get(field, [])
    l_e = []
    for ana in l_ana:
        e, st, ed = ana[:3]
        loc = (st, ed)
        sf = ana[-1]
        h = {'surface': sf, 'loc': loc, 'id': e}
        l_e.append(h)
    return l_e


def pool_sim_score(l_sim, l_weight=None):
    max_sim = 0
    mean_sim = 0
    l_bin = [0, 0, 0, 0]
    if not l_sim:
        return max_sim, mean_sim, l_bin
    max_sim = max(l_sim)
    if l_weight is None:
        l_weight = [1] * len(l_sim)
    s = np.array(l_sim)
    w = np.array(l_weight)
    mean_sim = s.dot(w) / sum(l_weight)
    for sim, weight in zip(l_sim, l_weight):
        if sim == 1:
            l_bin[0] += weight
        if 0.75 <= sim < 1:
            l_bin[1] += weight
        if 0.5 <= sim < 0.75:
            l_bin[2] += weight
        if 0.25 <= sim < 0.5:
            l_bin[3] += weight
    return max_sim, mean_sim, l_bin


def get_e_pos(e_id, l_ana):
    pos = None
    for p in xrange(len(l_ana)):
        if l_ana[p]['entities'][0]['id'] == e_id:
            pos = p
            break
    return pos


def cmns_feature(e_id, h_info, field, pos=None):
    h_feature = {'cmns': 0}
    l_ana = h_info.get(SPOT_FIELD, {}).get(field, [])

    if pos is None:
        pos = get_e_pos(e_id, l_ana)
    if pos is not None:
        cmns = l_ana[pos]['entities'][0]['cmns']
        h_feature['cmns'] = cmns
    return h_feature


def surface_ambiguity_feature(e_id, h_info, field, pos=None):
    h_sf_info = {}
    l_ana = h_info.get(SPOT_FIELD, {}).get(field, [])
    if pos is None:
        pos = get_e_pos(e_id, l_ana)
    if pos is not None:
        h_sf_info = l_ana[pos]
    h_feature = calc_surface_ambiguity(h_sf_info)
    # h_feature = [(field + '_' + item[0], item[1]) for item in h_feature.items()]
    return h_feature


def calc_surface_ambiguity(h_sf_info):
    h_feature = dict()
    l_e = h_sf_info.get('entities', [])
    l_cmns = [e_info.get('cmns', 0) for e_info in l_e]
    entropy = stats.entropy(l_cmns)
    l_cmns.sort(reverse=True)
    l_cmns.append(0)
    if len(l_cmns) < 2:
        logging.warn('%s no cmns', json.dumps(h_sf_info))
    diff = l_cmns[0] - l_cmns[1]

    h_feature['cmns_entropy'] = entropy
    h_feature['cmns_topdiff'] = diff
    return h_feature


def surface_coverage_features(self, h_sf_info, h_info):
    h_feature = {}
    loc = h_sf_info['loc']
    field = h_sf_info['field']
    h_feature['sf_coverage'] = float(loc[1] - loc[0]) / len(h_info.get(field, "").split())
    h_feature['sf_len'] = len(h_sf_info.get('surface', ''))
    return h_feature


def surface_lp(sf, resource):
    h_feature = {}
    h_stat = resource.h_surface_stat.get(sf, {})
    wiki_tf = h_stat.get('tf', 0)
    lp = 0
    if wiki_tf >= 10:
        lp = h_stat.get('lp', 0)
    h_feature['sf_lp'] = lp
    return h_feature


def word_embedding_vote(e_id, h_info, field, resource):
    l_sim = []
    if e_id in resource.embedding:
        text = h_info.get(field, "")
        logging.debug('[%s] voting for [%s]', text, e_id)
        for t in text.lower().split():
            if t in resource.embedding:
                sim = resource.embedding.similarity(e_id, t)
                l_sim.append(sim)
    else:
        logging.debug('[%s] has no embedding', e_id)
    max_sim, mean_sim, l_bin = pool_sim_score(l_sim)
    h_feature = dict()
    h_feature['w_vote_emb_max'] = max_sim
    h_feature['w_vote_emb_mean'] = mean_sim
    return h_feature


def uw_word_embedding_vote(e_id, h_info, field, loc, resource):
    text = h_info.get(field, "")
    # text = text[loc[0]-20:loc[1]+20]
    # text = ' '.join(text.split()[loc[0]-10:loc[1] + 10])
    l_t = text.split()
    l_t = l_t[loc[0]-10: loc[0]] + l_t[loc[1]: loc[1] + 10]
    text = ' '.join(l_t)
    # text = ' '.join(text.split()[1:-1])
    h_raw = {'uw_text': text}
    h_mid = word_embedding_vote(e_id, h_raw, 'uw_text', resource)
    h_feature = dict([('uw_' + item[0], item[1]) for item in h_mid.items()])
    return h_feature


def entity_embedding_vote(e_id, h_info, field, resource):
    l_sim = []
    embedding = resource.entity_embedding
    if not embedding:
        embedding = resource.embedding
    if e_id in embedding:
        l_e_id = [ana["id"] for ana in form_boe_per_field(h_info, field)]
        logging.debug('[%s] voting for [%s] with %s',
                      h_info['docno'], e_id, json.dumps(l_e_id))
        for other_e_id in l_e_id:
            if other_e_id == e_id:
                continue
            if other_e_id not in embedding:
                continue
            sim = embedding.similarity(e_id, other_e_id)
            l_sim.append(sim)
    else:
        logging.debug('[%s] has no embedding', e_id)
    max_sim, mean_sim, l_bin = pool_sim_score(l_sim)
    h_feature = dict()
    h_feature['e_vote_emb_max'] = max_sim
    h_feature['e_vote_emb_mean'] = mean_sim
    # for i in xrange(len(l_bin)):
    #     h_feature['e_vote_bin_%d' % i] = l_bin[i]
    return h_feature
