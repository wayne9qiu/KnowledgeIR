"""
resource to keep in memory to be shared across the pipeline
"""

import numpy as np
from traitlets.config import Configurable
from traitlets import (
    Unicode,
)
import logging
import json
from gensim.models import Word2Vec
from knowledge4ir.utils.retrieval_model import CorpusStat


class JointSemanticResource(Configurable):
    surface_form_path = Unicode(help="the location of surface form dict, in Json format"
                                ).tag(config=True)
    embedding_path = Unicode(help="embedding location (word2vec format)"
                             ).tag(config=True)
    surface_stat_path = Unicode(help="the location of surface form stat dict in json"
                                ).tag(config=True)
    entity_field_path = Unicode(help="entity field path"
                                ).tag(config=True)
    
    def __init__(self, **kwargs):
        super(JointSemanticResource, self).__init__(**kwargs)
        self.embedding = None
        self.h_surface_form = None
        self.h_surface_stat = None
        self.h_entity_fields = None
        self._load()
        self.corpus_stat = CorpusStat(**kwargs)

    @classmethod
    def class_print_help(cls, inst=None):
        super(JointSemanticResource, cls).class_print_help(inst)
        CorpusStat.class_print_help(inst)

    def _load(self):
        self._load_entity_fields()
        self._load_sf()
        self._load_emb()
        self._load_sf_stat()
        return

    def _load_sf(self):
        if not self.surface_form_path:
            return
        logging.info('loading sf dict from [%s]', self.surface_form_path)
        self.h_surface_form = json.load(open(self.surface_form_path))
        logging.info('sf dict of [%d] size loaded', len(self.h_surface_form))

    def _load_sf_stat(self):
        if not self.surface_stat_path:
            return
        logging.info('loading sf stat from [%s]', self.surface_stat_path)
        self.h_surface_stat = json.load(open(self.surface_stat_path))
        logging.info('sf stat of [%d] size loaded', len(self.h_surface_stat))

    def _load_emb(self):
        if not self.embedding_path:
            return
        logging.info('loading embedding [%s]', self.embedding_path)
        self.embedding = Word2Vec.load_word2vec_format(self.embedding_path)
        logging.info('embedding loaded')

    def _load_entity_fields(self):
        if not self.entity_field_path:
            return
        logging.info('loading entity fields from [%s]', self.entity_field_path)
        self.h_entity_fields = dict()
        for line in open(self.entity_field_path):
            h_field = json.loads(line)
            self.h_entity_fields[h_field['id']] = h_field

        logging.info('total [%d] entity fields loaded', len(self.h_entity_fields))


