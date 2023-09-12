import json
import requests
import os
from . import six
import io

SDK_VERSION = "2.2.0"

# Define the path to the trusted certificates file
TRUSTED_CERT_FILE = os.path.join(os.path.dirname(six.__file__), 'trusted-certs.crt')


class RESTResponse(io.IOBase):
    """
    Responses to requests can come in the form of ``RESTResponse``. These are
    thin wrappers around the socket file descriptor.
    :meth:`read()` and :meth:`close()` are implemented.
    It is important to call :meth:`close()` to return the connection
    back to the connection pool to be reused. If a connection
    is not closed by the caller it may leak memory. The object makes a
    best-effort attempt upon destruction to call :meth:`close()`,
    but it's still best to explicitly call :meth:`close()`.
    """

    def __init__(self, resp):
        # arg: A requests.Response object
        self.requests_response = resp
        self.status = resp.status_code
        self.reason = resp.reason
        self.is_closed = False

    def __del__(self):
        # Attempt to close when ref-count goes to zero.
        self.close()

    def __exit__(self, typ, value, traceback):
        # Allow this to be used in "with" blocks.
        self.close()

    # -----------------
    # Important methods
    # -----------------
    def read(self, amt=None):
        """
        Read data off the underlying socket.

        Parameters
            amt
              Amount of data to read. Defaults to ``None``, indicating to read
              everything.

        Returns
              Data off the socket. If ``amt`` is not ``None``, at most ``amt`` bytes are returned.
              An empty string when the socket has no data.

        Raises
            ``ValueError``
              If the ``RESTResponse`` has already been closed.
        """
        if self.is_closed:
            raise ValueError('Response already closed')
        return self.requests_response.content if amt is None else self.requests_response.content[:amt]

    BLOCKSIZE = 4 * 1024 * 1024  # 4MB at a time just because

    def close(self):
        """Closes the underlying socket."""

        # Double closing is harmless
        if self.is_closed:
            return

        # Read any remaining data off the socket before releasing the
        # connection.
        self.read(RESTResponse.BLOCKSIZE)

        # Mark as closed and release the connection (exactly once)
        self.is_closed = True

    @property
    def closed(self):
        return self.is_closed

    # ---------------------------------
    # Backwards compat for HTTPResponse
    # ---------------------------------
    def getheaders(self):
        """Returns a dictionary of the response headers."""
        return self.requests_response.headers.items()

    def getheader(self, name, default=None):
        """Returns a given response header."""
        return self.requests_response.headers.get(name, default)


def json_loadb(data):
    return json.loads(data.decode('utf8'))


class RESTClientObject(object):
    def __init__(self, max_reusable_connections=8, mock_urlopen=None):
        """
        Parameters
            max_reusable_connections
                max connections to keep alive in the pool
            mock_urlopen
                an optional alternate urlopen function for testing

        This class uses ``requests`` to maintain a pool of connections. We attempt
        to grab an existing idle connection from the pool, otherwise we send
        a new request. Once a response is closed, it is released
        back to the connection pool to be reused.

        SSL settings:
        - Certificates validated using Dropbox-approved trusted root certs
        - TLS v1.0 (newer TLS versions are not supported by requests)
        - Default ciphersuites. Choosing ciphersuites is not supported by requests
        - Hostname verification is provided by requests
        """
        self.mock_urlopen = mock_urlopen
        self.session = requests.Session()
        self.session.verify = TRUSTED_CERT_FILE
        self.session.headers.update({'User-Agent': 'OfficialDropboxPythonSDK/' + SDK_VERSION})

    def request(self, method, url, post_params=None, body=None, headers=None, raw_response=False):
        post_params = post_params or {}
        headers = headers or {}
        headers['User-Agent'] = 'OfficialDropboxPythonSDK/' + SDK_VERSION

        if post_params:
            if body:
                raise ValueError("body parameter cannot be used with post_params parameter")
            headers["Content-type"] = "application/x-www-form-urlencoded"

        # Handle StringIO instances, because requests doesn't.
        if hasattr(body, 'getvalue'):
            body = str(body.getvalue())
            headers["Content-Length"] = str(len(body))

        # Reject any headers containing newlines; the error from the server isn't pretty.
        for key, value in list(headers.items()):
            if isinstance(value, str) and '\n' in value:
                raise ValueError("headers should not contain newlines (%s: %s)" %
                                 (key, value))

        try:
            # Make the request using the requests library.
            r = self.session.request(
                method=method,
                url=url,
                data=body,
                headers=headers,
                params=post_params,
                stream=True  # Enable streaming to allow large responses to be read incrementally.
            )
            r.raise_for_status()  # Raise an exception for HTTP errors (status code not in 200-299 range)
        except requests.exceptions.RequestException as e:
            raise RESTSocketError(url, e)

        if r.status_code not in (200, 206):
            raise ErrorResponse(r, r.content)

        return self.process_response(r, raw_response)

    def process_response(self, r, raw_response):
        if raw_response:
            return r
        else:
            try:
                resp = json_loadb(r.content)
            except ValueError:
                raise ErrorResponse(r, r.content)
            finally:
                r.close()

        return resp

    def GET(self, url, headers=None, raw_response=False):
        assert type(raw_response) == bool
        return self.request("GET", url, headers=headers, raw_response=raw_response)

    def POST(self, url, params=None, headers=None, raw_response=False):
        assert type(raw_response) == bool
        if params is None:
            params = {}

        return self.request("POST", url,
                            post_params=params, headers=headers, raw_response=raw_response)

    def PUT(self, url, body, headers=None, raw_response=False):
        assert type(raw_response) == bool
        return self.request("PUT", url, body=body, headers=headers, raw_response=raw_response)


class RESTClient(object):
    """
    A class with all static methods to perform JSON REST requests that is used internally
    by the Dropbox Client API. It provides just enough gear to make requests
    and get responses as JSON data (when applicable). All requests happen over SSL.
    """

    IMPL = RESTClientObject()

    @classmethod
    def request(cls, *n, **kw):
        """Perform a REST request and parse the response."""
        return cls.IMPL.request(*n, **kw)

    @classmethod
    def GET(cls, *n, **kw):
        """Perform a GET request using :meth:`RESTClient.request()`."""
        return cls.IMPL.GET(*n, **kw)

    @classmethod
    def POST(cls, *n, **kw):
        """Perform a POST request using :meth:`RESTClient.request()`."""
        return cls.IMPL.POST(*n, **kw)

    @classmethod
    def PUT(cls, *n, **kw):
        """Perform a PUT request using :meth:`RESTClient.request()`."""
        return cls.IMPL.PUT(*n, **kw)


class RESTSocketError(requests.exceptions.RequestException):
    """A light wrapper for ``requests.exceptions.RequestException`` that adds some more information."""

    def __init__(self, host, e):
        msg = "Error connecting to \"%s\": %s" % (host, str(e))
        super(RESTSocketError, self).__init__(msg)


class ErrorResponse(Exception):
    """
    Raised by :meth:`RESTClient.request()` for requests that:

      - Return a non-200 HTTP response, or
      - Have a non-JSON response body, or
      - Have a malformed/missing header in the response.

    Most errors that Dropbox returns will have an error field that is unpacked and
    placed on the ErrorResponse exception. In some situations, a user_error field
    will also come back. Messages under user_error are worth showing to an end-user
    of your app, while other errors are likely only useful for you as the developer.
    """

    def __init__(self, http_resp, body):
        """
        Parameters
            http_resp
                      The :class:`RESTResponse` which errored
            body
                      Body of the :class:`RESTResponse`.
                      The reason we can't simply call ``http_resp.read()`` to
                      get the body, is that ``read()`` is not idempotent.
                      Since it can't be called more than once,
                      we have to pass the string body in separately
        """
        self.status = http_resp.status_code
        self.reason = http_resp.reason
        self.body = body
        self.headers = http_resp.headers
        http_resp.close()  # won't need this connection anymore

        try:
            self.body = json_loadb(self.body)
            self.error_msg = self.body.get('error')
            self.user_error_msg = self.body.get('user_error')
        except ValueError:
            self.error_msg = None
            self.user_error_msg = None

    def __str__(self):
        if self.user_error_msg and self.user_error_msg != self.error_msg:
            # one is translated and the other is English
            msg = "%r (%r)" % (self.user_error_msg, self.error_msg)
        elif self.error_msg:
            msg = repr(self.error_msg)
        elif not self.body:
            msg = repr(self.reason)
        else:
            msg = "Error parsing response body or headers: " + \
                  "Body - %.100r Headers - %r" % (self.body, self.headers)

        return "[%d] %s" % (self.status, msg)


def params_to_urlencoded(params):
    """
    Returns an application/x-www-form-urlencoded 'str' representing the key/value pairs in 'params'.

    Keys and values are str()'d before calling urllib.urlencode, with the exception of unicode
    objects which are utf8-encoded.
    """

    def encode(o):
        if isinstance(o, str):
            return o.encode('utf8')
        else:
            return str(o)

    utf8_params = {encode(k): encode(v) for k, v in params.items()}
    return urllib.parse.urlencode(utf8_params)
