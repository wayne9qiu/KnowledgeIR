"""
EF and Coor match feature
input:
    q info
    doc info
output:
    h_feature
"""

import json
from traitlets.config import Configurable
from traitlets import (
    Unicode,
)
import logging
from knowledge4ir.utils import (
    TARGET_TEXT_FIELDS,
    body_field,
    QUERY_FIELD,
    term2lm,
    mean_pool_feature,
    log_sum_feature,
    SPOT_FIELD,
    COREFERENCE_FIELD,
    add_feature_prefix, avg_embedding, text2lm)
from knowledge4ir.utils.retrieval_model import (
    RetrievalModel,
)
from knowledge4ir.utils.boe import (
    form_boe_per_field,
    form_boe_tagme_field,
)


class BoeFeature(Configurable):
    feature_name_pre = Unicode()
    ana_format = Unicode('spot', help='annotation format, tagme or spot').tag(config=True)

    def __init__(self, **kwargs):
        super(BoeFeature, self).__init__(**kwargs)
        self.resource = None


    def set_resource(self, resource):
        self.resource = resource

    def close_resource(self):
        pass

    def _get_field_ana(self, h_info, field):
        l_h_e = []
        if self.ana_format == 'spot':
            l_h_e = form_boe_per_field(h_info, field)
        else:
            l_h_e = form_boe_tagme_field(h_info, field)
        return l_h_e

    def _get_field_entity(self, h_info, field):
        l_h_e = self._get_field_ana(h_info, field)
        return [h['id'] for h in l_h_e]

    # def _get_spot_field_entity(self, h_info, field):
    #     l_h_e = form_boe_per_field(h_info, field)
    #     l_e = [h['id'] for h in l_h_e]
    #     return l_e
    #
    # def _get_tagme_field_entity(self, h_info, field):
    #     l_e = [ana['id'] for ana in form_boe_tagme_field(h_info, field)]
    #     return l_e

    def _get_q_entity(self, q_info):
        return self._get_field_entity(q_info, QUERY_FIELD)

    def _get_doc_entity(self, doc_info):
        l_field_doc_e = [(field, self._get_field_entity(doc_info, field)) for field in TARGET_TEXT_FIELDS]
        return l_field_doc_e

    def _get_e_location(self, e_id, doc_info):
        """
        find location of e_id
        :param e_id: target
        :param doc_info: spotted and coreference document
        :return: h_loc field-> st -> ed
        """
        h_loc = dict()
        for field in TARGET_TEXT_FIELDS:
            h_loc[field] = dict()
            if self.ana_format == 'spot':
                l_h_e = form_boe_per_field(doc_info, field)
            else:
                l_h_e = form_boe_tagme_field(doc_info, field)
            for h_e in l_h_e:
                if h_e['id'] == e_id:
                    st, ed = h_e['loc']
                    h_loc[field][st] = ed
        return h_loc

    # @classmethod
    # def _get_e_spot_location(cls, e_id, doc_info):
    #     h_loc = dict()
    #     for field in TARGET_TEXT_FIELDS:
    #         h_loc[field] = dict()
    #         l_h_e = form_boe_tagme_field(doc_info, field)
    #         for h_e in l_h_e:
    #             if h_e['id'] == e_id:
    #                 st, ed = h_e['loc']
    #                 h_loc[field][st] = ed
    #     return h_loc
    #
    # @classmethod
    # def _get_e_tagme_location(cls, e_id, doc_info):
    #     """
    #     get location from TagMe ana
    #     :param e_id:
    #     :param doc_info:
    #     :return:
    #     """
    #     h_loc = dict()
    #     for field in TARGET_TEXT_FIELDS:
    #         l_ana = doc_info.get('tagme', {}).get(field, [])
    #         h_loc[field] = dict()
    #         for ana in l_ana:
    #             if e_id != ana[0]:
    #                 continue
    #             st, ed = ana[1:3]
    #             h_loc[field][st] = ed
    #     return h_loc

    def extract_pair(self, q_info, doc_info):
        """

        :param q_info:
        :param doc_info:
        :return:
        """
        logging.debug('extracting e_grid nlss features for [%s][%s]',
                      q_info['qid'], doc_info['docno'])
        l_q_ana = self._get_field_ana(q_info, QUERY_FIELD)
        logging.debug('q info %s', json.dumps(q_info))
        logging.debug('q ana %s', json.dumps(l_q_ana))
        logging.debug('doc t [%s], info [%s]', doc_info.get('title', ""),
                      json.dumps(doc_info.get('spot', {}).get('title', []))
                      )
        l_h_feature = [self.extract_per_entity(q_info, ana, doc_info) for ana in l_q_ana]

        h_final_feature = {}
        # h_final_feature.update(log_sum_feature(l_h_feature))
        h_final_feature.update(mean_pool_feature(l_h_feature))
        # h_final_feature = dict([(self.feature_name_pre + item[0], item[1])
        #                         for item in h_final_feature.items()])
        h_final_feature = add_feature_prefix(h_final_feature, self.feature_name_pre + '_')

        return h_final_feature

    def extract_per_entity(self, q_info, ana, doc_info):
        logging.warn('need implement this function in inherited class')
        pass

    def _form_sents_emb(self, l_sent):
        l_emb = [avg_embedding(self.resource.embedding, sent)
                 for sent in l_sent]
        return l_emb

    def _form_sents_bow(self, l_sent):
        l_h_lm = [text2lm(sent, clean=True) for sent in l_sent]
        return l_h_lm


class AnaMatch(BoeFeature):
    feature_name_pre = Unicode('AnaMatch')

    def __init__(self, **kwargs):
        super(AnaMatch, self).__init__(**kwargs)
        logging.info('ana match features uses [%s] annotation', self.ana_format)

    def extract_pair(self, q_info, doc_info):
        """

        :param q_info: will use spot->query
        :param doc_info: will use spot -> doc
        only the first entity is used
        :return: h_feature={feature name : score}
        """

        l_q_e = self._get_q_entity(q_info)
        l_field_doc_e = self._get_doc_entity(doc_info)

        h_feature = dict()
        for field, l_e in l_field_doc_e:
            l_name_score = self._match_qe_de(l_q_e, l_e)
            for name, score in l_name_score:
                h_feature[self.feature_name_pre + '_' + field + '_' + name] = score

        return h_feature

    @classmethod
    def _match_qe_de(cls, l_qe, l_de):
        q_lm = term2lm(l_qe)
        d_lm = term2lm(l_de)
        retrieval_model = RetrievalModel()
        retrieval_model.set_from_raw(q_lm, d_lm)
        l_sim = list()
        l_sim.append(['tf', retrieval_model.tf()])
        l_sim.append(['lm', retrieval_model.lm()])
        l_sim.append(['coor', retrieval_model.coordinate()])
        l_sim.append(['bool_and', retrieval_model.bool_and()])
        return l_sim


class CoreferenceMatch(BoeFeature):
    """
    coreference features
    06/12/2017 version includes:
        has coreference in fields
        # of coreferences in fields
        # of different name variations (total only)
        # of clusters (total only)
    """
    feature_name_pre = Unicode('CoRef')

    def extract_pair(self, q_info, doc_info):
        """
        extract features using doc_infor's coreference field
        :param q_info:
        :param doc_info:
        :return: h_feature
        """
        l_q_e_id = self._get_q_entity(q_info)

        l_h_stats = []
        for q_e_id in l_q_e_id:
            l_mentions = self._find_match_mentions(q_e_id, doc_info)
            h_stats = self._mention_stats(l_mentions)
            l_h_stats.append(h_stats)
        h_feature = self._pull_stats_to_features(l_h_stats)
        h_feature = dict([(self.feature_name_pre + '_' + key, value)
                          for key, value in h_feature.items()
                          ])
        return h_feature

    def _find_match_mentions(self, e_id, doc_info):
        """
        find matched mentions with e_id
        1: get all loc of e_id (in fields)
        2: find all mentions in coreferences that aligns e_id's location
            align == head in e_id's location and equal st
        :param e_id:
        :param doc_info:
        :return: l_mentions = [mentions of e_id in coreferences]
        """
        logging.debug('finding matched mentions for [%s]', e_id)
        h_loc = self._get_e_location(e_id, doc_info)
        logging.debug('[%s] locations in doc %s', e_id, json.dumps(h_loc))
        l_mentions = []
        for mention in doc_info.get(COREFERENCE_FIELD, []):
            mention_cluster = mention['mentions']
            for p in xrange(len(mention_cluster)):
                if mention_cluster[p]['source'] == 'body':
                    mention_cluster[p]['source'] = body_field

            if self._mention_aligned(h_loc, mention_cluster):
                l_mentions.append(mention_cluster)
        logging.debug('mentions on coref %s', json.dumps(l_mentions))
        return l_mentions

    @classmethod
    def _mention_stats(cls, l_mentions):
        h_stats = dict()
        h_stats['nb_mentions'] = len(l_mentions)

        h_field_cnt = dict(zip(TARGET_TEXT_FIELDS, [0] * len(TARGET_TEXT_FIELDS)))
        s_name = set()
        for mention_cluster in l_mentions:
            for sf in mention_cluster:
                h_field_cnt[sf['source']] += 1
                s_name.add(sf['surface'])
        h_field_cnt = dict([(item[0] + '_cnt', item[1]) for item in h_field_cnt.items()])
        h_stats.update(h_field_cnt)
        h_stats['name_variants'] = len(s_name)
        return h_stats

    @classmethod
    def _pull_stats_to_features(cls, l_h_stats):
        """
        combina stats to features
            mean
            log product, with min -20
        :param l_h_stats:
        :return: h_feature
        """

        h_feature = dict()
        h_feature.update(mean_pool_feature(l_h_stats))
        h_feature.update(log_sum_feature(l_h_stats))
        return h_feature

    @classmethod
    def _mention_aligned(cls, h_loc, mention_cluster):
        """
        check if the mention cluster (coreferences) is aligned with h_loc
        alignment definition
            has a surface's head location in h_loc, and equal
        :param h_loc: field->st->ed
        :param mention_cluster: a mention cluster of coreferences,
        :return:
        """
        flag = False
        for sf in mention_cluster:
            field = sf['source']
            head_pos = sf['head']
            st = sf['loc'][0]
            if field in h_loc:
                if st in h_loc[field]:
                    ed = h_loc[field][st]
                    if ed > head_pos:
                        logging.debug('matched %s', json.dumps(sf))
                        flag = True
                        break
        # if flag:
        #     logging.debug('cluster [%s] matched', json.dumps(mention_cluster))
        # else:
        #     logging.debug('cluster [%s] no match', json.dumps(mention_cluster))
        return flag






