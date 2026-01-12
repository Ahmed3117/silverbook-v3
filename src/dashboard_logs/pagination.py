from rest_framework.pagination import PageNumberPagination


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'per_page'
    max_page_size = 100000
