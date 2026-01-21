from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('auth/me/', views.get_me, name='get_me'),
    path('properties/', views.properties_list, name='properties_list'),
    path('leases/', views.leases_list, name='leases_list'),
    path('leases/my-lease/', views.my_lease, name='my_lease'),
    path('payments/', views.payments_list, name='payments_list'),
    path('my-maintenance/', views.my_maintenance, name='my_maintenance'),
]