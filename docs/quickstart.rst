.. _quickstart:

Quickstart
==========

Install ``databench`` as shown at the top of the :ref:`overview` page. To start
a new analysis called *helloworld*, use ``scaffold-databench helloworld`` which
creates a directory structure like this:

.. code-block:: bash

    - workingDir/
        - analyses/
            - __init__.py
            - index.yaml
            - helloworld/
                - __init__.py
                - analysis.py
                - index.html
                - thumbnail.png (optional)

At this point you are all set up and can run ``databench``, view the analysis
in a browser at http://localhost:5000 and start modifying the analysis source code.

To understand the structure, this is a walk-through of the steps that just
happened in ``scaffold-databench``. First, add the analyses to the
``analyses/index.yaml`` file:

.. code-block:: yaml

    title: My Analyses
    description: Describing my analyses with words.

    analyses:
      - name: helloworld
        title: Hello World!
        description: A hello world example.

Next, create the helloworld backend in ``analyses/helloworld/analysis.py``:

.. code-block:: python

    import databench


    class HelloWorld(databench.Analysis):

        def on_connect(self):
            """Run as soon as a browser connects to this."""
            self.data['status'] = 'Hello World'


And the frontend in ``analyses/helloworld/index.html``:

.. code-block:: html

    {% extends "analysis.html" %}


    {% block analysis %}
    <p id="output"></p>
    {% end %}


    {% block footer %}
    <script>
        var d = new Databench.Connection();

        d.on('data', function(data) {
            document.getElementById('output').innerHTML = data.status;
        });

        d.connect();
    </script>
    {% end %}

Now you can run the executable ``databench`` in your ``workingDir`` folder
(outside of ``analyses``) which creates a webserver and you can open
http://localhost:5000 in your webbrowser. The command line options ``--host``
and ``--port`` set the host and port of the webserver ``--log`` changes the
loglevel. For example, calling ``databench --log=DEBUG`` enables all messages;
the options are ``NOTSET``, ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR`` and
``CRITICAL``. Running databench in ``WARNING`` or ``INFO`` enables autoreloading
on code changes. You can also create a ``requirements.txt`` file containing
other Python packages your analysis needs. An example of this setup is the
`databench_examples`_ repository.

.. _`databench_examples`: https://github.com/svenkreiss/databench_examples


**Without a template**: The analysis can also be run without a template. You
can replace ``index.html`` with

.. code-block:: html

    <!DOCTYPE html>
    <html>
    <head><title>Hello World</title></head>
    <body>
        <p id="output"></p>

        <script src="/_static/databench.js"></script>
        <script>
            var d = new Databench.Connection();

            d.on('data', function(data) {
                document.getElementById('output').innerHTML = data.status;
            });

            d.connect();
        </script>
    </body>
    </html>

You can find the result of this tutorial in the `helloworld analysis of the databench_examples`_ repo.

.. _`helloworld analysis of the databench_examples`: https://github.com/svenkreiss/databench_examples


Data flow
---------

At the lowest level, Databench communicates between frontend and backend by
sending messages on a long-lived bidirectional WebSocket connection. That means
that both frontend and backend can signal to the other end a change in state
or transmit an action without being polled.

Depending on where state is stored (and that can be mixed within an analysis),
two models for data flow are often used. First, a model where state is stored
in a Datastore in the backend. This datastore can be a store like Redis that is
shared across instances of the Python backend.

.. image:: images/dataflow_datastore_state.png
   :alt: data flow with state stored in datastore

Second, transient state -- state that is deleted at the end of a session
and is usually concerned with the user's UI -- is stored in the frontend.
In this case, the backend only sends actions but not state to the frontend.
The frontend can also send actions to the backend.

.. image:: images/dataflow_frontend_state.png
   :alt: data flow with state stored in frontend
