# -*- coding: utf-8 -*-
#  Copyright (C) 2010 elishowk@nonutc.fr
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)-8s %(message)s")

import neo4jrestclient.client
#neo4jrestclient.client.DEBUG=1
from neo4jrestclient.client import GraphDatabase, NotFoundError
from mongodbhandler import CablegateDatabase

import re
from datetime import datetime

def update_edge(graphdb, nodesource, nodetargets, type, value=1):
    for new_target in nodetargets:
        if new_target.id != nodesource.id:
            nodesource.relationships.create(type, new_target, weight=value)

def set_node_attr(record, node):
    """
    Type conversion from python/mongodb to neo4j
    restricts a node's attributes to string or numeric
    """
    for key, value in record.items():
        if type(value)==unicode:
            node.set(str(key), value.encode("utf_8","replace"))
        elif type(value) in [int,float,str]:
            node.set(str(key), value)
        elif type(value)==datetime:
            node.set(str(key), value.strftime('%Y-%m-%d'))

def add_node(graphdb, record):
    node = graphdb.nodes.create()
    set_node_attr(record, node)
    return node

def get_node(graphdb, _id):
    try:
        return graphdb.nodes.get(_id)
    except NotFoundError:
        return None


class CableNetwork(object):
    def __init__(self, config, overwrite=True, minoccs=1, mincoocs=1, maxcables=None):
        self.mongodb = CablegateDatabase(config['general']['mongodb'])["cablegate"]
        self.graphdb = GraphDatabase(config['general']['neo4j'])
        self.config = config
        nodecache = {}
        count=0
        if maxcables is None:
            self.mongodb.cables.count()
        for cable in self.mongodb.cables.find(timeout=False):
            cablenode = self.graphdb.nodes.get(cable['_id'])
            for ngid, occs in cable['edges']['NGram'].iteritems():
                if occs < minoccs: continue
                ngram = self.mongodb.ngrams.find_one({'_id':ngid})
                if ngram is None:
                    logging.warn('ngram %s linked to document %s but not found in mongodb'%(ngid, cable['_id']))
                    continue
                if str(ngram['nodeid']) not in nodecache:
                    nodecache[str(ngram['nodeid'])] = self.graphdb.nodes.get(ngram['nodeid'])
                cablenode.relationships.create("occurrence", nodecache[str(ngram['nodeid'])], weight=occs)
            count += 1
            if count > maxcables: break

        for ngram in self.mongodb.ngrams.find(timeout=False):
            if ngram['occs'] < minoccs:
                self.graphdb.nodes.delete(ngram['nodeid'])
                continue
            coocidRE = re.compile("^"+ngram['_id']+"_[a-z0-9]+$")

            if str(ngram['nodeid']) not in nodecache:
                nodecache[str(ngram['nodeid'])] = self.graphdb.nodes.get(ngram['nodeid'])

            for cooc in self.mongodb.cooc.find({"_id":{"$regex":coocidRE}}, timeout=False):
                if cooc['value'] < mincoocs: continue
                ng1, ng2 = cooc['_id'].split("_")
                if ng1 == ng2:
                    self.mongodb.cooc.delete({"_id":cooc['_id']})
                    continue
                ngram2 = self.mongodb.ngrams.find_one({'_id':ngid})
                if ngram2['occs'] < minoccs: continue
                #logging.debug("setting cooc from %s to %s = %d"%(ng1,ng1, cooc['value']))
                if str(ngram2['nodeid']) not in nodecache:
                    nodecache[str(ngram2['nodeid'])] = self.graphdb.nodes.get(ngram2['nodeid'])
                nodecache[str(ngram['nodeid'])].relationships.create("cooccurrence", nodecache[str(ngram2['nodeid'])], weight=cooc['value'])
