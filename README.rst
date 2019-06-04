
Do things with the Humio API
============================

.. code-block::

   Usage: hc COMMAND [OPTIONS] [ARGS]...


  Humio CLI for working with the humio API. Defaults to the search command.

  For detailed help about each command try:

.. code-block::

   hc <command> --help


  All options may be provided by environment variables on the format
  ``HUMIO_<OPTION>=<VALUE>``. If a .env file exists in ``~/.config/humio/.env`` it
  will be automatically sourced on execution without overwriting the
  existing environment.

Examples
--------

Execute a search in all repos starting with ``reponame`` and output ``@rawstring``\ s
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   hc --repo reponame* '#type=accesslog statuscode>=400'

Output aggregated results as ND-JSON events
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Simple example:

..

   *Humios bucketing currently creates partial buckets in both ends depending on search period. Provide a whole start and end to ensure we only get whole buckets.*


.. code-block:: bash

   hc --repo sandbox* --start=-60m@m --end=@m "#type=accesslog | timechart(span=1m, series=statuscode)"

Or with a long multiline search

.. code-block:: bash

   hc --repo sandbox* --start -60m@m --end=@m  "$(cat << EOF
   #type=accesslog
   | case {
       statuscode<=400 | status_ok := 1 ;
       statuscode=4*  | status_client_error := "client_error" ;
       statuscode=5*  | status_server_error := "server_error" ;
       * | status_broken := 1
   }
   | bucket(limit=50, function=[count(as="count"), count(field=status_ok, as="ok"), count(field=status_client_error, as="client_error"), count(field=status_server_error, as="server_error")])
   | error_percentage := (((client_error + server_error) / count) * 100)
   EOF
   )"

Upload a parser file to the destination repository, overwriting any existing parser
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   hc makeparser --repo=sandbox* customjson

Ingest a single-line log file with an ingest-token associated with a parser
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   hc ingest customjson

Ingest a multi-line file with a user provided record separator (markdown headers) and parser
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   hc ingest README.md --separator '^#' --fields '{"#repo":"sandbox", "#type":"markdown", "@host":"localhost"}'

Development
-----------

To install the cli and core packages in editable mode:

.. code-block:: bash

   git clone https://github.com/gwtwod/py3humiocore.git
   git clone https://github.com/gwtwod/py3humiocli.git
   # order matters if you want to be able to edit humiocore as well
   pip install -e py3humiocore
   pip install -e py3humiocli

Self-contained distribution
---------------------------

..

   *The runtime interpreter must be specified if the system interpreter is incompatible, for example on RHEL7*


With Shiv:

.. code-block:: bash

   git clone https://github.com/gwtwod/py3humiocli.git
   shiv -c hc -o hc py3humiocli/ -p /opt/rh/rh-python36/root/bin/python3.6

With Pex:

```bash
git clone https://github.com/gwtwod/py3humiocli.git
git clone https://github.com/gwtwod/py3humiocore.git
pex --disable-cache -c hc -o hc py3humiocli py3humiocore --python-shebang=/opt/rh/rh-python36/root/bin/python3.6
