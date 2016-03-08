"""Main Flask App."""

from __future__ import absolute_import, unicode_literals, division

import os
import sys
import glob
import logging
import traceback
import zmq.eventloop

import tornado.web
import tornado.autoreload

try:
    import glob2
except ImportError:
    glob2 = None

from .analysis import Meta
from .analysis_zmq import MetaZMQ
from .readme import Readme
from . import __version__ as DATABENCH_VERSION

log = logging.getLogger(__name__)


class App(object):
    """Databench app. Creates a Tornado app."""

    def __init__(self, zmq_port=None):

        self.info = {
            'title': 'Databench',
            'description': None,
            'author': None,
            'version': None,
        }

        self.routes = [
            (r'/(favicon\.ico)',
             tornado.web.StaticFileHandler,
             {'path': 'static/favicon.ico'}),

            (r'/_static/(.*)',
             tornado.web.StaticFileHandler,
             {'path': os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   'static')}),

            (r'/_node_modules/(.*)',
             tornado.web.StaticFileHandler,
             {'path': os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   'node_modules')}),

            (r'/',
             IndexHandler,
             {'info': self.info}),
        ]

        # check whether we have to determine zmq_port ourselves first
        if zmq_port is None:
            context = zmq.Context()
            socket = context.socket(zmq.PUB)
            zmq_port = socket.bind_to_random_port(
                'tcp://127.0.0.1',
                min_port=3000, max_port=9000,
            )
            socket.close()
            context.destroy()
            log.debug('determined: zmq_port={}'.format(zmq_port))

        self.spawned_analyses = {}

        zmq_publish = zmq.Context().socket(zmq.PUB)
        zmq_publish.bind('tcp://127.0.0.1:{}'.format(zmq_port))
        log.debug('main publishing to port {}'.format(zmq_port))

        zmq_publish_stream = zmq.eventloop.zmqstream.ZMQStream(zmq_publish)
        self.register_analyses_py(zmq_publish_stream, zmq_port)
        self.register_analyses_pyspark(zmq_publish_stream, zmq_port)
        self.register_analyses_go(zmq_publish_stream, zmq_port)
        self.import_analyses()
        self.register_analyses()

    def tornado_app(self, debug=False, template_path=None, **kwargs):
        if template_path is None:
            template_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                'templates',
            )

        if debug:
            self.build()

        return tornado.web.Application(
            self.routes,
            debug=debug,
            template_path=template_path,
            **kwargs
        )

    def register_analyses_py(self, zmq_publish, zmq_port):
        analysis_folders = glob.glob('analyses/*_py')
        if not analysis_folders:
            analysis_folders = glob.glob('databench/analyses_packaged/*_py')

        for analysis_folder in analysis_folders:
            name = analysis_folder.rpartition('/')[2]
            if name[0] in ('.', '_'):
                continue
            log.debug('creating MetaZMQ for {}'.format(name))
            MetaZMQ(name,
                    ['python', '{}/analysis.py'.format(analysis_folder),
                     '--zmq-subscribe={}'.format(zmq_port)],
                    zmq_publish)

    def register_analyses_pyspark(self, zmq_publish, zmq_port):
        analysis_folders = glob.glob('analyses/*_pyspark')
        if not analysis_folders:
            analysis_folders = glob.glob(
                'databench/analyses_packaged/*_pyspark'
            )

        for analysis_folder in analysis_folders:
            name = analysis_folder.rpartition('/')[2]
            if name[0] in ('.', '_'):
                continue
            log.debug('creating MetaZMQ for {}'.format(name))
            MetaZMQ(name,
                    ['pyspark', '{}/analysis.py'.format(analysis_folder),
                     '--zmq-subscribe={}'.format(zmq_port)],
                    zmq_publish)

    def register_analyses_go(self, zmq_publish, zmq_port):
        analysis_folders = glob.glob('analyses/*_go')
        if not analysis_folders:
            analysis_folders = glob.glob('databench/analyses_packaged/*_go')

        for analysis_folder in analysis_folders:
            name = analysis_folder.rpartition('/')[2]
            if name[0] in ('.', '_'):
                continue
            log.info('installing {}'.format(name))
            os.system('cd {}; go install'.format(analysis_folder))
            log.debug('creating MetaZMQ for {}'.format(name))
            MetaZMQ(name,
                    [name, '--zmq-subscribe={}'.format(zmq_port)],
                    zmq_publish)

    def import_analyses(self):
        """Add analyses from the analyses folder."""

        sys.path.append('.')
        try:
            import analyses
        except ImportError as e:
            if str(e).replace("'", "") != 'No module named analyses':
                traceback.print_exc(file=sys.stdout)
                raise e

            log.warning('Did not find "analyses" module. '
                        'Using packaged analyses.')
            from databench import analyses_packaged as analyses

        analyses_path = os.path.dirname(os.path.realpath(analyses.__file__))

        self.info['author'] = getattr(analyses, '__author__', None)
        self.info['version'] = getattr(analyses, '__version__', None)
        self.info['logo_url'] = getattr(analyses, 'logo_url', None)
        self.info['title'] = getattr(analyses, 'title', None)

        readme = Readme(analyses_path)
        self.info['description'] = readme.text
        self.info.update(readme.meta)

        if self.info['logo_url'] is None:
            log.info('Analyses module does not specify a logo url.')
            self.info['logo_url'] = '/_static/logo.svg'
        if self.info['version'] is None:
            log.info('Analyses module does not specify a version.')
        if self.info['author'] is None:
            log.info('Analyses module does not specify an author.')
        if self.info['title'] is None:
            log.info('Analyses module does not specify a title.')
            self.info['title'] = 'Databench'

        # process files to watch for autoreload
        if 'watch' in readme.meta:
            log.info('watching files: {}'.format(readme.meta['watch']))
            if glob2:
                files = glob2.glob(readme.meta['watch'])
            else:
                files = glob.glob(readme.meta['watch'])
                if '**' in readme.meta['watch']:
                    log.warning('Please run "pip install glob2" to properly '
                                'process watch patterns with "**".')
            for fn in files:
                log.debug('watch file {}'.format(fn))
                tornado.autoreload.watch(fn)

        # if 'analyses' contains a 'static' folder, make it available
        static_path = os.path.join(analyses_path, 'static')
        if os.path.isdir(static_path):
            log.debug('Making {} available under /static/.'
                      ''.format(static_path))

            self.routes.append((
                r'/static/(.*)',
                tornado.web.StaticFileHandler,
                {'path': static_path},
            ))
        else:
            log.debug('Did not find an analyses/static/ folder.')

        # if 'analyses' contains a 'node_modules' folder, make it available
        node_modules_path = os.path.join(analyses_path, 'node_modules')
        if os.path.isdir(node_modules_path):
            log.debug('Making {} available under /node_modules/.'
                      ''.format(node_modules_path))

            self.routes.append((
                r'/node_modules/(.*)',
                tornado.web.StaticFileHandler,
                {'path': node_modules_path},
            ))
        else:
            log.debug('Did not find an analyses/node_modules/ folder.')

    def register_analyses(self):
        """Register analyses (analyses need to be imported first)."""

        for meta in Meta.all_instances:
            log.info('Registering meta information {}'.format(meta.name))
            self.routes += meta.routes

            if 'logo_url' in self.info and \
               'logo_url' not in meta.info:
                meta.info['logo_url'] = self.info['logo_url']

    def build(self):
        """Run the build command specified in the Readme."""
        if 'build' not in self.info:
            return

        cmd = self.info['build']
        log.debug('building this command: {}'.format(cmd))
        os.system(cmd)


class IndexHandler(tornado.web.RequestHandler):
    def initialize(self, info):
        self.info = info

    def get(self):
        """Render the List-of-Analyses overview page."""
        return self.render(
            'index.html',
            analyses=Meta.all_instances,
            databench_version=DATABENCH_VERSION,
            **self.info
        )
