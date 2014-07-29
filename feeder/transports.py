#!/usr/bin/env python

# TODO: (FEAT) add graphite - https://github.com/daniellawrence/graphitesend

import pika
import logging
import os
from abc import abstractmethod, ABCMeta
from datetime import date
from time import sleep

# TRANSPORT SPECIFIC
from logentries import LogentriesHandler
import pymongo
from elasticsearch import Elasticsearch
import urllib2

# import pretty table for statistical data visualization
from prettytable import PrettyTable

# FILE DEFAULTS
DEFAULT_FILE_PATH = 'generated.log'
DEFAULT_MAXBYTES = 10000000
DEFAULT_BACKUPS = 20

# AMQP DEFAULTS
# queue name for packager events
DEFAULT_AMQP_QUEUE = 'myqueue'
# routing key..
DEFAULT_AMQP_ROUTING_KEY = 'myroutingkey'
# broker exchange
DEFAULT_AMQP_EXCHANGE = ''

# ES DEFAULTS
DEFAULT_ES_PORT = '9200'
DEFAULT_ES_URL_PREFIX = ''
DEFAULT_ES_TIMEOUT = '10'

d = date.today()
DEFAULT_ES_INDEX = 'logstash-{}.{}.{}'.format(d.year, d.month, d.day)
DEFAULT_ES_DOC_TYPE = 'doc'
DEFAULT_ES_SLEEP = 3

# LOGGLY DEFAULTS
DEFAULT_LOGGLY_DOMAIN = 'logs-01.loggly.com'

# MONGO DEFAULTS
DEFAULT_MONGO_PORT = 27017
DEFAULT_MONGO_DB = 'test'
DEFAULT_MONGO_COLLECTION = 'my_collection'
DEFAULT_MONGO_SLEEP = 1


class BaseTransport(object):

    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self, config):
        return

    @abstractmethod
    def configure(self):
        return

    @abstractmethod
    def send(self, client, log):
        return


class FileTransport(BaseTransport):
    """a RotatingFileHandler transport implementation"""
    def __init__(self, config):
        self.file_path = config.get('file', DEFAULT_FILE_PATH)
        self.max_bytes = config.get('max_bytes', DEFAULT_MAXBYTES)
        self.backups_count = config.get('backups_count', DEFAULT_BACKUPS)

    def configure(self):
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
        logger = logging.getLogger('feeder')
        handler = logging.handlers.RotatingFileHandler(
            self.file_path, maxBytes=self.max_bytes,
            backupCount=self.backups_count)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def send(self, client, log):
        client.info(log)

    def close(self):
        pass

    def get_data(self):
        # https://code.google.com/p/prettytable/wiki/Tutorial
        # you can also get data from csv's, htmls, etc...
        # so for instance, you could query elasticsearch right here,
        # get the data, and write it here, so that you can make sure
        # all logs you wrote actually made it through.
        data_table = PrettyTable(["Type", "Value"])
        # make sure the "type" field is always aligned to the left.
        data_table.align["Type"] = "l"
        # ...
        data_table.padding_width = 1
        with open(self.file_path) as f:
            # populate the table
            # TODO: (BUG) fix bug where rotating files will return a bad line
            # TODO: (BUG) count if more than one file is generated
            data_table.add_row(["lines written", sum(1 for _ in f)])
        return data_table


class AMQPTransport(BaseTransport):
    """an amqp transport implementation"""
    def __init__(self, config):
        try:
            self.host = config['host']
        except KeyError as ex:
            raise RuntimeError('configuration incomplete: {}'.format(ex))
        self.queue = config.get('queue', DEFAULT_AMQP_QUEUE)
        self.exchange = config.get('exchange', DEFAULT_AMQP_EXCHANGE)
        self.routing_key = config.get('routing_key', DEFAULT_AMQP_ROUTING_KEY)

    def configure(self):
        if not self.host:
            raise RuntimeError('no host defined')
        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(self.host))
        except:
            raise RuntimeError('could not connect to host')

        client = self.connection.channel()
        client.queue_declare(queue=self.queue, durable=True)
        return client

    def send(self, client, log):
        client.basic_publish(exchange=self.exchange,
                             routing_key=self.routing_key,
                             body=log,
                             properties=pika.BasicProperties(delivery_mode=2))

    # TODO: (FEAT) support connection closing
    def close(self):
        self.connection.close()


class UDPTransport(BaseTransport):
    """a udp transport implementation"""
    def __init__(self, config):
        try:
            self.host = config['host']
            self.port = config['port']
        except KeyError as ex:
            raise RuntimeError('configuration not complete: {}'.format(ex))

    def configure(self):
        logger = logging.getLogger('feeder')
        handler = logging.handlers.DatagramHandler(self.host, self.port)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def send(self, client, log):
        # getattr(logger, level)(message)
        client.debug(log)

    def close(self):
        pass


class StreamTransport(BaseTransport):
    """a shell stream transport implementation"""
    def __init__(self, config):
        pass

    def configure(self):
        logger = logging.getLogger('feeder')
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def send(self, client, log):
        client.debug(log)


class ElasticsearchTransport(BaseTransport):
    """an Elasticsearch transport implementation"""
    def __init__(self, config):
        try:
            self.host = config.get('host')
            self.port = config.get('port', DEFAULT_ES_PORT)
            self.url_prefix = config.get('url_prefix', DEFAULT_ES_URL_PREFIX)
            self.timeout = config.get('timeout', DEFAULT_ES_TIMEOUT)

            self.index = config.get('index', DEFAULT_ES_INDEX)
            self.doc_type = config.get('doc_type', DEFAULT_ES_DOC_TYPE)

            self.sleep = config.get('sleep', DEFAULT_ES_SLEEP)
        except KeyError as ex:
            raise RuntimeError('configuration not complete: {}'.format(ex))

    def configure(self):
        es = Elasticsearch(
            host=self.host,
            port=int(self.port),
            url_prefix=self.url_prefix,
            timeout=float(self.timeout)
        )
        es.indices.create(index=self.index, ignore=400)
        self.indices_client = es.indices
        self.docs = self.indices_client.stats(
            index=self.index)['_all']['total']['docs']['count']
        return es

    def send(self, client, log):
        client.index(
            index=self.index,
            doc_type=self.doc_type,
            body=log
        )

    def close(self):
        pass

    def get_data(self):
        sleep(self.sleep)
        data_table = PrettyTable(["Type", "Value"])
        data_table.align["Type"] = "l"
        data_table.padding_width = 1
        self.current_docs = self.indices_client.stats(
            index=self.index)['_all']['total']['docs']['count']
        data_table.add_row(["docs before", self.docs])
        data_table.add_row(["docs after", self.current_docs])
        data_table.add_row(["docs written", self.current_docs - self.docs])
        return data_table


class LogentriesTransport(BaseTransport):
    """a logentries transport implementation"""
    def __init__(self, config):
        try:
            self.token = config['token']
        except KeyError as ex:
            raise RuntimeError('configuration not complete: {}'.format(ex))

    def configure(self):
        logger = logging.getLogger('logentries')
        handler = LogentriesHandler(self.token)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def send(self, client, log):
        client.debug(log)

    def close(self):
        pass


class LogglyTransport(BaseTransport):
    """a Loggly transport implementation"""
    # TODO: (IMPRV) check out https://github.com/kennedyj/loggly-handler/
    def __init__(self, config):
        try:
            self.domain = config.get('url', DEFAULT_LOGGLY_DOMAIN)
            self.token = config['token']
        except KeyError as ex:
            raise RuntimeError('configuration not complete: {}'.format(ex))

    def configure(self):
        logger = "http://{0}/inputs/{1}/tag/python/".format(
            self.domain, self.token)
        return logger

    def send(self, client, log):
        log = "PLAINTEXT=" + urllib2.quote(log)
        urllib2.urlopen(client, log)

    def close(self):
        pass


class MongoDBTransport(BaseTransport):
    """a MongoDB transport implementation"""
    def __init__(self, config):
        try:
            self.host = config['host']
            self.port = config.get('port', DEFAULT_MONGO_PORT)
            self.db = config.get('db', DEFAULT_MONGO_DB)
            self.collection = config.get(
                'collection', DEFAULT_MONGO_COLLECTION)
            self.sleep = config.get('sleep', DEFAULT_MONGO_SLEEP)
        except KeyError as ex:
            raise RuntimeError('configuration not complete: {}'.format(ex))

    def configure(self):
        mongo = pymongo.MongoClient(self.host, self.port)
        self.collection_client = mongo[self.db][self.collection]
        self.docs = self.collection_client.count()
        return self.collection_client

    def send(self, client, log):
        client.save(log)

    def close(self):
        pass

    def get_data(self):
        sleep(self.sleep)
        data_table = PrettyTable(["Type", "Value"])
        data_table.align["Type"] = "l"
        data_table.padding_width = 1
        current_docs = self.collection_client.count()
        data_table.add_row(["docs before", self.docs])
        data_table.add_row(["docs after", current_docs])
        data_table.add_row(["docs written", current_docs - self.docs])
        return data_table
