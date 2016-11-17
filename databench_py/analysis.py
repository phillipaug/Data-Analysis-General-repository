"""Analysis module for Databench Python kernel."""

from databench import Datastore
import logging

log = logging.getLogger(__name__)


class Analysis(object):
    """Databench's analysis class."""

    datastore_class = Datastore

    def __init__(self, id_):
        self.id_ = id_
        self.emit = lambda s, pl: log.error('emit called before Analysis '
                                            'setup complete')

        self.data = Analysis.datastore_class(self.id_)
        self.data.on_change(self.data_change)
        self.class_data = Analysis.datastore_class(type(self).__name__)
        self.class_data.on_change(self.class_data_change)

    def set_emit_fn(self, emit_fn):
        """Sets what the emit function for this analysis will be."""
        self.emit = emit_fn
        return self

    """Events."""

    def on_connect(self):
        log.debug('on_connect called.')

    def on_disconnected(self):
        log.debug('on_disconnected called.')

    """Data callbacks."""

    def data_change(self, key, value):
        if hasattr(self, 'data_{}'.format(key)):
            value = getattr(self, 'data_{}'.format(key))(value)
        self.emit('data', {key: value})

    def class_data_change(self, key, value):
        if hasattr(self, 'class_data_{}'.format(key)):
            value = getattr(self, 'class_data_{}'.format(key))(value)
        self.emit('class_data', {key: value})