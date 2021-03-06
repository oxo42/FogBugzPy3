import urllib
import urllib.request
from io import StringIO
import email.mime

from BeautifulSoup.BeautifulSoup import BeautifulSoup, CData


DEBUG = False  # Set to True for debugging output.


class FogBugzAPIError(Exception):
    pass


class FogBugzLogonError(FogBugzAPIError):
    pass


class FogBugzConnectionError(FogBugzAPIError):
    pass


class FogBugz:
    def __init__(self, url, token=None):
        self.__handlerCache = {}
        if not url.endswith('/'):
            url += '/'

        if token:
            self._token = token.encode('utf-8')
        else:
            self._token = None

        self._opener = urllib.request.build_opener()
        try:
            soup = BeautifulSoup(self._opener.open(url + 'api.xml'))
        except (urllib.request.URLError, urllib.request.HTTPError) as e:
            raise FogBugzConnectionError(
                "Library could not connect to the FogBugz API.  Either this installation of FogBugz does not support "
                "the API, or the url, %s, is incorrect.\n\nError: %s" % (self._url, e))
        self._url = url + soup.response.url.string
        self.currentFilter = None

    def logon(self, username, password):
        """
        Logs the user on to FogBugz.

        Returns None for a successful login.
        """
        if self._token:
            self.logoff()
        try:
            response = self.__makerequest('logon', email=username, password=password)
        except FogBugzAPIError as e:
            raise FogBugzLogonError(e)

        self._token = response.token.string
        if type(self._token) == CData:
            self._token = self._token.encode('utf-8')

    def logoff(self):
        """
        Logs off the current user.
        """
        self.__makerequest('logoff')
        self._token = None

    def token(self, token):
        """
        Set the token without actually logging on.  More secure.
        """
        self._token = token.encode('utf-8')

    def __makerequest(self, cmd, **kwargs):
        kwargs["cmd"] = cmd
        if self._token:
            kwargs["token"] = self._token

        fields = dict([k, v.encode('utf-8') if isinstance(v, str) else v] for k, v in kwargs.items())
        files = fields.get('Files', {})
        if 'Files' in fields:
            del fields['Files']

        content_type, body = self.__encode_multipart_formdata(fields, files)
        headers = {'Content-Type': content_type,
                   'Content-Length': str(len(body))}

        try:
            request = urllib.request.Request(self._url.encode('utf-8'), body, headers)
            response = BeautifulSoup(self._opener.open(request)).response
        except urllib.request.URLError as e:
            raise FogBugzConnectionError(e)
        except UnicodeDecodeError:
            print(kwargs)
            raise

        if response.error:
            raise FogBugzAPIError('Error Code %s: %s' % (response.error['code'], response.error.string,))
        return response

    def __getattr__(self, name):
        """
        Handle all FogBugz API calls.

        >> fb.logon(email@example.com, password)
        >> response = fb.search(q="assignedto:email")
        """

        # Let's leave the private stuff to Python
        if name.startswith("__"):
            raise AttributeError("No such attribute '%s'" % name)

        if name not in self.__handlerCache:
            def handler(**kwargs):
                return self.__makerequest(name, **kwargs)

            self.__handlerCache[name] = handler
        return self.__handlerCache[name]

    @staticmethod
    def __encode_multipart_formdata(fields, files):
        """
        fields is a sequence of (key, value) elements for regular form fields.
        files is a sequence of (filename, filehandle) files to be uploaded
        returns (content_type, body)
        """
        boundary = email.mime.choose_boundary()

        if len(files) > 0:
            fields['nFileCount'] = str(len(files))

        crlf = '\r\n'
        buf = StringIO()

        for k, v in fields.items():
            if DEBUG:
                print("field: %s: %s" % (repr(k), repr(v)))
            buf.write(crlf.join(['--' + boundary, 'Content-disposition: form-data; name="%s"' % k, '', str(v), '']))

        n = 0
        for f, h in files.items():
            n += 1
            buf.write(crlf.join(
                ['--' + boundary, 'Content-disposition: form-data; name="File%d"; filename="%s"' % (n, f), '']))
            buf.write(crlf.join(['Content-type: application/octet-stream', '', '']))
            buf.write(h.read())
            buf.write(crlf)

        buf.write('--' + boundary + '--' + crlf)
        content_type = "multipart/form-data; boundary=%s" % boundary
        return content_type, buf.getvalue()
