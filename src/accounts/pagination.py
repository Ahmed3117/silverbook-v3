from rest_framework.pagination import PageNumberPagination

class CustomPageNumberPagination(PageNumberPagination):
    page_size = 100 # Default page size
    page_size_query_param = 'per_page'  # Query parameter for custom page size
    max_page_size = 100000  # Maximum allowed page size