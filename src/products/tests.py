from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from .models import Subject, Teacher, Product, Pill, PillItem, PurchasedBook, PromoCode

# Single placeholder used for every test user — not a real credential.
_TP = 'Xy7@test#pass'   # noqa: S105  (test-only, not a secret)
class PurchasedBookTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='student',
			password=_TP,
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
			password=_TP,
			name='Reviewer'
		)
		self.other_user = User.objects.create_user(
			username='reviewer2',
			password=_TP,
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
				password=_TP,
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


class PromoCodeAdminTests(APITestCase):
    """Tests for admin promo code management endpoints."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password=_TP, name='Admin User',
            is_staff=True,
        )
        self.student = User.objects.create_user(
            username='student1', password=_TP, name='Student One',
        )
        self.book = Product.objects.create(name='Chemistry 101', price=150)
        self.other_book = Product.objects.create(name='Physics 202', price=200)

        # Three codes: two for self.book, one for self.other_book
        self.code_a = PromoCode.objects.create(code='1111111111', book=self.book, created_by=self.admin)
        self.code_b = PromoCode.objects.create(code='2222222222', book=self.book, created_by=self.admin)
        self.code_other = PromoCode.objects.create(code='3333333333', book=self.other_book, created_by=self.admin)

        self.list_url = reverse('products:admin-promo-code-list')
        self.bulk_url = reverse('products:admin-promo-code-bulk-create')
        self.stats_url = reverse('products:admin-promo-code-book-stats')

    def _admin_auth(self):
        self.client.force_authenticate(user=self.admin)

    def _student_auth(self):
        self.client.force_authenticate(user=self.student)

    # ── list ───────────────────────────────────────────────────────────────

    def test_list_requires_admin(self):
        self._student_auth()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_unauthenticated(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_all_codes(self):
        self._admin_auth()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 3)

    def test_filter_by_book_id(self):
        self._admin_auth()
        resp = self.client.get(self.list_url, {'book_id': self.book.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)
        for item in resp.data['results']:
            self.assertEqual(item['book']['id'], self.book.id)

    def test_filter_by_is_used_false(self):
        self._admin_auth()
        # Mark one code as used
        self.code_a.is_used = True
        self.code_a.used_by = self.student
        self.code_a.save()
        resp = self.client.get(self.list_url, {'is_used': 'false'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

    def test_filter_by_is_used_true(self):
        self._admin_auth()
        self.code_a.is_used = True
        self.code_a.used_by = self.student
        self.code_a.save()
        resp = self.client.get(self.list_url, {'is_used': 'true'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['code'], '1111111111')

    def test_filter_by_is_active(self):
        self._admin_auth()
        self.code_a.is_active = False
        self.code_a.save()
        resp = self.client.get(self.list_url, {'is_active': 'false'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_filter_is_valid_true(self):
        self._admin_auth()
        # Deactivate one code — only 2 valid remain
        self.code_a.is_active = False
        self.code_a.save()
        resp = self.client.get(self.list_url, {'is_valid': 'true'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

    def test_search_by_code_partial(self):
        self._admin_auth()
        resp = self.client.get(self.list_url, {'search': '1111'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['code'], '1111111111')

    # ── bulk create ────────────────────────────────────────────────────────

    def test_bulk_create_requires_admin(self):
        self._student_auth()
        resp = self.client.post(self.bulk_url, {'book_id': self.book.id, 'number_of_codes': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_bulk_create_returns_correct_count(self):
        self._admin_auth()
        resp = self.client.post(self.bulk_url, {'book_id': self.book.id, 'number_of_codes': 10}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.data), 10)

    def test_bulk_create_codes_are_unique(self):
        self._admin_auth()
        resp = self.client.post(self.bulk_url, {'book_id': self.book.id, 'number_of_codes': 20}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        codes = [item['code'] for item in resp.data]
        self.assertEqual(len(codes), len(set(codes)))

    def test_bulk_create_codes_all_for_correct_book(self):
        self._admin_auth()
        resp = self.client.post(self.bulk_url, {'book_id': self.book.id, 'number_of_codes': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        for item in resp.data:
            self.assertEqual(item['book']['id'], self.book.id)

    def test_bulk_create_rejects_zero_count(self):
        self._admin_auth()
        resp = self.client.post(self.bulk_url, {'book_id': self.book.id, 'number_of_codes': 0}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_create_rejects_over_1000(self):
        self._admin_auth()
        resp = self.client.post(self.bulk_url, {'book_id': self.book.id, 'number_of_codes': 1001}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_create_with_validity_dates(self):
        self._admin_auth()
        valid_from = (timezone.now() + timedelta(days=1)).isoformat()
        valid_until = (timezone.now() + timedelta(days=30)).isoformat()
        resp = self.client.post(self.bulk_url, {
            'book_id': self.book.id,
            'number_of_codes': 3,
            'is_active': True,
            'valid_from': valid_from,
            'valid_until': valid_until,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.data), 3)
        for item in resp.data:
            self.assertIsNotNone(item['valid_from'])
            self.assertIsNotNone(item['valid_until'])

    def test_bulk_create_invalid_book_id(self):
        self._admin_auth()
        resp = self.client.post(self.bulk_url, {'book_id': 99999, 'number_of_codes': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── book stats ─────────────────────────────────────────────────────────

    def test_book_stats_requires_admin(self):
        self._student_auth()
        resp = self.client.get(self.stats_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_book_stats_total_counts(self):
        self._admin_auth()
        resp = self.client.get(self.stats_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = {row['id']: row for row in resp.data}
        self.assertEqual(data[self.book.id]['total_codes'], 2)
        self.assertEqual(data[self.other_book.id]['total_codes'], 1)

    def test_book_stats_used_codes(self):
        self._admin_auth()
        self.code_a.is_used = True
        self.code_a.save()
        resp = self.client.get(self.stats_url)
        data = {row['id']: row for row in resp.data}
        self.assertEqual(data[self.book.id]['used_codes'], 1)
        self.assertEqual(data[self.book.id]['available_codes'], 1)

    # ── retrieve / update / delete ─────────────────────────────────────────

    def test_retrieve_single_code(self):
        self._admin_auth()
        url = reverse('products:admin-promo-code-detail', args=[self.code_a.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['code'], '1111111111')
        self.assertIn('book', resp.data)
        self.assertFalse(resp.data['is_used'])

    def test_patch_deactivate_code(self):
        self._admin_auth()
        url = reverse('products:admin-promo-code-detail', args=[self.code_a.id])
        resp = self.client.patch(url, {'is_active': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['is_active'])
        self.code_a.refresh_from_db()
        self.assertFalse(self.code_a.is_active)

    def test_patch_does_not_allow_setting_is_used(self):
        """is_used is read-only; admin cannot flip it directly."""
        self._admin_auth()
        url = reverse('products:admin-promo-code-detail', args=[self.code_a.id])
        # should be silently ignored or still return 200, but is_used stays False
        resp = self.client.patch(url, {'is_used': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.code_a.refresh_from_db()
        self.assertFalse(self.code_a.is_used)

    def test_delete_code(self):
        self._admin_auth()
        url = reverse('products:admin-promo-code-detail', args=[self.code_a.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn('detail', resp.data)
        self.assertFalse(PromoCode.objects.filter(id=self.code_a.id).exists())

    def test_retrieve_nonexistent_code(self):
        self._admin_auth()
        url = reverse('products:admin-promo-code-detail', args=[99999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PromoCodeRedeemTests(APITestCase):
    """Tests for the student promo code redemption endpoint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin2', password=_TP, name='Admin 2', is_staff=True,
        )
        self.student = User.objects.create_user(
            username='student2', password=_TP, name='Student Two',
        )
        self.book = Product.objects.create(name='Biology 303', price=100)
        self.other_book = Product.objects.create(name='History 404', price=80)

        self.valid_code = PromoCode.objects.create(
            code='9999999999', book=self.book, created_by=self.admin
        )
        self.redeem_url = reverse('products:promo-code-redeem')

    def _auth(self):
        self.client.force_authenticate(user=self.student)

    # ── success ────────────────────────────────────────────────────────────

    def test_redeem_valid_code_grants_book(self):
        self._auth()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['promo_code'], '9999999999')
        self.assertFalse(resp.data['already_owned'])
        # Book must be granted
        self.assertTrue(PurchasedBook.objects.filter(user=self.student, product=self.book).exists())

    def test_redeem_marks_code_as_used(self):
        self._auth()
        self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.valid_code.refresh_from_db()
        self.assertTrue(self.valid_code.is_used)
        self.assertEqual(self.valid_code.used_by, self.student)
        self.assertIsNotNone(self.valid_code.used_at)

    def test_redeem_already_owned_returns_flag(self):
        self._auth()
        # Grant the book first
        PurchasedBook.objects.create(
            user=self.student, product=self.book,
            purchase_method='easypay', product_name=self.book.name, price_at_sale=0
        )
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['already_owned'])

    def test_redeem_purchase_method_is_promo_code(self):
        self._auth()
        self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        pb = PurchasedBook.objects.get(user=self.student, product=self.book)
        self.assertEqual(pb.purchase_method, 'promo_code')
        self.assertEqual(pb.price_at_sale, 0)

    # ── auth ───────────────────────────────────────────────────────────────

    def test_redeem_requires_authentication(self):
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── validation errors ─────────────────────────────────────────────────

    def test_redeem_nonexistent_code(self):
        self._auth()
        resp = self.client.post(self.redeem_url, {
            'code': '0000000000',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp.data)

    def test_redeem_already_used_code(self):
        self._auth()
        other_student = User.objects.create_user(username='s3', password=_TP)
        self.valid_code.is_used = True
        self.valid_code.used_by = other_student
        self.valid_code.save()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp.data)

    def test_redeem_inactive_code(self):
        self._auth()
        self.valid_code.is_active = False
        self.valid_code.save()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp.data)

    def test_redeem_expired_code(self):
        self._auth()
        self.valid_code.valid_until = timezone.now() - timedelta(days=1)
        self.valid_code.save()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp.data)

    def test_redeem_code_not_yet_valid(self):
        self._auth()
        self.valid_code.valid_from = timezone.now() + timedelta(days=5)
        self.valid_code.save()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp.data)

    def test_redeem_code_wrong_book(self):
        self._auth()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.other_book.id,  # code is for self.book, not this
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp.data)

    def test_redeem_invalid_product_id(self):
        self._auth()
        resp = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': 99999,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_redeem_cannot_double_redeem(self):
        """A code already consumed cannot be redeemed again."""
        self._auth()
        # First redemption
        resp1 = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        # Second redemption attempt
        resp2 = self.client.post(self.redeem_url, {
            'code': '9999999999',
            'product_id': self.book.id,
        }, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', resp2.data)
