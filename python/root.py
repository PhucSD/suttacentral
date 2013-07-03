import cherrypy, os
import config, suttacen, show, time

# We expose everything we need to here.

def error_page_404(status, message, traceback, version):
    return open(os.path.join(config.static_root, '404.html'), 'r').read()

class Root(object):

    _cp_config = {
        'error_page.404': error_page_404
    }

    @cherrypy.expose
    def default(self, *args, **kwargs):
        result = show.dispatch(*args, **kwargs)
        return result

    find = suttacen.Find()
    #  /find/  where the search queries go.
    #def find(self, **kwargs):
        #return suttacen.find(**kwargs)

    #  /debug/  Provides debug information
    @cherrypy.expose
    def debug(self, *args, **kwargs):
        return suttacen.debug(*args, **kwargs)

    #  /  Home page
    @cherrypy.expose
    def index(self):
        return suttacen.home()
        return 'Hello and welcome to Sutta Central!'