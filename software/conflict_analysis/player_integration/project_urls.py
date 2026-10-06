"""Compatibility alias for the single supported Conflict Analysis URL graph."""
from conflict_analysis.urls import urlpatterns as _root_urlpatterns

urlpatterns = list(_root_urlpatterns)
