from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from .models import Category, Subject, Teacher, Product, Pill, PillItem, PurchasedBook, Rating
class PurchasedBookTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='student',
			password='pass1234',
			name='Student User'
		)
		self.client.force_authenticate(user=self.user)

		self.category = Category.objects.create(name='Science')
		self.subject = Subject.objects.create(name='Chemistry')
		self.teacher = Teacher.objects.create(name='Dr. Smith', subject=self.subject)
		self.product = Product.objects.create(
			name='Chemistry 101',
			price=150,
			category=self.category,
			subject=self.subject,
			teacher=self.teacher
		)

		self.pill = Pill.objects.create(user=self.user, status='i')
		item = PillItem.objects.create(
			pill=self.pill,
			user=self.user,
			product=self.product,
			status='p'
		)
		self.pill.items.add(item)

		self.pill.status = 'p'
		self.pill.save()

	def test_purchased_book_created_when_pill_paid(self):
		purchased_book = PurchasedBook.objects.filter(user=self.user).first()
		self.assertIsNotNone(purchased_book)
		self.assertEqual(purchased_book.product, self.product)
		self.assertEqual(purchased_book.pill, self.pill)
		self.assertEqual(purchased_book.product_name, self.product.name)

	def test_my_books_endpoint_returns_purchased_books(self):
		url = reverse('products:purchased-books')
		response = self.client.get(url)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(len(response.data['results']), 1)

		payload = response.data['results'][0]
		book = PurchasedBook.objects.get()
		self.assertEqual(payload['book_id'], book.id)
		self.assertEqual(payload['product_id'], self.product.id)
		self.assertEqual(payload['name'], self.product.name)
		self.assertEqual(payload['pill_number'], self.pill.pill_number)
		self.assertEqual(payload['category_name'], self.category.name)

	def test_book_owned_check_endpoint(self):
		url = reverse('products:book-owned-check', args=[self.product.product_number])
		response = self.client.get(url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data['owned'])
		self.assertEqual(response.data['product_id'], self.product.id)
		self.assertEqual(response.data['product_number'], self.product.product_number)

		# Another product should return false
		other_product = Product.objects.create(name='Physics 101', price=200)
		url = reverse('products:book-owned-check', args=[other_product.product_number])
		response = self.client.get(url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertFalse(response.data['owned'])
		self.assertEqual(response.data['product_id'], other_product.id)
		self.assertEqual(response.data['product_number'], other_product.product_number)

	def test_pill_creation_filters_owned_products(self):
		owned_product = Product.objects.create(name='Owned Book', price=100)
		pill = Pill.objects.create(user=self.user, status='p')
		item = PillItem.objects.create(
			pill=pill,
			user=self.user,
			product=owned_product,
			status='p'
		)
		pill.items.add(item)
		PurchasedBook.objects.create(
			user=self.user,
			pill=pill,
			product=owned_product,
			pill_item=item,
			product_name=owned_product.name
		)

		new_product = Product.objects.create(name='New Book', price=120)
		payload = {
			'items': [
				{'product': owned_product.id},
				{'product': new_product.id},
			]
		}

		response = self.client.post(reverse('products:pill-create'), payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(len(response.data['items']), 1)
		self.assertEqual(response.data['items'][0]['product']['id'], new_product.id)

	def test_pill_creation_rejects_all_owned_products(self):
		product = Product.objects.create(name='Owned Book', price=100)
		pill = Pill.objects.create(user=self.user, status='p')
		item = PillItem.objects.create(
			pill=pill,
			user=self.user,
			product=product,
			status='p'
		)
		pill.items.add(item)
		PurchasedBook.objects.create(
			user=self.user,
			pill=pill,
			product=product,
			pill_item=item,
			product_name=product.name
		)

		payload = {
			'items': [
				{'product': product.id}
			]
		}

		response = self.client.post(reverse('products:pill-create'), payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('items', response.data)
		self.assertIn('already owned', response.data['items'][0])

	def test_add_free_book_success(self):
		free_product = Product.objects.create(
			name='Free Book',
			price=0,
			category=self.category,
			subject=self.subject,
			teacher=self.teacher
		)

		url = reverse('products:add-free-book', args=[free_product.product_number])
		response = self.client.post(url)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertTrue(PurchasedBook.objects.filter(user=self.user, product=free_product).exists())
		self.assertEqual(response.data['product_id'], free_product.id)

	def test_add_free_book_requires_free_price(self):
		url = reverse('products:add-free-book', args=[self.product.product_number])
		response = self.client.post(url)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('not free', response.data['detail'])

	def test_add_free_book_prevents_duplicates(self):
		free_product = Product.objects.create(
			name='Another Free Book',
			price=0,
			category=self.category,
			subject=self.subject,
			teacher=self.teacher
		)

		url = reverse('products:add-free-book', args=[free_product.product_number])
		first_response = self.client.post(url)
		self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

		second_response = self.client.post(url)
		self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('already exists', second_response.data['detail'])


class RatingTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='reviewer',
			password='pass1234',
			name='Reviewer'
		)
		self.other_user = User.objects.create_user(
			username='reviewer2',
			password='pass1234',
			name='Reviewer 2'
		)
		self.client.force_authenticate(user=self.user)

		self.category = Category.objects.create(name='Math')
		self.subject = Subject.objects.create(name='Algebra')
		self.teacher = Teacher.objects.create(name='Prof. Alan', subject=self.subject)
		self.product = Product.objects.create(
			name='Algebra Basics',
			price=120,
			category=self.category,
			subject=self.subject,
			teacher=self.teacher
		)
		self.list_url = reverse('products:product-rating-list-create', args=[self.product.id])

	def test_user_can_create_rating_for_product(self):
		payload = {'star_number': 4, 'review': 'Great'}
		response = self.client.post(self.list_url, payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(Rating.objects.count(), 1)
		rating = Rating.objects.get()
		self.assertEqual(rating.user, self.user)
		self.assertEqual(rating.product, self.product)

	def test_user_cannot_rate_same_product_twice(self):
		payload = {'star_number': 5, 'review': 'Excellent'}
		first = self.client.post(self.list_url, payload, format='json')
		self.assertEqual(first.status_code, status.HTTP_201_CREATED)
		second = self.client.post(self.list_url, payload, format='json')
		self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('already rated', second.data['detail'])

	def test_product_rating_list_includes_average_and_all_entries(self):
		self.client.post(self.list_url, {'star_number': 4, 'review': 'Nice'}, format='json')
		self.client.force_authenticate(user=self.other_user)
		self.client.post(self.list_url, {'star_number': 5, 'review': 'Loved it'}, format='json')
		self.client.force_authenticate(user=self.user)

		response = self.client.get(self.list_url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['ratings_count'], 2)
		self.assertEqual(response.data['average_rating'], 4.5)
		self.assertEqual(len(response.data['ratings']), 2)
		self.assertIsNotNone(response.data['current_user_rating'])
		self.assertIsNotNone(response.data['pagination'])
		self.assertEqual(response.data['pagination']['current_page'], 1)
		self.assertEqual(response.data['pagination']['page_size'], 10)
		self.assertSetEqual(
			set(r['user'] for r in response.data['ratings']),
			{'Reviewer', 'Reviewer 2'}
		)

	def test_current_user_rating_included_in_list(self):
		create = self.client.post(self.list_url, {'star_number': 3, 'review': 'Okay'}, format='json')
		self.assertEqual(create.status_code, status.HTTP_201_CREATED)

		response = self.client.get(self.list_url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIsNotNone(response.data['current_user_rating'])
		self.assertEqual(response.data['current_user_rating']['star_number'], 3)

	def test_current_user_rating_none_when_not_rated(self):
		self.client.force_authenticate(user=self.other_user)
		self.client.post(self.list_url, {'star_number': 5, 'review': 'Great'}, format='json')
		self.client.force_authenticate(user=self.user)

		response = self.client.get(self.list_url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIsNone(response.data['current_user_rating'])

	def test_user_can_update_and_delete_rating(self):
		create = self.client.post(self.list_url, {'star_number': 2, 'review': 'Bad'}, format='json')
		self.assertEqual(create.status_code, status.HTTP_201_CREATED)
		rating_id = create.data['id']
		detail_url = reverse('products:product-rating-detail', args=[self.product.id, rating_id])

		update = self.client.patch(detail_url, {'star_number': 5}, format='json')
		self.assertEqual(update.status_code, status.HTTP_200_OK)
		self.assertEqual(update.data['star_number'], 5)

		delete = self.client.delete(detail_url)
		self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(Rating.objects.filter(id=rating_id).exists())

	def test_rating_list_pagination_controls(self):
		self.client.post(self.list_url, {'star_number': 3, 'review': 'My review'}, format='json')
		# Create additional ratings from distinct users
		for idx in range(12):
			user = User.objects.create_user(
				username=f'bulk{idx}',
				password='pass1234',
				name=f'Bulk User {idx}'
			)
			Rating.objects.create(
				product=self.product,
				user=user,
				star_number=(idx % 5) + 1,
				review=f'Review {idx}'
			)

		url = f"{self.list_url}?page=2&page_size=5"
		response = self.client.get(url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['ratings_count'], 13)
		self.assertEqual(response.data['pagination']['current_page'], 2)
		self.assertEqual(response.data['pagination']['total_pages'], 3)
		self.assertEqual(response.data['pagination']['page_size'], 5)
		self.assertEqual(len(response.data['ratings']), 5)
