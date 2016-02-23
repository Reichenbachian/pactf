"""Do what ratelimit.middleware.RatelimitMiddleware would have done, except fixing the import_module import"""

from importlib import import_module

from django.conf import settings

from ratelimit.exceptions import Ratelimited


class RatelimitMiddleware(object):
    def process_exception(self, request, exception):
        if not isinstance(exception, Ratelimited):
            return
        module_name, _, view_name = settings.RATELIMIT_VIEW.rpartition('.')
        module = import_module(module_name)
        view = getattr(module, view_name)
        return view(request, exception)