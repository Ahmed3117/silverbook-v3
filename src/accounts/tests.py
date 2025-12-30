from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from products.models import Product, Pill, PillItem


class DeleteAccountTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='student1',
			password='pass1234',
			name='Student One'
		)
		self.admin = User.objects.create_superuser(
			username='admin',
			password='adminpass',
			email='admin@example.com'
		)
		self.url = reverse('accounts:delete-account')

	def test_authenticated_student_can_delete_account(self):
		self.client.force_authenticate(user=self.user)
		response = self.client.delete(self.url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertFalse(User.objects.filter(username='student1').exists())

	def test_unauthenticated_request_is_rejected(self):
		response = self.client.delete(self.url)
		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

	def test_admin_cannot_use_student_delete_endpoint(self):
		self.client.force_authenticate(user=self.admin)
		response = self.client.delete(self.url)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertTrue(User.objects.filter(username='admin').exists())


class UserOrdersTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='orders-user',
			password='pass1234',
			name='Orders User'
		)
		self.other_user = User.objects.create_user(
			username='other-user',
			password='pass1234',
			name='Other User'
		)
		self.product = Product.objects.create(name='Math Book', price=150)
		self.other_product = Product.objects.create(name='Physics Book', price=200)

		# Create pill for main user
		self.pill = Pill.objects.create(user=self.user, status='p')
		item = PillItem.objects.create(
			pill=self.pill,
			user=self.user,
			product=self.product,
			status='p',
			price_at_sale=140
		)
		self.pill.items.add(item)

		# Another user's order should not appear
		other_pill = Pill.objects.create(user=self.other_user, status='i')
		other_item = PillItem.objects.create(
			pill=other_pill,
			user=self.other_user,
			product=self.other_product,
			status='i',
			price_at_sale=190
		)
		other_pill.items.add(other_item)

		self.url = reverse('accounts:user-orders')

	def test_user_can_view_their_orders(self):
		self.client.force_authenticate(user=self.user)
		response = self.client.get(self.url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 1)
		order = response.data['results'][0]
		self.assertEqual(order['pill_number'], self.pill.pill_number)
		self.assertEqual(order['status'], 'p')
		self.assertEqual(order['items_count'], 1)
		self.assertEqual(len(order['items']), 1)
		self.assertEqual(order['items'][0]['product_id'], self.product.id)
		self.assertEqual(order['items'][0]['product_name'], 'Math Book')

	def test_authentication_required_for_orders(self):
		response = self.client.get(self.url)
		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
