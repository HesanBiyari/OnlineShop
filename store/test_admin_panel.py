from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Category, Product

class AdminPanelTests(TestCase):
    def setUp(self):
        self.staff=User.objects.create_user(username='paneladmin',password='StrongPass123!',is_staff=True)
        self.user=User.objects.create_user(username='normaluser',password='StrongPass123!')
        category=Category.objects.create(name='Panel',slug='panel-test')
        self.product=Product.objects.create(category=category,name='Panel Product',price=100000,stock=5)

    def test_dashboard_requires_staff(self):
        self.client.force_login(self.user)
        response=self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code,302)

    def test_staff_dashboard(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'داشبورد فروشگاه')
        self.assertContains(response,'فروش امروز')

    def test_product_crud_panel(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('admin_model_list',args=['products']))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.product.name)
        response=self.client.get(reverse('admin_model_create',args=['products']))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'ذخیره')

    def test_admin_root_redirects_to_giftweb_dashboard(self):
        self.client.force_login(self.staff)
        response=self.client.get('/admin/')
        self.assertEqual(response.status_code,302)
        self.assertTrue(response['Location'].endswith('/dashboard/'))
