"""URL Config
"""

from django.contrib.auth import urls as auth_urls
from django.contrib.auth import views as auth_views
from django.conf.urls import include, url
from django.contrib import admin


urlpatterns = [
    # TODO(Yatharth): Write custom templates (then move these rules to ctf/urls.py)
    url(r'^login/$', auth_views.login),
    url(r'^logout/$', auth_views.logout, {'next_page': 'ctf:index'}),
    url('^', include(auth_urls)),

    url(r'^admin/', include(admin.site.urls), name='admin'),
    url(r'', include('ctf.urls')),
]
