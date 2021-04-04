
"""Promise API for Scrapy."""

from promise_scrapy import Promise
from scrapy.http import Request


def fetch(url, *, cls=Request, base: Request = None, callback=None, errback=None, **kwargs) -> Promise:
    def make_request(resolve, reject):
        if base:
            request = base.replace(url=url, callback=resolve, errback=reject, **kwargs)
        else:
            request = cls(url, callback=resolve, errback=reject, **kwargs)
        yield request

    promise = Promise(make_request)
    if callback and errback:
        promise = promise.then(callback, errback)
    elif callback:
        promise = promise.then(callback)
    elif errback:
        promise = promise.catch(errback)

    return promise

 

