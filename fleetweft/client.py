"""Small operational client; tests use these same HTTP APIs, not a second engine."""
from .net import request


def register(controller, node, name='a'):
    status = request(node, '/status')
    old = request(controller, '/status')['agents'].get(name)
    request(controller, '/register', {'node': name, 'incarnation': status['incarnation'], 'expected': old})
    return status


def accept(controller, node, name='a'):
    token = request(controller, '/grant', {'node': name})
    status = request(node, '/status')
    return request(node, '/accept', {'token': token, 'incarnation': status['incarnation']})


def activate(node, status):
    return request(node, '/activate', {'token': status['token'], 'incarnation': status['incarnation']})


def sample(controller, node, sequence):
    status = request(node, '/status'); active = request(controller, '/status')['active']
    value = request(node, '/sample', {'token': status['token'], 'incarnation': status['incarnation'],
                                     'challenge': active['challenge'], 'sequence': sequence, 'input': 7})
    return request(controller, '/sample', value)
