Cache dir structure
-------------------

::

    config.cache.path/          # ~/.cache/too-many-repos by default
                     /gists/
                         /bin/
                             /ids.pickle
                             /<id>/
                                  /filenames.pickle
                                  /<filename>/
                                             /content.pickle
                         /raw/
                             /<id>/
                                  /<filename>/
                                             /local/
                                                   /<filename>.py
                                                   /<filename>.stripped.py
                                             /fetched/
                                                     /<filename>.py
                                                     /<filename>.stripped.py
                     /repos/