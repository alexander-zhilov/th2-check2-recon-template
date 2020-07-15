# *******************************************************************************
#  * Copyright 2009-2020 Exactpro (Exactpro Systems Limited)
#  *
#  * Licensed under the Apache License, Version 2.0 (the "License");
#  * you may not use this file except in compliance with the License.
#  * You may obtain a copy of the License at
#  *
#  * http://www.apache.org/licenses/LICENSE-2.0
#  *
#  * Unless required by applicable law or agreed to in writing, software
#  * distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.
#  ******************************************************************************

import atexit
import importlib
import logging.config
import os
import pkgutil

import sys
import pika

from th2recon import comparator, store, services
from th2recon.rules_configurations_loader import load_rules
from th2recon.th2 import infra_pb2

logging.config.fileConfig(fname=str(sys.argv[1]), disable_existing_loggers=False)
logger = logging.getLogger()

RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT'))
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_EXCHANGE_NAME_TH2_CONNECTIVITY = os.getenv('RABBITMQ_EXCHANGE_NAME_TH2_CONNECTIVITY')
CACHE_SIZE = int(os.getenv('CACHE_SIZE'))
RECON_TIMEOUT = int(os.getenv('RECON_TIMEOUT'))
ROUTING_KEYS = [key.replace('{', '').replace('}', '').replace('"', '').replace(' ', '') for key in
                os.getenv('ROUTING_KEYS').split(',')]
TIME_INTERVAL = int(os.getenv('TIME_INTERVAL'))
EVENT_STORAGE_URI = os.getenv('EVENT_STORAGE')
COMPARATOR_URI = os.getenv('COMPARATOR_URI')
RECON_NAME = str(os.getenv('RECON_NAME'))
RULES_CONFIGURATIONS_PATH = str(os.getenv('RULES_CONFIGURATIONS_FILE'))
RULES_PACKAGE_PATH = 'rules'

credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
params = pika.ConnectionParameters(virtual_host=RABBITMQ_VHOST, host=RABBITMQ_HOST, port=RABBITMQ_PORT,
                                   credentials=credentials)

connection = pika.BlockingConnection(params)
channel = connection.channel()

channel.exchange_declare(exchange=RABBITMQ_EXCHANGE_NAME_TH2_CONNECTIVITY, exchange_type='direct')

queue_listeners = {
    routing_key: services.QueueListener(routing_key, CACHE_SIZE, channel, RECON_TIMEOUT,
                                        ROUTING_KEYS.index(routing_key)) for routing_key in ROUTING_KEYS}

for queue_listener in queue_listeners.values():
    channel.queue_bind(exchange=RABBITMQ_EXCHANGE_NAME_TH2_CONNECTIVITY,
                       queue=queue_listener.queue_name,
                       routing_key=queue_listener.routing_key)


def callback(ch, method, properties, body):
    message_batch = infra_pb2.MessageBatch()
    message_batch.ParseFromString(body)
    for message in message_batch.messages:
        queue_listeners[method.routing_key].buffer.put(item=message, block=True)
        logger.debug("Received message from %r:%r %r" % (
            method.routing_key, message.metadata.message_type, message.metadata.timestamp.seconds))


for queue_listener in queue_listeners.values():
    channel.basic_consume(queue_listener.queue_name,
                          callback,
                          auto_ack=True)


def import_submodules(package, recursive=True):
    if isinstance(package, str):
        package = importlib.import_module(package)
    results = {}
    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + '.' + name
        results[full_name] = importlib.import_module(full_name)
        if recursive and is_pkg:
            results.update(import_submodules(full_name))
    return results


event_store = store.Store(EVENT_STORAGE_URI, RECON_NAME)
comparator = comparator.Comparator(COMPARATOR_URI)
loaded_rules = load_rules(RULES_CONFIGURATIONS_PATH, RULES_PACKAGE_PATH)
rules = []
for rule in loaded_rules:
    rules.append(rule.module.Rule(event_store, ROUTING_KEYS, CACHE_SIZE, TIME_INTERVAL, comparator, rule.enabled,
                                  rule.configuration))

recon = services.Recon(rules, queue_listeners)


def shutdown_hook():
    channel.stop_consuming()
    recon.stop()


atexit.register(shutdown_hook)

try:
    recon.start()
    logger.info("Waiting for messages")
    channel.start_consuming()
except KeyboardInterrupt:
    shutdown_hook()
finally:
    shutdown_hook()