"""Meta class for Databench Python kernel."""

import sys
import zmq
import json
import logging

log = logging.getLogger(__name__)


class Meta(object):
    """Class providing Meta information about analyses.

    For Python kernels.

    Args:
        name (str): Name of this analysis.
        import_name (str): Usually the file name ``__name__`` where this
            analysis is instantiated.
        description (str): Usually the ``__doc__`` string of the analysis.
        analysis (Analysis): Analysis class.

    """

    def __init__(self, name, description, analysis_class):
        self.name = name
        self.description = description

        analysis_id, zmq_port_subscribe, zmq_port_publish = None, None, None
        for cl in sys.argv:
            if cl.startswith('--analysis-id'):
                analysis_id = cl.partition('=')[2]
            if cl.startswith('--zmq-subscribe'):
                zmq_port_subscribe = cl.partition('=')[2]
            if cl.startswith('--zmq-publish'):
                zmq_port_publish = cl.partition('=')[2]

        log.info('Analysis id: {}, port sub: {}, port pub: {}'.format(
                 analysis_id, zmq_port_subscribe, zmq_port_publish))

        self.analysis = analysis_class(analysis_id)

        def emit(signal, message):
            self.emit(signal, message, analysis_id)
        self.analysis.set_emit_fn(emit)

        self._init_zmq(zmq_port_publish, zmq_port_subscribe)
        log.info('Language kernel for {} initialized.'.format(self.name))

    def _init_zmq(self, port_publish, port_subscribe):
        """Initialize zmq messaging. Listen on sub_port. This port might at
        some point receive the message to start publishing on a certain
        port, but until then, no publishing."""

        log.debug('kernel {} publishing on port {}'
                  ''.format(self.analysis.id_, port_publish))
        self.zmq_publish = zmq.Context().socket(zmq.PUB)
        self.zmq_publish.connect('tcp://127.0.0.1:{}'.format(port_publish))

        log.debug('kernel {} subscribed on port {}'
                  ''.format(self.analysis.id_, port_subscribe))
        self.zmq_sub = zmq.Context().socket(zmq.SUB)
        self.zmq_sub.setsockopt(zmq.SUBSCRIBE,
                                self.analysis.id_.encode('utf-8'))
        self.zmq_sub.connect('tcp://127.0.0.1:{}'.format(port_subscribe))

    def run_action(self, analysis, fn_name, message='__nomessagetoken__'):
        """Executes an action in the analysis with the given message. It
        also handles the start and stop signals in case an action_id
        is given.

        This method is exactly the same as in databench.Analysis.
        """

        # detect action_id
        action_id = None
        if isinstance(message, dict) and '__action_id' in message:
            action_id = message['__action_id']
            del message['__action_id']

        if action_id:
            analysis.emit('__action', {'id': action_id, 'status': 'start'})

        log.debug('kernel calling {}'.format(fn_name))
        fn = getattr(analysis, fn_name)

        # Check whether this is a list (positional arguments)
        # or a dictionary (keyword arguments).
        if isinstance(message, list):
            fn(*message)
        elif isinstance(message, dict):
            fn(**message)
        elif message == '__nomessagetoken__':
            fn()
        else:
            fn(message)

        if action_id:
            analysis.emit('__action', {'id': action_id, 'status': 'end'})

        if fn_name == 'on_disconnect':
            log.debug('kernel {} shutting down'.format(analysis.id_))
            self.zmq_publish.close()
            sys.exit(0)

    def event_loop(self):
        """Event loop."""
        while True:
            msg = self.zmq_sub.recv().decode('utf-8')
            log.debug('kernel msg: {}'.format(msg))
            msg = json.loads(msg.partition('|')[2])

            if 'signal' not in msg or 'load' not in msg:
                continue

            if not hasattr(self.analysis,
                           'on_{}'.format(msg['signal'])):
                print('Analysis does not contain on_{}()'
                      ''.format(msg['signal']))
                continue

            # standard message
            fn_name = 'on_'+msg['signal']
            log.debug('kernel processing '+fn_name)
            self.run_action(self.analysis, fn_name, msg['load'])

    def emit(self, signal, message, analysis_id):
        """Emit signal to main.

        Args:
            signal: Name of the signal to be emitted.
            message: Message to be sent.
            analysis_id: Identifies the instance of this analysis.

        """

        self.zmq_publish.send_json({
            'analysis_id': analysis_id,
            'frame': {'signal': signal, 'load': message},
        })
