from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    MediaProxyView,
    ThrottledTokenObtainPairView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='auth_token_refresh'),
    path('api/', include('core.urls')),  # your app routes
    # Private media: nginx proxies /media/<path> here so Django can run object-level
    # auth before serving the file. Never bypass this with a public alias.
    path('media/<path:relative_path>', MediaProxyView.as_view(), name='media-proxy'),
]
