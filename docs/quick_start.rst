===========
Quick Start
===========

well... all you really need is python and pip.. and..

.. code-block:: bash

 pip install feedr

then you can run

.. code-block:: bash

 mouth feed -m 100

and VOILA! (look in your current dir for a "generated.log" file.)


to go beyond `mouth feed`, run:

.. code-block:: bash

 mouth -h
 mouth feed # to send send infinite amount of messages
 mouth list transports # to list the default transports available to you
 mouth list formatters # to list the default formatters available to you
 mouth list fake # for a list of fake data fields you can use

and to configure feedr, see the `configuration <http://feedr.readthedocs.org/en/latest/configuration.html>`_ section.

.. note:: you can use the supplied `vagrantfile <https://github.com/cloudify-cosmo/packman/blob/develop/vagrant/Vagrantfile>`_ which will load a vm with feedr for you..(soon, it will also contain rabbitmq, logstash, elasticsearch and kibana so that you can do some more play.)
