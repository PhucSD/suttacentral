import babel.dates, cherrypy, http.client, jinja2, newrelic.agent, os.path
import datetime, regex, socket, time, urllib.parse
from webassets.ext.jinja2 import AssetsExtension
from bs4 import BeautifulSoup

import assets, config, scdb, scm
from menu import menu_data
from classes import Parallel, Sutta

import logging
logger = logging.getLogger(__name__)

__jinja2_environment = None
def jinja2_environment():
    """Return the Jinja2 environment singleton used by all views.
    
    For information on Jinja2 custom filters, see
    http://jinja.pocoo.org/docs/api/#custom-filters
    """

    global __jinja2_environment
    if __jinja2_environment:
        return __jinja2_environment

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(config.templates_root),
        extensions=[AssetsExtension],
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.assets_environment = assets.env

    def date_filter(value, format='short', locale=config.default_locale):
        return babel.dates.format_date(value, format=format, locale=locale)
    env.filters['date'] = date_filter

    def time_filter(value, format='short', locale=config.default_locale):
        return babel.dates.format_time(value, format=format, locale=locale)
    env.filters['time'] = time_filter

    def datetime_filter(value, format='short', locale=config.default_locale):
        return babel.dates.format_datetime(value, format=format, locale=locale)
    env.filters['datetime'] = datetime_filter

    def sub_filter(string, pattern, repl):
        return regex.sub(pattern, repl, string)
    env.filters['sub'] = sub_filter

    def sht_expansion(string):
        """Add links from SHT vol/page references to the sht-lookup page."""
        if 'SHT' in string:
            # Replace &nbsp; with spaces
            string = string.replace('&nbsp;', ' ')
            baseurl = '/sht-lookup/'
            def replacement(m):
                # Ignore 'also cf. ix p. 393ff' and ' A'
                first, second = m[1], m[2]
                if regex.match(r'.+p\.\s*', first) or \
                   regex.match(r'.+A', first):
                    return '{}{}'.format(first, second)
                else:
                    # replace n-dash with dash
                    path = second.replace('−', '-')
                    return '{}<a href="{}{}" target="_blank">{}</a>'.format(
                        first, baseurl, path, second)
            string = regex.sub(r'([^0-9]+)([0-9]{1,4}(?:\.?[\−\+0-9a-zA-Z]+)?)',
                replacement, string)
        return string
    env.filters['sht_expansion'] = sht_expansion

    __jinja2_environment = env
    return env

class NewRelicBrowserTimingProxy:
    """New Relic real user monitoring proxy.
    
    See: https://newrelic.com/docs/python/real-user-monitoring-in-python
    """

    @property
    def header(self):
        if config.newrelic_real_user_monitoring:
            return newrelic.agent.get_browser_timing_header()
        else:
            return ''

    @property
    def footer(self):
        if config.newrelic_real_user_monitoring:
            return newrelic.agent.get_browser_timing_footer()
        else:
            return ''

class ViewContext(dict):
    """A dictionary with easy object-style setters/getters.
    
    >>> context = ViewContext()
    >>> context['a'] = 1
    >>> context.b = 2
    >>> context
    {'a': 1, 'b': 2}
    """

    def __getattr__(self, attr):
        return self[attr]

    def __setattr__(self, attr, value):
        self[attr] = value

class ViewBase:
    """The base class for all SuttaCentral views.

    Views must set or override the template_name property.

    Views can optionally define a setup_context() method that will be executed
    during the render() method.

    Views should assign the 'title' context variable so that the page will have
    a (reasonably) relavent title.
    """

    env = jinja2_environment()

    @property
    def template_name(self):
        """Return the template name for this view."""
        raise NotImplementedError('Views must define template_name')

    def get_template(self):
        """Return the Jinja2 template for this view."""
        return self.env.get_template(self.template_name + ".html")

    def setup_context(self, context):
        """Optional method for subclasses to assign additional context
        variables. This is executed during the render() method. The context
        variable is a dictionary with magic setters (see ViewContext)."""
        pass

    def get_global_context(self):
        """Return a dictionary of variables accessible by all templates."""
        return ViewContext({
            'collections': menu_data,
            'config': config,
            'current_datetime': datetime.datetime.now(),
            'development_bar': config.development_bar,
            'newrelic_browser_timing': NewRelicBrowserTimingProxy(),
            'nonfree_fonts': config.nonfree_fonts and not cherrypy.request.offline,
            'offline': cherrypy.request.offline,
            'page_lang': 'en',
            'scm': scm,
            'search_query': '',
        })

    def render(self):
        """Return the HTML for this view."""
        template = self.get_template()
        context = self.get_global_context()
        self.setup_context(context)
        return template.render(dict(context))

class InfoView(ViewBase):
    """A simple view that renders the template page_name; mostly used for
    static pages."""

    def __init__(self, page_name):
        self.page_name = page_name
    
    @property
    def template_name(self):
        return self.page_name

    def setup_context(self, context):
        if self.page_name != 'home':
            title = self.page_name.replace('_', ' ').capitalize()
            if title == 'Contacts':
                title = 'People'
            context.title = title

class DownloadsView(InfoView):
    """The view for the downloads page."""

    formats = ['zip', '7z']

    def __init__(self):
        super().__init__('downloads')

    def setup_context(self, context):
        super().setup_context(context)
        context.offline_data = self.__offline_data()
        context.db_data = self.__db_data()

    def __file_data(self, basename, exports_path):
        data = []
        for format in self.formats:
            latest_filename = '{}-latest.{}'.format(basename, format)
            latest_path = os.path.join(exports_path, latest_filename)
            local_path = os.path.realpath(latest_path)
            logger.debug(latest_path)
            if os.path.exists(local_path):
                data.append({
                    'filename': os.path.basename(local_path),
                    'url': local_path[len(config.static_root):],
                    'time': os.path.getctime(local_path),
                    'size': os.path.getsize(local_path),
                    'format': format,
                })
        return data

    def __offline_data(self):
        return self.__file_data('sc-offline', config.exports_root)

    def __db_data(self):
        return self.__file_data('sc-db', config.exports_root)

class ParallelView(ViewBase):
    """The view for the sutta parallels page."""

    template_name = 'parallel'

    def __init__(self, sutta):
        self.sutta = sutta

    def setup_context(self, context):
        context.title = "{}: {}".format(
            self.sutta.acronym, self.sutta.name)
        context.sutta = self.sutta

        # Add the origin to the beginning of the list of 
        # parallels. The template will display this at the
        # top of the list with a different style.
        origin = Parallel(sutta=self.sutta, partial=False, footnote="", indirect=False)
        parallels = [origin] + self.sutta.parallels

        # Get the information for the table footer.
        has_alt_volpage = False
        has_alt_acronym = False

        for parallel in parallels:
            if parallel.sutta.alt_volpage_info:
                has_alt_volpage = True
            if parallel.sutta.alt_acronym:
                has_alt_acronym = True
        
        # Add data specific to the parallel page to the context.
        context.parallels = parallels
        context.has_alt_volpage = has_alt_volpage
        context.has_alt_acronym = has_alt_acronym
        context.citation = SuttaCitationView(self.sutta).render()

class TextView(ViewBase):
    """The view for showing the text of a sutta or tranlsation."""

    template_name = 'text'

    def __init__(self, uid, lang_code):
        self.uid = uid
        self.lang_code = lang_code

    def setup_context(self, context):
        doc = self.get_document()
        context.title = self.get_title(doc) or '?'
        self.annotate_heading(doc)
        context.text = self.content_html(doc.body)

    @property
    def path(self):
        return scdb.getDBR().text_paths[self.lang_code].get(self.uid) or ''
    
    def get_document(self):
        """Return the BeautifulSoup document object of the text or raise
        a cherrypy.NotFound exception"""
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return BeautifulSoup(f)
        except OSError:
            raise cherrypy.NotFound()

    def get_title(self, doc):
        hgroup = doc.hgroup
        if hgroup:
            h1 = hgroup.h1
            if h1:
                return h1.text

    def annotate_heading(self, doc):
        """Add navigation links to the header h1 and h2"""
        hgroup = doc.hgroup
        if not hgroup:
            return
        h1 = hgroup.h1
        if h1:
            href = '/{}'.format(self.uid)
            a = doc.new_tag('a', href=href,
                title='Click for details of parallels and translations.')
            h1.wrap(a)
            h1.unwrap()
            a.wrap(h1)
        if hasattr(self, 'subdivision'):
            h2 = hgroup.h2
            if h2:
                href = '/{}'.format(self.subdivision.uid)
                a = doc.new_tag('a', href=href,
                    title='Click to go to the division or subdivision page.')
                h2.wrap(a)
                h2.unwrap()
                a.wrap(h2)

    def content_html(self, el):
        """Return the HTML of the contents of el."""
        output = []
        for c in el.contents:
            output.append(str(c))
        output.append('\n')
        return '\n'.join(output)

class SuttaView(TextView):
    """The view for showing the sutta text in original sutta langauge."""

    def __init__(self, sutta, lang, uid, lang_code):
        super().__init__(uid, lang_code)
        self.sutta = sutta
        self.lang = lang

    def setup_context(self, context):
        super().setup_context(context)
        context.title = '{}: {} ({}) - {}'.format(
            self.sutta.acronym, context.title, self.lang.name,
            self.subdivision.name)
        context.sutta_lang_code = self.lang_code

    @property
    def subdivision(self):
        subdivision = self.sutta.subdivision
        if subdivision.uid.endswith('-nosub'):
            return subdivision.division
        else:
            return subdivision

class DivisionView(ViewBase):
    """Thew view for a division."""

    template_name = 'division'

    def __init__(self, division):
        self.division = division

    @property
    def division_lang_code(self):
        """Ugly hack to handle sk/skt discrepancy..."""
        code = self.division.collection.lang.code
        if code == 'sk':
            return 'skt'
        else:
            return code

    @property
    def division_text_url(self):
        """Division-level text URL (if it exists)"""
        if os.path.exists(self.division_text_path):
            return '/{}/{}'.format(self.division.uid,
                self.division_lang_code)
        else:
            return None

    @property
    def division_text_path(self):
        """Division-level text path"""
        return os.path.join(config.text_root,
            self.division_lang_code,
            self.division.uid) + '.html'

    def setup_context(self, context):
        context.title = "{}: {}".format(self.division.acronym,
            self.division.name)
        context.division = self.division
        context.division_text_url = self.division_text_url
        context.has_alt_volpage = False
        context.has_alt_acronym = False

        for subdivision in self.division.subdivisions:
            for sutta in subdivision.suttas:
                if sutta.alt_volpage_info:
                    context.has_alt_volpage = True
                if sutta.alt_acronym:
                    context.has_alt_acronym = True

class SubdivisionView(ViewBase):
    """The view for a subdivision."""

    def __init__(self, subdivision):
        self.subdivision = subdivision

    template_name = 'subdivision'

    def setup_context(self, context):
        context.title = "{} {}: {} - {}".format(
            self.subdivision.division.acronym, self.subdivision.acronym,
            self.subdivision.name, self.subdivision.division.name)
        context.subdivision = self.subdivision
        context.has_alt_volpage = False
        context.has_alt_acronym = False

        for sutta in self.subdivision.suttas:
            if sutta.alt_volpage_info:
                context.has_alt_volpage = True
            if sutta.alt_acronym:
                context.has_alt_acronym = True

class SubdivisionHeadingsView(ViewBase):
    """The view for the list of subdivisions for a division."""

    template_name = 'subdivision_headings'

    def __init__(self, division):
        self.division = division

    def setup_context(self, context):
        context.title = "{}: {}".format(self.division.acronym,
            self.division.name)
        context.division = self.division

class SearchResultView(ViewBase):
    """The view for the search page."""

    template_name = 'search_result'

    def __init__(self, search_query, search_result):
        super().__init__()
        self.search_query = search_query
        self.search_result = search_result

    def setup_context(self, context):
        context.search_query = self.search_query
        context.title = 'Search: "{}"'.format(
            self.search_query)
        context.result = self.search_result
        context.dbr = scdb.getDBR()

class AjaxSearchResultView(SearchResultView):
    """The view for /search?ajax=1."""

    template_name = 'ajax_search_result'

class ShtLookupView(ViewBase):
    """The view for the SHT lookup page."""

    template_name = 'sht_lookup'

    def __init__(self, query):
        self.sht_id = self.parse_first_id(query)
        if self.sht_id:
            self.redir_url = self.get_idp_url(self.sht_id)

    def parse_first_id(self, query):
        m = regex.match(r'^([0-9]{1,4}(?:\.?[0-9a-zA-Z]+)?)', query)
        if m:
            # replace . with /
            return m[1].replace('.', '/')
        else:
            return None

    def get_idp_url(self, sht_id):
        host = 'idp.bl.uk'
        path = '/database/oo_loader.a4d?pm=SHT%20{}'.format(
            urllib.parse.quote_plus(sht_id)
        )
        url = 'http://{}{}'.format(host, path)
        timeout = 1.0
        conn = http.client.HTTPConnection(host, timeout=timeout)
        try:
            conn.request('GET', path)
            response = conn.getresponse()
        except socket.timeout:
            logger.error('SHT Lookup {} timed out after {}s'.format(
                url, timeout))
            return False
        if response.status in [301, 302, 303]:
            location = response.headers['Location']
            if 'itemNotFound' not in location:
                return 'http://idp.bl.uk/database/' + location
            else:
                logger.info('SHT Lookup ID {} not found'.format(sht_id))
                return False
        else:
            logger.error('SHT Lookup {} returned unexpected response {}'.format(
                url, response.status))
            return False

    def setup_context(self, context):
        context.title = 'SHT Lookup {}'.format(self.sht_id)
        context.sht_id = self.sht_id
        context.redir_url = self.redir_url
        if self.redir_url:
            raise cherrypy.HTTPRedirect(self.redir_url, 302)

class SuttaCitationView(ViewBase):

    def __init__(self, sutta):
        self.sutta = sutta

    def get_template(self):
        return self.env.get_template('sutta_citation.txt')

    def setup_context(self, context):
        context.sutta = self.sutta