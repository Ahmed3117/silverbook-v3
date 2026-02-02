"""
Management command to setup dashboard pages and features.
Customize PAGES_CONFIG and FEATURES_CONFIG for your project.

Usage:
    python manage.py setup_permissions
    python manage.py setup_permissions --clear  # Clear existing and recreate
"""
from django.core.management.base import BaseCommand
from permissions.models import BackendEndpoint, DashboardPage, DashboardFeature


class Command(BaseCommand):
    help = 'Setup dashboard pages and features with their backend endpoints'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing pages and features before creating new ones',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing permissions data...')
            DashboardFeature.objects.all().delete()
            DashboardPage.objects.all().delete()
            BackendEndpoint.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared all existing data.'))

        # ==================== CONFIGURE YOUR PAGES HERE ====================
        # Format: (code, name, route_name, icon, parent_code)
        # NOTE: Pages inherit endpoints from their features, no need to specify them here
        PAGES_CONFIG = [
            # Main pages (no parent)
            {
                'code': 'page.dashboard',
                'name': 'Dashboard',
                'route_name': 'dashboard-home',
                'icon': 'home',
                'parent_code': None,
                'display_order': 1,
            },
            {
                'code': 'page.users',
                'name': 'Users',
                'route_name': 'dashboard-users',
                'icon': 'users',
                'parent_code': None,
                'display_order': 2,
            },
            {
                'code': 'page.products',
                'name': 'Products',
                'route_name': 'dashboard-products',
                'icon': 'package',
                'parent_code': None,
                'display_order': 3,
            },
            {
                'code': 'page.orders',
                'name': 'Orders',
                'route_name': 'dashboard-orders',
                'icon': 'shopping-cart',
                'parent_code': None,
                'display_order': 4,
            },
            {
                'code': 'page.analytics',
                'name': 'Analytics',
                'route_name': 'dashboard-analytics',
                'icon': 'bar-chart',
                'parent_code': None,
                'display_order': 5,
            },
            {
                'code': 'page.settings',
                'name': 'Settings',
                'route_name': 'dashboard-settings',
                'icon': 'settings',
                'parent_code': None,
                'display_order': 6,
            },
            # Child pages
            {
                'code': 'page.users.admins',
                'name': 'Admin Users',
                'route_name': 'dashboard-users-admins',
                'icon': 'shield',
                'parent_code': 'page.users',
                'display_order': 1,
            },
            {
                'code': 'page.users.customers',
                'name': 'Customers',
                'route_name': 'dashboard-users-customers',
                'icon': 'user',
                'parent_code': 'page.users',
                'display_order': 2,
            },
        ]

        # ==================== CONFIGURE YOUR FEATURES HERE ====================
        # Format: (code, name, page_code, description, endpoints)
        # NOTE: If an endpoint is shared by multiple features, just add it to all of them.
        #       Logic: If user has ANY feature using an endpoint, they can access it.
        FEATURES_CONFIG = [
            # User features
            {
                'code': 'users.view',
                'name': 'View Users',
                'page_code': 'page.users',
                'description': 'View user list and details',
                'display_order': 1,
                'endpoints': [
                    ('accounts:user-list', 'GET'),
                    ('accounts:user-detail', 'GET'),
                ],
            },
            {
                'code': 'users.create',
                'name': 'Create User',
                'page_code': 'page.users',
                'description': 'Create new users',
                'display_order': 2,
                'endpoints': [
                    ('accounts:user-list', 'POST'),
                    ('accounts:user-create', 'POST'),
                ],
            },
            {
                'code': 'users.edit',
                'name': 'Edit User',
                'page_code': 'page.users',
                'description': 'Edit existing users',
                'display_order': 3,
                'endpoints': [
                    ('accounts:user-detail', 'GET'),  # Shared with View feature
                    ('accounts:user-detail', 'PUT'),
                    ('accounts:user-detail', 'PATCH'),
                ],
            },
            {
                'code': 'users.delete',
                'name': 'Delete User',
                'page_code': 'page.users',
                'description': 'Delete users',
                'display_order': 4,
                'endpoints': [
                    ('accounts:user-detail', 'DELETE'),
                ],
            },
            # Product features
            {
                'code': 'products.view',
                'name': 'View Products',
                'page_code': 'page.products',
                'description': 'View product list and details',
                'display_order': 1,
                'endpoints': [
                    ('products:product-list', 'GET'),
                    ('products:product-detail', 'GET'),
                ],
            },
            {
                'code': 'products.create',
                'name': 'Create Product',
                'page_code': 'page.products',
                'description': 'Create new products',
                'display_order': 2,
                'endpoints': [
                    ('products:product-list', 'POST'),
                ],
            },
            {
                'code': 'products.edit',
                'name': 'Edit Product',
                'page_code': 'page.products',
                'description': 'Edit existing products',
                'display_order': 3,
                'endpoints': [
                    ('products:product-detail', 'GET'),  # Shared with View feature
                    ('products:product-detail', 'PUT'),
                    ('products:product-detail', 'PATCH'),
                ],
            },
            {
                'code': 'products.delete',
                'name': 'Delete Product',
                'page_code': 'page.products',
                'description': 'Delete products',
                'display_order': 4,
                'endpoints': [
                    ('products:product-detail', 'DELETE'),
                ],
            },
            # Analytics features
            {
                'code': 'analytics.view',
                'name': 'View Analytics',
                'page_code': 'page.analytics',
                'description': 'View analytics and reports',
                'display_order': 1,
                'endpoints': [],
            },
            {
                'code': 'analytics.export',
                'name': 'Export Reports',
                'page_code': 'page.analytics',
                'description': 'Export analytics reports',
                'display_order': 2,
                'endpoints': [],
            },
            # Settings features
            {
                'code': 'settings.view',
                'name': 'View Settings',
                'page_code': 'page.settings',
                'description': 'View system settings',
                'display_order': 1,
                'endpoints': [],
            },
            {
                'code': 'settings.edit',
                'name': 'Edit Settings',
                'page_code': 'page.settings',
                'description': 'Modify system settings',
                'display_order': 2,
                'endpoints': [],
            },
        ]

        # ==================== CREATE PAGES ====================
        self.stdout.write('Creating dashboard pages...')
        pages_created = 0
        page_objects = {}

        # First pass: create all pages without parents
        for page_config in PAGES_CONFIG:
            page, created = DashboardPage.objects.update_or_create(
                code=page_config['code'],
                defaults={
                    'name': page_config['name'],
                    'route_name': page_config.get('route_name', ''),
                    'icon': page_config.get('icon', ''),
                    'display_order': page_config.get('display_order', 0),
                }
            )
            page_objects[page_config['code']] = page
            if created:
                pages_created += 1
                self.stdout.write(f"  Created page: {page.name}")
            else:
                self.stdout.write(f"  Updated page: {page.name}")

        # Second pass: set parents and view_endpoints
        for page_config in PAGES_CONFIG:
            page = page_objects[page_config['code']]

            # Set parent
            parent_code = page_config.get('parent_code')
            if parent_code and parent_code in page_objects:
                page.parent = page_objects[parent_code]
                page.save()

        # ==================== CREATE FEATURES ====================
        self.stdout.write('\nCreating dashboard features...')
        features_created = 0
        endpoints_created = 0

        for feature_config in FEATURES_CONFIG:
            # Get page
            page = page_objects.get(feature_config.get('page_code'))

            # Create endpoints
            endpoint_objects = []
            for view_name, method in feature_config.get('endpoints', []):
                endpoint, created = BackendEndpoint.objects.get_or_create(
                    view_name=view_name,
                    method=method,
                    defaults={'description': f'Endpoint for {feature_config["name"]}'}
                )
                endpoint_objects.append(endpoint)
                if created:
                    endpoints_created += 1

            # Create feature
            feature, created = DashboardFeature.objects.update_or_create(
                code=feature_config['code'],
                defaults={
                    'name': feature_config['name'],
                    'description': feature_config.get('description', ''),
                    'page': page,
                    'display_order': feature_config.get('display_order', 0),
                }
            )

            # Set endpoints
            feature.endpoints.set(endpoint_objects)

            if created:
                features_created += 1
                self.stdout.write(f"  Created feature: {feature.name}")
            else:
                self.stdout.write(f"  Updated feature: {feature.name}")

        # ==================== SUMMARY ====================
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done! Created {pages_created} pages, {features_created} features, '
            f'and {endpoints_created} endpoints.'
        ))
        self.stdout.write(
            '\nNext steps:\n'
            '1. Create PermissionGroups in Django Admin\n'
            '2. Assign AdminPermissions to your admin users\n'
            '3. Add HasEndpointPermission to your views'
        )
